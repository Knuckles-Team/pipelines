"""Offline release-bundle checks for compiled kernel wheel completeness."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import zipfile

import pytest

from tests.test_release_bundle import TARGETS, context, write_archive
from tests.test_wheel_readiness import guard, report, wheel


ACTION = Path(__file__).parents[1] / ".github/actions/wheel-readiness"
kernels_spec = importlib.util.spec_from_file_location("wheel_kernels", ACTION / "kernels.py")
assert kernels_spec and kernels_spec.loader
kernels = importlib.util.module_from_spec(kernels_spec)
kernels_spec.loader.exec_module(kernels)

bundle = guard.sibling("bundle")


_BINARY_NAMES = {
    "linux-x86_64": "fixture/_numeric.cpython-314-x86_64-linux-gnu.so",
    "linux-aarch64": "fixture/_numeric.cpython-314-aarch64-linux-gnu.so",
    "macos-aarch64": "fixture/_numeric.cpython-314-darwin.dylib",
    "windows-x86_64": "fixture/_numeric.cp314-win_amd64.pyd",
}


def _wheel_with_optional_kernel(directory: Path, target: str, compiled: bool) -> Path:
    _, _, platform_tag = TARGETS[target]
    path = wheel(directory, name=f"fixture-1.0-cp314-cp314-{platform_tag}.whl")
    if compiled:
        with zipfile.ZipFile(path, "a") as archive:
            archive.writestr(_BINARY_NAMES[target], b"synthetic compiled extension")
    return path


@pytest.fixture
def make_bundle(tmp_path, monkeypatch):
    """Build exact synthetic receipts; no native compilation or network."""

    directory = tmp_path / "dist"
    directory.mkdir()
    evidence = tmp_path / "source-evidence"
    evidence.mkdir()
    receipts = tmp_path / "target-receipts"
    receipts.mkdir()
    identity = {"source_commit": "a" * 40, "contract_commit": "b" * 40}
    monkeypatch.setattr(guard, "identity", lambda: identity)
    monkeypatch.setattr(bundle, "guard_module", lambda: guard)

    def build(compiled_targets: set[str]):
        proofs = {}
        for target in TARGETS:
            observed = context(target)
            path = _wheel_with_optional_kernel(directory, target, target in compiled_targets)
            metadata = guard.metadata(path, observed)
            resolver = report(path, metadata)
            resolver["environment"] = observed["environment"]
            item = {
                "file": path.name,
                "sha256": guard.digest(path),
                "metadata": metadata,
                "profiles": ["base"],
                "evidence": [{"profile": "base", "report": resolver}],
            }
            proofs[target] = {
                "schema": 1,
                "target": target,
                "index": guard.PUBLIC_INDEX,
                "scope": "all-runtime-dependencies",
                **identity,
                "context": observed,
                "interpreter": observed["interpreter"],
                "wheels": [item],
            }

        reference = directory / proofs["linux-x86_64"]["wheels"][0]["file"]
        (evidence / reference.name).write_bytes(reference.read_bytes())
        archive = directory / "fixture-1.0.tar.gz"
        write_archive(archive, "fixture/pyproject.toml")
        source = {
            "archive": {"file": archive.name, "sha256": guard.digest(archive)},
            "rebuilt_wheel_proof": json.loads(json.dumps(proofs["linux-x86_64"])),
            "build_prerequisites": {
                "version": "1",
                "pip_version": "25.1.1",
                "environment": context("linux-x86_64")["environment"],
                "install": [
                    {
                        "metadata": {"name": "maturin", "version": "1"},
                        "download_info": {
                            "url": "https://files.pythonhosted.org/maturin-1-py3-none-any.whl",
                            "archive_info": {"hashes": {"sha256": "c" * 64}},
                        },
                    }
                ],
            },
        }
        for target, proof in proofs.items():
            (receipts / f"{target}.json").write_text(json.dumps(proof))
        (receipts / "sdist.json").write_text(json.dumps(source))
        return directory, receipts, evidence

    return build


def test_kernel_matrix_model_is_closed():
    required = kernels.required_cells({"linux-x86_64": object(), "windows-x86_64": object()}, ("cp313", "cp314"))
    assert [(cell.target, cell.python_tag) for cell in required] == [
        ("linux-x86_64", "cp313"),
        ("linux-x86_64", "cp314"),
        ("windows-x86_64", "cp313"),
        ("windows-x86_64", "cp314"),
    ]
    matrix = kernels.KernelMatrix(required, [kernels.KernelCell("linux-x86_64", "cp313", Path("a.whl"))])
    assert {(cell.target, cell.python_tag) for cell in kernels.missing_cells(matrix)} == {
        ("linux-x86_64", "cp314"),
        ("windows-x86_64", "cp313"),
        ("windows-x86_64", "cp314"),
    }


def test_wheel_without_binary_is_missing(tmp_path):
    path = _wheel_with_optional_kernel(tmp_path, "linux-x86_64", False)
    assert kernels.inspect_wheel(path, "linux-x86_64", "cp314") is None
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr(_BINARY_NAMES["linux-x86_64"], b"compiled")
    found, binaries = kernels.inspect_wheel(path, "linux-x86_64", "cp314")
    assert found.wheel == path
    assert binaries == (_BINARY_NAMES["linux-x86_64"],)


def test_aggregate_calls_kernel_gate(make_bundle, tmp_path):
    directory, receipts, evidence = make_bundle(set(TARGETS) - {"windows-x86_64"})
    output = tmp_path / "release-readiness.json"
    with pytest.raises(ValueError, match="windows-x86_64/cp314"):
        bundle.aggregate(directory, receipts, output, '["base"]', evidence)
    assert not output.exists()


def test_missing_cell_refusal_lists_all_pairs(make_bundle, tmp_path):
    directory, receipts, evidence = make_bundle(set())
    output = tmp_path / "release-readiness.json"
    with pytest.raises(ValueError) as refusal:
        bundle.aggregate(directory, receipts, output, '["base"]', evidence)
    message = str(refusal.value)
    assert "no-kernel-declared" in message
    assert all(f"{target}/cp314" in message for target in TARGETS)
    assert not output.exists()


def test_receipt_records_kernel_cells(make_bundle, tmp_path):
    directory, receipts, evidence = make_bundle(set(TARGETS))
    output = tmp_path / "release-readiness.json"
    bundle.aggregate(directory, receipts, output, '["base"]', evidence)
    payload = json.loads(output.read_text())
    cells = {(item["target"], item["python_tag"]): item for item in payload["kernel_cells"]}
    assert set(cells) == {(target, "cp314") for target in TARGETS}
    for target, item in cells.items():
        assert item["wheel"].endswith(".whl")
        assert item["binary_files"] == [_BINARY_NAMES[target[0]]]
    bundle.verify_snapshot(directory, payload, '["base"]', evidence)


def test_release_bundle_blocks_missing_kernel_wheel(make_bundle, monkeypatch, tmp_path):
    directory, receipts, evidence = make_bundle(set(TARGETS) - {"macos-aarch64"})
    output = tmp_path / "release-readiness.json"
    output.write_text("stale success")
    github_env = tmp_path / "github-env"
    github_env.write_text("")
    monkeypatch.setenv("GITHUB_ENV", str(github_env))
    argv = [
        "readiness.py",
        "aggregate",
        "--directory",
        str(directory),
        "--receipts",
        str(receipts),
        "--receipt",
        str(output),
        "--source-evidence",
        str(evidence),
    ]
    original_sibling = guard.sibling
    monkeypatch.setattr(guard, "sibling", lambda name: bundle if name == "bundle" else original_sibling(name))
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exit_status:
        guard.main()
    assert exit_status.value.code == 1
    assert not output.exists()
    assert github_env.read_text() == ""
