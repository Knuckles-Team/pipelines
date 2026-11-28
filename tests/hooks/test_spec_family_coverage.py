"""spec-family-coverage: a spec directory with rows needs a node of its own repository in the model."""

from __future__ import annotations

import pytest

from pipelines_hooks.specs import family_coverage
from pipelines_hooks.specs.family_coverage import ModelUnavailable
from tests.hooks.conftest import Repo

ROW = "| `ALPHA-WIDGETS-R001` | **Widgets.** A widget exists. | Test: `tests/test_widgets.py`. |\n"
HEADER = "| ID | Requirement | Verification |\n| --- | --- | --- |\n"


def _node(node_id: str, fam: list[str], repo: str | None = None, children: list[dict] | None = None) -> dict:
    node: dict = {"id": node_id, "fam": fam, "children": children or []}
    if repo:
        node["repo"] = repo
    return node


#: ``beta`` also owns a family called ``widgets``; that must never count for ``alpha``.
MODEL = {
    "id": "root",
    "children": [
        _node("a", ["gadgets"], "alpha", [_node("a.child", ["parts"])]),
        _node("b", ["widgets", "gadgets"], "beta"),
        _node("c", ["NEW-things"], "gamma"),
        _node("d", ["*"], "delta"),
        {**_node("ext", ["externals"], "alpha"), "external": True},
    ],
}
REGISTRY = {"repositories": [{"name": "alpha", "slug": "alpha"}, {"name": "beta", "slug": "beta"}]}


def _repo(repo: Repo, slug: str, dirs: dict[str, str | None], aliases: str = "") -> Repo:
    files = {
        "pyproject.toml": f'[project]\nname = "x"\nversion = "0"\n\n[tool.pipelines_hooks.public_surface]\nrepository = "{slug}"\n'
    }
    for name, rows in dirs.items():
        files[f"specs/{name}/requirements.md"] = HEADER + (rows or "")
    if aliases:
        files[".config/spec-aliases.toml"] = aliases
    repo.commit(files)
    return repo


def _fetch(url: str) -> dict:
    return MODEL if url == family_coverage.MODEL_URL else REGISTRY


def _run(repo: Repo, fetch=_fetch) -> int:
    return family_coverage.main(["--root", str(repo.root)], fetch=fetch)


@pytest.mark.spec("PIPE-GATES-R061.1")
def test_a_mapped_family_passes(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    _repo(repo, "alpha", {"gadgets": ROW, "parts": ROW})
    assert _run(repo) == 0
    assert "SPEC_FAMILY_UNMAPPED" not in capsys.readouterr().out


@pytest.mark.spec("PIPE-GATES-R061.1")
def test_an_unmapped_family_fails_with_the_exact_message(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    _repo(repo, "alpha", {"gadgets": ROW, "fresh-family": ROW})
    assert _run(repo) == 1
    assert (
        "SPEC_FAMILY_UNMAPPED alpha:fresh-family — add fam to a node in pipelines "
        "scripts/architecture_explorer/model.json" in capsys.readouterr().out
    )


@pytest.mark.spec("PIPE-GATES-R061.1")
def test_another_repositorys_fam_of_the_same_name_does_not_count(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    _repo(repo, "alpha", {"widgets": ROW})
    assert _run(repo) == 1
    assert "SPEC_FAMILY_UNMAPPED alpha:widgets" in capsys.readouterr().out


@pytest.mark.spec("PIPE-GATES-R061.1")
def test_an_external_node_does_not_own_a_family(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    _repo(repo, "alpha", {"externals": ROW})
    assert _run(repo) == 1
    assert "SPEC_FAMILY_UNMAPPED alpha:externals" in capsys.readouterr().out


@pytest.mark.spec("PIPE-GATES-R061.1")
def test_a_prefix_alias_resolves_to_the_canonical_family(repo: Repo) -> None:
    aliases = '"OLD-" = "NEW-"\n'
    _repo(repo, "gamma", {"OLD-things": ROW}, aliases)
    assert _run(repo) == 0


@pytest.mark.spec("PIPE-GATES-R061.1")
def test_a_wildcard_node_owns_every_family_of_its_repository(repo: Repo) -> None:
    _repo(repo, "delta", {"anything": ROW})
    assert _run(repo) == 0


@pytest.mark.spec("PIPE-GATES-R061.1")
def test_a_directory_without_rows_is_not_a_family(repo: Repo) -> None:
    _repo(repo, "alpha", {"gadgets": ROW, "empty-one": None})
    assert _run(repo) == 0


@pytest.mark.spec("PIPE-GATES-R061.1")
def test_the_registry_name_keys_the_repository(repo: Repo) -> None:
    registry = {"repositories": [{"name": "alpha", "slug": "alpha-repo"}]}
    assert family_coverage.explorer_name("alpha-repo", registry) == "alpha"
    assert family_coverage.explorer_name("unlisted", registry) == "unlisted"


def _down(url: str) -> dict:
    raise ModelUnavailable(f"{url}: network is down")


@pytest.mark.spec("PIPE-GATES-R061.2")
def test_network_down_fails_closed_in_github_actions(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    _repo(repo, "alpha", {"gadgets": ROW})
    assert _run(repo, _down) == 1
    assert "failing closed" in capsys.readouterr().out


@pytest.mark.spec("PIPE-GATES-R061.2")
def test_network_down_warns_once_and_passes_locally(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    _repo(repo, "alpha", {"gadgets": ROW})
    assert _run(repo, _down) == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 1 and "WARNING" in lines[0]


@pytest.mark.spec("PIPE-GATES-R061.2")
def test_no_spec_directory_needs_no_network(repo: Repo) -> None:
    _repo(repo, "alpha", {})
    assert _run(repo, _down) == 0


@pytest.mark.spec("PIPE-GATES-R061.1")
def test_the_pipelines_working_tree_model_is_used_without_the_network() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    assert family_coverage.main(["--root", str(root)], fetch=_down) == 0
