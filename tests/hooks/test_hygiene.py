"""root-hygiene, gitignore-convergence, sprawl, patch-safety and mermaid fire on planted violations."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.layout import RETIRED, located
from pipelines_hooks.hygiene.gitignore import REQUIRED
from tests.hooks.conftest import Repo

LAYOUT = (
    '[dirs]\npkg = "the package"\n".config" = "gate inputs"\n\n[files]\n"pyproject.toml" = "metadata"\n\n'
    '[dotfiles]\n".gitignore" = "git exclusions"\n'
)


def test_root_hygiene_fires_on_undeclared_and_stale_entries(repo: Repo) -> None:
    repo.commit({".config/repo-layout.toml": LAYOUT, ".gitignore": "x\n"})
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


def test_root_hygiene_refuses_a_manifest_left_at_the_retired_root_location(repo: Repo) -> None:
    repo.commit({".config/repo-layout.toml": LAYOUT, ".gitignore": "x\n"})
    assert repo.run("root-hygiene") == 0
    repo.commit({".repo-layout.toml": LAYOUT})
    assert repo.run("root-hygiene") == 2


def test_gitignore_convergence_fires_on_a_tracked_cache_at_any_depth(repo: Repo) -> None:
    repo.commit({"pkg/sub/__pycache__/mod.cpython-312.pyc": "x"})
    repo.commit({".gitignore": "\n".join(sorted(REQUIRED)) + "\n"})
    assert repo.run("gitignore-convergence") == 1
    repo.git("rm", "-q", "--cached", "pkg/sub/__pycache__/mod.cpython-312.pyc")
    repo.git("commit", "-q", "-m", "untrack")
    assert repo.run("gitignore-convergence") == 0


@pytest.mark.parametrize("canonical", sorted(RETIRED))
def test_every_gate_input_refuses_its_retired_root_copy(tmp_path: Path, canonical: str) -> None:
    assert located(tmp_path, canonical) == tmp_path / canonical
    retired = tmp_path / RETIRED[canonical]
    retired.parent.mkdir(parents=True, exist_ok=True)
    retired.write_text("x\n", encoding="utf-8")
    with pytest.raises(CannotRun, match=canonical):
        located(tmp_path, canonical)
