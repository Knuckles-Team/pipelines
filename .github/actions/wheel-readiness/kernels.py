"""Check that a release bundle contains compiled kernel wheels per cell.

The wheel filename supplies the declared Python and platform tags, while the
archive contents supply the independent proof that the wheel is not merely a
platform-tagged pure-Python artifact.  This module deliberately has no build
or import step; it only inspects the bytes that the release bundle is about to
publish.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
import re
import stat
import struct
from pathlib import PurePosixPath, PureWindowsPath
import zipfile

try:
    from pip._vendor.packaging.utils import parse_wheel_filename
except ImportError:  # pragma: no cover - used by the project test environment
    from packaging.utils import parse_wheel_filename


# ``targets.py`` and the Maturin publisher both require CPython 3.14.  Keep
# that existing publication axis as the named default; publishers may pass
# another explicit tuple only when their reviewed matrix supports it.
DEFAULT_PYTHON_TAGS = ("cp314",)

_PLATFORM_PATTERNS = {
    "linux-x86_64": re.compile(r"^(?:manylinux(?:_\d+_\d+|1|2010|2014)|linux)_x86_64$"),
    "linux-aarch64": re.compile(r"^(?:manylinux(?:_\d+_\d+|2014)|linux)_aarch64$"),
    "macos-aarch64": re.compile(r"^macosx_\d+_\d+_(?:arm64|universal2)$"),
    "windows-x86_64": re.compile(r"^win_amd64$"),
}
_BINARY_SUFFIXES = (".so", ".pyd", ".dylib")
MAX_WHEEL_BYTES = 512 * 1024 * 1024
MAX_MEMBERS = 100_000
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_BINARY_BYTES = 64 * 1024 * 1024
MAX_COMPRESSION_RATIO = 1_000
_READ_CHUNK_BYTES = 1024 * 1024
_MAX_TABLE_ENTRIES = 4_096
_MAX_TABLE_BYTES = 4 * 1024 * 1024

_ELF_ET_DYN = 3
_ELF_PT_LOAD = 1
_ELF_PF_X = 4
_MACHO_ARM64 = 0x0100000C
_MACHO_MH_DYLIB = 6
_MACHO_MH_BUNDLE = 8
_MACHO_LC_SEGMENT_64 = 0x19
_MACHO_VM_PROT_EXECUTE = 4
_MACHO_SECTION_PURE_INSTRUCTIONS = 0x80000000
_MACHO_SECTION_SOME_INSTRUCTIONS = 0x00000400
_PE_IMAGE_FILE_DLL = 0x2000
_PE_IMAGE_SCN_CNT_CODE = 0x00000020
_PE_IMAGE_SCN_MEM_EXECUTE = 0x20000000


@dataclass(frozen=True, slots=True)
class KernelCell:
    """One target/Python wheel slot in the publication matrix."""

    target: str
    python_tag: str
    wheel: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.target, str) or not self.target:
            raise ValueError("kernel target must be a non-empty string")
        if not isinstance(self.python_tag, str) or not self.python_tag:
            raise ValueError("kernel Python tag must be a non-empty string")
        if self.wheel is not None:
            object.__setattr__(self, "wheel", Path(self.wheel))

    @property
    def key(self) -> tuple[str, str]:
        return self.target, self.python_tag


@dataclass(frozen=True, slots=True)
class KernelMatrix:
    """Required cells and the cells found in a concrete release bundle."""

    required: tuple[KernelCell, ...] | Sequence[KernelCell]
    found: tuple[KernelCell, ...] | Sequence[KernelCell]

    def __post_init__(self) -> None:
        required = tuple(self.required)
        found = tuple(self.found)
        if len({cell.key for cell in required}) != len(required):
            raise ValueError("kernel matrix has duplicate required cells")
        if len({cell.key for cell in found}) != len(found):
            raise ValueError("kernel matrix has duplicate found cells")
        object.__setattr__(self, "required", required)
        object.__setattr__(self, "found", found)


class KernelCellMissing(ValueError):
    """The publication matrix is missing one or more compiled kernel wheels."""

    def __init__(self, cells: Iterable[KernelCell], *, reason: str | None = None) -> None:
        self.cells = tuple(cells)
        self.missing = self.cells
        self.missing_cells = self.cells
        self.reason = reason
        pairs = ", ".join(f"{cell.target}/{cell.python_tag}" for cell in self.cells)
        prefix = f"{reason}: " if reason else ""
        super().__init__(f"{prefix}missing compiled kernel wheel cells: {pairs}")


def _names(targets: Mapping[str, object] | Iterable[str]) -> tuple[str, ...]:
    values = tuple(targets) if isinstance(targets, Mapping) else tuple(targets)
    if not values or any(not isinstance(item, str) or not item for item in values):
        raise ValueError("kernel targets must be non-empty names")
    if len(set(values)) != len(values):
        raise ValueError("kernel targets must be unique")
    return tuple(sorted(values))


def _python_tags(python_tags: Iterable[str]) -> tuple[str, ...]:
    values = tuple(python_tags)
    if not values or any(not isinstance(item, str) or not item for item in values):
        raise ValueError("kernel Python tags must be non-empty names")
    if len(set(values)) != len(values):
        raise ValueError("kernel Python tags must be unique")
    return values


def required_cells(
    targets: Mapping[str, object] | Iterable[str], python_tags: Iterable[str] = DEFAULT_PYTHON_TAGS
) -> tuple[KernelCell, ...]:
    """Return the deterministic closed target/Python matrix."""

    target_names = _names(targets)
    tag_names = _python_tags(python_tags)
    return tuple(KernelCell(target, python_tag) for target in target_names for python_tag in tag_names)


def missing_cells(matrix: KernelMatrix) -> list[KernelCell]:
    """Return every required cell not represented by a found cell."""

    found = {cell.key for cell in matrix.found}
    return [cell for cell in matrix.required if cell.key not in found]


def _matching_platform(target: str, platform: str) -> bool:
    try:
        pattern = _PLATFORM_PATTERNS[target]
    except KeyError as error:
        raise ValueError(f"unknown kernel target: {target}") from error
    return platform != "any" and bool(pattern.fullmatch(platform))


def _safe_member_name(name: str) -> None:
    normalized = name[:-1] if name.endswith("/") else name
    path = PurePosixPath(normalized)
    windows = PureWindowsPath(normalized)
    if (
        not normalized
        or "\x00" in name
        or "\\" in name
        or path.is_absolute()
        or not path.parts
        or ".." in path.parts
        or str(path) != normalized
        or windows.drive
        or windows.root
    ):
        raise ValueError(f"wheel archive path escapes its root: {name!r}")


def _safe_infos(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    infos = archive.infolist()
    if len(infos) > MAX_MEMBERS:
        raise ValueError("wheel archive has too many members")
    seen: set[str] = set()
    total = 0
    for info in infos:
        _safe_member_name(info.filename)
        if info.filename in seen:
            raise ValueError(f"wheel archive has duplicate member: {info.filename!r}")
        seen.add(info.filename)
        if info.flag_bits & 0x1:
            raise ValueError("encrypted wheel archive member is unsupported")
        mode = (info.external_attr >> 16) & 0o170000
        if mode and mode not in {stat.S_IFREG, stat.S_IFDIR}:
            raise ValueError(f"wheel archive has linked or special member: {info.filename!r}")
        if info.file_size > MAX_MEMBER_BYTES:
            raise ValueError(f"wheel archive member exceeds the size limit: {info.filename!r}")
        total += info.file_size
        if total > MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise ValueError("wheel archive exceeds the uncompressed size limit")
        if info.file_size and info.file_size / max(info.compress_size, 1) > MAX_COMPRESSION_RATIO:
            raise ValueError(f"wheel archive member compression ratio is excessive: {info.filename!r}")
    return infos


def _read_bounded(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    if info.file_size > MAX_BINARY_BYTES:
        raise ValueError(f"compiled binary exceeds the payload limit: {info.filename!r}")
    parts: list[bytes] = []
    size = 0
    try:
        with archive.open(info, "r") as stream:
            while True:
                chunk = stream.read(min(_READ_CHUNK_BYTES, MAX_BINARY_BYTES + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_BINARY_BYTES:
                    raise ValueError(f"compiled binary exceeds the payload limit: {info.filename!r}")
                parts.append(chunk)
    except zipfile.BadZipFile as error:
        raise ValueError(f"compiled binary CRC is invalid: {info.filename!r}") from error
    if size != info.file_size:
        raise ValueError(f"compiled binary size is inconsistent: {info.filename!r}")
    return b"".join(parts)


def _bounded_end(length: int, offset: int, size: int, cap: int) -> int | None:
    if offset < 0 or size < 0 or size > cap or offset > length:
        return None
    end = offset + size
    return end if end <= length else None


def _bounded_table(length: int, offset: int, count: int, entry_size: int) -> int | None:
    if count <= 0 or count > _MAX_TABLE_ENTRIES:
        return None
    return _bounded_end(length, offset, count * entry_size, _MAX_TABLE_BYTES)


def _has_code_bytes(data: bytes, start: int, end: int, after: int) -> bool:
    start = max(start, after)
    return start < end and any(memoryview(data)[start:end])


def _valid_elf(data: bytes, target: str) -> bool:
    machines = {"linux-x86_64": 0x3E, "linux-aarch64": 0xB7}
    if len(data) < 64 or data[:4] != b"\x7fELF" or data[4:7] != b"\x02\x01\x01":
        return False
    header = struct.unpack_from("<HHIQQQIHHHHHH", data, 16)
    elf_type, machine, version, _, phoff, shoff, _, ehsize, phentsize, phnum, shentsize, shnum, shstrndx = header
    if (
        elf_type != _ELF_ET_DYN
        or machine != machines.get(target)
        or version != 1
        or ehsize != 64
        or phentsize != 56
        or shstrndx > shnum
    ):
        return False
    ph_end = _bounded_table(len(data), phoff, phnum, phentsize)
    if ph_end is None:
        return False
    if shnum:
        if shoff == 0 or shentsize != 64 or _bounded_table(len(data), shoff, shnum, shentsize) is None:
            return False
    elif shoff or shstrndx:
        return False
    for index in range(phnum):
        offset = phoff + index * phentsize
        p_type, p_flags, _, _, file_offset, file_size, memory_size, _ = struct.unpack_from("<IIQQQQQQ", data, offset)
        if p_type != _ELF_PT_LOAD or not p_flags & _ELF_PF_X or memory_size < file_size or not file_size:
            continue
        segment_end = _bounded_end(len(data), file_offset, file_size, MAX_BINARY_BYTES)
        if segment_end is not None and _has_code_bytes(data, file_offset, segment_end, ph_end):
            return True
    return False


def _valid_macho_section(data: bytes, offset: int, endian: str, segment_end: int) -> bool:
    _, _, _, size, file_offset, _, _, _, flags, _, _, _ = struct.unpack_from(endian + "16s16sQQIIIIIIII", data, offset)
    section_end = _bounded_end(len(data), file_offset, size, MAX_BINARY_BYTES)
    if section_end is None or section_end > segment_end:
        return False
    return (
        bool(flags & (_MACHO_SECTION_PURE_INSTRUCTIONS | _MACHO_SECTION_SOME_INSTRUCTIONS))
        and bool(size)
        and any(memoryview(data)[file_offset:section_end])
    )


def _valid_macho_thin(data: bytes, endian: str) -> bool:
    if len(data) < 32:
        return False
    _, cpu_type, _, file_type, command_count, command_size, _, _ = struct.unpack_from(endian + "IIIIIIII", data, 0)
    if (
        cpu_type != _MACHO_ARM64
        or file_type not in {_MACHO_MH_DYLIB, _MACHO_MH_BUNDLE}
        or command_count <= 0
        or command_count > _MAX_TABLE_ENTRIES
        or command_size > _MAX_TABLE_BYTES
    ):
        return False
    commands_end = _bounded_end(len(data), 32, command_size, _MAX_TABLE_BYTES)
    if commands_end is None:
        return False
    cursor = 32
    executable = False
    for _ in range(command_count):
        if cursor + 8 > commands_end:
            return False
        command, size = struct.unpack_from(endian + "II", data, cursor)
        if size < 8 or size > commands_end - cursor:
            return False
        if command == _MACHO_LC_SEGMENT_64:
            if size < 72:
                return False
            fields = struct.unpack_from(endian + "II16sQQQQiiII", data, cursor)
            file_offset, file_size = fields[5:7]
            init_protection, section_count = fields[8:10]
            segment_end = _bounded_end(len(data), file_offset, file_size, MAX_BINARY_BYTES)
            if section_count > _MAX_TABLE_ENTRIES:
                return False
            section_table_end = cursor + 72 + section_count * 80
            if section_table_end > cursor + size:
                return False
            if segment_end is not None and init_protection & _MACHO_VM_PROT_EXECUTE:
                executable = executable or _has_code_bytes(data, file_offset, segment_end, commands_end)
            for index in range(section_count):
                section_offset = cursor + 72 + index * 80
                if _valid_macho_section(data, section_offset, endian, segment_end or 0):
                    executable = True
        cursor += size
    return cursor == commands_end and executable


def _valid_macho(data: bytes) -> bool:
    if len(data) < 4:
        return False
    magic = data[:4]
    if magic in {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf"}:
        return _valid_macho_thin(data, "<" if magic == b"\xcf\xfa\xed\xfe" else ">")
    if magic not in {b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"} or len(data) < 8:
        return False
    endian = ">" if magic == b"\xca\xfe\xba\xbe" else "<"
    count = struct.unpack_from(endian + "I", data, 4)[0]
    table_end = _bounded_table(len(data), 8, count, 20)
    if table_end is None:
        return False
    for index in range(count):
        offset = 8 + index * 20
        cpu_type, _, file_offset, file_size, _ = struct.unpack_from(endian + "IIIII", data, offset)
        slice_end = _bounded_end(len(data), file_offset, file_size, MAX_BINARY_BYTES)
        if cpu_type != _MACHO_ARM64 or slice_end is None:
            continue
        payload = data[file_offset:slice_end]
        slice_magic = payload[:4]
        if slice_magic not in {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf"}:
            continue
        if _valid_macho_thin(payload, "<" if slice_magic == b"\xcf\xfa\xed\xfe" else ">"):
            return True
    return False


def _valid_pe(data: bytes) -> bool:
    if len(data) < 0x40 or data[:2] != b"MZ":
        return False
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    pe_end = _bounded_end(len(data), pe_offset, 24, _MAX_TABLE_BYTES)
    if pe_end is None or data[pe_offset : pe_offset + 4] != b"PE\x00\x00":
        return False
    machine, section_count, _, _, _, optional_size, characteristics = struct.unpack_from(
        "<HHIIIHH", data, pe_offset + 4
    )
    if machine != 0x8664 or section_count <= 0 or section_count > _MAX_TABLE_ENTRIES:
        return False
    optional_offset = pe_offset + 24
    optional_end = _bounded_end(len(data), optional_offset, optional_size, _MAX_TABLE_BYTES)
    if optional_end is None or optional_size < 112 or struct.unpack_from("<H", data, optional_offset)[0] != 0x20B:
        return False
    directory_count = struct.unpack_from("<I", data, optional_offset + 108)[0]
    directory_end = _bounded_end(len(data), optional_offset + 112, directory_count * 8, _MAX_TABLE_BYTES)
    if not characteristics & _PE_IMAGE_FILE_DLL or directory_count > 16 or directory_end is None:
        return False
    if directory_end > optional_end:
        return False
    image_size = struct.unpack_from("<I", data, optional_offset + 56)[0]
    header_size = struct.unpack_from("<I", data, optional_offset + 60)[0]
    section_end = _bounded_table(len(data), optional_end, section_count, 40)
    if section_end is None or header_size < section_end or header_size > len(data) or not image_size:
        return False
    executable = False
    for index in range(section_count):
        offset = optional_end + index * 40
        _, virtual_size, virtual_address, raw_size, raw_offset, _, _, _, _, section_flags = struct.unpack_from(
            "<8sIIIIIIHHI", data, offset
        )
        raw_end = _bounded_end(len(data), raw_offset, raw_size, MAX_BINARY_BYTES)
        if raw_size and raw_end is None:
            return False
        if virtual_address + max(virtual_size, raw_size) > image_size:
            return False
        if (
            raw_end is not None
            and raw_size
            and raw_offset >= section_end
            and section_flags & _PE_IMAGE_SCN_CNT_CODE
            and section_flags & _PE_IMAGE_SCN_MEM_EXECUTE
            and _has_code_bytes(data, raw_offset, raw_end, section_end)
        ):
            executable = True
    return executable


def _valid_binary(data: bytes, target: str, name: str) -> bool:
    suffix = Path(name).suffix.lower()
    if target.startswith("linux"):
        return suffix == ".so" and _valid_elf(data, target)
    if target == "macos-aarch64":
        return suffix in {".so", ".dylib"} and _valid_macho(data)
    if target == "windows-x86_64":
        return suffix == ".pyd" and _valid_pe(data)
    return False


def _binary_names(archive: zipfile.ZipFile, infos: Sequence[zipfile.ZipInfo], target: str) -> tuple[str, ...]:
    if target not in _PLATFORM_PATTERNS:
        raise ValueError(f"unknown kernel target: {target}")
    names = []
    for info in infos:
        name = info.filename
        if name.endswith("/") or ".dist-info/" in name or ".data/" in name:
            continue
        if not name.lower().endswith(_BINARY_SUFFIXES):
            continue
        if _valid_binary(_read_bounded(archive, info), target, name):
            names.append(name)
    return tuple(sorted(names))


def inspect_wheel(path: Path, target: str, python_tag: str) -> tuple[KernelCell, tuple[str, ...]] | None:
    """Return the found cell and binary names, or ``None`` for a non-kernel wheel."""

    if not path.is_file() or path.is_symlink() or path.suffix != ".whl":
        raise ValueError("kernel wheel must be a regular .whl file")
    if path.stat().st_size > MAX_WHEEL_BYTES:
        raise ValueError("wheel archive exceeds the compressed size limit")
    _, _, _, tags = parse_wheel_filename(path.name)
    with zipfile.ZipFile(path) as archive:
        infos = _safe_infos(archive)
        matching = any(tag.interpreter == python_tag and _matching_platform(target, tag.platform) for tag in tags)
        if not matching:
            return None
        binaries = _binary_names(archive, infos, target)
    if not binaries:
        return None
    return KernelCell(target, python_tag, path), binaries


def scan_bundle(
    directory: Path,
    proofs: Mapping[str, dict],
    targets: Mapping[str, object] | Iterable[str],
    python_tags: Iterable[str] = DEFAULT_PYTHON_TAGS,
) -> tuple[KernelMatrix, dict[tuple[str, str], tuple[str, ...]]]:
    """Inspect target receipts and return the matrix plus binary evidence."""

    target_names = _names(targets)
    tags = _python_tags(python_tags)
    required = required_cells(target_names, tags)
    found: list[KernelCell] = []
    binaries: dict[tuple[str, str], tuple[str, ...]] = {}
    for target in target_names:
        proof = proofs.get(target)
        if not isinstance(proof, dict):
            raise ValueError(f"kernel target receipt missing: {target}")
        for item in proof.get("wheels", []):
            filename = item.get("file") if isinstance(item, dict) else None
            if not isinstance(filename, str) or Path(filename).name != filename:
                raise ValueError("kernel target receipt has an invalid wheel filename")
            path = directory / filename
            for python_tag in tags:
                result = inspect_wheel(path, target, python_tag)
                if result is None:
                    continue
                cell, names = result
                if cell.key in binaries:
                    raise ValueError(f"multiple compiled kernel wheels for {cell.target}/{cell.python_tag}")
                found.append(cell)
                binaries[cell.key] = names
    return KernelMatrix(required, found), binaries


def receipt_cells(matrix: KernelMatrix, binaries: Mapping[tuple[str, str], Iterable[str]]) -> list[dict[str, object]]:
    """Serialize complete found-cell evidence for the aggregate receipt."""

    missing = missing_cells(matrix)
    if missing:
        raise KernelCellMissing(missing)
    found = {cell.key: cell for cell in matrix.found}
    return [
        {
            "target": cell.target,
            "python_tag": cell.python_tag,
            "wheel": found[cell.key].wheel.name if found[cell.key].wheel else None,
            "binary_files": sorted(binaries[cell.key]),
        }
        for cell in matrix.required
    ]
