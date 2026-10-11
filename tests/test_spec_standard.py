"""spec-standard passes a clean spec and fires once per check kind."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pipelines_hooks.specs.standard import main

FILES = (
    "spec.md",
    "plan.md",
    "requirements.md",
    "tasks.md",
    "test-spec.md",
    "status.json",
)


def _spec(root: Path, name: str = "foo", spec_id: str = "FOO") -> Path:
    d = root / "specs" / name
    d.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        (d / f).write_text("{}\n" if f.endswith(".json") else "x\n")
    (d / "spec.md").write_text(f"# {spec_id} — Title\n")
    (d / "requirements.md").write_text(f"| `{spec_id}-R001` | req |\n")
    (root / "specs" / "README.md").write_text(f"- [x]({name}/spec.md)\n")
    return d


@pytest.fixture
def root(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def _run(root: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = main(["--root", str(root)])
    return code, capsys.readouterr().out


def test_clean(root, capsys):
    _spec(root)
    assert _run(root, capsys) == (0, "spec-standard: clean (1 spec(s) checked)\n")


def test_template_skipped(root, capsys):
    _spec(root)
    (root / "specs" / "_template").mkdir()
    (root / "specs" / "_template" / "spec.md").write_text("junk\n")
    assert _run(root, capsys)[0] == 0


def test_file_set(root, capsys):
    d = _spec(root)
    (d / "plan.md").unlink()
    (d / "design.md").write_text("x")
    code, out = _run(root, capsys)
    assert code == 1
    assert "missing required file plan.md" in out and "forbidden file design.md" in out


def test_title(root, capsys):
    d = _spec(root)
    (d / "spec.md").write_text("# FOO - Title\n")
    assert "line 1 must match" in _run(root, capsys)[1]


def test_id_suffix_and_rows(root, capsys):
    d = _spec(root, "foo", "FOO-001")
    (d / "requirements.md").write_text("| `BAR-R001` | req |\n")
    out = _run(root, capsys)[1]
    assert "numeric suffix" in out and "does not start with FOO-001-R" in out


def test_names(root, capsys):
    _spec(root, "foo-audit", "FOO-FIX")
    out = _run(root, capsys)[1]
    assert "directory name contains forbidden word 'audit'" in out
    assert "spec ID contains forbidden word 'fix'" in out


def test_index(root, capsys):
    _spec(root)
    (root / "specs" / "README.md").write_text("nothing\n")
    assert "not listed in specs/README.md" in _run(root, capsys)[1]
