"""The advisory workflow keys its scanner cache on every provisioning input and stays advisory."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = yaml.safe_load((REPO / ".github/workflows/advisory_pipeline.yml").read_text())
STEPS = WORKFLOW["jobs"]["advisory"]["steps"]
KEYED_INPUTS = (
    "scripts/install_scanners.sh",
    "scripts/install_jscpd.py",
    "scripts/patches/jscpd-markdown-glob.patch",
    "pipelines_hooks/core/jscpd_build.py",
)


def _step(name: str) -> dict:
    return next(item for item in STEPS if item["name"] == name)


def test_cache_identity_covers_every_provisioning_input() -> None:
    fetch = _step("Fetch the pipelines revision of this workflow")
    assert all(path in fetch["run"] for path in KEYED_INPUTS)
    assert "SCANNER_ROOT=$RUNNER_TEMP/pipelines-scanners" in fetch["run"]
    restore = next(item for item in STEPS if item.get("id") == "scanner-cache")
    save = _step("Save pinned scanner toolchain")
    assert restore["with"]["path"] == save["with"]["path"] == "${{ env.SCANNER_ROOT }}"
    assert restore["with"]["key"] == "pipelines-scanners-${{ runner.os }}-${{ runner.arch }}-${{ env.SCANNER_KEY }}"
    assert save["with"]["key"] == "${{ steps.scanner-cache.outputs.cache-primary-key }}"


def test_cache_hits_still_prove_the_scanners() -> None:
    on_path = _step("Put scanners on PATH")
    assert "cache-hit" not in on_path.get("if", "")
    assert 'install_scanners.sh" "$SCANNER_ROOT" >> "$GITHUB_PATH"' in on_path["run"]


def test_the_advisory_workflow_never_fails_and_only_reads() -> None:
    assert WORKFLOW["permissions"] == {"contents": "read"}
    assert WORKFLOW["jobs"]["advisory"]["permissions"] == {"contents": "read"}
    report = _step("Write the advisory report")
    assert report["run"].rstrip().endswith("exit 0")
    assert "set -e" not in report["run"].replace("set -uo pipefail", "")
    for step in STEPS:
        if step["name"] not in {
            "Checkout",
            "Install uv",
            "Fetch the pipelines revision of this workflow",
            "Write the advisory report",
        }:
            assert step.get("continue-on-error") is True, step["name"]


def test_gate_failures_are_report_rows_not_red_checks() -> None:
    # The report step runs under the runner's default `bash -e {0}` wrapper.
    # An unguarded failing gate call would abort the script before REPORT is
    # exported (main run 39259668552: the upload step then died on the empty
    # `path` input and the job went red), so the call must capture the exit
    # status instead of letting errexit kill the step.
    report = _step("Write the advisory report")
    run = report["run"]
    assert "local status=0" in run
    assert 'timeout 900 bash -c "$*" > "$log" 2>&1 || status=$?' in run
    # Adversarial: the guard must be the only exit path of the gate call; a
    # bare `local status=$?` right after an unguarded timeout would still let
    # errexit abort the step on the first finding.
    assert 'timeout 900 bash -c "$*" > "$log" 2>&1\n' not in run


def test_gate_row_survives_findings_and_unrunnable_gates() -> None:
    # Semantic check: exec the row() function extracted from the workflow
    # under the runner's `bash -e` wrapper and prove a finding (exit 1) and
    # an unrunnable gate (exit 2) both become report rows while the script
    # itself exits zero. (A timeout is the same code path: 124 is just
    # another non-zero status.)
    import subprocess
    import tempfile

    report = _step("Write the advisory report")
    # The run block is a YAML literal scalar, so the body is dedented to
    # column 0 relative to the script; the function's closing brace is the
    # only bare `}` at the start of a line.
    function = report["run"].split("row() {", 1)[1].split("\n}", 1)[0]
    with tempfile.TemporaryDirectory() as tmp:
        report_path = Path(tmp) / "report.md"
        details_path = Path(tmp) / "details.md"
        logs_dir = Path(tmp) / "logs"
        script = f"""
set -uo pipefail
report="{report_path}"
details="{details_path}"
logs="{logs_dir}"
mkdir -p "$logs"
: > "$report"
: > "$details"
row() {{
{function}
}}
row exit-one "true; exit 1"
row exit-two "true; exit 2"
exit 0
"""
        completed = subprocess.run(
            ["bash", "-e", "-c", script],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert completed.returncode == 0, completed.stderr
        rows = report_path.read_text()
        for gate, status in (("exit-one", "1"), ("exit-two", "2")):
            assert f"| `{gate}` | {status} |" in rows, f"{gate}: {rows}"
