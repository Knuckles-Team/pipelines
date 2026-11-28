"""spec-trailers: the imported-history boundary (PIPE-CONNSPEC-R001.3)."""

from __future__ import annotations

import pytest

from pipelines_hooks.specs.imported_history import load_boundaries
from pipelines_hooks.core.errors import CannotRun
from tests.hooks.conftest import PYPROJECT, Repo
from tests.hooks.test_spec_trailers import _commit, _requirements_md

pytestmark = pytest.mark.spec("PIPE-CONNSPEC-R001.3")

_BINDING = '"""test"""\nimport pytest\n\n\n@pytest.mark.spec("DEMO-R001")\ndef test_feature():\n    assert True\n'
_SOURCE = "Example-Org/source-repo"


def _boundary_toml(merge: str, parent: str, source: str = _SOURCE) -> str:
    return (
        f"{PYPROJECT}\n[tool.pipelines_hooks.spec_trailers]\n"
        f'imported_history = [{{ merge = "{merge}", parent = "{parent}", source = "{source}" }}]\n'
    )


class Imported:
    """A fixture repo with a local row, an unrelated imported history, and the merge."""

    def __init__(self, repo: Repo) -> None:
        self.repo = repo
        self.base = repo.git("rev-parse", "HEAD").strip()
        _commit(
            repo,
            {"specs/demo/requirements.md": _requirements_md("DEMO-R001"), "tests/test_feature.py": _BINDING},
            "local row",
            trailer="DEMO-R001",
        )
        repo.git("checkout", "-q", "--orphan", "imported")
        repo.git("rm", "-rq", "-f", "--", ".")
        self.imported = [
            _commit(repo, {f"pkg/imported_{n}.py": f"VALUE = {n}\n"}, f"imported {n}", trailer=f"OLDREPO-R{n:03d}")
            for n in range(1, 4)
        ]
        repo.git("checkout", "-q", "main")
        repo.git(
            "merge", "-q", "--no-ff", "--allow-unrelated-histories", "-m",
            "Import history\n\nSpec: DEMO-R001", self.imported[-1],
        )  # fmt: skip
        self.merge = repo.git("rev-parse", "HEAD").strip()
        self.parent = self.imported[-1]

    def declare(self, merge: str | None = None, parent: str | None = None) -> str:
        return _commit(
            self.repo,
            {"pyproject.toml": _boundary_toml(merge or self.merge, parent or self.parent)},
            "declare the imported history",
            trailer="DEMO-R001",
        )


@pytest.fixture
def imported(repo: Repo) -> Imported:
    return Imported(repo)


def test_imported_commits_with_unknown_ids_are_excluded(imported: Imported, capsys: pytest.CaptureFixture[str]) -> None:
    imported.declare()
    assert imported.repo.run("spec-trailers", "--base-ref", imported.base) == 0
    out = capsys.readouterr().out
    assert f"3 commit(s) excluded, imported from {_SOURCE}" in out


def test_without_the_declaration_the_imported_unknown_ids_fail(
    imported: Imported, capsys: pytest.CaptureFixture[str]
) -> None:
    assert imported.repo.run("spec-trailers", "--base-ref", imported.base) == 1
    assert "OLDREPO-R001" in capsys.readouterr().out


def test_a_bad_local_commit_after_the_merge_still_fails(imported: Imported, capsys: pytest.CaptureFixture[str]) -> None:
    imported.declare()
    _commit(imported.repo, {"pkg/local.py": "VALUE = 1\n"}, "bad local", trailer="NOSUCH-R404")
    assert imported.repo.run("spec-trailers", "--base-ref", imported.base) == 1
    assert "NOSUCH-R404" in capsys.readouterr().out


def test_the_merge_commit_itself_is_still_checked(imported: Imported) -> None:
    imported.repo.git("commit", "-q", "--allow-empty", "--amend", "-m", "Import history\n\nSpec: NOSUCH-R404")
    merge = imported.repo.git("rev-parse", "HEAD").strip()
    imported.declare(merge=merge)
    assert imported.repo.run("spec-trailers", "--base-ref", imported.base) == 1


def test_an_unknown_merge_sha_is_refused(imported: Imported, capsys: pytest.CaptureFixture[str]) -> None:
    imported.declare(merge="1" * 40)
    assert imported.repo.run("spec-trailers", "--base-ref", imported.base) == 2
    assert "IMPORT_BOUNDARY_UNKNOWN" in capsys.readouterr().err


def test_an_unknown_parent_sha_is_refused(imported: Imported, capsys: pytest.CaptureFixture[str]) -> None:
    imported.declare(parent="2" * 40)
    assert imported.repo.run("spec-trailers", "--base-ref", imported.base) == 2
    assert "IMPORT_BOUNDARY_UNKNOWN" in capsys.readouterr().err


def test_a_sha_that_is_not_a_parent_of_the_merge_is_refused(
    imported: Imported, capsys: pytest.CaptureFixture[str]
) -> None:
    imported.declare(parent=imported.imported[0])
    assert imported.repo.run("spec-trailers", "--base-ref", imported.base) == 2
    assert "IMPORT_BOUNDARY_NOT_PARENT" in capsys.readouterr().err


def test_a_declared_commit_that_is_not_a_merge_is_refused(
    imported: Imported, capsys: pytest.CaptureFixture[str]
) -> None:
    imported.declare(merge=imported.base, parent=imported.parent)
    assert imported.repo.run("spec-trailers", "--base-ref", imported.base) == 2
    assert "IMPORT_BOUNDARY_NOT_MERGE" in capsys.readouterr().err


def test_the_first_parent_cannot_be_declared_imported(imported: Imported, capsys: pytest.CaptureFixture[str]) -> None:
    first = imported.repo.git("rev-parse", f"{imported.merge}^1").strip()
    imported.declare(parent=first)
    assert imported.repo.run("spec-trailers", "--base-ref", imported.base) == 2
    assert "IMPORT_BOUNDARY_NOT_IMPORTED" in capsys.readouterr().err


def test_a_related_parent_cannot_exempt_local_commits(repo: Repo) -> None:
    base = repo.git("rev-parse", "HEAD").strip()
    repo.git("checkout", "-q", "-b", "side")
    side = _commit(repo, {"pkg/side.py": "S = 1\n"}, "side", trailer="NOSUCH-R404")
    repo.git("checkout", "-q", "main")
    _commit(repo, {"pkg/main.py": "M = 1\n"}, "main work", trailer="NOSUCH-R404")
    repo.git("merge", "-q", "--no-ff", "-m", "merge side\n\nSpec: none (test)", side)
    merge = repo.git("rev-parse", "HEAD").strip()
    _commit(repo, {"pyproject.toml": _boundary_toml(merge, side)}, "declare", trailer="none (test)")
    with pytest.raises(CannotRun, match="IMPORT_BOUNDARY_NOT_IMPORTED"):
        load_boundaries(repo.root)
    assert repo.run("spec-trailers", "--base-ref", base) == 2


def test_a_malformed_entry_is_refused(imported: Imported) -> None:
    _commit(
        imported.repo,
        {
            "pyproject.toml": f'{PYPROJECT}\n[tool.pipelines_hooks.spec_trailers]\nimported_history = [{{ merge = "*", parent = "*", source = "x" }}]\n'
        },
        "wildcard",
        trailer="DEMO-R001",
    )
    with pytest.raises(CannotRun, match="IMPORT_BOUNDARY_INVALID"):
        load_boundaries(imported.repo.root)
