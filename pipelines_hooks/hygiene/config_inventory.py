"""config-inventory: every declared project carries the four standard configuration roles.

A declaration (``.config/project-config.toml``) lists the projects and their
rendering parameters.  Each project must carry four roles -- ``version-bump``,
``pre-commit``, ``project-metadata`` and ``pytest`` -- as managed sections
bounded by ``# pipelines:managed`` / ``# pipelines:end`` markers.  Two roles may
share ``pyproject.toml`` through distinct sections.  ``--check`` (the hook) reads
the staged snapshot and never writes; ``--render DEST`` renders the packaged
versioned templates into a new directory.  A template receipt is reproducibility
evidence for the managed section, not proof of who authored it.
"""

from __future__ import annotations

import argparse
import configparser
import hashlib
import re
import string
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import blob_bytes, repo_root
from pipelines_hooks.core.tracked import tracked_paths
from pipelines_hooks.hygiene import config_inventory_docs as docs

DECLARATION = ".config/project-config.toml"
TEMPLATE_VERSION = "1"
#: role -> (file, template, parser, section)
ROLES: dict[str, tuple[str, str, str, str]] = {
    "version-bump": (".bumpversion.cfg", "bumpversion.cfg.tmpl", "ini", "bumpversion:file:pyproject.toml"),
    "pre-commit": (".pre-commit-config.yaml", "pre-commit-config.yaml.tmpl", "yaml", "repos"),
    "project-metadata": ("pyproject.toml", "pyproject.toml.tmpl", "toml", "project"),
    "pytest": ("pyproject.toml", "pyproject.toml.tmpl", "toml", "tool.pytest.ini_options"),
}
#: Versioned templates, kept in code so an installed hook needs no data files.
TEMPLATES: dict[str, str] = {
    "pyproject.toml.tmpl": """[build-system]
requires = ["setuptools>=84.0.0"]
build-backend = "setuptools.build_meta"

[project]
# pipelines:managed role=project-metadata template=1
name = "$name"
requires-python = ">=$python"
readme = "README.md"
# pipelines:end role=project-metadata
version = "0.0.0"

[tool.pytest.ini_options]
# pipelines:managed role=pytest template=1
testpaths = ["tests"]
addopts = "-p no:cacheprovider"
# pipelines:end role=pytest
""",
    "pre-commit-config.yaml.tmpl": """# pipelines:managed role=pre-commit template=1
repos:
  - repo: https://github.com/Knuckles-Team/pipelines
    rev: main
    hooks:
      - id: root-hygiene
# pipelines:end role=pre-commit
""",
    "bumpversion.cfg.tmpl": """[bumpversion]
current_version = 0.0.0
commit = False
tag = False

# pipelines:managed role=version-bump template=1
[bumpversion:file:pyproject.toml]
search = version = "{current_version}"
replace = version = "{new_version}"
# pipelines:end role=version-bump
""",
}
PARAMETERS = ("name", "python")
#: Evidence lines of the last documentation check (printed by ``main``).
_DOC_LINES: list[str] = []
_BLOCK = r"# pipelines:managed role={role} template=(?P<template>\S+)\n(?P<body>.*?)# pipelines:end role={role}\n"


@dataclass(frozen=True)
class TemplateReceipt:
    """Reproducibility evidence for one managed section of one project role."""

    project: str
    role: str
    path: str
    section: str
    parser: str
    template: str
    params_digest: str
    expected_digest: str
    observed_digest: str | None

    def line(self) -> str:
        return (
            f"receipt project={self.project} role={self.role} path={self.path} section={self.section} "
            f"parser={self.parser} template={self.template} params={self.params_digest} "
            f"expected={self.expected_digest} observed={self.observed_digest or 'absent'}"
        )


