"""PIPE-GATES-R076: readme-deploy-block runs from a linked worktree and never skips."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from pipelines_hooks.core.gitenv import sanitized_env
from pipelines_hooks.core.settings import process_environment

BEGIN = "<!-- BEGIN GENERATED: additional-deployment-options -->"
END = "<!-- END GENERATED: additional-deployment-options -->"
GOOD = f"# Pkg\n\n{BEGIN}\n### Additional Deployment Options\n\nRun a pinned image.\n{END}\n"
BAD = f"# Pkg\n\n{BEGIN}\nrun registry.example.invalid/pkg:latest\n{END}\n"


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", *args],
        cwd=root,
        env=sanitized_env(),
        check=True,
        capture_output=True,
    )


def _hook(root: Path) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, "-m", "pipelines_hooks", "readme-deploy-block", "--root", str(root)],
        env=process_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout + result.stderr


def _repo(tmp_path: Path, readme: str) -> Path:
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q", "-b", "main")
    (main / "README.md").write_text(readme, encoding="utf-8")
    _git(main, "add", "--", "README.md")
    _git(main, "commit", "-q", "-m", "base")
    return main


# spec: PIPE-GATES-R076
def test_runs_its_check_from_a_linked_worktree(tmp_path: Path) -> None:
    main = _repo(tmp_path, GOOD)
    linked = tmp_path / "linked"
    _git(main, "worktree", "add", "-q", "-b", "topic", str(linked))
    assert (linked / ".git").is_file()  # a linked worktree: .git is a pointer file
    status, output = _hook(linked)
    assert status == 0 and "OK: one well-formed deployment block" in output
    (linked / "README.md").write_text(BAD, encoding="utf-8")
    status, output = _hook(linked)
    assert status == 1 and ":latest" in output


# spec: PIPE-GATES-R076
def test_a_missing_block_and_a_broken_marker_fail(tmp_path: Path) -> None:
    main = _repo(tmp_path, "# Pkg\n")
    assert _hook(main)[0] == 1
    (main / "README.md").write_text(f"{BEGIN}\nbody\n", encoding="utf-8")
    status, output = _hook(main)
    assert status == 1 and "exactly one" in output
    (main / "README.md").write_text(f"{END}\nbody\n{BEGIN}\n", encoding="utf-8")
    assert "ends before it begins" in _hook(main)[1]


# spec: PIPE-GATES-R076
def test_an_unresolvable_work_tree_root_is_cannot_run_not_a_skip(tmp_path: Path) -> None:
    outside = tmp_path / "not-a-repo"
    outside.mkdir()
    (outside / "README.md").write_text(GOOD, encoding="utf-8")
    status, output = _hook(outside)
    assert status == 2 and "CANNOT RUN" in output
