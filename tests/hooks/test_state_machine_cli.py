"""PIPE-GATES-R086.5 and R086.7: the two hooks, their modes, exit codes and policy."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pipelines_hooks import cli
from pipelines_hooks.code import state_machine
from tests.hooks.state_machine_repo import fixture_repo, git

REPO = Path(__file__).resolve().parents[2]


def _run(root: Path, *args: str) -> int:
    return state_machine.main(["--root", str(root), *args])


@pytest.mark.spec("PIPE-GATES-R086.5")
def test_staged_mode_reports_only_types_touched_by_staged_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = fixture_repo(tmp_path, "py/two_assigners")
    monkeypatch.delenv("PRE_COMMIT_FROM_REF", raising=False)
    assert _run(root) == 0
    assert "SM-" not in capsys.readouterr().out
    (root / "pkg/job.py").write_text((root / "pkg/job.py").read_text() + "\n", encoding="utf-8")
    git(root, "add", "pkg/job.py")
    assert _run(root) == 1
    assert "pkg/job.py" in capsys.readouterr().out


@pytest.mark.spec("PIPE-GATES-R086.5")
def test_census_mode_reports_the_whole_tree_with_no_baseline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = fixture_repo(tmp_path, "py/two_assigners")
    assert cli.main(["state-machine-census", "--root", str(root)]) == 1
    out = capsys.readouterr().out
    assert "pkg/job.py" in out and "SM-MULTI-ASSIGN" in out
    assert not any(name for name in ("baseline", "allow") if name in state_machine._load_policy(root).__dict__)


@pytest.mark.spec("PIPE-GATES-R086.5")
def test_exit_codes_are_zero_one_and_two(tmp_path: Path) -> None:
    assert cli.main(["state-machine-census", "--root", str(fixture_repo(tmp_path / "a", "py/compliant"))]) == 0
    assert cli.main(["state-machine-census", "--root", str(fixture_repo(tmp_path / "b", "py/two_assigners"))]) == 1
    broken = fixture_repo(tmp_path / "c", "py/compliant")
    (broken / "pkg/job.py").write_text("class Job(:\n", encoding="utf-8")
    assert cli.main(["state-machine-census", "--root", str(broken)]) == 2


@pytest.mark.spec("PIPE-GATES-R086.5")
def test_an_unparseable_rust_file_stops_only_a_change_that_touches_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = fixture_repo(tmp_path, "rs/two_assigners")
    job = root / "src/job.rs"
    # A grammar gap: an attribute on a struct-pattern field parses for rustc, not for the grammar.
    job.write_text(
        job.read_text(encoding="utf-8")
        + '\npub fn fields(job: Job) {\n    let Job {\n        #[cfg(feature = "x")]\n        status,\n    } = job;\n}\n',
        encoding="utf-8",
    )
    git(root, "commit", "-q", "-am", "grammar gap")
    monkeypatch.delenv("PRE_COMMIT_FROM_REF", raising=False)
    assert cli.main(["state-machine-census", "--root", str(root)]) == 1
    out = capsys.readouterr().out
    assert "SM-MULTI-ASSIGN" in out
    assert "src/job.rs: partial parse" in out and "1 partially parsed file(s)" in out
    job.write_text(job.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    git(root, "add", "src/job.rs")
    assert cli.main(["state-machine-shape", "--root", str(root)]) == 2


@pytest.mark.spec("PIPE-GATES-R086.5")
def test_a_finding_line_names_file_line_type_code_and_rule(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = fixture_repo(tmp_path, "rs/lifecycle_flags")
    assert _run(root, "--census") == 1
    (line,) = [line for line in capsys.readouterr().out.splitlines() if "SM-" in line]
    assert line.startswith("src/job.rs:17 Job SM-LIFECYCLE-FLAGS rule 3")


@pytest.mark.spec("PIPE-GATES-R086.5")
def test_both_hooks_are_registered_in_the_cli_and_the_hook_file() -> None:
    assert cli.GATES["state-machine-shape"] == "pipelines_hooks.code.state_machine"
    assert cli.GATES["state-machine-census"] == "pipelines_hooks.code.state_machine_census"
    hooks = {hook["id"]: hook for hook in yaml.safe_load((REPO / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))}
    ids = list(hooks)
    assert ids.index("state-machine-shape") == ids.index("no-stub") + 1
    assert hooks["state-machine-shape"]["stages"] == ["pre-commit", "pre-push"]
    assert hooks["state-machine-census"]["stages"] == ["manual"]


@pytest.mark.spec("PIPE-GATES-R086.5")
def test_the_gate_set_check_lists_both_hooks() -> None:
    standard = (REPO / "reference/gate-standard.md").read_text(encoding="utf-8")
    (line,) = [line for line in standard.splitlines() if line.startswith("- Code shape:")]
    assert "`state-machine-shape`" in line and "`state-machine-census`" in line


@pytest.mark.spec("PIPE-GATES-R086.7")
def test_missing_policy_table_exits_two_with_declares_no_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = fixture_repo(tmp_path, "py/compliant", policy=False)
    assert cli.main(["state-machine-census", "--root", str(root)]) == 2
    assert "declares no paths" in capsys.readouterr().err


@pytest.mark.spec("PIPE-GATES-R086.7")
def test_staged_mode_prints_findings_and_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = fixture_repo(tmp_path, "py/two_assigners", mode="staged")
    assert _run(root, "--census") == 0
    assert "SM-MULTI-ASSIGN" in capsys.readouterr().out


@pytest.mark.spec("PIPE-GATES-R086.7")
def test_blocking_mode_exits_one_on_a_finding(tmp_path: Path) -> None:
    assert _run(fixture_repo(tmp_path, "rs/two_assigners", mode="blocking"), "--census") == 1


@pytest.mark.spec("PIPE-GATES-R086.7")
def test_exclude_globs_skip_fixture_and_test_sources(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = fixture_repo(tmp_path, "py/two_assigners", extra='exclude = ["pkg/job.py"]\nlanguages = ["python"]\n')
    assert _run(root, "--census") == 0
    assert "SM-" not in capsys.readouterr().out
    rust_only = fixture_repo(tmp_path / "rs", "py/two_assigners", extra='languages = ["rust"]\n')
    assert _run(rust_only, "--census") == 0
