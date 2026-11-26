"""The source provider and the tree-based gate run (PIPE-GATES-R003 groundwork).

The engine tree binding awaits the epistemic-graph tree and blob reads
(MEDULLA-SCM-R004); these tests pin the provider contract instead: files by
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
from pipelines_hooks.source_provider import DiskProvider, EngineTreeProvider, blob_digest

from tests.hooks.arbora_loopback import Loopback, serving

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


@pytest.mark.spec("PIPE-GATES-R003")
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


@pytest.mark.spec("PIPE-GATES-R003")
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


@pytest.mark.spec("PIPE-GATES-R003")
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


def _run_engine_sanitizer(endpoint: str, ref: str = "demo@main") -> tuple[int, str]:
    environment = process_environment()
    environment["PIPELINES_ARBORA_ENDPOINT"] = endpoint
    result = subprocess.run(
        [sys.executable, "-m", "pipelines_hooks", "security-sanitizer", "--engine", ref],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout + result.stderr


@pytest.mark.spec("PIPE-GATES-R003")
@pytest.mark.parametrize("files", [CLEAN, DIRTY], ids=["clean", "dirty"])
def test_the_engine_tree_and_checkout_runs_agree(tmp_path, files) -> None:
    tree, checkout = tmp_path / "tree", tmp_path / "checkout"
    _write_tree(tree, files)
    _checkout(checkout, files)
    with serving(Loopback(tree)) as engine:
        engine_status, engine_output = _run_engine_sanitizer(engine.endpoint)
    checkout_status, checkout_output = _run_sanitizer(["--root", str(checkout)])
    assert engine_status == checkout_status == (0 if files is CLEAN else 1)
    assert evidence_digest(engine_output) == evidence_digest(checkout_output)
    assert not (tmp_path / "tree" / ".git").exists()
    assert {call[0] for call in engine.calls} == {"source.tree", "source.blob"}


def test_an_engine_blob_that_misses_its_declared_digest_fails_closed(tmp_path) -> None:
    tree = tmp_path / "tree"
    _write_tree(tree, CLEAN)
    state = Loopback(tree)
    with serving(state) as engine:
        provider = EngineTreeProvider(engine.endpoint, "", "demo", "main")
        (tree / "pkg" / "config.py").write_text("changed\n", encoding="utf-8")
        with pytest.raises(CannotRun, match="declared digest"):
            provider.read("pkg/config.py")
        assert provider.read("README.md") == CLEAN["README.md"].encode("utf-8")
        with pytest.raises(CannotRun, match="not a declared file"):
            provider.read("nope.py")


def test_an_unreachable_engine_fails_the_tree_run_closed(tmp_path) -> None:
    with serving(Loopback(tmp_path, fail=True)) as engine:
        status, output = _run_engine_sanitizer(engine.endpoint)
    assert status == 2
    assert "engine tree provider" in output
    status, output = _run_engine_sanitizer("")
    assert status == 2


def _receipt(files: dict[str, str]) -> dict[str, str]:
    return {path: blob_digest(text.encode("utf-8")) for path, text in files.items()}


# spec: PIPE-GATES-R084
def test_content_digest_detects_a_change_where_git_diff_reports_none(tmp_path) -> None:
    from pipelines_hooks.core.gitenv import EXTRACTED_TREE_MARKER, run_git
    from pipelines_hooks.source_provider import verify_tree

    tree = tmp_path / "tree"
    _write_tree(tree, CLEAN)
    receipt = _receipt(CLEAN)
    (tree / EXTRACTED_TREE_MARKER).write_text("{}", encoding="utf-8")
    assert verify_tree(DiskProvider(tree), receipt) == []
    (tree / "pkg" / "config.py").write_text("setting = 'other'\n", encoding="utf-8")
    (tree / "extra.py").write_text("x = 1\n", encoding="utf-8")
    (tree / "README.md").unlink()
    findings = verify_tree(DiskProvider(tree), receipt)
    assert any(f.startswith("pkg/config.py: digest differs") for f in findings)
    assert any(f.startswith("extra.py: undeclared") for f in findings)
    assert any(f.startswith("README.md: missing") for f in findings)
    # Git has no working copy to ask here: the call is refused, never answered "no change".
    with pytest.raises(CannotRun, match="extracted tree"):
        run_git(tree, ("diff", "--stat"))
    with pytest.raises(CannotRun, match="extracted tree"):
        run_git(tree / "pkg", ("status", "--short"))


# spec: PIPE-GATES-R084
def test_a_working_copy_still_runs_git_beside_an_extracted_marker(tmp_path) -> None:
    from pipelines_hooks.core.gitenv import EXTRACTED_TREE_MARKER, run_git

    checkout = tmp_path / "checkout"
    _checkout(checkout, CLEAN)
    (checkout / EXTRACTED_TREE_MARKER).write_text("{}", encoding="utf-8")
    assert run_git(checkout, ("status", "--short")).returncode == 0
