"""PIPE-GATES-R007: original marker semantics at the canonical shared entry."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from pipelines_hooks.cli import main
from pipelines_hooks.code.no_legacy_concepts import scan
from pipelines_hooks.core.gitenv import sanitized_env
from tests.hooks.conftest import HOOK_REPOSITORY, Repo

# Assemble legacy examples so this tracked test does not itself violate the gate.
MARKER = "CONCEPT:" + "AU-2"


# spec: PIPE-GATES-R007
@pytest.mark.parametrize("extension", ["py", "rs", "md"])
def test_detects_exact_pattern_and_location(repo: Repo, extension: str, capsys) -> None:
    repo.stage({f"pkg/source.{extension}": f"clean\n  {MARKER} old\n"})
    assert repo.run("no-legacy-concepts") == 1
    assert f"pkg/source.{extension}:2: {MARKER} old" in capsys.readouterr().out
    repo.write(f"pkg/source.{extension}", "CONCEPT:AU-OS.governance.current\n")
    assert repo.run("no-legacy-concepts") == 0


def test_exact_grammar_and_suffix(repo: Repo) -> None:
    repo.stage({"clean.md": "CONCEPT:au-2\nCONCEPT:AU_OS-2\nCONCEPT:AU-x\n", "data.txt": MARKER})
    assert scan(repo.root) == []
    repo.stage({"match.md": "embedded " + MARKER + "tail"})
    assert len(scan(repo.root)) == 1


@pytest.mark.parametrize(
    "name",
    ["check_no_legacy_markers.py", "CHANGELOG.md", "concept_map.md", "concepts.yaml", "concept_reservations.yaml"],
)
def test_preserves_historical_exclusions(repo: Repo, name: str) -> None:
    repo.stage({f"history/{name}": MARKER})
    assert scan(repo.root) == []
    repo.stage({"history/other.md": MARKER})
    assert len(scan(repo.root)) == 1


@pytest.mark.parametrize("directory", ["__pycache__", ".venv", "node_modules", "target", "build", "dist"])
def test_preserves_directory_exclusions(repo: Repo, directory: str) -> None:
    repo.write(f"{directory}/old.py", MARKER)
    repo.git("add", "-f", f"{directory}/old.py")
    assert scan(repo.root) == []


def test_uses_tracked_files_even_with_empty_matching_set(repo: Repo) -> None:
    repo.stage({".gitignore": "ignored/\n"})
    repo.write("ignored/stale.md", MARKER)
    repo.write("untracked.md", MARKER)
    assert scan(repo.root) == []
    repo.git("add", "-f", "ignored/stale.md")
    assert len(scan(repo.root)) == 1


# spec: PIPE-GATES-R007
def test_foreign_worktree_and_ambient_git_selectors(repo: Repo, tmp_path: Path, monkeypatch) -> None:
    worktree = tmp_path / "foreign"
    repo.git("worktree", "add", "-q", "-b", "foreign", str(worktree))
    foreign = Repo(worktree)
    foreign.stage({"foreign.md": MARKER})
    monkeypatch.setenv("GIT_DIR", str(repo.root / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(repo.root))
    monkeypatch.setenv("GIT_INDEX_FILE", str(repo.root / ".git/index"))
    monkeypatch.setenv("GIT_COMMON_DIR", str(repo.root / ".git"))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.bare")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "true")
    monkeypatch.chdir(repo.root)
    assert main(["no-legacy-concepts", str(worktree)]) == 1
    assert main(["no-legacy-concepts", str(repo.root)]) == 0


def test_subtree_relative_default_and_multiple_roots(repo: Repo, monkeypatch, capsys) -> None:
    repo.stage({"pkg/source.md": MARKER, "outside.md": MARKER})
    monkeypatch.chdir(repo.root / "pkg")
    assert main(["no-legacy-concepts"]) == 1
    output = capsys.readouterr().out
    assert "source.md:1:" in output and "outside.md" not in output
    assert main(["no-legacy-concepts", str(repo.root), str(repo.root / "pkg")]) == 1
    assert "3 legacy" in capsys.readouterr().out


def test_cli_process_exits_nonzero_for_findings(repo: Repo) -> None:
    repo.stage({"bad.md": MARKER})
    result = subprocess.run(
        [sys.executable, "-m", "pipelines_hooks.cli", "no-legacy-concepts", str(repo.root)],
        cwd=HOOK_REPOSITORY,
        env=sanitized_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "bad.md:1:" in result.stdout


# spec: PIPE-GATES-R007
def test_unreadable_or_non_repository_input_fails_closed(repo: Repo, tmp_path: Path) -> None:
    repo.stage({"bad.md": "clean"})
    (repo.root / "bad.md").write_bytes(b"\xff")
    assert repo.run("no-legacy-concepts") == 2
    assert main(["no-legacy-concepts", str(tmp_path / "absent")]) == 2


def test_deleted_tracked_file_is_not_a_survivor(repo: Repo) -> None:
    repo.stage({"gone.md": MARKER})
    (repo.root / "gone.md").unlink()
    assert scan(repo.root) == []


def test_tracked_helper_keeps_ambient_index_default(repo: Repo, tmp_path: Path, monkeypatch) -> None:
    from pipelines_hooks.core.tracked import tracked_paths

    alternate = tmp_path / "alternate-index"
    alternate.write_bytes((repo.root / ".git/index").read_bytes())
    repo.stage({"later.md": MARKER})
    monkeypatch.setenv("GIT_INDEX_FILE", str(alternate))
    assert "later.md" not in tracked_paths(repo.root)
    assert "later.md" in tracked_paths(repo.root, preserve_index=False)
    assert len(scan(repo.root)) == 1


def test_diagnostics_keep_original_output_limit(repo: Repo, capsys) -> None:
    repo.stage({"many.md": "\n".join([MARKER + " " + "x" * 120] * 61)})
    assert repo.run("no-legacy-concepts") == 1
    output = capsys.readouterr().out
    assert "61 legacy" in output
    assert "many.md:60:" in output and "many.md:61:" not in output
    assert "… and 1 more" in output
    assert "x" * 101 not in output
