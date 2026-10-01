"""scripts/write_github_env.sh imports a downloaded .env safely into GITHUB_ENV.

PIPE-RELEASE-R003: the release/deploy build job writes and sources
environment variables -- including compiler flags such as ``CFLAGS`` -- in a
properly quoted form so a multi-token value is never misinterpreted as a
shell command.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "write_github_env.sh"

ENV_FILE = (
    "CFLAGS=-O2 -march=native\n"
    "SIMPLE=value\n"
    "# a comment is ignored\n"
    "\n"
    'QUOTED=has "internal" quotes and $dollar and `backticks`\n'
)


def _run_sourced(tmp_path: Path, *, print_var: str, set_github_env: bool) -> tuple[subprocess.CompletedProcess, Path]:
    env_file = tmp_path / ".env"
    env_file.write_text(ENV_FILE, encoding="utf-8")
    github_env = tmp_path / "github_env.txt"
    github_env.write_text("", encoding="utf-8")
    environment = {"PATH": "/usr/bin:/bin"}
    if set_github_env:
        environment["GITHUB_ENV"] = str(github_env)
    command = f'source {SCRIPT} "$1" && printf %s "${print_var}"'
    result = subprocess.run(
        ["bash", "-c", command, "_", str(env_file)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result, github_env


def test_a_multi_token_value_is_exported_intact_not_run_as_a_command(tmp_path: Path) -> None:
    result, _ = _run_sourced(tmp_path, print_var="CFLAGS", set_github_env=True)
    assert result.returncode == 0, result.stderr
    assert "command not found" not in result.stderr
    assert result.stdout == "-O2 -march=native"


def test_unquoted_special_characters_are_not_expanded(tmp_path: Path) -> None:
    result, _ = _run_sourced(tmp_path, print_var="QUOTED", set_github_env=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == 'has "internal" quotes and $dollar and `backticks`'


def test_blank_lines_and_comments_are_skipped(tmp_path: Path) -> None:
    result, _ = _run_sourced(tmp_path, print_var="SIMPLE", set_github_env=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "value"


def test_github_env_receives_the_delimited_form_with_the_value_intact(tmp_path: Path) -> None:
    _, github_env = _run_sourced(tmp_path, print_var="CFLAGS", set_github_env=True)
    lines = github_env.read_text(encoding="utf-8").splitlines()
    opener = next(line for line in lines if line.startswith("CFLAGS<<"))
    delimiter = opener[len("CFLAGS<<"):]
    start = lines.index(opener)
    assert lines[start + 1] == "-O2 -march=native"
    assert lines[start + 2] == delimiter


def test_github_env_is_untouched_when_not_set(tmp_path: Path) -> None:
    result, github_env = _run_sourced(tmp_path, print_var="CFLAGS", set_github_env=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "-O2 -march=native"
    assert github_env.read_text(encoding="utf-8") == ""


def test_services_pipeline_workflow_sources_the_script() -> None:
    workflow = Path(__file__).resolve().parents[1] / ".github/workflows/services_pipeline.yml"
    text = workflow.read_text(encoding="utf-8")
    assert "source scripts/write_github_env.sh ./.env" in text
    assert "source ./.env" not in text.replace("source scripts/write_github_env.sh ./.env", "")
