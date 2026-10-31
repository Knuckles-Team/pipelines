"""spec-templates: the repository's ``.specify/templates/`` equals the vended templates.

Pipelines owns the spec templates. A consumer repository holds a byte-identical copy in
``.specify/templates/`` so that authors and tools find them at the upstream location. The
gate fails on a missing, changed or unknown file; ``--write`` copies the vended files.
``specs/_template/`` is not a template location and is a finding of ``spec-standard``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pipelines_hooks
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root

#: Repository-relative location of the templates, in pipelines and in every consumer.
TEMPLATES = Path(".specify") / "templates"


def vended_source() -> Path:
    """The canonical templates: packaged in a wheel, or the pipelines checkout's own directory."""
    package = Path(pipelines_hooks.__file__).resolve().parent
    for candidate in (package / "spec_templates", package.parent / TEMPLATES):
        if candidate.is_dir():
            return candidate
    raise CannotRun("the vended spec templates are not installed with pipelines_hooks")


def _names(directory: Path) -> set[str]:
    return {p.name for p in directory.iterdir() if p.is_file() and p.suffix == ".md"} if directory.is_dir() else set()


def mismatches(source: Path, destination: Path) -> list[str]:
    """How ``destination`` diverges from ``source``: missing, changed and unknown files."""
    wanted = _names(source)
    if not wanted:
        raise CannotRun(f"no vended spec templates in {source}")
    out = []
    for name in sorted(wanted):
        target = destination / name
        if not target.is_file():
            out.append(f"{TEMPLATES.as_posix()}/{name} is missing")
        elif target.read_bytes() != (source / name).read_bytes():
            out.append(f"{TEMPLATES.as_posix()}/{name} differs from the vended template")
    out += [f"{TEMPLATES.as_posix()}/{n} is not a vended template" for n in sorted(_names(destination) - wanted)]
    return out


def write(source: Path, destination: Path) -> None:
    """Copy every vended file and delete every unknown one."""
    destination.mkdir(parents=True, exist_ok=True)
    for name in _names(source):
        (destination / name).write_bytes((source / name).read_bytes())
    for name in _names(destination) - _names(source):
        (destination / name).unlink()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="spec-templates", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path, default=None, help="vended templates (default: this pipelines install)")
    parser.add_argument("--write", action="store_true", help="copy the vended templates instead of checking")
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    source = args.source or vended_source()
    destination = root / TEMPLATES
    if args.write:
        write(source, destination)
        print(f"spec-templates: wrote {len(_names(source))} template(s)")
        return 0
    found = mismatches(source, destination)
    for finding in found:
        print(f"spec-templates: {finding}", file=sys.stderr)
    if found:
        print(
            "spec-templates: FAIL: run `python scripts/sync_spec_templates.py` from a pipelines checkout",
            file=sys.stderr,
        )
        return 1
    print("spec-templates: clean")
    return 0
