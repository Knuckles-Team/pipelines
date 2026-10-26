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


# The target readiness proof is currently pinned to CPython 3.14.  Publishers
# may pass another explicit tuple to ``required_cells``/``scan_bundle`` when a
# product's reviewed matrix supports a different Python range.
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


def _valid_elf(data: bytes, target: str) -> bool:
    machines = {"linux-x86_64": 0x3E, "linux-aarch64": 0xB7}
    if len(data) < 64 or data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 1 or data[6] != 1:
        return False
    return struct.unpack_from("<H", data, 18)[0] == machines.get(target)


def _valid_macho(data: bytes) -> bool:
    if len(data) < 8:
        return False
    magic = data[:4]
    if magic == b"\xcf\xfa\xed\xfe":  # 64-bit little-endian Mach-O
        return struct.unpack_from("<I", data, 4)[0] == 0x0100000C
    if magic == b"\xfe\xed\xfa\xcf":  # 64-bit big-endian Mach-O
        return struct.unpack_from(">I", data, 4)[0] == 0x0100000C
    if magic not in {b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"} or len(data) < 8:
        return False
    endian = ">" if magic == b"\xca\xfe\xba\xbe" else "<"
    count = struct.unpack_from(endian + "I", data, 4)[0]
    if count > 64 or len(data) < 8 + count * 20:
        return False
    return any(struct.unpack_from(endian + "I", data, 8 + index * 20)[0] == 0x0100000C for index in range(count))


def _valid_pe(data: bytes) -> bool:
    if len(data) < 0x40 or data[:2] != b"MZ":
        return False
    offset = struct.unpack_from("<I", data, 0x3C)[0]
    return (
        offset + 6 <= len(data)
        and data[offset : offset + 4] == b"PE\x00\x00"
        and struct.unpack_from("<H", data, offset + 4)[0] == 0x8664
    )


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
