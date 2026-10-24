"""connector-version: the version lives in ``pyproject.toml`` alone; this command reads and bumps it.

    pipelines-connector version [--root R] read
    pipelines-connector version [--root R] bump {major,minor,patch}
    pipelines-connector version [--root R] set X.Y.Z

Only the ``version = "..."`` line of the ``[project]`` table changes; no other file is touched.
Every other consumer reads package metadata (``importlib.metadata.version``).
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun

_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_LINE = re.compile(r'^(version\s*=\s*)"([^"]+)"(\s*(?:#.*)?)$')


def _project_version_line(lines: list[str]) -> int:
    in_project = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("["):
            in_project = stripped == "[project]"
        elif in_project and _LINE.match(line.rstrip("\n")):
            return index
    raise CannotRun("pyproject.toml has no static [project] version line")


def read_version(root: Path) -> str:
    lines = (root / "pyproject.toml").read_text(encoding="utf-8").splitlines()
    match = _LINE.match(lines[_project_version_line(lines)])
    assert match is not None
    return match.group(2)


def bumped(version: str, part: str) -> str:
    if not _VERSION.match(version):
        raise CannotRun(f"version {version!r} is not MAJOR.MINOR.PATCH")
    major, minor, patch = (int(piece) for piece in version.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def write_version(root: Path, version: str) -> str:
    """Rewrite the one version line; returns the previous version."""
    path = root / "pyproject.toml"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    index = _project_version_line(lines)
    match = _LINE.match(lines[index].rstrip("\n"))
    assert match is not None
    newline = "\n" if lines[index].endswith("\n") else ""
    lines[index] = f'{match.group(1)}"{version}"{match.group(3)}{newline}'
    path.write_text("".join(lines), encoding="utf-8")
    return match.group(2)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="connector-version", description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("read")
    bump = sub.add_parser("bump")
    bump.add_argument("part", choices=("major", "minor", "patch"))
    setter = sub.add_parser("set")
    setter.add_argument("version")
    args = parser.parse_args(argv)
    root = args.root
    if args.command == "read":
        print(read_version(root))
        return 0
    new = bumped(read_version(root), args.part) if args.command == "bump" else str(args.version)
    if not _VERSION.match(new):
        raise CannotRun(f"version {new!r} is not MAJOR.MINOR.PATCH")
    old = write_version(root, new)
    print(f"{old} -> {new}")
    return 0
