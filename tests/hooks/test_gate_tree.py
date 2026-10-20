"""The source provider and the tree-based gate run (PIPE-GATES-R003 groundwork).

The engine tree binding awaits the epistemic-graph tree and blob reads
(EG-SCM-R004); these tests pin the provider contract instead: files by
path and blob digest, no working copy. The verdict-equality contract
runs one blocking gate on a tree fixture and on an identical materialized
checkout of the same revision, and asserts that both runs produce the
same verdict and evidence digest. The tree run creates no checkout.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import sanitized_env
from pipelines_hooks.core.settings import process_environment
from pipelines_hooks.gate_runner import evidence_digest
from pipelines_hooks.source_provider import DiskProvider

CLEAN = {
    "README.md": "# Fixture\n",
    "pkg/__init__.py": '"""Fixture package."""\n',
    "pkg/config.py": "setting = 'value'\n",
}
_CREDS_LINE = "access_key = 'AKIAZZZZZZZZZZZZZZZZ'\n"  # sanitizer:ignore - reviewed synthetic fixture for the verdict-equality test
DIRTY = {**CLEAN, "pkg/creds.py": _CREDS_LINE}


def _write_tree(root: Path, files: dict[str, str]) -> None:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=tree-test",
            "-c",
            "user.email=tree@example.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=root,
        env=sanitized_env(),
        check=True,
        capture_output=True,
    )


def _checkout(root: Path, files: dict[str, str]) -> None:
    """The materialized checkout of the same revision: one committed git tree."""
    _write_tree(root, files)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "--", *files)
    _git(root, "commit", "-q", "-m", "base")


def _run_sanitizer(args: list[str]) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, "-m", "pipelines_hooks", "security-sanitizer", *args],
        env=process_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout + result.stderr


def test_the_tree_and_checkout_runs_agree_on_a_clean_tree(tmp_path) -> None:
    tree, checkout = tmp_path / "tree", tmp_path / "checkout"
    _write_tree(tree, CLEAN)
    _checkout(checkout, CLEAN)
    tree_status, tree_output = _run_sanitizer(["--tree", str(tree)])
    checkout_status, checkout_output = _run_sanitizer(["--root", str(checkout)])
    assert tree_status == checkout_status == 0
    assert evidence_digest(tree_output) == evidence_digest(checkout_output)
    assert "security-sanitizer: OK" in tree_output


def test_the_tree_and_checkout_runs_agree_on_a_dirty_tree(tmp_path) -> None:
    tree, checkout = tmp_path / "tree", tmp_path / "checkout"
    _write_tree(tree, DIRTY)
    _checkout(checkout, DIRTY)
    tree_status, tree_output = _run_sanitizer(["--tree", str(tree)])
    checkout_status, checkout_output = _run_sanitizer(["--root", str(checkout)])
    assert tree_status == checkout_status == 1
    assert evidence_digest(tree_output) == evidence_digest(checkout_output)
    assert "AWS access key" in tree_output


def test_the_tree_run_needs_no_checkout_at_all(tmp_path) -> None:
    tree = tmp_path / "tree"
    _write_tree(tree, CLEAN)
    assert not (tree / ".git").exists()
    status, output = _run_sanitizer(["--tree", str(tree)])
    assert status == 0
    assert not (tree / ".git").exists()
    assert output.strip()


def test_the_gate_entry_point_fails_closed_on_a_missing_tree(tmp_path) -> None:
    status, output = _run_sanitizer(["--tree", str(tmp_path / "missing")])
    assert status == 2
    assert output.strip()


def test_the_provider_reports_paths_digests_and_sizes(tmp_path) -> None:
    tree = tmp_path / "tree"
    _write_tree(tree, CLEAN)
    entries = DiskProvider(tree).list_files()
    by_path = {entry.path: entry for entry in entries}
    assert set(by_path) == set(CLEAN)
    entry = by_path["pkg/config.py"]
    assert entry.digest == "sha256:" + hashlib.sha256(CLEAN["pkg/config.py"].encode("utf-8")).hexdigest()
    assert entry.size == len(CLEAN["pkg/config.py"].encode("utf-8"))


def test_an_empty_prefix_lists_the_whole_tree(tmp_path) -> None:
    tree = tmp_path / "tree"
    _write_tree(tree, CLEAN)
    provider = DiskProvider(tree)
    assert provider.list_files("") == provider.list_files()
    assert len(provider.list_files("")) == len(CLEAN)


def test_a_prefix_limits_the_listing(tmp_path) -> None:
    tree = tmp_path / "tree"
    _write_tree(tree, CLEAN)
    entries = DiskProvider(tree).list_files("pkg")
    assert {entry.path for entry in entries} == {"pkg/__init__.py", "pkg/config.py"}


def test_checkout_metadata_is_not_tree_content(tmp_path) -> None:
    tree = tmp_path / "tree"
    _write_tree(tree, CLEAN)
    (tree / ".git" / "objects").mkdir(parents=True)
    (tree / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    entries = DiskProvider(tree).list_files()
    assert {entry.path for entry in entries} == set(CLEAN)


def test_reading_a_path_returns_the_declared_blob(tmp_path) -> None:
    tree = tmp_path / "tree"
    _write_tree(tree, CLEAN)
    assert DiskProvider(tree).read("pkg/config.py") == CLEAN["pkg/config.py"].encode("utf-8")


def test_reading_an_undeclared_path_fails_closed(tmp_path) -> None:
    tree = tmp_path / "tree"
    _write_tree(tree, CLEAN)
    with pytest.raises(CannotRun, match="not a declared file"):
        DiskProvider(tree).read("nope.py")


def test_a_mutated_blob_fails_its_declared_digest(tmp_path) -> None:
    tree = tmp_path / "tree"
    _write_tree(tree, CLEAN)
    provider = DiskProvider(tree)
    (tree / "pkg" / "config.py").write_text("changed\n", encoding="utf-8")
    with pytest.raises(CannotRun, match="declared digest"):
        provider.read("pkg/config.py")
