"""fast-tests: affected tests only, under a hard cap (PIPE-RELEASE-R007)."""

from __future__ import annotations

import pytest

from tests.hooks.conftest import Repo


def test_fast_tests_runs_only_the_affected_subset(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = repo.commit(
        {
            "pkg/mod_a.py": "VALUE = 1\n",
            "tests/test_a.py": "from pkg import mod_a\n\n\ndef test_a() -> None:\n    assert mod_a.VALUE == 2\n",
            "tests/test_other.py": "def test_other() -> None:\n    raise AssertionError('must not run')\n",
        },
        "baseline",
    )
    repo.commit({"pkg/mod_a.py": "VALUE = 2\n"}, "change")
    assert repo.run("fast-tests", "--base-ref", base, "--src-root", "pkg") == 0
    capsys.readouterr()
    repo.commit({"pkg/mod_a.py": "VALUE = 30\n"}, "break it")
    assert repo.run("fast-tests", "--base-ref", base, "--src-root", "pkg") == 1


def test_fast_tests_reports_no_affected_tests(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = repo.commit({"README.md": "x\n", "tests/test_x.py": "def test_x() -> None:\n    assert True\n"}, "baseline")
    repo.commit({"README.md": "y\n"}, "docs")
    assert repo.run("fast-tests", "--base-ref", base, "--src-root", "pkg") == 0
    assert "no affected tests" in capsys.readouterr().out


def test_fast_tests_timeout_fails_the_hook(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = repo.commit(
        {
            "pkg/slow.py": "VALUE = 1\n",
            "tests/test_slow.py": "import time\nfrom pkg import slow\n\n\ndef test_slow() -> None:\n    time.sleep(30)\n    assert slow.VALUE\n",
        },
        "baseline",
    )
    repo.commit({"pkg/slow.py": "VALUE = 2\n"}, "change")
    assert repo.run("fast-tests", "--base-ref", base, "--src-root", "pkg", "--timeout", "2") == 1
    assert "exceeded 2s" in capsys.readouterr().err
