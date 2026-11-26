"""PIPE-PAGES-R023.7-.12: pinned external rule packs inside the deterministic skill grader."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.docs import skill_grade
from tests.hooks.conftest import HOOK_REPOSITORY, Repo
from tests.hooks.test_skill_grade_hook import VALID_SKILL

PACK_BODY = (
    "rules:\n"
    "  no-faq:\n    adapter: forbidden-heading\n    params: {heading: faq}\n"
    "  prose-only:\n    description: be helpful\n"
    "  needs-name:\n    adapter: required-frontmatter-key\n    params: {key: name}\n"
)
WEIGHTS = {"frontmatter": 20, "description": 20, "structure": 20, "links": 20, "file_metadata": 20}


def _digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def _policy(pack_text: str = PACK_BODY, **overrides: object) -> dict[str, object]:
    pack: dict[str, object] = {
        "pack_id": "reviewed-pack",
        "version": "1.0.0",
        "path": "rules/pack.yaml",
        "digest": _digest(pack_text),
        "credit": "Reviewed Rules Project",
        "target_scope": "skills/*",
        "rules": [{"rule_id": "no-faq", "criterion": "structure", "weight": 0, "hard": True}],
    }
    pack.update(overrides)
    return {"schema_version": "skill-grade-v1", "criterion_weights": WEIGHTS, "minimum_grade": 80, "rule_packs": [pack]}


def _repo(tmp_path: Path, skill: str = VALID_SKILL, policy: dict[str, object] | None = None) -> Repo:
    repo = Repo(tmp_path)
    repo.git("init", "-q", "-b", "main")
    repo.commit(
        {
            "README.md": "# fixture\n",
            "skills/demo/SKILL.md": skill,
            "skills/demo/guide.md": "# Guide\n",
            "rules/pack.yaml": PACK_BODY,
            ".config/grade.yaml": yaml.safe_dump(policy or _policy()),
        }
    )
    return repo


def _dir(base: Path, name: str) -> Path:
    path = base / name
    path.mkdir()
    return path


def _run(repo: Repo, capsys: pytest.CaptureFixture[str], fmt: str = "json") -> tuple[int, str]:
    code = repo.run("skill-grade", "--policy", ".config/grade.yaml", "--format", fmt)
    return code, capsys.readouterr().out


# spec: PIPE-PAGES-R023.7
def test_external_grade_rules_model() -> None:
    policy = skill_grade.policy_from_mapping(_policy())
    pack = policy.rule_packs[0]
    assert (pack.pack_id, pack.version, pack.credit) == ("reviewed-pack", "1.0.0", "Reviewed Rules Project")
    assert pack.rules[0].hard is True
    assert policy.as_dict()["rule_packs"]
    duplicate = _policy(rules=[{"rule_id": "a"}, {"rule_id": "a"}])
    with pytest.raises(CannotRun, match="duplicate rule ID"):
        skill_grade.policy_from_mapping(duplicate)
    unpinned = _policy()
    del unpinned["rule_packs"][0]["digest"]  # type: ignore[index]
    with pytest.raises(CannotRun, match="digest"):
        skill_grade.policy_from_mapping(unpinned)
    with pytest.raises(CannotRun, match="digest must be sha256"):
        skill_grade.policy_from_mapping(_policy(digest="latest"))
    with pytest.raises(CannotRun, match="credit"):
        skill_grade.policy_from_mapping(_policy(credit=""))


# spec: PIPE-PAGES-R023.8
def test_external_grade_rules_behavior(tmp_path: Path) -> None:
    diagnostic = _policy(rules=[{"rule_id": "no-faq"}])
    faq_skill = VALID_SKILL + "\n## FAQ\n\nAsked.\n"
    repo = _repo(tmp_path, faq_skill, diagnostic)
    selected = skill_grade._snapshot(repo.root)
    report = skill_grade.grade_document(
        repo.root, Path("skills/demo/SKILL.md"), skill_grade.policy_from_mapping(diagnostic), snapshot=selected
    )
    # A diagnostic-only rule is identifiable but never changes the baseline grade.
    assert report.total_grade == 100 and report.status == "pass"
    assert [(f.pack, f.rule, f.blocking) for f in report.findings if f.pack] == [("reviewed-pack", "no-faq", False)]
    # A weighted replacement must declare a complete normalized 100-point policy.
    weighted = _policy(rules=[{"rule_id": "no-faq", "weight": 10}])
    with pytest.raises(CannotRun, match="must total 100"):
        skill_grade.policy_from_mapping(weighted)
    weighted["criterion_weights"] = {**WEIGHTS, "links": 10}  # type: ignore[index]
    policy = skill_grade.policy_from_mapping(weighted)
    graded = skill_grade.grade_document(repo.root, Path("skills/demo/SKILL.md"), policy, snapshot=selected)
    assert graded.total_grade == 90 and graded.hard_failure is False


# spec: PIPE-PAGES-R023.9
def test_external_grade_rules_wiring(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path, VALID_SKILL + "\n## FAQ\n\nAsked.\n")
    code, out = _run(repo, capsys)
    payload = json.loads(out)
    assert code == 1
    report = payload["reports"][0]
    assert report["external_rules"][0]["rule_id"] == "no-faq"
    assert report["findings"][-1]["rule"] == "no-faq"
    code, text = _run(repo, capsys, "text")
    assert code == 1 and "rule no-faq" in text and "reviewed-pack@1.0.0" in text
    hooks = yaml.safe_load((HOOK_REPOSITORY / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))
    assert "pipelines-hook skill-grade" in {hook["entry"] for hook in hooks}


# spec: PIPE-PAGES-R023.10
def test_external_grade_rules_refusal(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    assert _run(repo, capsys)[0] == 0
    tampered = Repo(_dir(tmp_path, "tampered"))
    tampered.git("init", "-q", "-b", "main")
    tampered.commit(
        {
            "README.md": "# f\n",
            "skills/demo/SKILL.md": VALID_SKILL,
            "skills/demo/guide.md": "# Guide\n",
            "rules/pack.yaml": PACK_BODY + "  extra: {adapter: required-heading}\n",
            ".config/grade.yaml": yaml.safe_dump(_policy()),
        }
    )
    assert _run(tampered, capsys)[0] == 2
    for name, rules in {
        "unknown": [{"rule_id": "not-in-pack"}],
        "prose": [{"rule_id": "prose-only"}],
    }.items():
        case = Repo(_dir(tmp_path, name))
        case.git("init", "-q", "-b", "main")
        case.commit(
            {
                "README.md": "# f\n",
                "skills/demo/SKILL.md": VALID_SKILL,
                "skills/demo/guide.md": "# Guide\n",
                "rules/pack.yaml": PACK_BODY,
                ".config/grade.yaml": yaml.safe_dump(_policy(rules=rules)),
            }
        )
        assert _run(case, capsys)[0] == 2, name
    assert _run(_repo(_dir(tmp_path, "faq"), VALID_SKILL + "\n## FAQ\n\nA.\n"), capsys)[0] == 1


# spec: PIPE-PAGES-R023.11
def test_external_grade_rules_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    policy = _policy(target_scope="elsewhere/*", rules=[{"rule_id": "no-faq", "hard": True}, {"rule_id": "needs-name"}])
    code, out = _run(_repo(_dir(tmp_path, "s"), policy=policy), capsys)
    baseline = json.loads(out)["reports"][0]
    assert code == 0
    entries = baseline["external_rules"]
    assert {e["disposition"] for e in entries} == {"skipped"} and len(entries) == 2
    assert entries[0]["pack_digest"] == _digest(PACK_BODY) and entries[0]["credit"] == "Reviewed Rules Project"
    assert "reason" in entries[0]
    # Diagnostic-only packs leave the baseline grade unchanged.
    diag = _repo(_dir(tmp_path, "d"), policy=_policy(rules=[{"rule_id": "needs-name"}]))
    report = json.loads(_run(diag, capsys)[1])["reports"][0]
    assert report["total_grade"] == 100
    assert report["external_rules"][0]["disposition"] == "pass"
    assert report["external_rules"][0]["measurement"]


# spec: PIPE-PAGES-R023.12
def test_external_grade_rules_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path, VALID_SKILL + "\n## FAQ\n\nAsked.\n")
    first = _run(repo, capsys)
    assert first[0] == 1
    assert json.loads(first[1])["reports"][0]["findings"][-1]["disposition"] == "hard-failure"
    repo.commit({"skills/demo/SKILL.md": VALID_SKILL})
    second = _run(repo, capsys)
    assert second[0] == 0
    assert _run(repo, capsys)[1] == second[1]  # stable serialization
    repo.commit({"rules/pack.yaml": PACK_BODY.replace("faq", "faqs")})
    assert _run(repo, capsys)[0] == 2
    repo.commit({"rules/pack.yaml": PACK_BODY.replace("forbidden-heading", "model-judgement")})
    assert _run(repo, capsys)[0] == 2
