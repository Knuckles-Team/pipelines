"""PIPE-PAGES-R020.13-.18: the offline changelog grammar gate over one Git snapshot."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from pipelines_hooks.cli import GATES
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.docs.changelog import ChangelogFinding, ChangelogPolicy, check, policy_from_mapping
from tests.hooks.conftest import HOOK_REPOSITORY, Repo

BASE = "https://example.invalid/org/repo"
VALID = f"""# Changelog

## [Unreleased]

## [1.1.0] - 2026-02-01

### Added

- A feature.
- [Breaking] A renamed option.

### Fixed

- A defect.

## [1.0.0] - 2026-01-01

### Added

- The first release.

[Unreleased]: {BASE}/compare/v1.1.0...HEAD
[1.1.0]: {BASE}/compare/v1.0.0...v1.1.0
[1.0.0]: {BASE}/releases/tag/v1.0.0
"""
ONLY_UNRELEASED = f"# Changelog\n\n## [Unreleased]\n\n[Unreleased]: {BASE}/compare/v0.0.0...HEAD\n"


def rules(text: str) -> list[tuple[int, str]]:
    _sections, findings, _links = check(ChangelogPolicy(), text)
    return [(f.line, f.rule) for f in findings]


def _fresh(base: Path, name: str, files: dict[str, str]) -> Repo:
    path = base / name
    path.mkdir()
    repo = Repo(path)
    repo.git("init", "-q")
    repo.commit(files)
    return repo


def _repo(tmp_path: Path, text: str | None = VALID) -> Repo:
    repo = Repo(tmp_path)
    repo.git("init", "-q")
    repo.commit({"README.md": "# fixture\n", **({"CHANGELOG.md": text} if text is not None else {})})
    return repo


# spec: PIPE-PAGES-R020.13
def test_changelog_model() -> None:
    policy = policy_from_mapping({"path": "docs/CHANGELOG.md", "tag_template": "release-{version}"})
    assert policy.tag("1.2.3") == "release-1.2.3"
    with pytest.raises(CannotRun, match="unknown field"):
        policy_from_mapping({"grammar_extra": 1})
    with pytest.raises(CannotRun, match="unsupported grammar"):
        policy_from_mapping({"grammar": "changelog-v9"})
    with pytest.raises(CannotRun, match="unsafe"):
        policy_from_mapping({"path": "../CHANGELOG.md"})
    sections, findings, _links = check(ChangelogPolicy(), VALID)
    assert findings == []
    assert [(s.version, s.date, s.line) for s in sections] == [
        ("Unreleased", None, 3),
        ("1.1.0", "2026-02-01", 5),
        ("1.0.0", "2026-01-01", 16),
    ]
    assert sections[1].categories["Added"][1] == (10, "[Breaking] A renamed option.")
    assert sections[1].link == f"{BASE}/compare/v1.0.0...v1.1.0"
    with pytest.raises(ValueError):
        ChangelogFinding("CHANGELOG.md", 1, "invented")
    assert [
        line
        for line, rule in rules(VALID.replace("## [1.0.0] - 2026-01-01", "## [1.1.0] - 2026-01-01"))
        if rule == "duplicate"
    ]


# spec: PIPE-PAGES-R020.14
def test_changelog_grammar() -> None:
    assert rules(VALID) == []
    cases = {
        "date": VALID.replace("2026-02-01", "2026-02-30"),
        "version": VALID.replace("[1.1.0] -", "[01.1.0] -").replace("[1.1.0]:", "[01.1.0]:"),
        "category": VALID.replace("### Fixed", "### Tweaked"),
        "entry": VALID.replace("### Added\n\n- A feature.", "- Stray bullet.\n\n### Added\n\n- A feature."),
        "link": VALID.replace(f"[1.0.0]: {BASE}/releases/tag/v1.0.0\n", ""),
        "duplicate": VALID.replace("## [1.0.0] - 2026-01-01", "## [1.1.0] - 2026-01-01"),
        "order": VALID.replace("2026-01-01", "2026-03-01"),
    }
    for rule, text in cases.items():
        assert rule in {r for _line, r in rules(text)}, rule
    assert any(rule == "link" for _l, rule in rules(VALID.replace("v1.0.0...v1.1.0", "v0.9.0...v1.1.0")))
    assert any(
        rule == "version" for _l, rule in rules(VALID.replace("[1.0.0] -", "[1.0] -").replace("[1.0.0]:", "[1.0]:"))
    )
    assert not any(
        rule == "version"
        for _l, rule in rules(VALID.replace("[1.0.0]", "[1.0.0-rc.1+build.5]").replace("v1.0.0", "v1.0.0-rc.1+build.5"))
    )


# spec: PIPE-PAGES-R020.15
def test_changelog_hook_wiring(tmp_path: Path) -> None:
    assert GATES["changelog"] == "pipelines_hooks.docs.changelog"
    hooks = yaml.safe_load((HOOK_REPOSITORY / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))
    assert "pipelines-hook changelog" in {hook["entry"] for hook in hooks}
    repo = _repo(tmp_path)
    repo.commit(
        {
            ".config/changelog.toml": 'path = "docs/CHANGES.md"\ntag_template = "rel-{version}"\n',
            "docs/CHANGES.md": VALID.replace("/v1", "/rel-1").replace("...v1", "...rel-1"),
        }
    )
    assert repo.run("changelog") == 0
    # With the policy file named absent, the default policy checks the root document.
    assert repo.run("changelog", "--policy", "absent-policy.toml") == 0


# spec: PIPE-PAGES-R020.16
def test_changelog_refusals(tmp_path: Path) -> None:
    assert _fresh(tmp_path, "a", {"README.md": "x\n"}).run("changelog") == 2
    bad_policy = _fresh(tmp_path, "b", {"CHANGELOG.md": VALID, ".config/changelog.toml": 'grammar = "other"\n'})
    assert bad_policy.run("changelog") == 2
    bad_policy.commit({".config/changelog.toml": "not = [valid"})
    assert bad_policy.run("changelog") == 2
    only = _fresh(tmp_path, "c", {"CHANGELOG.md": ONLY_UNRELEASED})
    assert only.run("changelog") == 2
    only.commit({"CHANGELOG.md": "# Changelog\n\n## [Unreleased]\n"})
    assert only.run("changelog") == 2
    with pytest.raises(CannotRun, match="missing-release-anchor at CHANGELOG.md:3"):
        check(ChangelogPolicy(), ONLY_UNRELEASED)
    with pytest.raises(CannotRun, match="parser limit"):
        check(ChangelogPolicy(max_lines=5), VALID)
    missing = _fresh(tmp_path, "d", {"CHANGELOG.md": VALID.replace(f"[1.1.0]: {BASE}/compare/v1.0.0...v1.1.0\n", "")})
    assert missing.run("changelog") == 1


# spec: PIPE-PAGES-R020.17
def test_changelog_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path, VALID.replace("2026-02-01", "2026-02-30"))
    assert repo.run("changelog") == 1
    lines = capsys.readouterr().out.splitlines()
    digest = "sha256:" + hashlib.sha256(VALID.replace("2026-02-01", "2026-02-30").encode()).hexdigest()
    tree = repo.git("write-tree").strip()
    assert lines[0].startswith(f"changelog: snapshot index:{tree}, policy default") and lines[0].endswith(
        f"document {digest}"
    )
    assert lines[1] == "changelog: checked releases 3, categories 3, entries 4, links 3"
    assert "  link [1.1.0] compares v1.0.0...v1.1.0" in lines
    assert "  link [1.0.0] release v1.0.0" in lines
    assert "changelog: unverified: remote link reachability, completeness of release notes" in lines
    assert "  CHANGELOG.md:5 date invalid calendar date 2026-02-30" in lines


# spec: PIPE-PAGES-R020.18
def test_changelog_cli(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert repo.run("changelog") == 0
    before = (tmp_path / "CHANGELOG.md").read_bytes()
    repo.stage({"CHANGELOG.md": VALID.replace("2026-02-01", "2026-13-01")})
    assert repo.run("changelog") == 1
    repo.write("CHANGELOG.md", VALID)  # an unstaged repair cannot hide the staged invalid text
    assert repo.run("changelog") == 1
    repo.stage({"CHANGELOG.md": VALID})
    assert repo.run("changelog") == 0
    repo.stage(
        {"CHANGELOG.md": VALID.replace("### Added\n\n- A feature.", "- Misplaced.\n\n### Added\n\n- A feature.")}
    )
    assert repo.run("changelog") == 1
    repo.stage({"CHANGELOG.md": VALID})
    repo.git("rm", "-q", "-f", "--", "CHANGELOG.md")
    assert repo.run("changelog") == 2
    first = _fresh(tmp_path, "fresh", {"CHANGELOG.md": ONLY_UNRELEASED})
    assert first.run("changelog") == 2
    first.commit(
        {
            "CHANGELOG.md": VALID.split("## [1.1.0]")[0]
            + "## [1.0.0] - 2026-01-01\n\n### Added\n\n- The first release.\n\n"
            f"[Unreleased]: {BASE}/compare/v1.0.0...HEAD\n[1.0.0]: {BASE}/releases/tag/v1.0.0\n"
        }
    )
    assert first.run("changelog") == 0
    assert (tmp_path / "fresh" / "CHANGELOG.md").read_bytes() != before
