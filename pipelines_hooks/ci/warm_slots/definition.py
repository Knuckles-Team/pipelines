"""warm-slot-definition: the slot image matches the repository pins and the cache is local (PIPE-GATES-R070).

A warm slot is a container image pinned to the consuming repository's
toolchain (the ``rust-toolchain.toml`` channel and components, the Python
version of ``.python-version``, nextest and sccache) plus a persistent
volume on local solid-state storage that holds the cargo target directory
and a local sccache directory. The volume is never a network filesystem and
never sits inside the checkout, because the checkout cleans ignored files.
"""

from __future__ import annotations

import argparse
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pipelines_hooks.core.errors import CannotRun

if TYPE_CHECKING:
    from pipelines_hooks.ci.warm_slots.config import SlotConfig

#: Filesystem types that are network or shared-block storage, never a slot cache.
NETWORK_FILESYSTEMS = frozenset(
    {
        "nfs",
        "nfs4",
        "cifs",
        "smb",
        "smbfs",
        "smb3",
        "9p",
        "ceph",
        "cephfs",
        "glusterfs",
        "lustre",
        "sshfs",
        "afs",
        "fuse.sshfs",
    }
)
#: The default location of the one slot configuration, relative to the repository root.
DEFAULT_CONFIG = ".config/warm-slots.toml"


@dataclass(frozen=True)
class SlotDefinition:
    """The toolchain one slot image carries."""

    image: str
    rust_channel: str
    rust_components: tuple[str, ...]
    python: str
    nextest: str
    sccache: str

    @classmethod
    def from_mapping(cls, table: Mapping[str, object]) -> SlotDefinition:
        components = table.get("rust_components", ())
        if isinstance(components, str) or not isinstance(components, (list, tuple)):
            raise CannotRun("warm slots: image.rust_components must be a list of strings")
        return cls(
            image=str(table.get("reference", "")),
            rust_channel=str(table.get("rust_channel", "")),
            rust_components=tuple(str(item) for item in components),
            python=str(table.get("python", "")),
            nextest=str(table.get("nextest", "")),
            sccache=str(table.get("sccache", "")),
        )


def _read_toml(path: Path) -> Mapping[str, object]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"warm slots: cannot read {path.name}: {exc}") from None


def _toolchain_pin(root: Path) -> tuple[str, tuple[str, ...]]:
    pin = root / "rust-toolchain.toml"
    if not pin.is_file():
        raise CannotRun("warm slots: the repository has no rust-toolchain.toml to pin the image to")
    table = _read_toml(pin).get("toolchain")
    if not isinstance(table, Mapping) or not table.get("channel"):
        raise CannotRun("warm slots: rust-toolchain.toml names no toolchain channel")
    components = table.get("components", ())
    return str(table["channel"]), tuple(str(item) for item in components) if isinstance(components, list) else ()


def _python_pin(root: Path) -> str:
    pin = root / ".python-version"
    if not pin.is_file():
        raise CannotRun("warm slots: the repository has no .python-version to pin the image to")
    return pin.read_text(encoding="utf-8").strip()


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def check_definition(root: Path, config: SlotConfig) -> list[str]:
    """Findings: an image whose toolchain differs from the pins and any cache path that is not local storage outside the checkout."""
    findings: list[str] = []
    definition = config.definition
    channel, components = _toolchain_pin(root)
    if definition.rust_channel != channel:
        findings.append(
            f"image rust channel {definition.rust_channel or '(none)'} differs from the repository pin {channel}"
        )
    if set(definition.rust_components) != set(components):
        findings.append(
            f"image rust components {sorted(definition.rust_components)} differ from the repository pin {sorted(components)}"
        )
    python = _python_pin(root)
    if definition.python != python:
        findings.append(f"image python {definition.python or '(none)'} differs from the repository pin {python}")
    for tool in ("nextest", "sccache"):
        version = getattr(definition, tool)
        if not version or version.casefold() == "latest":
            findings.append(f"image {tool} is not pinned to a version")
    resolved = root.resolve()
    for pool in config.pools:
        cache = Path(pool.cache_root)
        if not cache.is_absolute() or ".." in cache.parts:
            findings.append(f"pool {pool.name}: cache path {pool.cache_root} must be absolute with no '..'")
        elif _inside(Path(cache.resolve()), resolved):
            findings.append(f"pool {pool.name}: cache path {pool.cache_root} sits inside the checkout")
        if pool.cache_filesystem.casefold() in NETWORK_FILESYSTEMS:
            findings.append(
                f"pool {pool.name}: cache path {pool.cache_root} is on a network filesystem ({pool.cache_filesystem})"
            )
        elif not pool.cache_filesystem:
            findings.append(f"pool {pool.name}: the cache filesystem is not declared (cache_filesystem)")
    return findings


def main(argv: list[str]) -> int:
    from pipelines_hooks.ci.warm_slots.config import load_config

    parser = argparse.ArgumentParser(prog="warm-slot-definition", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, default=None, help=f"the slot configuration (default {DEFAULT_CONFIG})")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    path = args.config or root / DEFAULT_CONFIG
    if not path.is_file():
        print(f"warm-slot-definition: no slot configuration at {path.name}; nothing to check")
        return 0
    findings = check_definition(root, load_config(path))
    if findings:
        print("FAIL: the warm slot definition breaks the repository pins:")
        for finding in findings:
            print(f"    {finding}")
        return 1
    print("warm-slot-definition: OK: the image matches the repository pins and the cache is local")
    return 0
