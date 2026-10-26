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


def _binary_names(path: Path, target: str) -> tuple[str, ...]:
    if target not in _PLATFORM_PATTERNS:
        raise ValueError(f"unknown kernel target: {target}")
    suffixes = _BINARY_SUFFIXES
    with zipfile.ZipFile(path) as archive:
        return tuple(
            sorted(
                name
                for name in archive.namelist()
                if not name.endswith("/")
                and ".dist-info/" not in name
                and ".data/" not in name
                and name.lower().endswith(suffixes)
            )
        )


def inspect_wheel(path: Path, target: str, python_tag: str) -> tuple[KernelCell, tuple[str, ...]] | None:
    """Return the found cell and binary names, or ``None`` for a non-kernel wheel."""

    if not path.is_file() or path.is_symlink() or path.suffix != ".whl":
        raise ValueError("kernel wheel must be a regular .whl file")
    _, _, _, tags = parse_wheel_filename(path.name)
    binaries = _binary_names(path, target)
    if not binaries:
        return None
    for tag in sorted(tags, key=str):
        if tag.interpreter != python_tag or not _matching_platform(target, tag.platform):
            continue
        return KernelCell(target, python_tag, path), binaries
    return None


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
