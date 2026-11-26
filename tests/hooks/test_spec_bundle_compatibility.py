"""spec-artifacts: a spec-bundle/1 is admitted unchanged, or refused with the reason."""

from __future__ import annotations

import hashlib
import json

import pytest
import yaml

from pipelines_hooks.cli import GATES
from pipelines_hooks.specs import spec_bundle
from tests.hooks.conftest import HOOK_REPOSITORY, Repo

_CAPABILITY = "alpha-feature"
_FILES = {
    "spec.md": "# ALPHA — alpha feature\n",
    "plan.md": "# plan\n",
    "requirements.md": "| `ALPHA-R001` | **One.** | Run `tests/test_a.py::test_a`. |\n| `ALPHA-R001.1` | Child. | tbd |\n",
    "tasks.md": "- [ ] T001 ALPHA-R001 do it\n",
    "test-spec.md": "| T-ALPHA-R001 | ALPHA-R001 | tbd |\n",
    "checklists/requirements.md": "- [x] ok\n",
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _manifest(capability: str = _CAPABILITY, **overrides: object) -> dict:
    document: dict = {
        "format": "spec-bundle/1",
        "encoding": "utf-8",
        "schema_version": 1,
        "capability": capability,
        "spec_id": "ALPHA",
        "ids": ["ALPHA-R001", "ALPHA-R001.1"],
        "files": [{"path": f"specs/{capability}/{n}", "sha256": _sha(t)} for n, t in _FILES.items()],
    }
    document.update(overrides)
    return document


def _commit_bundle(repo: Repo, manifest: dict | None = None, capability: str = _CAPABILITY) -> str:
    files = {f"specs/{capability}/{name}": text for name, text in _FILES.items()}
    path = f"specs/{capability}/spec-bundle.json"
    files[path] = json.dumps(manifest or _manifest(capability), indent=1)
    repo.commit(files, f"bundle {capability}")
    return path


def _evidence(out: str) -> dict:
    return json.loads(next(line for line in out.splitlines() if line.startswith("{")))


# spec: PIPE-PAGES-R012.8
def test_spec_bundle_compatibility_model(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    path = _commit_bundle(repo)
    assert repo.run("spec-artifacts", "--manifest", path) == 0
    evidence = _evidence(capsys.readouterr().out)
    assert evidence["format"] == "spec-bundle/1"
    assert sorted(evidence["consumed"]) == sorted(f"specs/{_CAPABILITY}/{n}" for n in _FILES)
    assert spec_bundle.STANDARD_FILES == tuple(_FILES)
    for bad in (_manifest(encoding="latin-1"), _manifest(ids=["ALPHA-R001"]), _manifest(files="none")):
        broken = _commit_bundle(repo, bad)
        assert repo.run("spec-artifacts", "--manifest", broken) == 1


# spec: PIPE-PAGES-R012.9
def test_spec_bundle_compatibility_behavior(repo: Repo) -> None:
    path = _commit_bundle(repo)
    before = {p: (repo.root / p).read_bytes() for p in (path, *(f"specs/{_CAPABILITY}/{n}" for n in _FILES))}
    assert repo.run("spec-artifacts", "--manifest", path, "--feature", "ALPHA") == 0
    assert before == {p: (repo.root / p).read_bytes() for p in before}
    assert repo.git("status", "--porcelain").strip() == ""
    # a second directory for the already-owned capability is refused, and so is a feature that skips the owner
    other = _commit_bundle(repo, _manifest("alpha-feature-two"), "alpha-feature-two")
    assert repo.run("spec-artifacts", "--manifest", other) == 1
    assert repo.run("spec-artifacts", "--manifest", path, "--feature", "ALPHA") == 1
    assert repo.run("spec-artifacts", "--manifest", f"specs/{_CAPABILITY}/spec.md") == 1  # a .md name proves nothing


# spec: PIPE-PAGES-R012.10
def test_spec_bundle_compatibility_wiring() -> None:
    assert GATES["spec-artifacts"] == "pipelines_hooks.specs.spec_bundle"
    hooks = yaml.safe_load((HOOK_REPOSITORY / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))
    assert [h["entry"] for h in hooks if h["id"] == "spec-artifacts"] == ["pipelines-hook spec-artifacts"]


# spec: PIPE-PAGES-R012.11
def test_spec_bundle_compatibility_refusal(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    unknown = _commit_bundle(repo, _manifest(format="spec-bundle/2"))
    assert repo.run("spec-artifacts", "--manifest", unknown) == 1
    assert "unknown format version" in capsys.readouterr().out
    escaping = _manifest(files=[{"path": "specs/other/../../x.md", "sha256": "0"}])
    assert repo.run("spec-artifacts", "--manifest", _commit_bundle(repo, escaping)) == 1
    assert "escapes the capability directory" in capsys.readouterr().out
    missing = _manifest()
    missing["files"].append({"path": f"specs/{_CAPABILITY}/nope.md", "sha256": "0"})
    assert repo.run("spec-artifacts", "--manifest", _commit_bundle(repo, missing)) == 1
    assert "missing file" in capsys.readouterr().out
    path = _commit_bundle(repo)
    repo.commit({f"specs/{_CAPABILITY}/plan.md": "# plan changed\n"})
    assert repo.run("spec-artifacts", "--manifest", path) == 1
    assert "altered input bytes" in capsys.readouterr().out
    # an unavailable consumer is unchecked evidence and exit status 2
    repo.commit({f"specs/{_CAPABILITY}/plan.md": _FILES["plan.md"]})
    assert repo.run("spec-artifacts", "--manifest", path, "--require-consumer") == 2


# spec: PIPE-PAGES-R012.12
def test_spec_bundle_compatibility_evidence(repo: Repo, tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _commit_bundle(repo)
    assert repo.run("spec-artifacts", "--manifest", path) == 0
    evidence = _evidence(capsys.readouterr().out)
    assert evidence["input_digest"] == _sha((repo.root / path).read_text())
    assert evidence["consumed"][f"specs/{_CAPABILITY}/plan.md"] == _sha(_FILES["plan.md"])
    assert evidence["owner"] == {"spec_id": "ALPHA", "directory": _CAPABILITY, "repository": repo.root.name}
    assert evidence["canonical_generation"]["status"] == "checked"
    assert evidence["graph_ingestion"]["status"] == "unchecked"
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({"consumer": "owner-adapter", "revision": "abc", "digests": evidence["consumed"]}))
    assert repo.run("spec-artifacts", "--manifest", path, "--consumer-receipt", str(receipt)) == 0
    assert _evidence(capsys.readouterr().out)["graph_ingestion"] == {
        "status": "checked",
        "revision": "abc",
        "consumer": "owner-adapter",
    }


# spec: PIPE-PAGES-R012.13
def test_spec_bundle_compatibility_cli(repo: Repo, tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _commit_bundle(repo)
    assert repo.run("spec-artifacts") == 0  # discovers specs/*/spec-bundle.json
    assert _evidence(capsys.readouterr().out)["owner"]["directory"] == _CAPABILITY
    stale = tmp_path / "receipt.json"
    stale.write_text(
        json.dumps({"consumer": "owner-adapter", "revision": "abc", "digests": {f"specs/{_CAPABILITY}/plan.md": "0"}})
    )
    assert repo.run("spec-artifacts", "--manifest", path, "--consumer-receipt", str(stale)) == 1
    assert "read as" in capsys.readouterr().out
    assert repo.run("spec-artifacts", "--manifest", path, "--require-consumer") == 2
    # an adapter receipt of the served shape (fixture of it) that read matching bytes is accepted unchanged
    evidence = _evidence(capsys.readouterr().out)
    served = tmp_path / "served.json"
    served.write_text(json.dumps({"consumer": "owner-adapter", "revision": "r1", "digests": evidence["consumed"]}))
    manifest_before = (repo.root / path).read_bytes()
    assert repo.run("spec-artifacts", "--manifest", path, "--consumer-receipt", str(served)) == 0
    assert (repo.root / path).read_bytes() == manifest_before
    # an unknown version is refused
    other = _commit_bundle(repo, _manifest(format="spec-bundle/9"), capability="beta-feature")
    assert repo.run("spec-artifacts", "--manifest", other) == 1
    assert "unknown format version" in capsys.readouterr().out
