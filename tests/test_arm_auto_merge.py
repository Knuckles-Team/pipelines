"""Owner-armed merges and releases (PIPE-GATES-R016.116, PIPE-RELEASE-R018) with a stub gh on PATH."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
REPO = "Knuckles-Team/demo"
SHA = "b" * 40

STUB = r"""#!/usr/bin/env bash
echo "$*" >> "$STUB_LOG"
a="$*"
case "$a" in
  "api repos/$STUB_REPO/rules/branches/main"*) [[ -n "${STUB_RULE:-}" ]] && echo "$STUB_RULE"; exit 0 ;;
  "api repos/$STUB_REPO/branches/main/protection"*) [[ -n "${STUB_CLASSIC:-}" ]] && echo "$STUB_CLASSIC"; exit 0 ;;
  "pr view"*) echo "$STUB_SHA"; exit 0 ;;
  "pr merge"*) exit 0 ;;
  "run list"*) echo "${STUB_RUN:-}"; exit 0 ;;
  "run view"*) echo "${STUB_JOBS:-0}"; exit 0 ;;
  "api repos/$STUB_REPO/git/matching-refs/tags/v"*) printf 'refs/tags/v1.2.3\nrefs/tags/v1.10.0\n'; exit 0 ;;
  "api repos/$STUB_REPO/contents/pyproject.toml"*) printf '[project]\nname = "demo"\nversion = "0.1.0"\n' | base64 -w0; exit 0 ;;
  "api repos/$STUB_REPO/git/ref/tags/"*) exit 1 ;;
esac
exit 0
"""


def _run(tmp_path: Path, script: str, *args: str, **env: str) -> tuple[subprocess.CompletedProcess, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(STUB)
    gh.chmod(0o755)
    log = tmp_path / "gh.log"
    log.write_text("")
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "STUB_LOG": str(log),
        "STUB_REPO": REPO,
        "STUB_SHA": SHA,
        **env,
    }
    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / script), *args], env=environment, capture_output=True, text=True, check=False
    )
    return result, log.read_text()


@pytest.mark.spec("PIPE-GATES-R016.116")
def test_arm_refuses_when_main_requires_no_ci_required_check(tmp_path: Path) -> None:
    result, log = _run(tmp_path, "arm_auto_merge.sh", REPO, "7", STUB_RULE="Other check")
    assert result.returncode == 2 and "refusing" in result.stderr
    assert "pr merge" not in log


@pytest.mark.spec("PIPE-GATES-R016.116")
def test_arm_arms_with_match_head_commit_from_rules_or_classic_protection(tmp_path: Path) -> None:
    for env in ({"STUB_RULE": "CI required"}, {"STUB_CLASSIC": "CI required"}):
        result, log = _run(tmp_path, "arm_auto_merge.sh", REPO, "7", **env)
        assert result.returncode == 0, result.stderr
        assert f"pr merge 7 -R {REPO} --auto --merge --match-head-commit {SHA}" in log


@pytest.mark.spec("PIPE-RELEASE-R018")
def test_release_refuses_on_a_red_main(tmp_path: Path) -> None:
    result, log = _run(tmp_path, "release_connector.sh", REPO, "patch", STUB_RUN="123", STUB_JOBS="0")
    assert result.returncode == 2 and "refusing" in result.stderr
    assert "pr create" not in log and "git/refs" not in log


@pytest.mark.spec("PIPE-RELEASE-R018")
def test_release_dry_run_computes_the_next_version_from_the_latest_tag(tmp_path: Path) -> None:
    result, log = _run(tmp_path, "release_connector.sh", "--dry-run", REPO, "minor", STUB_RUN="123", STUB_JOBS="1")
    assert result.returncode == 0, result.stderr
    assert "1.10.0 -> 1.11.0" in result.stdout and "dry run" in result.stdout
    assert "pr create" not in log and "-X POST" not in log


@pytest.mark.spec("PIPE-RELEASE-R018")
def test_scripts_carry_no_token_and_workflows_hold_no_merge_machinery() -> None:
    for name in ("arm_auto_merge.sh", "release_connector.sh"):
        text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "GIT_TOKEN" not in text and "x-access-token" not in text
    release = (ROOT / "scripts/release_connector.sh").read_text(encoding="utf-8")
    assert "Spec: none (release)" in release and "Co-Authored-By: Claude Sonnet 5.5" in release
    assert "arm_auto_merge.sh" in release and "git/tags" in release and "git/refs" in release
    for gone in (
        ".github/workflows/auto_merge_pipeline.yml",
        ".github/workflows/auto_merge.yml",
        "templates/workflows/auto_merge.yml",
        "scripts/auto_merge.py",
    ):
        assert not (ROOT / gone).exists()
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        assert "GIT_TOKEN" not in path.read_text(encoding="utf-8"), path
    settings = (ROOT / "scripts/apply_repo_ci_settings.sh").read_text(encoding="utf-8")
    assert "allow_auto_merge=true" in settings
    assert yaml.safe_load((ROOT / "templates/workflows/connector.yml").read_text(encoding="utf-8"))


@pytest.mark.spec("PIPE-GATES-R016.116")
def test_settings_script_refuses_without_a_green_check_and_has_dry_run(tmp_path: Path) -> None:
    result, log = _run(tmp_path, "apply_repo_ci_settings.sh", "--dry-run", REPO)
    assert result.returncode == 2 and "refusing" in result.stderr
    assert "--dry-run" in (ROOT / "scripts/apply_repo_ci_settings.sh").read_text(encoding="utf-8")
