"""Validation behavior manifest of the project configuration inventory.

Extends ``config-inventory`` (never a second project list): when the declaration carries a
``[validation]`` table (``baseline``, ``repository``, ``revision``, ``entry_point``) the checker
compares the complete behavior inventory of the pinned former central validation command with
every declared project's configured hooks.  The baseline artifact (``validation-baseline/1``)
is recovered and pinned independently; this module never reconstructs behavior from memory.

Each behavior carries its kind (``validation`` or ``test``), inputs, environment, expected exit and
a positive and a negative fixture tree (bound by digest).  A behavior is either mapped to a
configured hook (``gate`` is the pipelines gate that observes it) or retired by an explicit owner
decision that stays visible.  The fixtures run in disposable Git trees through the real gate; an
observed exit that differs from the pinned expectation, or a behavior with no configured hook in a
project, is a finding (exit 1).  An absent baseline, a pin that does not match, an unsupported
historical environment or stale fixtures is ``CannotRun`` (exit 2): migration stays unproved.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import yaml

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import blob_bytes, sanitized_env
from pipelines_hooks.core.tracked import tracked_paths

GATE = "config-inventory"
FORMAT = "validation-baseline/1"
KINDS = {"validation", "test"}
_REVISION = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class Fixture:
    path: str
    digest: str
    exit: int


@dataclass(frozen=True)
class ValidationBehavior:
    id: str
    kind: str
    inputs: tuple[str, ...]
    env: tuple[str, ...]
    expected_exit: int
    hook: str | None
    gate: str | None
    positive: Fixture | None
    negative: Fixture | None
    retired: str | None


@dataclass(frozen=True)
class ValidationPolicy:
    baseline: str
    repository: str
    revision: str
    entry_point: str


@dataclass
class ValidationBehaviorManifest:
    """The pinned former command, its complete behavior inventory and the evidence of one check."""

    policy: ValidationPolicy
    digest: str
    behaviors: list[ValidationBehavior]
    unknown_scope: tuple[str, ...]
    unsupported: tuple[str, ...]
    lines: list[str] = field(default_factory=list)


def parse_policy(data: object) -> ValidationPolicy:
    if not isinstance(data, dict) or set(data) != {"baseline", "repository", "revision", "entry_point"}:
        raise CannotRun(f"{GATE}: [validation] must declare exactly baseline, repository, revision, entry_point")
    if not all(isinstance(v, str) and v for v in data.values()):
        raise CannotRun(f"{GATE}: [validation] values must be non-empty strings")
    if not _REVISION.match(data["revision"]):
        raise CannotRun(f"{GATE}: the former command revision {data['revision']!r} is not a pinned 40-hex revision")
    pure = PurePosixPath(data["baseline"])
    if pure.is_absolute() or ".." in pure.parts:
        raise CannotRun(f"{GATE}: unsafe baseline path {data['baseline']!r}")
    return ValidationPolicy(data["baseline"], data["repository"], data["revision"], data["entry_point"])


def _fixture(bid: str, label: str, raw: object) -> Fixture:
    if not isinstance(raw, dict) or set(raw) != {"path", "digest", "exit"}:
        raise CannotRun(f"{GATE}: behavior {bid} {label} fixture must carry path, digest and exit")
    return Fixture(raw["path"], raw["digest"], int(raw["exit"]))


def load_manifest(root: Path, policy: ValidationPolicy) -> ValidationBehaviorManifest:
    raw = blob_bytes(root, f":{policy.baseline}")
    if raw is None:
        raise CannotRun(f"{GATE}: the pinned baseline {policy.baseline} is not in the snapshot; migration unproved")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise CannotRun(f"{GATE}: baseline {policy.baseline} is unreadable: {exc}") from exc
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise CannotRun(f"{GATE}: unsupported baseline format")
    command = data.get("command", {})
    pin = (command.get("repository"), command.get("revision"), command.get("entry_point"))
    if pin != (policy.repository, policy.revision, policy.entry_point):
        raise CannotRun(
            f"{GATE}: the baseline is not the pinned former command {policy.entry_point}@{policy.revision[:12]}"
        )
    behaviors: list[ValidationBehavior] = []
    for entry in data.get("behaviors", []):
        bid = str(entry.get("id", ""))
        if not bid or entry.get("kind") not in KINDS:
            raise CannotRun(f"{GATE}: behavior {bid!r} lacks an id or a known kind")
        mapping = entry.get("mapping") or {}
        retired = (entry.get("retired") or {}).get("decision")
        behaviors.append(
            ValidationBehavior(
                bid,
                entry["kind"],
                tuple(entry.get("inputs", [])),
                tuple(entry.get("env", [])),
                int(entry.get("expected_exit", 0)),
                mapping.get("hook"),
                mapping.get("gate"),
                _fixture(bid, "positive", entry["positive"]) if "positive" in entry else None,
                _fixture(bid, "negative", entry["negative"]) if "negative" in entry else None,
                retired,
            )
        )
    ids = [b.id for b in behaviors]
    if not behaviors or len(set(ids)) != len(ids):
        raise CannotRun(f"{GATE}: the baseline lists no behaviors or repeats an id")
    return ValidationBehaviorManifest(
        policy,
        hashlib.sha256(raw).hexdigest()[:16],
        behaviors,
        tuple(data.get("unknown_scope", [])),
        tuple(data.get("unsupported_environments", [])),
    )


def _tree_digest(root: Path, path: str) -> tuple[str, dict[str, bytes]]:
    files = {}
    for tracked in tracked_paths(root, (path + "/",)):
        raw = blob_bytes(root, f":{tracked}")
        if raw is not None:
            files[str(PurePosixPath(tracked).relative_to(path))] = raw
    if not files:
        raise CannotRun(f"{GATE}: fixture tree {path} is not in the snapshot")
    blob = b"".join(k.encode() + b"\0" + hashlib.sha256(v).digest() for k, v in sorted(files.items()))
    return hashlib.sha256(blob).hexdigest()[:16], files


def _observe(gate: str, files: dict[str, bytes]) -> tuple[int, str]:
    """Run one pipelines gate in a disposable Git tree; return its exit and an output digest."""
    from pipelines_hooks.cli import GATES, run_gate

    if gate not in GATES:
        raise CannotRun(f"{GATE}: unknown gate {gate!r} for a behavior mapping")
    tmp = Path(tempfile.mkdtemp(prefix="validation-behavior-"))
    try:
        for rel, raw in files.items():
            target = tmp / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        env = sanitized_env()
        subprocess.run(["git", "init", "-q"], cwd=tmp, env=env, check=True, capture_output=True)
        subprocess.run(["git", "add", "--", *files], cwd=tmp, env=env, check=True, capture_output=True)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = run_gate(gate, ["--root", str(tmp)])
        text = (out.getvalue() + err.getvalue()).replace(str(tmp), "<tree>")
        return code, hashlib.sha256(text.encode()).hexdigest()[:16]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _configured_hooks(root: Path, path: str) -> set[str]:
    raw = blob_bytes(root, f":{path}")
    if raw is None:
        return set()
    try:
        data = yaml.safe_load(raw.decode("utf-8")) or {}
    except (UnicodeError, yaml.YAMLError):
        return set()
    return {
        h["id"] for repo in data.get("repos", []) for h in repo.get("hooks", []) if isinstance(h, dict) and "id" in h
    }


def check_behaviors(
    root: Path, project_configs: dict[str, str], policy: ValidationPolicy
) -> tuple[list[str], ValidationBehaviorManifest]:
    """Findings (exit 1) comparing the whole behavior inventory with each project's hooks."""
    manifest = load_manifest(root, policy)
    if manifest.unsupported:
        raise CannotRun(
            f"{GATE}: unsupported historical environments remain unavailable evidence: {list(manifest.unsupported)}"
        )
    findings: list[str] = []
    lines = manifest.lines
    lines.append(
        f"baseline repository={policy.repository} revision={policy.revision} entry-point={policy.entry_point} "
        f"digest={manifest.digest} behaviors={[b.id for b in manifest.behaviors]}"
    )
    lines.append(f"unknown-scope {list(manifest.unknown_scope) or 'none declared'}")
    configured = {project: _configured_hooks(root, path) for project, path in project_configs.items()}
    for behavior in manifest.behaviors:
        where = f"{policy.baseline}: behavior {behavior.id}"
        if behavior.retired:
            lines.append(f"behavior id={behavior.id} state=retired decision={behavior.retired}")
            continue
        if not behavior.hook or not behavior.gate:
            findings.append(
                f"{where}: no mapped hook and no owner retirement decision; an absent mapping is not equivalence"
            )
            continue
        mapped = []
        for project, hooks in configured.items():
            if behavior.hook in hooks:
                mapped.append(project)
            else:
                findings.append(
                    f"{project_configs[project]}: project {project!r} configures no hook {behavior.hook} for {behavior.id}"
                )
        if behavior.positive is None or behavior.negative is None:
            findings.append(f"{where}: needs a positive and a negative fixture")
            continue
        observations = []
        for label, fixture, want in (
            ("positive", behavior.positive, 0),
            ("negative", behavior.negative, behavior.expected_exit),
        ):
            digest, files = _tree_digest(root, fixture.path)
            if digest != fixture.digest:
                raise CannotRun(f"{GATE}: stale fixture {fixture.path} for behavior {behavior.id}")
            code, out_digest = _observe(behavior.gate, files)
            observations.append(f"{label}:fixture={digest} exit={code} want={want} output={out_digest}")
            if fixture.exit != want:
                findings.append(
                    f"{where}: pinned {label} fixture expects exit {fixture.exit}, the baseline requires {want}"
                )
            if code != fixture.exit:
                findings.append(
                    f"{where}: {label} fixture observed exit {code}, pinned {fixture.exit} ({behavior.hook})"
                )
        lines.append(
            f"behavior id={behavior.id} kind={behavior.kind} state=mapped hook={behavior.hook} projects={mapped} "
            f"inputs={list(behavior.inputs)} env={list(behavior.env)} " + " ".join(observations)
        )
    return findings, manifest
