"""Real dispatch and Git-event acceptance for the shared validation command."""

from __future__ import annotations

import errno
import json
import os
import shlex
import sys
import time
from pathlib import Path

import pytest

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.hygiene.gitignore import REQUIRED
from pipelines_hooks.validation import cli, policy, runner
from pipelines_hooks.validation.runner import execute
from tests.hooks.conftest import HOOK_REPOSITORY


def declaration(*, required=True, gate="gitignore-convergence", identifier="ignore"):
    return (
        "version = 1\nbudget_seconds = 5\n[[checks]]\n"
        f'id = "{identifier}"\ngroup = "repository"\ngate = "{gate}"\n'
        f"required = {str(required).lower()}\ntimeout_seconds = 3\n"
        'acceptance = ["AU ignore patterns", "tracked build families"]\n'
        'remedy = "Restore required ignore patterns and remove tracked build output"\n'
    )


@pytest.fixture
def validation_repo(repo, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(HOOK_REPOSITORY))
    repo.write(".config/validation.toml", declaration())
    repo.write(".gitignore", "\n".join(sorted(REQUIRED)) + "\n")
    repo.git("add", "--", ".gitignore", ".config/validation.toml")
    return repo


@pytest.mark.spec("PIPE-VALIDATION-R001.1")
def test_policy_accepts_repository_group(validation_repo):
    result = policy.load(validation_repo.root / ".config/validation.toml")
    assert result.checks[0].gate == "gitignore-convergence"
    assert result.checks[0].required


@pytest.mark.spec("PIPE-VALIDATION-R001.1")
@pytest.mark.parametrize(
    "change",
    [
        lambda value: value + '\nunknown = "typo"\n',
        lambda value: value.replace(
            '"gitignore-convergence"', '"dependency-readiness"'
        ),
        lambda value: value.replace("budget_seconds = 5", "budget_seconds = 0"),
        lambda value: value.replace("timeout_seconds = 3", "timeout_seconds = true"),
        lambda value: value.replace("required = true", 'required = "yes"'),
        lambda value: value.replace(
            '["AU ignore patterns", "tracked build families"]', "[]"
        ),
        lambda value: value + "\n[[checks]]\n" + value.split("[[checks]]\n")[1],
        lambda value: (
            value
            + "\n[[checks]]\n"
            + value.split("[[checks]]\n")[1].replace('id = "ignore"', 'id = "second"')
        ),
    ],
)
def test_policy_refuses_ambiguous_checks(validation_repo, change):
    path = validation_repo.write(".config/validation.toml", change(declaration()))
    with pytest.raises(CannotRun):
        policy.load(path)


@pytest.mark.spec("PIPE-VALIDATION-R001.3")
@pytest.mark.parametrize("required, expected", [(True, 1), (False, 0)])
def test_required_and_advisory_outcomes(validation_repo, tmp_path, required, expected):
    validation_repo.write(".config/validation.toml", declaration(required=required))
    validation_repo.write(".gitignore", "# missing patterns\n")
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    report = runner.run(
        policy.load(validation_repo.root / ".config/validation.toml"),
        validation_repo.root,
        evidence,
    )
    assert report["exit_code"] == expected
    assert report["checks"][0]["outcome"] == "fail"
    assert "Missing from .gitignore" in Path(report["checks"][0]["log"]).read_text()


@pytest.mark.spec("PIPE-VALIDATION-R001.3")
def test_missing_git_is_unavailable(validation_repo, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "")
    report = runner.run(
        policy.load(validation_repo.root / ".config/validation.toml"),
        validation_repo.root,
        tmp_path,
    )
    assert report["exit_code"] == 2
    assert report["checks"][0]["outcome"] == "unavailable"
    assert "provision Git explicitly" in Path(report["checks"][0]["log"]).read_text()


@pytest.mark.spec("PIPE-VALIDATION-R001.5")
@pytest.mark.parametrize("bad, expected", [(False, 0), (True, 1)])
def test_summary_matches_evidence(validation_repo, tmp_path, capsys, bad, expected):
    if bad:
        validation_repo.write(".gitignore", "")
    result = cli.main(
        ["--root", str(validation_repo.root), "--evidence-dir", str(tmp_path)]
    )
    assert result == expected
    (report_path,) = tmp_path.glob("pipelines-validation-*/report.json")
    report = json.loads(report_path.read_text())
    assert report["exit_code"] == result
    assert report["checks"][0]["acceptance"] == [
        "AU ignore patterns",
        "tracked build families",
    ]
    output = capsys.readouterr().out
    assert str(report_path) in output and "repository: 1 checks" in output
    if bad:
        assert (
            "ignore: fail (required)" in output and "Restore required ignore" in output
        )


