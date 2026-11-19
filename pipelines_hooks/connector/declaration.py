"""A connector's own declaration: ``[tool.pipelines.connector]`` in ``pyproject.toml``.

``profile`` names the surface the connector serves:

* ``full`` (the default): tools, data resources, prompts, tool-use contracts, links and data locations, plus the
  packaged skills and ontology (``reference/connector-surface.md``);
* ``content-only``: packaged skills and skill files only. It still needs the one entry point, packaged skills, an
  ontology that rolls up to core, SHACL shapes and a server that builds with no tool, so the engine attaches its
  pack; it needs no tool, resource, prompt, tool-use contract, link or data location.

``vendored`` lists repository paths (a file or a directory) that hold third-party content kept byte-identical to its
source. The content checks of ``connector-standard`` (codespell, the skill path check and the surface stray-skill
count) leave them out. A vendored path must exist, stay inside the repository and leave the package itself checked.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from pipelines_hooks.connector import project

PROFILES = ("full", "content-only")
CONTENT_ONLY = "content-only"
KEYS = frozenset({"profile", "vendored"})
TABLE = "[tool.pipelines.connector]"


@dataclass(frozen=True)
class Declaration:
    """The validated table; ``errors`` holds one line per refused value (the defaults then apply)."""

    profile: str = "full"
    vendored: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def content_only(self) -> bool:
        return self.profile == CONTENT_ONLY

    def is_vendored(self, path: str) -> bool:
        """True when ``path`` (relative, ``/``-separated) is a vendored path or lies under one."""
        return any(path == v or path.startswith(v + "/") for v in self.vendored)


def _vendored(raw: Any, root: Path, package: str | None, errors: list[str]) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(isinstance(v, str) for v in raw):
        errors.append(f"{TABLE} vendored must be a list of repository paths")
        return ()
    kept: list[str] = []
    for value in raw:
        path = PurePosixPath(value.strip().rstrip("/"))
        text = path.as_posix()
        if not value.strip() or path.is_absolute() or ".." in path.parts or text == ".":
            errors.append(f"{TABLE} vendored path {value!r} must be a relative path inside the repository")
        elif not (root / text).exists():
            errors.append(f"{TABLE} vendored path {text!r} does not exist")
        elif package and (text == package or package.startswith(text + "/")):
            errors.append(f"{TABLE} vendored path {text!r} covers the package {package!r}; name the vendored folder")
        elif text in kept:
            errors.append(f"{TABLE} vendored path {text!r} is listed twice")
        else:
            kept.append(text)
    return tuple(kept)


def read(pyproject: dict[str, Any], root: Path, package: str | None = None) -> Declaration:
    """The declaration of the connector whose parsed ``pyproject.toml`` is ``pyproject``; ``package`` is relative."""
    table = pyproject.get("tool", {}).get("pipelines", {}).get("connector", {})
    if not isinstance(table, dict):
        return Declaration(errors=(f"{TABLE} must be a table",))
    errors: list[str] = []
    unknown = sorted(set(table) - KEYS)
    if unknown:
        errors.append(f"{TABLE} has unknown keys: {', '.join(unknown)}")
    profile = table.get("profile", "full")
    if profile not in PROFILES:
        errors.append(f"{TABLE} profile {profile!r} is not one of: {', '.join(PROFILES)}")
        profile = "full"
    vendored = _vendored(table.get("vendored", []), root, package, errors)
    return Declaration(profile=profile, vendored=vendored, errors=tuple(errors))


def for_root(root: Path) -> Declaration:
    """The declaration of the connector checkout at ``root``; its package is the connector entry point's module."""
    pyproject = project.load(root)
    return read(pyproject, root, project.package_dir(root, pyproject).relative_to(root).as_posix())
