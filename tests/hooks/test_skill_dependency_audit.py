"""repository-validation audits skill dependencies: findings, stored proposals, never an install."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipelines_hooks.cli import GATES
from pipelines_hooks.code import repository_validation as rv
from pipelines_hooks.core.errors import CannotRun
from tests.hooks.conftest import HOOK_REPOSITORY, Repo

AS_OF = "2026-11-26"
SKILL = "skills/demo/SKILL.md"
REQUIREMENTS = "# group: runtime\nrequests==2.0.0\nleft-pad==1.0.0\n# group: dev\npytest==8.0.0\n"
ADVISORIES = {
    "captured_at": "2026-11-25",
    "advisories": [{"id": "ADV-1", "package": "requests", "affected": ["2.0.0"], "fixed": "2.1.0"}],
}


def _fixture(repo: Repo, requirements: str | None = REQUIREMENTS, advisories: dict | None = None) -> Path:
    files = {SKILL: "---\nname: demo\n---\n# demo\n"}
    if requirements is not None:
        files["skills/demo/requirements.txt"] = requirements
    repo.commit(files)
    path = repo.root.parent / f"{repo.root.name}-advisories.json"
    path.write_text(json.dumps(advisories or ADVISORIES), encoding="utf-8")
    return path


def _run(repo: Repo, advisories: Path, store: Path | None, *extra: str) -> int:
    args = ["--audit-skill-dependencies", str(advisories), "--as-of", AS_OF, *extra]
    if store is not None:
        args += ["--proposal-store", str(store)]
    return repo.run("repository-validation", *args)


def _evidence(out: str) -> dict:
    return json.loads(next(line for line in out.splitlines() if line.startswith("{")))


@pytest.mark.spec("PIPE-PAGES-R021.31")
def test_skill_dependency_audit_model() -> None:
    groups = rv.parse_declaration(SKILL, REQUIREMENTS)
    assert groups == {"dev": (("pytest", "8.0.0"),), "runtime": (("left-pad", "1.0.0"), ("requests", "2.0.0"))}
    audit = rv.SkillDependencyAudit(SKILL, "s", "i", groups, "a")
    assert audit.installation_effects == 0 and audit.approval_state == "unapproved"
    proposal = {"identity": "p", "old": "2.0.0", "target": "2.1.0", "finding": "ADV-1", "provenance": {"advisory": "a"}}
    assert {"old", "target", "finding", "provenance"} <= set(
        proposal
    )  # a proposal carries versions, finding and source


@pytest.mark.spec("PIPE-PAGES-R021.32")
def test_skill_dependency_audit_behavior(repo: Repo, tmp_path: Path, capsys) -> None:
    advisories = _fixture(repo)
    store = tmp_path / "store"
    assert _run(repo, advisories, store) == 1
    evidence = _evidence(capsys.readouterr().out)
    assert [f["package"] for f in evidence["findings"]] == ["requests"]
    stored = json.loads((store / f"{evidence['proposals'][0]}.json").read_text())
    assert (stored["old"], stored["target"], stored["finding"]) == ("2.0.0", "2.1.0", "ADV-1")
    audit = rv.audit_skill(SKILL, REQUIREMENTS, ADVISORIES["advisories"], "d", rv.ProposalStore(store))
    assert len(audit.receipts) == 1 and audit.installation_effects == 0  # one proposal per vulnerable dependency
    assert sorted(n for pins in rv.parse_declaration(SKILL, REQUIREMENTS).values() for n, _ in pins) == [
        "left-pad",
        "pytest",
        "requests",
    ]  # every declared dependency is enumerated


@pytest.mark.spec("PIPE-PAGES-R021.33")
def test_skill_dependency_audit_wiring() -> None:
    assert GATES["repository-validation"] == "pipelines_hooks.code.repository_validation"
    hooks = (HOOK_REPOSITORY / ".pre-commit-hooks.yaml").read_text()
    assert "pipelines-hook repository-validation" in hooks
    assert rv.main is not None and hasattr(rv, "ProposalStore")


@pytest.mark.spec("PIPE-PAGES-R021.34")
def test_skill_dependency_audit_refusal(repo: Repo, tmp_path: Path, capsys) -> None:
    advisories = _fixture(repo, requirements=None)
    assert _run(repo, advisories, tmp_path / "s") == 2  # no declaration
    repo.commit({"skills/demo/requirements.txt": "requests>=2\n"})
    assert _run(repo, advisories, tmp_path / "s") == 2  # an unresolved version
    repo.commit({"skills/demo/requirements.txt": REQUIREMENTS})
    stale = tmp_path / "stale.json"
    stale.write_text(json.dumps({**ADVISORIES, "captured_at": "2026-01-01"}))
    assert _run(repo, stale, tmp_path / "s") == 2  # stale advisory evidence
    capsys.readouterr()
    blocked = tmp_path / "blocked"
    blocked.write_text("a file where the store directory belongs")
    assert _run(repo, advisories, blocked) == 2  # unavailable owner storage
    assert _evidence(capsys.readouterr().out)["findings"][0]["advisory"] == "ADV-1"  # the finding survives
    assert _run(repo, advisories, tmp_path / "s", "--install") == 2  # an install request fails
    with pytest.raises(CannotRun):
        rv.bind_approval(rv.ProposalStore(tmp_path / "none"), "missing", "digest")


@pytest.mark.spec("PIPE-PAGES-R021.35")
def test_skill_dependency_audit_evidence(repo: Repo, tmp_path: Path, capsys) -> None:
    advisories = _fixture(repo)
    assert _run(repo, advisories, tmp_path / "store") == 1
    evidence = _evidence(capsys.readouterr().out)
    for key in ("skill_digest", "inventory_digest", "advisory_digest", "findings", "proposals", "receipts"):
        assert evidence[key]
    assert evidence["receipts"][0] == {"identity": evidence["proposals"][0], "stored": True}
    assert evidence["approval_state"] == "unapproved" and evidence["installation_effects"] == 0


@pytest.mark.spec("PIPE-PAGES-R021.36")
def test_skill_dependency_audit_cli(repo: Repo, tmp_path: Path, capsys) -> None:
    advisories = _fixture(repo)
    before = {p.name: p.read_bytes() for p in (repo.root / "skills/demo").iterdir()}
    store = tmp_path / "store"
    assert _run(repo, advisories, store) == 1
    evidence = _evidence(capsys.readouterr().out)
    assert {
        p.name: p.read_bytes() for p in (repo.root / "skills/demo").iterdir()
    } == before  # no package or lock change
    readback = rv.ProposalStore(store).get(evidence["proposals"][0])  # an independent read of the stored proposal
    assert readback["package"] == "requests"
    listing = sorted(p.name for p in store.iterdir())
    with pytest.raises(CannotRun):  # a stale approval refuses without effects
        rv.bind_approval(rv.ProposalStore(store), readback["identity"], "stale-digest")
    assert _run(repo, advisories, store, "--install") == 2  # a direct install attempt refuses
    assert sorted(p.name for p in store.iterdir()) == listing
    assert (
        rv.bind_approval(rv.ProposalStore(store), readback["identity"], readback["artifact_digest"])["approval_state"]
        == "approved"
    )
