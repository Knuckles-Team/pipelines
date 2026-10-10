"""pr-test-scope: an unmapped source change narrows via the import graph, not FULL."""

from __future__ import annotations

import pytest

from tests.hooks.conftest import Repo


def test_unmapped_module_selects_only_its_importers(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = repo.commit(
        {
            "pkg/mod_a.py": "def helper() -> int:\n    return 1\n",
            "tests/test_importer.py": "from pkg import mod_a\n\n\ndef test_helper() -> None:\n    assert mod_a.helper() == 1\n",
            "tests/test_unrelated.py": "def test_noop() -> None:\n    assert True\n",
        },
        "baseline",
    )
    repo.commit({"pkg/mod_a.py": "def helper() -> int:\n    return 2\n"}, "change mod_a")

    assert repo.run("pr-test-scope", "--base-ref", base, "--src-root", "pkg", "--tests-root", "tests") == 0
    out = capsys.readouterr().out.splitlines()

    # pkg/mod_a.py has no mirrored tests/test_mod_a.py, so this exercises the
    # import-graph fallback: only the test that actually imports pkg.mod_a is
    # selected, not the full suite and not the unrelated test file.
    assert out == ["tests/test_importer.py"]


def test_unmapped_module_with_no_importers_selects_nothing(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = repo.commit(
        {
            "pkg/orphan.py": "def helper() -> int:\n    return 1\n",
            "tests/test_unrelated.py": "def test_noop() -> None:\n    assert True\n",
        },
        "baseline",
    )
    repo.commit({"pkg/orphan.py": "def helper() -> int:\n    return 2\n"}, "change orphan")

    assert repo.run("pr-test-scope", "--base-ref", base, "--src-root", "pkg", "--tests-root", "tests") == 0
    out = capsys.readouterr().out.splitlines()

    # Nothing imports pkg.orphan: the gate trusts the graph (NONE) rather
    # than forcing FULL, since this is not an unreadable diff.
    assert out == ["NONE"]


def test_conftest_change_still_forces_full_suite(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = repo.commit(
        {
            "pkg/mod_a.py": "def helper() -> int:\n    return 1\n",
            "tests/test_importer.py": "from pkg import mod_a\n\n\ndef test_helper() -> None:\n    assert mod_a.helper() == 1\n",
            "tests/conftest.py": "import pytest\n",
        },
        "baseline",
    )
    repo.commit({"tests/conftest.py": "import pytest\n\n\ndef pytest_configure(config):\n    pass\n"}, "change conftest")

    assert repo.run("pr-test-scope", "--base-ref", base, "--src-root", "pkg", "--tests-root", "tests") == 0
    out = capsys.readouterr().out.splitlines()

    assert out == ["FULL"]
