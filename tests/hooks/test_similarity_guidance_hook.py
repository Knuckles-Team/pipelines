"""PIPE-PAGES-R024 clone guidance through the published dupehound hook."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from pipelines_hooks.clones import dupehound_report
from pipelines_hooks.clones.contract import DUPEHOUND_DIAGNOSTIC_THRESHOLD, DUPEHOUND_THRESHOLD
from pipelines_hooks.cli import GATES, run_gate
from pipelines_hooks.core.errors import CannotRun
from tests.hooks.conftest import Repo


def _worker(name: str) -> str:
    return (
        f"def {name}(records):\n"
        "    totals = {}\n"
        "    for record in records:\n"
        "        key = record.get('group', 'none')\n"
        "        totals[key] = totals.get(key, 0) + record['score']\n"
        "    return sorted(totals.items())\n"
    )


def _rust_worker(name: str) -> str:
    return (
        f"fn {name}(records: &[i64]) -> i64 {{\n"
        "    let mut total = 0;\n"
        "    for record in records {\n"
        "        let normalized = record.abs();\n"
        "        if normalized > 0 {\n"
        "            total += normalized;\n"
        "        } else {\n"
        "            total -= 1;\n"
        "        }\n"
        "    }\n"
        "    if total > 100 { 100 } else { total }\n"
        "}\n"
    )


def _distinct_python() -> str:
    return "def distinct(value):\n    return value * 3 + 1\n"


def _distinct_rust() -> str:
    return "fn distinct(value: i64) -> i64 { value * 3 + 1 }\n"


def _finding(
    similarity: float,
    *,
    file: str = "pkg/copy.py",
    original_file: str = "pkg/original.py",
    name: str = "copy",
    original_name: str = "original",
) -> dict[str, object]:
    return {
        "file": file,
        "line": 1,
        "name": name,
        "original_file": original_file,
        "original_line": 1,
        "original_name": original_name,
        "similarity": similarity,
    }


def _result(root: Path, similarity: float) -> subprocess.CompletedProcess[str]:
    (root / "pkg").mkdir(parents=True, exist_ok=True)
    (root / "pkg/copy.py").write_text(_worker("copy"), encoding="utf-8")
    (root / "pkg/original.py").write_text(_worker("original"), encoding="utf-8")
    payload = {"schema_version": 1, "findings": [_finding(similarity)]}
    return subprocess.CompletedProcess(
        ["dupehound"],
        1,
        stdout=json.dumps(payload),
        stderr="",
    )


def _fake_scanner(tmp_path: Path, findings: list[dict[str, object]], *, malformed: bool = False) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    payload = "this is not JSON" if malformed else json.dumps({"schema_version": 1, "findings": findings})
    script = tmp_path / "dupehound"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "if len(sys.argv) > 1 and sys.argv[1] == '--version':\n"
        "    print('dupehound 0.1.2')\n"
        "else:\n"
        f"    print({payload!r})\n"
        "    raise SystemExit(1)\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


@pytest.mark.spec("PIPE-PAGES-R024.1")
def test_similarity_report_model(tmp_path: Path) -> None:
    result = _result(tmp_path, DUPEHOUND_DIAGNOSTIC_THRESHOLD)
    [report] = dupehound_report.reports(result, tmp_path)
    assert report.file == "pkg/copy.py"
    assert report.original_file == "pkg/original.py"
    assert report.line == report.original_line == 1
    assert report.disposition == "diagnostic"
    assert report.source_digest.startswith("sha256:")
    assert report.original_source_digest.startswith("sha256:")
    assert report.as_dict()["scanner"] == "dupehound 0.1.2"


@pytest.mark.spec("PIPE-PAGES-R024.2")
def test_similarity_threshold_boundaries(tmp_path: Path) -> None:
    reports = [
        dupehound_report.reports(_result(tmp_path, score), tmp_path)[0]
        for score in (0.799, DUPEHOUND_DIAGNOSTIC_THRESHOLD, 0.849, DUPEHOUND_THRESHOLD)
    ]
    ignored, diagnostic, enforcement = dupehound_report.partition_reports(reports)
    assert [report.similarity for report in ignored] == [0.799]
    assert [report.similarity for report in diagnostic] == [DUPEHOUND_DIAGNOSTIC_THRESHOLD, 0.849]
    assert [report.similarity for report in enforcement] == [DUPEHOUND_THRESHOLD]
    with pytest.raises(CannotRun, match="cannot exceed"):
        dupehound_report.validate_thresholds(0.86, DUPEHOUND_THRESHOLD)


@pytest.mark.spec("PIPE-PAGES-R024.3")
def test_similarity_reporting_wiring(repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    base = repo.commit({"pkg/original.py": _worker("original")})
    repo.commit({"pkg/copy.py": _worker("copy")})
    scanner = _fake_scanner(tmp_path, [_finding(0.82)])
    monkeypatch.setenv("DUPEHOUND_BIN", str(scanner))

    assert run_gate("dupehound-changed", ["--root", str(repo.root), "--base-ref", base]) == 0
    output = capsys.readouterr().out
    assert "diagnostic floor 0.800" in output
    assert "diagnostic: pkg/copy.py:1 copy" in output
    assert "advice: review the pair" in output
    assert "full-tree clean" not in output


@pytest.mark.spec("PIPE-PAGES-R024.4")
def test_similarity_refusals(tmp_path: Path) -> None:
    source = tmp_path / "pkg"
    source.mkdir()
    (source / "copy.py").write_text(_worker("copy"), encoding="utf-8")
    (source / "original.py").write_text(_worker("original"), encoding="utf-8")
    malformed = subprocess.CompletedProcess(["dupehound"], 1, stdout="not JSON", stderr="")
    with pytest.raises(CannotRun, match="invalid JSON"):
        dupehound_report.reports(malformed, tmp_path)
    with pytest.raises(CannotRun, match="invalid similarity"):
        dupehound_report.reports(
            subprocess.CompletedProcess(
                ["dupehound"],
                1,
                stdout=json.dumps({"schema_version": 1, "findings": [_finding(float("nan"))]}),
                stderr="",
            ),
            tmp_path,
        )
    with pytest.raises(CannotRun, match="invalid file"):
        dupehound_report.reports(
            subprocess.CompletedProcess(
                ["dupehound"],
                1,
                stdout=json.dumps({"schema_version": 1, "findings": [_finding(0.82, file="../outside.py")]}),
                stderr="",
            ),
            tmp_path,
        )
    with pytest.raises(CannotRun, match="exited 2"):
        dupehound_report.reports(
            subprocess.CompletedProcess(["dupehound"], 2, stdout="", stderr="scanner failed"),
            tmp_path,
        )
    with pytest.raises(CannotRun, match="between 0 and 1"):
        dupehound_report.validate_thresholds(-0.1, DUPEHOUND_THRESHOLD)


@pytest.mark.spec("PIPE-PAGES-R024.5")
def test_similarity_evidence(tmp_path: Path) -> None:
    result = _result(tmp_path, 0.91)
    [report] = dupehound_report.reports(result, tmp_path)
    evidence = report.as_dict()
    assert (
        set(
            (
                "file",
                "line",
                "original_file",
                "original_line",
                "similarity",
                "source_digest",
                "original_source_digest",
                "scanner",
                "diagnostic_threshold",
                "enforcement_threshold",
                "disposition",
                "verdict",
                "advice",
            )
        )
        <= evidence.keys()
    )
    assert evidence["disposition"] == "enforcement"
    assert "rewrite" in str(evidence["advice"])
    source = tmp_path / "pkg/copy.py"
    source.write_text(source.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    [changed] = dupehound_report.reports(result, tmp_path)
    assert changed.source_digest != evidence["source_digest"]


@pytest.mark.scanner("dupehound")
@pytest.mark.spec("PIPE-PAGES-R024.6")
def test_similarity_guidance_cli(repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    base = repo.commit(
        {
            "pkg/original.py": _worker("original"),
            "pkg/original.rs": _rust_worker("original"),
        }
    )
    repo.commit(
        {
            "pkg/copy.py": _worker("copy"),
            "pkg/copy.rs": _rust_worker("copy"),
        }
    )

    diagnostic = _fake_scanner(
        tmp_path / "diagnostic",
        [
            _finding(0.82),
            _finding(
                0.82,
                file="pkg/copy.rs",
                original_file="pkg/original.rs",
                name="copy",
                original_name="original",
            ),
        ],
    )
    monkeypatch.setenv("DUPEHOUND_BIN", str(diagnostic))
    assert run_gate("dupehound-changed", ["--root", str(repo.root), "--base-ref", base]) == 0
    output = capsys.readouterr().out
    assert "diagnostic pair(s) require review" in output
    assert "diagnostic: pkg/copy.py:1 copy" in output
    assert "diagnostic: pkg/copy.rs:1 copy" in output
    assert "reviewed-distinct" in output

    monkeypatch.delenv("DUPEHOUND_BIN", raising=False)
    assert run_gate("dupehound-changed", ["--root", str(repo.root), "--base-ref", base]) == 1
    output = capsys.readouterr().out
    assert "enforcement: pkg/copy.py:1 copy" in output
    assert "enforcement: pkg/copy.rs:1 copy" in output
    assert "FAIL: 2 structural clone(s)" in output

    below_floor = _fake_scanner(tmp_path / "below-floor", [_finding(0.799)])
    monkeypatch.setenv("DUPEHOUND_BIN", str(below_floor))
    assert run_gate("dupehound-changed", ["--root", str(repo.root), "--base-ref", base]) == 0
    assert "ignored 1 pair(s) below diagnostic floor" in capsys.readouterr().out

    malformed = _fake_scanner(tmp_path / "malformed", [], malformed=True)
    monkeypatch.setenv("DUPEHOUND_BIN", str(malformed))
    assert run_gate("dupehound-changed", ["--root", str(repo.root), "--base-ref", base]) == 2
    assert "invalid JSON" in capsys.readouterr().err

    repo.git("reset", "--hard", base)
    assert run_gate("dupehound-changed", ["--root", str(repo.root), "--base-ref", base]) == 0
    assert "no changed supported-language production source" in capsys.readouterr().out
    assert GATES["dupehound-changed"] == "pipelines_hooks.clones.dupehound_gate"


@pytest.mark.scanner("dupehound")
@pytest.mark.spec("PIPE-PAGES-R024.6")
def test_similarity_guidance_cli_distinct_pair_passes(repo: Repo, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    base = repo.commit({"pkg/original.py": _worker("original"), "pkg/original.rs": _rust_worker("original")})
    repo.commit({"pkg/distinct.py": _distinct_python(), "pkg/distinct.rs": _distinct_rust()})
    monkeypatch.delenv("DUPEHOUND_BIN", raising=False)

    assert run_gate("dupehound-changed", ["--root", str(repo.root), "--base-ref", base]) == 0
    output = capsys.readouterr().out
    assert "checking changed source (pkg/distinct.py, pkg/distinct.rs)" in output
    assert "reviewed-distinct" in output
