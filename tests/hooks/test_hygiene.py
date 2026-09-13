"""root-hygiene, gitignore-convergence, sprawl, patch-safety and mermaid fire on planted violations."""

from __future__ import annotations

from pathlib import Path

from pipelines_hooks.hygiene.gitignore import REQUIRED
from tests.hooks.conftest import Repo

LAYOUT = (
    '[dirs]\npkg = "the package"\n".kiss" = "KISS thresholds"\n\n[files]\n"pyproject.toml" = "metadata"\n\n'
    '[dotfiles]\n".gitignore" = "git exclusions"\n'
)


def test_root_hygiene_fires_on_undeclared_and_stale_entries(repo: Repo) -> None:
    repo.commit({".repo-layout.toml": LAYOUT, ".gitignore": "x\n"})
    assert repo.run("root-hygiene") == 0
    repo.commit({"scratch.md": "notes\n"})
    assert repo.run("root-hygiene") == 1
    repo.git("rm", "-q", "scratch.md", ".gitignore")
    repo.git("commit", "-q", "-m", "drop")
    assert repo.run("root-hygiene") == 1


def test_gitignore_convergence_fires_on_a_missing_entry_and_tracked_output(repo: Repo) -> None:
    full = "\n".join(sorted(REQUIRED)) + "\n"
    repo.commit({".gitignore": full})
    assert repo.run("gitignore-convergence") == 0
    repo.commit({".gitignore": full.replace("scratch/\n", "")})
    assert repo.run("gitignore-convergence") == 1


def test_sprawl_fires_on_clones_artifacts_and_merge_markers_but_not_quoted_markers(repo: Repo) -> None:
    marker = "# --- Merged" + " from"
    repo.commit({"docs/gate.md": f"The gate rejects `{marker}` lines.\n"})
    assert repo.run("sprawl") == 0
    repo.commit({"pkg/merged.py": f"{marker} other branch\nVALUE = 1\n"})
    assert repo.run("sprawl") == 1
    repo.git("rm", "-q", "pkg/merged.py")
    repo.commit({"pkg/engine_old.py": "VALUE = 1\n"})
    assert repo.run("sprawl") == 1


def test_patch_safety_fires_while_a_parked_patch_holds_live_work(repo: Repo, tmp_path: Path) -> None:
    repo.write("pkg/__init__.py", '"""Fixture package, edited."""\n')
    patches = tmp_path / "cache"
    patches.mkdir()
    (patches / "patch1789000000-4242").write_text(repo.git("diff"), encoding="utf-8")
    repo.git("checkout", "--", "pkg/__init__.py")
    assert repo.run("pre-commit-patch-safety", "--patch-dir", str(patches)) == 1
    repo.git("apply", str(patches / "patch1789000000-4242"))
    assert repo.run("pre-commit-patch-safety", "--patch-dir", str(patches)) == 0


def test_mermaid_fires_on_an_unquoted_special_character_and_passes_a_quoted_label(repo: Repo) -> None:
    repo.commit({"docs/flow.md": "```mermaid\ngraph TD\n  A[\"load (cache)\"] --> B\n```\n"})
    assert repo.run("mermaid") == 0
    repo.commit({"docs/flow.md": "```mermaid\ngraph TD\n  A[load (cache)] --> B\n```\n"})
    assert repo.run("mermaid") == 1
