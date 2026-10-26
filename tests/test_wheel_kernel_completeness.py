"""Offline release-bundle checks for compiled kernel wheel completeness."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct
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


def _elf_payload(machine: int) -> bytes:
    code = b"\x90\xc3kernel-fixture"
    payload = bytearray(0x100 + len(code))
    payload[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into(
        "<HHIQQQIHHHHHH",
        payload,
        16,
        3,
        machine,
        1,
        0,
        64,
        0,
        0,
        64,
        56,
        1,
        64,
        0,
        0,
    )
    struct.pack_into("<IIQQQQQQ", payload, 64, 1, 5, 0, 0, 0, len(payload), len(payload), 0x1000)
    payload[0x100:] = code
    return bytes(payload)


def _macho_payload() -> bytes:
    code = b"\x90\xc3kernel-fixture"
    payload = bytearray(0x100 + len(code))
    struct.pack_into("<IIIIIIII", payload, 0, 0xFEEDFACF, 0x0100000C, 0, 8, 1, 72, 0, 0)
    struct.pack_into("<II16sQQQQiiII", payload, 32, 0x19, 72, b"__TEXT", 0, len(payload), 0, len(payload), 7, 5, 0, 0)
    payload[0x100:] = code
    return bytes(payload)


def _pe_payload() -> bytes:
    payload = bytearray(0x400)
    payload[:2] = b"MZ"
    struct.pack_into("<I", payload, 0x3C, 0x40)
    payload[0x40:0x44] = b"PE\x00\x00"
    struct.pack_into("<HHIIIHH", payload, 0x44, 0x8664, 1, 0, 0, 0, 0xF0, 0x2000)
    optional = 0x58
    struct.pack_into("<H", payload, optional, 0x20B)
    struct.pack_into("<I", payload, optional + 4, 0x200)
    struct.pack_into("<I", payload, optional + 16, 0x1000)
    struct.pack_into("<I", payload, optional + 20, 0x1000)
    struct.pack_into("<Q", payload, optional + 24, 0x140000000)
    struct.pack_into("<II", payload, optional + 32, 0x1000, 0x200)
    struct.pack_into("<II", payload, optional + 56, 0x2000, 0x200)
    struct.pack_into("<H", payload, optional + 68, 3)
    struct.pack_into("<H", payload, optional + 70, 0x160)
    struct.pack_into("<I", payload, optional + 108, 16)
    section = optional + 0xF0
    payload[section : section + 8] = b".text\x00\x00\x00"
    struct.pack_into(
        "<IIIIIIHHI", payload, section + 8, len(payload) - 0x200, 0x1000, 0x200, 0x200, 0, 0, 0, 0, 0x60000020
    )
    payload[0x200 : 0x200 + len(b"\x90\xc3kernel-fixture")] = b"\x90\xc3kernel-fixture"
    return bytes(payload)


def _truncated_elf(machine: int) -> bytes:
    payload = bytearray(64)
    payload[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<HHIQQQIHHHHHH", payload, 16, 3, machine, 1, 0, 64, 0, 0, 64, 56, 1, 64, 0, 0)
    return bytes(payload)


def _truncated_macho() -> bytes:
    payload = bytearray(32)
    struct.pack_into("<IIIIIIII", payload, 0, 0xFEEDFACF, 0x0100000C, 0, 8, 1, 72, 0, 0)
    return bytes(payload)


def _truncated_pe() -> bytes:
    payload = bytearray(0x46)
    payload[:2] = b"MZ"
    struct.pack_into("<I", payload, 0x3C, 0x40)
    payload[0x40:0x44] = b"PE\x00\x00"
    struct.pack_into("<H", payload, 0x44, 0x8664)
    return bytes(payload)


_BINARY_PAYLOADS = {
    "linux-x86_64": _elf_payload(0x3E),
    "linux-aarch64": _elf_payload(0xB7),
    "macos-aarch64": _macho_payload(),
    "windows-x86_64": _pe_payload(),
}

_TRUNCATED_PAYLOADS = {
    "linux-x86_64": _truncated_elf(0x3E),
    "macos-aarch64": _truncated_macho(),
    "windows-x86_64": _truncated_pe(),
}


def _wheel_with_optional_kernel(directory: Path, target: str, compiled: bool) -> Path:
    _, _, platform_tag = TARGETS[target]
    path = wheel(directory, name=f"fixture-1.0-cp314-cp314-{platform_tag}.whl")
    if compiled:
        with zipfile.ZipFile(path, "a") as archive:
            archive.writestr(_BINARY_NAMES[target], _BINARY_PAYLOADS[target])
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


# spec: PIPE-RELEASE-R004.1
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


# spec: PIPE-RELEASE-R004.2
def test_wheel_without_binary_is_missing(tmp_path):
    path = _wheel_with_optional_kernel(tmp_path, "linux-x86_64", False)
    assert kernels.inspect_wheel(path, "linux-x86_64", "cp314") is None


def test_real_binary_header_counts_as_kernel(tmp_path):
    path = _wheel_with_optional_kernel(tmp_path, "linux-x86_64", True)
    found, binaries = kernels.inspect_wheel(path, "linux-x86_64", "cp314")
    assert found.wheel == path
    assert binaries == (_BINARY_NAMES["linux-x86_64"],)


# spec: PIPE-RELEASE-R004.4
def test_plain_binary_payload_is_missing(tmp_path):
    path = _wheel_with_optional_kernel(tmp_path, "linux-x86_64", False)
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr(_BINARY_NAMES["linux-x86_64"], b"plain text")
    assert kernels.inspect_wheel(path, "linux-x86_64", "cp314") is None


@pytest.mark.parametrize("target", _TRUNCATED_PAYLOADS)
def test_truncated_binary_tables_are_missing(tmp_path, target):
    path = _wheel_with_optional_kernel(tmp_path, target, False)
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr(_BINARY_NAMES[target], _TRUNCATED_PAYLOADS[target])
    assert kernels.inspect_wheel(path, target, "cp314") is None


def test_binary_table_offset_out_of_bounds_is_missing(tmp_path):
    payload = bytearray(_BINARY_PAYLOADS["linux-x86_64"])
    struct.pack_into("<Q", payload, 32, len(payload) + 1)
    path = _wheel_with_optional_kernel(tmp_path, "linux-x86_64", False)
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr(_BINARY_NAMES["linux-x86_64"], payload)
    assert kernels.inspect_wheel(path, "linux-x86_64", "cp314") is None


def test_corrupt_binary_crc_is_refused(tmp_path):
    path = _wheel_with_optional_kernel(tmp_path, "linux-x86_64", True)
    raw = path.read_bytes()
    assert raw.count(b"kernel-fixture") == 1
    path.write_bytes(raw.replace(b"kernel-fixture", b"kernel-corrupt", 1))
    with pytest.raises(ValueError, match="CRC"):
        kernels.inspect_wheel(path, "linux-x86_64", "cp314")


def test_traversal_member_is_refused_before_payload_read(tmp_path):
    path = _wheel_with_optional_kernel(tmp_path, "linux-x86_64", False)
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr("../outside.so", _BINARY_PAYLOADS["linux-x86_64"])
    with pytest.raises(ValueError, match="escapes its root"):
        kernels.inspect_wheel(path, "linux-x86_64", "cp314")


def test_noncanonical_duplicate_member_is_refused(tmp_path):
    path = _wheel_with_optional_kernel(tmp_path, "linux-x86_64", False)
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr(_BINARY_NAMES["linux-x86_64"], _BINARY_PAYLOADS["linux-x86_64"])
        archive.writestr("./" + _BINARY_NAMES["linux-x86_64"], _BINARY_PAYLOADS["linux-x86_64"])
    with pytest.raises(ValueError, match="escapes its root"):
        kernels.inspect_wheel(path, "linux-x86_64", "cp314")


def test_member_count_cap_is_refused_before_payload_read(tmp_path, monkeypatch):
    path = _wheel_with_optional_kernel(tmp_path, "linux-x86_64", False)
    monkeypatch.setattr(kernels, "MAX_MEMBERS", 3)
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr("fixture/extra.txt", b"extra")
    with pytest.raises(ValueError, match="too many members"):
        kernels.inspect_wheel(path, "linux-x86_64", "cp314")


def test_member_size_cap_is_refused_before_payload_read(tmp_path, monkeypatch):
    path = _wheel_with_optional_kernel(tmp_path, "linux-x86_64", False)
    with zipfile.ZipFile(path) as archive:
        baseline = max(info.file_size for info in archive.infolist())
    monkeypatch.setattr(kernels, "MAX_MEMBER_BYTES", baseline)
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr("fixture/oversize.bin", b"x" * (baseline + 1))
    with pytest.raises(ValueError, match="size limit"):
        kernels.inspect_wheel(path, "linux-x86_64", "cp314")


def test_compression_ratio_cap_is_refused_before_payload_read(tmp_path, monkeypatch):
    path = _wheel_with_optional_kernel(tmp_path, "linux-x86_64", False)
    monkeypatch.setattr(kernels, "MAX_COMPRESSION_RATIO", 10)
    info = zipfile.ZipInfo(_BINARY_NAMES["linux-x86_64"])
    info.compress_type = zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr(info, _BINARY_PAYLOADS["linux-x86_64"] + b"A" * 20_000)
    with pytest.raises(ValueError, match="compression ratio"):
        kernels.inspect_wheel(path, "linux-x86_64", "cp314")


# spec: PIPE-RELEASE-R004.3
def test_aggregate_calls_kernel_gate(make_bundle, tmp_path):
    directory, receipts, evidence = make_bundle(set(TARGETS) - {"windows-x86_64"})
    output = tmp_path / "release-readiness.json"
    with pytest.raises(ValueError, match="windows-x86_64/cp314"):
        bundle.aggregate(directory, receipts, output, '["base"]', evidence)
    assert not output.exists()


# spec: PIPE-RELEASE-R004.4
def test_missing_cell_refusal_lists_all_pairs(make_bundle, tmp_path):
    directory, receipts, evidence = make_bundle(set())
    output = tmp_path / "release-readiness.json"
    with pytest.raises(ValueError) as refusal:
        bundle.aggregate(directory, receipts, output, '["base"]', evidence)
    message = str(refusal.value)
    assert "no-kernel-declared" in message
    assert all(f"{target}/cp314" in message for target in TARGETS)
    assert not output.exists()


# spec: PIPE-RELEASE-R004.5
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


# spec: PIPE-RELEASE-R004.6
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
