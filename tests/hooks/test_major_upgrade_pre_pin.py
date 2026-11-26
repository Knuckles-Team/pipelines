"""PIPE-RELEASE-R001.7--R001.12: major dependency upgrade admission on compatibility receipts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import sanitized_env
from pipelines_hooks.release.major_upgrade import parse_candidate, preflight

ENV = {
    **sanitized_env(),
    "GIT_AUTHOR_NAME": "Fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "Fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
}
PRIOR, TARGET = "sdk>=1,<2", "sdk>=2,<3"
PACKAGES = ["consumer-one", "consumer-two"]


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=ENV, check=True)  # noqa: S603, S607
    return done.stdout.strip()


def _consumer(root: Path, name: str) -> dict[str, Any]:
    repo = root / name
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "pyproject.toml").write_text(f'dependencies = ["{PRIOR}"]\n', encoding="utf-8")
    _git(repo, "add", "pyproject.toml")
    _git(repo, "commit", "-q", "-m", "init")
    return {
        "package": name,
        "repository": name,
        "pin_file": "pyproject.toml",
        "source_head": _git(repo, "rev-parse", "HEAD"),
        "prior_pin": PRIOR,
        "target_pin": TARGET,
        "artifact": "sha256:" + name.encode().hex().ljust(64, "0")[:64],
    }


def _receipt(consumer: dict[str, Any], **override: Any) -> dict[str, Any]:
    base = {
        "package": consumer["package"],
        "artifact": consumer["artifact"],
        "target_major": 2,
        "certification_revision": "cert-7",
        "profile": "installed-wheel",
        "source_head": consumer["source_head"],
        "result": "passed",
    }
    return {**base, **override}


class Fixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.consumers = [_consumer(root, name) for name in PACKAGES]
        self.candidate_raw = {
            "dependency": "sdk",
            "target_major": 2,
            "certification_revision": "cert-7",
            "profile": "installed-wheel",
            "consumers": self.consumers,
        }
        self.inventory = {"packages": PACKAGES}
        self.receipts = {"receipts": [_receipt(c) for c in self.consumers]}

    def write(self) -> list[str]:
        files = {"candidate.json": self.candidate_raw, "inventory.json": self.inventory, "receipts.json": self.receipts}
        for name, payload in files.items():
            (self.root / name).write_text(json.dumps(payload), encoding="utf-8")
        return [
            "--root", str(self.root),
            "--major-upgrade", str(self.root / "candidate.json"),
            "--owner-inventory", str(self.root / "inventory.json"),
            "--receipts", str(self.root / "receipts.json"),
            "--report", str(self.root / "report.json"),
        ]  # fmt: skip

    def pins(self) -> list[bytes]:
        return [(self.root / name / "pyproject.toml").read_bytes() for name in PACKAGES]


def _pin(arguments: list[str], *extra: str) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-m", "pipelines_hooks", "release-phases", "pin", *arguments, *extra]
    env = {**ENV, "PYTHONPATH": str(Path(__file__).resolve().parents[2])}
    return subprocess.run(command, capture_output=True, text=True, env=env, check=False)  # noqa: S603


# spec: PIPE-RELEASE-R001.7
def test_major_upgrade_pre_pin_model(tmp_path: Path) -> None:
    fixture = Fixture(tmp_path)
    candidate = parse_candidate(fixture.candidate_raw, fixture.inventory)
    assert candidate.target_major == 2 and candidate.certification_revision == "cert-7"
    assert [c.package for c in candidate.consumers] == PACKAGES
    assert all(c.prior_pin == PRIOR and c.target_pin == TARGET and c.source_head for c in candidate.consumers)
    assert candidate.profile == "installed-wheel"
    with pytest.raises(CannotRun, match="exactly the owner inventory"):
        parse_candidate(fixture.candidate_raw, {"packages": [*PACKAGES, "consumer-three"]})
    with pytest.raises(CannotRun, match="exactly the owner inventory"):
        parse_candidate({**fixture.candidate_raw, "consumers": fixture.consumers[:1]}, fixture.inventory)
    with pytest.raises(CannotRun, match="incomplete"):
        parse_candidate({"dependency": "sdk"}, fixture.inventory)
    code, findings = preflight(candidate, fixture.receipts, tmp_path)
    assert (code, findings) == (0, [])


# spec: PIPE-RELEASE-R001.8
def test_major_upgrade_pre_pin_behavior(tmp_path: Path) -> None:
    fixture = Fixture(tmp_path)
    before = fixture.pins()
    fixture.receipts["receipts"][1]["result"] = "failed"
    arguments = fixture.write()
    refused = _pin(arguments)
    assert refused.returncode == 1 and fixture.pins() == before
    fixture.receipts["receipts"][1]["result"] = "passed"
    fixture.write()
    (tmp_path / "report.json").unlink()
    admitted = _pin(arguments)
    assert admitted.returncode == 0, admitted.stderr
    assert fixture.pins() == [f'dependencies = ["{TARGET}"]\n'.encode()] * 2
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["atomic_across_repositories"] is False
    assert [c["status"] for c in report["consumers"]] == ["applied", "applied"]


# R001.9 stays unbound: the Scion SDK receipt producer is not served yet.
def test_major_upgrade_pre_pin_wiring(tmp_path: Path) -> None:
    from pipelines_hooks.cli import GATES

    assert GATES["release-phases"] == "pipelines_hooks.release.phases"
    fixture = Fixture(tmp_path)
    marker = tmp_path / "bumped"
    names = ["only"]
    inventory = {
        "readiness": {"ready": True},
        "order": names,
        "candidates": [{"component_id": "only", "source_commit": "a" * 40, "artifact_digest": "sha256:" + "b" * 64}],
    }
    policy = {
        "phases": [{"name": "P1", "projects": names, "delay_seconds": 0, "timeout_seconds": 30}],
        "projects": {"only": {"bump_argv": [sys.executable, "-c", f"open({str(marker)!r}, 'w').close()"]}},
    }
    (tmp_path / "policy.json").write_text(json.dumps(policy), encoding="utf-8")
    (tmp_path / "candidates.json").write_text(json.dumps(inventory), encoding="utf-8")
    arguments = fixture.write()
    base = [
        "run", "--root", str(tmp_path), "--policy", str(tmp_path / "policy.json"),
        "--candidates", str(tmp_path / "candidates.json"), "--state", str(tmp_path / "state.json"),
        "--run-id", "r1", "--major-upgrade", str(tmp_path / "candidate.json"),
        "--owner-inventory", str(tmp_path / "inventory.json"),
    ]  # fmt: skip
    command = [sys.executable, "-m", "pipelines_hooks", "release-phases", *base]
    env = {**ENV, "PYTHONPATH": str(Path(__file__).resolve().parents[2])}
    # the Scion SDK receipt producer is not served here: no receipts, no pin, no bump
    unavailable = subprocess.run(command, capture_output=True, text=True, env=env, check=False)  # noqa: S603
    assert unavailable.returncode == 2 and "unavailable" in unavailable.stderr
    assert not marker.exists() and fixture.pins() == [f'dependencies = ["{PRIOR}"]\n'.encode()] * 2
    admitted = subprocess.run(  # noqa: S603
        [*command, "--receipts", arguments[7], "--report", arguments[9]],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert admitted.returncode == 0, admitted.stderr
    assert marker.exists() and fixture.pins() == [f'dependencies = ["{TARGET}"]\n'.encode()] * 2


# spec: PIPE-RELEASE-R001.10
def test_major_upgrade_pre_pin_refusal(tmp_path: Path) -> None:
    candidate_of = lambda fx: parse_candidate(fx.candidate_raw, fx.inventory)  # noqa: E731
    fixture = Fixture(tmp_path)
    candidate = candidate_of(fixture)

    def verdict(mutate) -> tuple[int, list[dict[str, str]]]:  # type: ignore[no-untyped-def]
        receipts = json.loads(json.dumps(fixture.receipts))
        mutate(receipts["receipts"])
        return preflight(candidate, receipts, tmp_path)

    assert verdict(lambda r: r[0].update(result="failed")) == (1, [{"package": PACKAGES[0], "problem": "failed"}])
    assert verdict(lambda r: r.pop(0)) == (2, [{"package": PACKAGES[0], "problem": "missing"}])
    assert verdict(lambda r: r[0].update(source_head="0" * 40))[1] == [{"package": PACKAGES[0], "problem": "stale"}]
    assert verdict(lambda r: r[0].update(result="skipped"))[1] == [{"package": PACKAGES[0], "problem": "skipped"}]
    assert verdict(lambda r: r[1].update(certification_revision="old"))[1][0]["problem"] == "mismatched"
    assert verdict(lambda r: r[1].update(artifact="sha256:" + "f" * 64))[1][0]["problem"] == "mismatched"

    # a changed expected head or prior pin invalidates admission
    (tmp_path / PACKAGES[0] / "other.txt").write_text("x", encoding="utf-8")
    _git(tmp_path / PACKAGES[0], "add", "other.txt")
    _git(tmp_path / PACKAGES[0], "commit", "-q", "-m", "move head")
    code, findings = preflight(candidate, fixture.receipts, tmp_path)
    assert (code, findings) == (2, [{"package": PACKAGES[0], "problem": "expected-head-changed"}])
    arguments = fixture.write()
    assert _pin(arguments).returncode == 2
    other = Fixture(_mk(tmp_path, "x"))
    (other.root / PACKAGES[1] / "pyproject.toml").write_text("dependencies = []\n", encoding="utf-8")
    assert preflight(candidate_of(other), other.receipts, other.root)[1] == [
        {"package": PACKAGES[1], "problem": "prior-pin-changed"}
    ]

    # after admission, a failure stops the rest and is reported; resuming demands --resume and revalidation
    third = Fixture(_mk(tmp_path, "y"))
    third.consumers[0]["after_update_argv"] = [sys.executable, "-c", "raise SystemExit(7)"]
    args = third.write()
    failed = _pin(args)
    report = json.loads((third.root / "report.json").read_text(encoding="utf-8"))
    assert failed.returncode == 1
    assert [c["status"] for c in report["consumers"]] == ["failed", "unstarted"]
    again = _pin(args)  # a prior report needs --resume
    assert again.returncode == 2 and "prior report exists" in again.stderr


# spec: PIPE-RELEASE-R001.11
def test_major_upgrade_pre_pin_evidence(tmp_path: Path) -> None:
    fixture = Fixture(tmp_path)
    fixture.receipts["receipts"][0]["result"] = "failed"
    arguments = fixture.write()
    before = fixture.pins()
    assert _pin(arguments).returncode == 1
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["admission"]["admitted"] is False
    assert report["admission"]["findings"] == [{"package": PACKAGES[0], "problem": "failed"}]
    assert len(report["admission"]["receipts"]) == 2
    for entry, raw in zip(report["consumers"], fixture.consumers, strict=True):
        assert entry["pin_digest_before"] == entry["pin_digest_after"]  # byte-identical pin evidence
        assert entry["expected_head"] == raw["source_head"] == entry["head_before"]
        assert {"prior_pin", "target_pin", "artifact", "profile", "status"} <= set(entry)
        assert entry["status"] == "unstarted"
    assert fixture.pins() == before

    # post-admission: applied, failed and unstarted are distinct, with exact resulting heads
    second = Fixture(_mk(tmp_path, "post"))
    second.consumers[0]["after_update_argv"] = [sys.executable, "-c", "raise SystemExit(5)"]
    assert _pin(second.write()).returncode == 1
    entries = json.loads((second.root / "report.json").read_text(encoding="utf-8"))["consumers"]
    assert [e["status"] for e in entries] == ["failed", "unstarted"]
    assert entries[0]["reason"] == "after-update command exited 5"
    assert entries[0]["head_after"] == _git(second.root / PACKAGES[0], "rev-parse", "HEAD")
    assert entries[0]["pin_digest_after"] != entries[0]["pin_digest_before"]


# R001.12 stays unbound: the Scion SDK receipt producer is not served yet.
def test_major_upgrade_pre_pin_cli(tmp_path: Path) -> None:
    incompatible = Fixture(_mk(tmp_path, "incompatible"))
    incompatible.receipts["receipts"].pop(1)
    before = incompatible.pins()
    assert _pin(incompatible.write()).returncode == 2
    assert incompatible.pins() == before

    fixture = Fixture(_mk(tmp_path, "race"))
    move = (
        "import subprocess, sys; subprocess.run(['git', '-c', 'user.name=x', '-c', 'user.email=x@example.invalid', '-C', sys.argv[1],"
        " 'commit', '-q', '--allow-empty', '-m', 'concurrent'], check=True)"
    )
    fixture.consumers[0]["after_update_argv"] = [sys.executable, "-c", move, str(fixture.root / PACKAGES[1])]
    arguments = fixture.write()
    done = _pin(arguments)
    assert done.returncode == 1
    entries = json.loads((fixture.root / "report.json").read_text(encoding="utf-8"))["consumers"]
    assert [e["status"] for e in entries] == ["applied", "unstarted"]
    assert entries[1]["reason"] == "expected head changed after admission"
    assert (fixture.root / PACKAGES[1] / "pyproject.toml").read_text(
        encoding="utf-8"
    ) == f'dependencies = ["{PRIOR}"]\n'
    # revalidation precedes resumption: the moved head now fails admission with exit 2 and writes nothing
    resumed = _pin(arguments, "--resume")
    assert resumed.returncode == 2
    assert (fixture.root / PACKAGES[1] / "pyproject.toml").read_text(
        encoding="utf-8"
    ) == f'dependencies = ["{PRIOR}"]\n'


def _mk(parent: Path, name: str) -> Path:
    path = parent / name
    path.mkdir()
    return path
