"""Real pre-commit reporting and runner interruption contracts."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from pipelines_hooks.core.gitenv import sanitized_env
from tests.hooks.conftest import HOOK_REPOSITORY
from tests.hooks.test_validation import _process_exited, declaration


def _registration(source):
    path = HOOK_REPOSITORY / source
    document = yaml.safe_load(path.read_text())
    if isinstance(document, dict):
        document = [hook for group in document["repos"] for hook in group["hooks"]]
    return next(hook for hook in document if hook["id"] == "validate")


def _hook_entry(repo, outcome, evidence):
    setup = ""
    if outcome == "unavailable":
        setup = 'os.environ["PATH"] = ""; '
    if outcome == "timeout":
        slow = repo.write(
            "slow-tools/git", f"#!/bin/sh\nexec {shlex.quote(sys.executable)} -c 'import time; time.sleep(30)'\n"
        )
        slow.chmod(0o755)
        setup = f'os.environ["PATH"] = {str(slow.parent)!r} + os.pathsep + os.environ["PATH"]; '
    script = (
        "import os; "
        + setup
        + "from pipelines_hooks.validation.cli import main; "
        + f"raise SystemExit(main(['--evidence-dir', {str(evidence)!r}]))"
    )
    return shlex.join([sys.executable, "-c", script])


@pytest.mark.spec("PIPE-VALIDATION-R001.5")
@pytest.mark.parametrize("source", [".pre-commit-hooks.yaml", ".config/pre-commit.yaml"])
@pytest.mark.parametrize("outcome", ["fail", "unavailable", "timeout"])
def test_advisory_report_is_visible_through_pre_commit(repo, tmp_path, source, outcome):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    repo.write(
        ".config/validation.toml", declaration(required=False).replace("timeout_seconds = 3", "timeout_seconds = 1")
    )
    repo.write(".gitignore", "# missing required patterns\n")
    hook = _registration(source)
    # Use the existing interpreter without creating or installing a hook environment.
    hook.update(language="system", entry=_hook_entry(repo, outcome, evidence))
    repo.write("hooks.yaml", yaml.safe_dump({"repos": [{"repo": "local", "hooks": [hook]}]}))
    repo.git("add", "--", ".config/validation.toml", ".gitignore", "hooks.yaml")
    executable = shutil.which("pre-commit")
    command = [executable] if executable else [shutil.which("python3", path=os.defpath), "-m", "pre_commit"]
    env = sanitized_env()
    env["PYTHONPATH"] = str(HOOK_REPOSITORY)
    env["PRE_COMMIT_HOME"] = str(tmp_path / "pre-commit")
    result = subprocess.run(
        [*command, "run", "--config", "hooks.yaml", "--all-files", "--hook-stage", "manual"],
        cwd=repo.root,
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    (report_path,) = evidence.glob("pipelines-validation-*/report.json")
    report = json.loads(report_path.read_text())
    assert report["checks"][0]["outcome"] == outcome
    assert report["exit_code"] == 0
    assert f"ignore: {outcome} (advisory)" in result.stdout
    assert "Restore required ignore patterns" in result.stdout
    assert f"report: {report_path}" in result.stdout


def _await_file(path):
    deadline = time.monotonic() + 5
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert path.exists(), "worker did not publish its process identifiers"
    return json.loads(path.read_text())


def _kill_group(pid):
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError as exc:
        print(f"fixture process group already exited: {exc}")


def _assert_exited(pids):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if all(_process_exited(Path(f"/proc/{pid}/stat")) for pid in pids):
            return
        time.sleep(0.01)
    pytest.fail(f"runner interruption left running processes: {pids}")


@pytest.mark.spec("PIPE-VALIDATION-R001.4")
@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGINT])
def test_runner_signal_cleans_worker_group_and_keeps_signal_exit(tmp_path, signum):
    pids_path = tmp_path / "worker-pids.json"
    worker = (
        "import subprocess,sys,time,pathlib,json,os; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
        f"pathlib.Path({str(pids_path)!r}).write_text(json.dumps([os.getpid(),child.pid])); "
        "time.sleep(30)"
    )
    code = (
        "from pathlib import Path; import signal; "
        "from pipelines_hooks.validation.runner import execute; "
        "signal.signal(signal.SIGTERM, signal.SIG_DFL); "
        # CI launchers (nohup/background jobs) start us with SIGINT ignored, in which case
        # Python never installs its KeyboardInterrupt handler; make the precondition explicit.
        "signal.signal(signal.SIGINT, signal.default_int_handler); "
        f"execute({[sys.executable, '-c', worker]!r}, Path({str(tmp_path)!r}), "
        f"Path({str(tmp_path / 'worker.log')!r}), timeout=20)"
    )
    env = sanitized_env()
    env["PYTHONPATH"] = str(HOOK_REPOSITORY)
    pids = []
    with (tmp_path / "runner.log").open("w") as output:
        process = subprocess.Popen(
            [sys.executable, "-c", code], env=env, stdout=output, stderr=subprocess.STDOUT, start_new_session=True
        )
        try:
            pids = _await_file(pids_path)
            process.send_signal(signum)
            assert process.wait(timeout=5) == -signum
            _assert_exited(pids)
        finally:
            _kill_group(process.pid)
            if pids:
                _kill_group(pids[0])
            process.wait(timeout=5)


@pytest.mark.spec("PIPE-VALIDATION-R001.4")
@pytest.mark.parametrize("mode", ["ignored", "custom"])
def test_runner_preserves_existing_sigterm_policy(tmp_path, mode):
    worker = "import os,signal,time; os.kill(os.getppid(), signal.SIGTERM); time.sleep(0.1)"
    code = (
        "from pathlib import Path; import signal; "
        "from pipelines_hooks.validation.runner import execute; "
        "seen=[]; "
        f"handler = signal.SIG_IGN if {mode!r} == 'ignored' else lambda *_: seen.append(1); "
        "signal.signal(signal.SIGTERM, handler); "
        f"result=execute({[sys.executable, '-c', worker]!r}, Path({str(tmp_path)!r}), "
        f"Path({str(tmp_path / 'policy.log')!r}), timeout=2); "
        "assert result['outcome'] == 'pass'; "
        "assert signal.getsignal(signal.SIGTERM) == handler; "
        f"assert seen == {[] if mode == 'ignored' else [1]!r}"
    )
    env = sanitized_env()
    env["PYTHONPATH"] = str(HOOK_REPOSITORY)
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        text=True,
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stdout + result.stderr
