"""PIPE-PAGES-R021.25-.30: one deterministic health score and a prioritised fix list."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipelines_hooks.code import repository_health as health
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.validation_report import ValidationReport
from pipelines_hooks.docs import skill_grade
from pipelines_hooks.supply_chain.finding import Finding
from tests.hooks.conftest import PYPROJECT, Repo
from tests.hooks.pinned_tools import pinned_ruff  # noqa: F401

CLEAN = "import os\nimport sys\n\nVALUE: int = 1\nprint(os, sys)\n"
RULES = {
    "dead-code": ["unused-symbol"],
    "secrets": ["secret-shaped-token"],
    "dependency-risk": ["advisory-match"],
    "complexity": ["hotspot"],
    "untested": ["untested-function"],
}
KIND = {
    "dead-code": "candidate",
    "secrets": "measured",
    "dependency-risk": "advisory",
    "complexity": "measured",
    "untested": "coverage",
}
POLICY = """version = 1
block_at = "high"
[weights]
dead-code = 1
secrets = 3
dependency-risk = 2
complexity = 1
untested = 1
[penalties]
critical = 50
high = 30
medium = 10
low = 2
"""


def adapters(optional: tuple[str, ...] = ()) -> str:
    out = ""
    for category, rules in RULES.items():
        out += (
            f'[[adapters]]\ncategory = "{category}"\nversion = "1.0"\nscope = ["pkg"]\nrules = {json.dumps(rules)}\n'
            f'required = {"false" if category in optional else "true"}\nevidence_kind = "{KIND[category]}"\n'
            f'receipt = ".receipts/{category}.json"\n[adapters.severity_map]\nerror = "high"\nwarn = "low"\nnote = "medium"\n'
        )
    return out


def repo(tmp_path: Path, mod: str = CLEAN, policy: str | None = None) -> tuple[Repo, str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    r = Repo(tmp_path)
    r.git("init", "-q")
    r.stage(
        {
            "pyproject.toml": PYPROJECT,
            "pkg/__init__.py": "",
            "pkg/mod.py": mod,
            "health.toml": policy or POLICY + adapters(),
        }
    )
    return r, skill_grade.select_snapshot(tmp_path).identity


def receipt(r: Repo, snap: str, category: str, findings: list[dict[str, object]] | None = None, **over: object) -> None:
    body = {"snapshot": snap, "version": "1.0", "findings": findings or []}
    body.update(over)
    r.write(f".receipts/{category}.json", json.dumps(body))


def all_receipts(r: Repo, snapshot: str, extra: dict[str, list[dict[str, object]]] | None = None) -> None:
    for category in RULES:
        receipt(r, snapshot, category, (extra or {}).get(category))


def finding(category: str, severity: str = "error", path: str = "pkg/mod.py", line: int = 1) -> dict[str, object]:
    return {
        "rule": RULES[category][0],
        "severity": severity,
        "path": path,
        "line": line,
        "digest": f"sha256:{category}{line}",
    }


def evaluate(r: Repo, snapshot: str):  # type: ignore[no-untyped-def]
    return health.evaluate(r.root, health.load_policy(r.root / "health.toml"), snapshot, {})


# spec: PIPE-PAGES-R021.25
def test_policy_model_scored_and_unscored(tmp_path: Path) -> None:
    r, snap = repo(tmp_path)
    policy = health.load_policy(r.root / "health.toml")
    assert set(policy.weights) == set(health.SCORED) and not set(health.UNSCORED) & set(policy.weights)
    assert {a.category: a.evidence_kind for a in policy.adapters}["dependency-risk"] == "advisory"
    for bad in (POLICY.replace("secrets = 3", "secrets = 0"), POLICY.replace("[weights]", "[weights]\nlint = 1")):
        (r.root / "bad.toml").write_text(bad + adapters())
        with pytest.raises(CannotRun):
            health.load_policy(r.root / "bad.toml")
    assert snap


# spec: PIPE-PAGES-R021.26
def test_score_is_deterministic_deduplicated_and_priority_ordered(tmp_path: Path) -> None:
    r, snap = repo(tmp_path)
    all_receipts(
        r,
        snap,
        {
            "secrets": [finding("secrets"), finding("secrets")],
            "untested": [finding("untested", "warn", line=9)],
            "dead-code": [finding("dead-code", "note", "pkg/a.py", 3)],
        },
    )
    checks, summary = evaluate(r, snap)
    assert summary.categories["secrets"].findings == 1 and summary.categories["secrets"].score == 70
    assert summary.score == round((1 * 90 + 3 * 70 + 2 * 100 + 1 * 100 + 1 * 98) / 8) and summary.score_available
    assert [(f.rank, f.category, f.blocking) for f in summary.fixes] == [
        (1, "secrets", True),
        (2, "dead-code", False),
        (3, "untested", False),
    ]
    assert evaluate(r, snap)[1] == summary
    assert {c.category for c in checks} == set(health.SCORED)
    r2, snap2 = repo(tmp_path / "unchecked")
    all_receipts(r2, snap2)
    (r2.root / ".receipts/complexity.json").unlink()
    with pytest.raises(CannotRun, match="required receipt"):
        evaluate(r2, snap2)
    optional, osnap = repo(tmp_path / "optional", policy=POLICY + adapters(("complexity",)))
    all_receipts(optional, osnap)
    (optional.root / ".receipts/complexity.json").unlink()
    partial = evaluate(optional, osnap)[1]
    assert partial.score is None and not partial.score_available and partial.coverage == 0.8
    assert partial.categories["complexity"].status == "skipped"


# spec: PIPE-PAGES-R021.27
def test_wiring_adapts_supply_chain_findings_and_the_aggregate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    r, snap = repo(tmp_path)
    leaked = Finding("repo", "pkg/mod.py", 1, "secret-shaped-token", "token=ghp_" + "a" * 30)
    adapted = health.supply_chain_receipt([leaked], snapshot=snap, version="1.0")
    assert "ghp_" not in json.dumps(adapted)
    r.stage({"pyproject.toml": PYPROJECT + '\n[tool.pipelines_hooks.repository_validation]\nrequired = ["skill"]\n'})
    snap = skill_grade.select_snapshot(tmp_path).identity
    all_receipts(r, snap)
    adapted = health.supply_chain_receipt([leaked], snapshot=snap, version="1.0")
    receipt(r, snap, "secrets", adapted["findings"])  # type: ignore[arg-type]
    assert r.run("repository-validation", "--health-policy", "health.toml") == 1
    assert "health: score=" in capsys.readouterr().out


# spec: PIPE-PAGES-R021.28
def test_refusals(tmp_path: Path) -> None:
    r, snap = repo(tmp_path)
    receipt(r, snap, "secrets", [finding("secrets", "catastrophic")])
    for c in RULES:
        if c != "secrets":
            receipt(r, snap, c)
    with pytest.raises(CannotRun, match="unknown severity"):
        evaluate(r, snap)
    receipt(r, snap, "secrets", **{"snapshot": "stale"})
    with pytest.raises(CannotRun, match="stale receipt"):
        evaluate(r, snap)
    receipt(r, snap, "secrets")
    (r.root / ".receipts/dependency-risk.json").write_text("{")
    with pytest.raises(CannotRun, match="malformed"):
        evaluate(r, snap)
    r.write("health.toml", (POLICY + adapters()).replace('evidence_kind = "advisory"', 'evidence_kind = "format"'))
    receipt(r, snap, "dependency-risk")
    with pytest.raises(CannotRun, match="advisory evidence"):
        evaluate(r, snap)


# spec: PIPE-PAGES-R021.29
def test_evidence_counts_redaction_and_unscored_categories(tmp_path: Path) -> None:
    r, snap = repo(tmp_path)
    all_receipts(r, snap, {"secrets": [{**finding("secrets"), "digest": "token=ghp_" + "b" * 30}]})
    checks, summary = evaluate(r, snap)
    dump = json.dumps([c.model_dump(mode="json") for c in checks])
    assert "ghp_" not in dump and "[REDACTED]" in dump
    assert set(summary.unscored) == {"lint", "import-order", "type"} and summary.categories["dead-code"].weight == 1
    assert summary.weights["secrets"] == 3 and summary.penalties["high"] == 30
    report = ValidationReport.build(repository="x", snapshot=snap, checks=checks, health=summary)
    assert ValidationReport.from_json(report.to_json()).health == summary


# spec: PIPE-PAGES-R021.30
def test_hot_path_required_phase_fails_despite_the_score(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    r, snap = repo(tmp_path, "import os\nVALUE: int = 1\n")
    all_receipts(r, snap)
    assert r.run("repository-validation", "--health-policy", "health.toml") == 1
    out = capsys.readouterr().out
    assert "lint: pkg/mod.py:1 F401" in out and "health: score=100" in out
    r.stage({"pkg/mod.py": CLEAN})
    snap = skill_grade.select_snapshot(tmp_path).identity
    all_receipts(r, snap, {"dead-code": [finding("dead-code", "note")]})
    assert r.run("repository-validation", "--health-policy", "health.toml") == 0
    assert "health: score=99" in capsys.readouterr().out
