"""Admit a major dependency upgrade only on passing compatibility receipts.

Before any pin is written, every supported consumer package in the owner
inventory needs a passing Scion SDK compatibility receipt for the exact target
artifact, certification revision and profile. This module consumes those
receipts; it never decides compatibility itself. Admission is bound to the
unchanged prior pins and the expected source head of each consumer
repository. After admission the updates apply one repository at a time in the
owner's order, each behind its own expected-head check. There is no atomic
transaction across repositories: a failure stops the remaining updates and the
report says exactly which updates were applied, failed or never started.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import run_git, sanitized_env
from pipelines_hooks.release.phases import load_json

REPORT_VERSION = 1
_PASSED, _FAILED = "passed", "failed"


@dataclass(frozen=True)
class ConsumerPackage:
    """One supported consumer: its repository, pins, source head and artifact."""

    package: str
    repository: str
    pin_file: str
    source_head: str
    prior_pin: str
    target_pin: str
    artifact: str
    after_update_argv: tuple[str, ...] = ()


@dataclass(frozen=True)
class MajorUpgradeCandidate:
    """The dependency, its target major, the certification revision and every consumer."""

    dependency: str
    target_major: int
    certification_revision: str
    profile: str
    consumers: tuple[ConsumerPackage, ...]


def parse_candidate(raw: Mapping[str, Any], owner_inventory: Mapping[str, Any]) -> MajorUpgradeCandidate:
    """Validate the candidate against the single owner inventory of fleet membership."""
    consumers = []
    try:
        for item in raw["consumers"]:
            consumers.append(
                ConsumerPackage(
                    item["package"],
                    item["repository"],
                    item["pin_file"],
                    item["source_head"],
                    item["prior_pin"],
                    item["target_pin"],
                    item["artifact"],
                    tuple(item.get("after_update_argv", ())),
                )
            )
        candidate = MajorUpgradeCandidate(
            raw["dependency"], int(raw["target_major"]), raw["certification_revision"], raw["profile"], tuple(consumers)
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CannotRun(f"major upgrade candidate is incomplete: {exc!r}") from exc
    declared = [consumer.package for consumer in consumers]
    if sorted(declared) != sorted(owner_inventory.get("packages", [])) or len(set(declared)) != len(declared):
        raise CannotRun("major upgrade candidate does not enumerate exactly the owner inventory packages")
    return candidate


def _head(root: Path, consumer: ConsumerPackage) -> str:
    result = run_git(root / consumer.repository, ("rev-parse", "HEAD"))
    return result.stdout.strip() if result.returncode == 0 else ""


def _pin_text(root: Path, consumer: ConsumerPackage) -> str:
    try:
        return (root / consumer.repository / consumer.pin_file).read_text(encoding="utf-8")
    except OSError as exc:
        raise CannotRun(f"{consumer.package}: pin file is unreadable") from exc


def _sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _receipt_problem(candidate: MajorUpgradeCandidate, consumer: ConsumerPackage, receipt: Mapping[str, Any]) -> str:
    bound = {
        "artifact": consumer.artifact,
        "target_major": candidate.target_major,
        "certification_revision": candidate.certification_revision,
        "profile": candidate.profile,
    }
    if any(receipt.get(key) != value for key, value in bound.items()):
        return "mismatched"
    if receipt.get("source_head") != consumer.source_head:
        return "stale"
    if receipt.get("result") == "skipped":
        return "skipped"
    return "" if receipt.get("result") in {_PASSED, _FAILED} else "mismatched"


def preflight(
    candidate: MajorUpgradeCandidate, receipts: Mapping[str, Any], root: Path, *, applied: Sequence[str] = ()
) -> tuple[int, list[dict[str, str]]]:
    """Exit code (0 admitted, 1 incompatible, 2 incomplete) and per-package findings."""
    by_package: dict[str, list[Mapping[str, Any]]] = {}
    for receipt in receipts.get("receipts", []):
        by_package.setdefault(str(receipt.get("package")), []).append(receipt)
    findings: list[dict[str, str]] = []
    for consumer in candidate.consumers:
        if consumer.package in applied:
            continue
        problem = _consumer_problem(candidate, consumer, by_package.get(consumer.package, []), root)
        if problem:
            findings.append({"package": consumer.package, "problem": problem})
    if any(item["problem"] != _FAILED for item in findings):
        return 2, findings
    return (1 if findings else 0), findings


def _consumer_problem(
    candidate: MajorUpgradeCandidate, consumer: ConsumerPackage, matching: list[Mapping[str, Any]], root: Path
) -> str:
    if _head(root, consumer) != consumer.source_head:
        return "expected-head-changed"
    if consumer.prior_pin not in _pin_text(root, consumer):
        return "prior-pin-changed"
    if not matching:
        return "missing"
    problems = {_receipt_problem(candidate, consumer, receipt) for receipt in matching}
    if "" not in problems:
        return sorted(problems)[0]
    if all(
        receipt.get("result") == _PASSED for receipt in matching if not _receipt_problem(candidate, consumer, receipt)
    ):
        return ""
    return _FAILED


def _entry(consumer: ConsumerPackage, root: Path, candidate: MajorUpgradeCandidate) -> dict[str, Any]:
    text = _pin_text(root, consumer)
    return {
        "package": consumer.package,
        "repository": consumer.repository,
        "prior_pin": consumer.prior_pin,
        "target_pin": consumer.target_pin,
        "artifact": consumer.artifact,
        "profile": candidate.profile,
        "expected_head": consumer.source_head,
        "head_before": _head(root, consumer),
        "pin_digest_before": _sha(text),
        "status": "unstarted",
        "reason": "",
    }


def _apply_one(consumer: ConsumerPackage, root: Path, entry: dict[str, Any]) -> bool:
    path = root / consumer.repository / consumer.pin_file
    text = path.read_text(encoding="utf-8")
    if text.count(consumer.prior_pin) != 1:
        entry.update(status="failed", reason="prior pin does not occur exactly once")
        return False
    path.write_text(text.replace(consumer.prior_pin, consumer.target_pin), encoding="utf-8")
    entry["status"] = "applied"
    if consumer.after_update_argv:
        done = subprocess.run(
            consumer.after_update_argv, cwd=root / consumer.repository, env=sanitized_env(), check=False
        )  # noqa: S603
        if done.returncode:
            entry.update(status="failed", reason=f"after-update command exited {done.returncode}")
    return entry["status"] == "applied"


def _finish(entry: dict[str, Any], consumer: ConsumerPackage, root: Path) -> None:
    entry["head_after"] = _head(root, consumer)
    entry["pin_digest_after"] = _sha(_pin_text(root, consumer))


def apply_updates(
    candidate: MajorUpgradeCandidate, root: Path, entries: list[dict[str, Any]], *, done: Sequence[str] = ()
) -> int:
    """Apply in owner order behind per-repository head checks; stop at the first non-applied update."""
    stopped = False
    for consumer, entry in zip(candidate.consumers, entries, strict=True):
        if consumer.package in done:
            entry["status"] = "already-applied"
        elif stopped:
            continue
        elif _head(root, consumer) != consumer.source_head:
            entry["reason"], stopped = "expected head changed after admission", True
        else:
            stopped = not _apply_one(consumer, root, entry)
        _finish(entry, consumer, root)
    return 1 if stopped else 0


def _prior_report(path: Path, resume: bool) -> dict[str, Any] | None:
    if not path.is_file():
        if resume:
            raise CannotRun("cannot resume: no prior report")
        return None
    if not resume:
        raise CannotRun("a prior report exists; revalidate and resume it with --resume")
    return load_json(path, "prior report")


def _already_applied(prior: Mapping[str, Any] | None, candidate: MajorUpgradeCandidate, root: Path) -> list[str]:
    if prior is None:
        return []
    names = [
        item["package"] for item in prior.get("consumers", []) if item.get("status") in {"applied", "already-applied"}
    ]
    for consumer in candidate.consumers:
        if consumer.package in names:
            text = _pin_text(root, consumer)
            if consumer.target_pin not in text or consumer.prior_pin in text:
                raise CannotRun(f"{consumer.package}: an applied pin no longer holds; refusing to resume")
    return names


def admit_from_arguments(args: argparse.Namespace, root: Path) -> int:
    """Preflight every consumer, then apply; the entry of the rollout."""
    if not args.receipts or not Path(args.receipts).is_file():
        raise CannotRun("scion-sdk compatibility receipts are unavailable; no pin may be written")
    candidate = parse_candidate(
        load_json(args.major_upgrade, "major upgrade candidate"), load_json(args.owner_inventory, "owner inventory")
    )
    receipts = load_json(args.receipts, "compatibility receipts")
    report_path = Path(args.report) if args.report else None
    prior = _prior_report(report_path, args.resume) if report_path else None
    applied = _already_applied(prior, candidate, root)
    entries = [_entry(consumer, root, candidate) for consumer in candidate.consumers]
    code, findings = preflight(candidate, receipts, root, applied=applied)
    admission = {"admitted": code == 0, "findings": findings, "receipts": receipts.get("receipts", [])}
    if code == 0:
        code = apply_updates(candidate, root, entries, done=applied)
    for entry, consumer in zip(entries, candidate.consumers, strict=True):
        if "head_after" not in entry:
            _finish(entry, consumer, root)
    report = {
        "version": REPORT_VERSION,
        "dependency": candidate.dependency,
        "target_major": candidate.target_major,
        "certification_revision": candidate.certification_revision,
        "admission": admission,
        "consumers": entries,
        "atomic_across_repositories": False,
    }
    if report_path:
        report_path.write_text(json.dumps(report, sort_keys=True, indent=2), encoding="utf-8")
    print(json.dumps(report, sort_keys=True), flush=True)
    return code
