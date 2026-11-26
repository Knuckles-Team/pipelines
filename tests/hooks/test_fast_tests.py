"""fast-tests: affected tests only, under a hard cap (PIPE-RELEASE-R007)."""

from __future__ import annotations

import pytest

from tests.hooks.conftest import Repo


# spec: PIPE-RELEASE-R007.6
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


# spec: PIPE-RELEASE-R007.5
def test_fast_tests_reports_no_affected_tests(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = repo.commit({"README.md": "x\n", "tests/test_x.py": "def test_x() -> None:\n    assert True\n"}, "baseline")
    repo.commit({"README.md": "y\n"}, "docs")
    assert repo.run("fast-tests", "--base-ref", base, "--src-root", "pkg") == 0
    assert "no affected tests" in capsys.readouterr().out


# spec: PIPE-RELEASE-R007.5
def test_fast_tests_reports_full_suite_ownership(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = repo.git("rev-parse", "HEAD").strip()
    repo.commit(
        {"pyproject.toml": '[project]\nname = "fixture"\nversion = "0"\n\n# shared config change\n'},
        "config",
    )
    assert repo.run("fast-tests", "--base-ref", base, "--src-root", "pkg") == 0
    assert "main CI" in capsys.readouterr().out


# spec: PIPE-RELEASE-R007.4
def test_fast_tests_rejects_a_non_positive_timeout(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    base = repo.commit({"README.md": "x\n"}, "baseline")
    repo.commit({"README.md": "y\n"}, "docs")
    assert repo.run("fast-tests", "--base-ref", base, "--src-root", "pkg", "--timeout", "0") == 2
    assert "positive" in capsys.readouterr().err


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


# spec: PIPE-GATES-R065
def test_a_run_with_zero_suites_fails(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    from pipelines_hooks.ci_replica.fast_tests import require_suites

    assert require_suites(["pytest", "-q"], 0, 0) == 1
    assert require_suites(["pytest", "-q"], 5, None) == 1
    base = repo.commit(
        {"pkg/mod.py": "VALUE = 1\n", "tests/test_mod.py": "from pkg import mod\n\nHELPER = mod.VALUE\n"}, "baseline"
    )
    repo.commit({"pkg/mod.py": "VALUE = 2\n"}, "change")
    assert repo.run("fast-tests", "--base-ref", base, "--src-root", "pkg") == 1
    assert "no test suites ran" in capsys.readouterr().err


# spec: PIPE-GATES-R065
def test_a_run_with_one_suite_passes() -> None:
    from pipelines_hooks.ci_replica.fast_tests import require_suites

    assert require_suites(["pytest"], 0, 1) == 0
    assert require_suites(["pytest"], 1, 3) == 1
    assert require_suites(["pytest"], 0, None) == 0


# spec: PIPE-GATES-R065
def test_the_failure_names_the_command(capsys: pytest.CaptureFixture[str]) -> None:
    from pipelines_hooks.ci_replica.fast_tests import require_suites

    assert require_suites(["uv", "run", "pytest", "tests/test_x.py"], 0, 0) == 1
    assert "uv run pytest tests/test_x.py" in capsys.readouterr().err