@pytest.mark.spec("PIPE-VALIDATION-R001.2")
@pytest.mark.parametrize("event", ["post-merge", "post-checkout", "post-rewrite"])
def test_passive_git_event_does_not_dispatch(repo, monkeypatch, event):
    monkeypatch.setenv("PYTHONPATH", str(HOOK_REPOSITORY))
    sentinels = repo.root / "sentinels"
    sentinels.mkdir()
    marker = repo.root / "unexpected-setup"
    for name in ("uv", "pip", "pip3", "curl", "wget"):
        tool = sentinels / name
        tool.write_text(
            f"#!/bin/sh\nprintf invoked >> {shlex.quote(str(marker))}\nexit 93\n"
        )
        tool.chmod(0o755)
    monkeypatch.setenv("PATH", f"{sentinels}:{os.environ['PATH']}")
    # Invalid policy proves passive handling occurs before policy evaluation.
    repo.write(".config/validation.toml", "this is not TOML")
    hook = repo.root / ".git" / "hooks" / event
    command = shlex.join(
        [sys.executable, "-m", "pipelines_hooks", "validate", "--event", event]
    )
    hook.write_text(f"#!/bin/sh\nexec {command}\n")
    hook.chmod(0o755)
    repo.git("checkout", "-qb", "incoming")
    repo.commit({"incoming.txt": "change\n"})
    repo.git("checkout", "main")
    repo.stage({"user.txt": "staged user work\n"})
    repo.write("user.txt", "unstaged user work\n")
    before = repo.git("diff", "--cached", "--binary")
    repo.git("-c", "pull.rebase=false", "pull", "--ff-only", ".", "incoming")
    assert repo.git("diff", "--cached", "--binary") == before
    assert (repo.root / "user.txt").read_text() == "unstaged user work\n"
    # Execute all passive event paths even when Git did not emit that event.
    output = repo.git("-c", f"alias.passive=!{command}", "passive")
    assert json.loads(output)["state"] == "inactive"
    assert not marker.exists()


def _process_exited(status):
    """A reaped process may disappear while procfs status is being read."""
    try:
        return status.read_text().split()[2] == "Z"
    except OSError as exc:
        if exc.errno in (errno.ENOENT, errno.ESRCH):
            return True
        raise


@pytest.mark.parametrize("number", [errno.ENOENT, errno.ESRCH])
def test_reaped_process_is_an_exited_child(number):
    class Reaped:
        def read_text(self):
            raise OSError(number, "child already reaped")

    assert _process_exited(Reaped())


def test_child_status_permission_failure_is_not_success():
    class Inaccessible:
        def read_text(self):
            raise PermissionError(errno.EACCES, "status denied")

    with pytest.raises(PermissionError, match="status denied"):
        _process_exited(Inaccessible())


@pytest.mark.spec("PIPE-VALIDATION-R001.4")
def test_deadline_terminates_child_process(tmp_path):
    child_file = tmp_path / "child"
    child = "import time; time.sleep(30)"
    code = (
        "import subprocess,sys,time,pathlib; "
        f"p=subprocess.Popen([sys.executable,'-c',{child!r}]); "
        f"pathlib.Path({str(child_file)!r}).write_text(str(p.pid)); time.sleep(30)"
    )
    result = execute(
        [sys.executable, "-c", code], tmp_path, tmp_path / "timeout.log", timeout=0.5
    )
    assert result["outcome"] == "timeout" and result["seconds"] < 3
    pid = int(child_file.read_text())
    status = Path(f"/proc/{pid}/stat")
    for _ in range(20):
        if _process_exited(status):
            break
        time.sleep(0.01)
    else:
        pytest.fail("timed-out worker left a running child")


@pytest.mark.spec("PIPE-VALIDATION-R001.4")
def test_run_budget_marks_remaining_checks(validation_repo, tmp_path, monkeypatch):
    # The actual process deadline is covered above; force clock advancement at dispatch.
    ticks = iter([0.0, 6.0, 6.0])
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(ticks))
    report = runner.run(
        policy.load(validation_repo.root / ".config/validation.toml"),
        validation_repo.root,
        tmp_path,
    )
    assert report["checks"][0]["outcome"] == "timeout"
    assert report["exit_code"] == 2