@dataclass(frozen=True)
class ProjectConfigInventory:
    """The declared project set: canonical paths, schema versions and rendering parameters."""

    template: str
    projects: dict[str, dict[str, str]]
    documentation: docs.DocPolicy | None = None

    def __post_init__(self) -> None:
        if self.template != TEMPLATE_VERSION:
            raise CannotRun(f"config-inventory: unknown template version {self.template!r}")
        if not self.projects:
            raise CannotRun("config-inventory: no project is declared")
        for path, params in self.projects.items():
            pure = PurePosixPath(path)
            if pure.is_absolute() or ".." in pure.parts or "\\" in path or not path:
                raise CannotRun(f"config-inventory: unsafe project path {path!r}")
            if set(params) != set(PARAMETERS) or not all(isinstance(v, str) and v for v in params.values()):
                raise CannotRun(f"config-inventory: project {path!r} must declare exactly {', '.join(PARAMETERS)}")

    def file_of(self, project: str, role: str) -> str:
        name = ROLES[role][0]
        return name if project == "." else f"{project}/{name}"

    def params_digest(self, project: str) -> str:
        blob = "\0".join(f"{k}={self.projects[project][k]}" for k in PARAMETERS) + f"\0template={self.template}"
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def load_inventory(root: Path) -> ProjectConfigInventory:
    raw = blob_bytes(root, f":{DECLARATION}")
    if raw is None:
        raise CannotRun(f"config-inventory: {DECLARATION} is not in the snapshot")
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"config-inventory: {DECLARATION} is unreadable: {exc}") from exc
    if set(data) - {"schema", "template", "project", "documentation"} or data.get("schema") != 1:
        raise CannotRun("config-inventory: unsupported schema or unknown top-level fields")
    projects: dict[str, dict[str, str]] = {}
    for entry in data.get("project", []):
        if set(entry) - {"path", "parameters"}:
            raise CannotRun("config-inventory: unknown project fields")
        path = str(entry.get("path", ""))
        if path in projects:
            raise CannotRun(f"config-inventory: duplicate authority for project {path!r}")
        projects[path] = dict(entry.get("parameters", {}))
    policy = docs.parse_policy(data["documentation"]) if "documentation" in data else None
    return ProjectConfigInventory(str(data.get("template", "")), projects, policy)


def _template(role: str) -> str:
    return TEMPLATES[ROLES[role][1]]


def render_file(inventory: ProjectConfigInventory, project: str, role: str) -> str:
    try:
        return string.Template(_template(role)).substitute(inventory.projects[project])
    except (KeyError, ValueError, OSError) as exc:
        raise CannotRun(f"config-inventory: cannot render {role}: {exc}") from exc


def _block(text: str, role: str) -> re.Match[str] | None:
    return re.search(_BLOCK.format(role=re.escape(role)), text, re.S)


def _parse(parser: str, text: str) -> object:
    if parser == "toml":
        return tomllib.loads(text)
    if parser == "yaml":
        return yaml.safe_load(text)
    ini = configparser.ConfigParser(interpolation=None)
    ini.read_string(text)
    return ini


def _required_ok(role: str, parsed: object) -> bool:
    if role == "project-metadata":
        project = parsed.get("project", {}) if isinstance(parsed, dict) else {}
        return bool(project.get("name") and project.get("requires-python"))
    if role == "pytest":
        return isinstance(parsed, dict) and "ini_options" in parsed.get("tool", {}).get("pytest", {})
    if role == "pre-commit":
        return isinstance(parsed, dict) and isinstance(parsed.get("repos"), list)
    return isinstance(parsed, configparser.ConfigParser) and parsed.has_option("bumpversion", "current_version")


