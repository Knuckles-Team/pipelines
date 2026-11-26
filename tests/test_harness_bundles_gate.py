"""The harness-bundles-untracked gate (PIPE-RELEASE-R028.2)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from pipelines_hooks.cli import run_gate


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-C", str(root), *args],
        check=True,
        capture_output=True,
    )


def _repo(root: Path, files: dict[str, str]) -> None:
    _git(root, "init", "-q")
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    _git(root, "add", "--", *files)


PYPROJECT = '[project]\nname = "x"\nversion = "1"\n\n[tool.pipelines.harness_bundles]\ncommand = "x"\noutput = "out"\ncatalog = ".codex-plugin/catalog.json"\n'


# spec: PIPE-RELEASE-R028.2
def test_tracked_bundle_fails_and_a_declared_catalog_passes(tmp_path: Path, capsys) -> None:
    dirty = tmp_path / "dirty"
    dirty.mkdir()
    _repo(
        dirty,
        {"pyproject.toml": PYPROJECT, ".claude-plugin/plugin.json": "{}", ".grok-plugin/a.json": "{}", "out/x/y": "1"},
    )
    assert run_gate("harness-bundles-untracked", ["--root", str(dirty)]) == 1
    printed = capsys.readouterr().out
    for path in (".claude-plugin/plugin.json", ".grok-plugin/a.json", "out/x/y"):
        assert f"BUNDLE_COMMITTED {path}" in printed
    clean = tmp_path / "clean"
    clean.mkdir()
    _repo(clean, {"pyproject.toml": PYPROJECT, ".codex-plugin/catalog.json": "{}", "src/a.py": ""})
    assert run_gate("harness-bundles-untracked", ["--root", str(clean)]) == 0