def check(
    root: Path, inventory: ProjectConfigInventory, *, scope: str = "all"
) -> tuple[list[str], list[TemplateReceipt]]:
    """Findings (exit 1) and one receipt per project role; every declared project is validated."""
    findings: list[str] = []
    if scope == "documentation":
        if inventory.documentation is None:
            return findings, []
        findings, lines = docs.check_docs(root, inventory.projects, inventory.documentation)
        _DOC_LINES[:] = lines
        return findings, []
    receipts: list[TemplateReceipt] = []
    for project in inventory.projects:
        pdigest = inventory.params_digest(project)
        parsed_files: dict[str, object] = {}
        for role, (_name, _tmpl, parser, section) in ROLES.items():
            path = inventory.file_of(project, role)
            raw = blob_bytes(root, f":{path}")
            expected = _block(render_file(inventory, project, role), role)
            assert expected is not None, f"template for {role} lacks its managed section"
            want = _digest(expected.group("body"))
            if raw is None:
                findings.append(f"{path}: project {project!r} role {role}: required file is missing")
                receipts.append(
                    TemplateReceipt(project, role, path, section, parser, TEMPLATE_VERSION, pdigest, want, None)
                )
                continue
            text = raw.decode("utf-8", errors="replace")
            if path not in parsed_files:
                try:
                    parsed_files[path] = _parse(parser, text)
                except (tomllib.TOMLDecodeError, yaml.YAMLError, configparser.Error) as exc:
                    parsed_files[path] = exc
                    findings.append(f"{path}: invalid {parser} format: {str(exc).splitlines()[0][:80]}")
            found = _block(text, role)
            observed = _digest(found.group("body")) if found else None
            receipts.append(
                TemplateReceipt(project, role, path, section, parser, TEMPLATE_VERSION, pdigest, want, observed)
            )
            line = text[: found.start()].count("\n") + 1 if found else 1
            if found is None:
                findings.append(f"{path}:1: project {project!r} role {role}: managed section {section} is missing")
            elif found.group("template") != TEMPLATE_VERSION:
                findings.append(f"{path}:{line}: project {project!r} role {role}: template version drift")
            elif observed != want:
                findings.append(f"{path}:{line}: project {project!r} role {role}: managed section {section} drifted")
            parsed = parsed_files[path]
            if not isinstance(parsed, Exception) and not _required_ok(role, parsed):
                findings.append(
                    f"{path}:{line}: project {project!r} role {role}: required fields of {section} are absent"
                )
    if inventory.documentation is not None:
        doc_findings, lines = docs.check_docs(root, inventory.projects, inventory.documentation)
        findings.extend(doc_findings)
        _DOC_LINES[:] = lines
    declared = set(inventory.projects)
    for found_root in discovered_projects(root):
        if found_root not in declared:
            findings.append(f"{found_root}: project root is not in the declared inventory")
    return findings, receipts


def discovered_projects(root: Path) -> list[str]:
    roots = {str(PurePosixPath(p).parent) for p in tracked_paths(root, ("pyproject.toml", "**/pyproject.toml"))}
    return sorted(roots)


def render(inventory: ProjectConfigInventory, dest: Path) -> list[Path]:
    """Render every declared project's files into the new directory ``dest``."""
    if dest.exists():
        raise CannotRun(f"config-inventory: refusing to overwrite existing destination {dest}")
    if ".git" in dest.parts or any(part == ".." for part in dest.parts):
        raise CannotRun(f"config-inventory: unsafe destination {dest}")
    written: list[Path] = []
    for project in inventory.projects:
        for role in ROLES:
            target = dest / inventory.file_of(project, role)
            if target in written:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(render_file(inventory, project, role), encoding="utf-8")
            written.append(target)
    if inventory.documentation is not None:
        for project, params in inventory.projects.items():
            content = inventory.documentation.content or "pages"
            files = {
                docs.doc_file(project, role, content): docs.render_role(role, params, content) for role in docs.ROLES
            }
            files.update({docs._join(project, rel): text for rel, text in docs.render_pages(params, content).items()})
            for rel, text in files.items():
                target = dest / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
                written.append(target)
    return written


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="config-inventory", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="validate the staged snapshot (default)")
    mode.add_argument("--render", type=Path, metavar="DEST", help="render templates into a new directory")
    parser.add_argument(
        "--scope", choices=("all", "documentation"), default="all", help="documentation: only the documentation roles"
    )
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    inventory = load_inventory(root)
    if args.render is not None:
        for path in render(inventory, args.render):
            print(f"rendered {path}")
        return 0
    findings, receipts = check(root, inventory, scope=args.scope)
    print(f"projects: declared={sorted(inventory.projects)} discovered={discovered_projects(root)}")
    for receipt in receipts:
        print(receipt.line())
    for line in _DOC_LINES:
        print(line)
    if not findings:
        print("config inventory: clean")
        return 0
    print("FAIL: project configuration inventory.")
    for finding in findings:
        print(f"  - {finding}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
