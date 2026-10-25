"""connector-graphql: a connector that imports GraphQL declares it through the SDK extra.

The connector SDK owns the GraphQL transport. Its ``graphql`` extra installs
the protocol client and the query-language core, so a connector declares
GraphQL in one place: ``agent-connector-sdk[graphql]`` (with any other extras)
in ``[project].dependencies``.

This gate applies to a repository whose non-test Python imports ``gql`` or
``graphql``. It reports two findings:

* no core dependency on ``agent-connector-sdk`` with the ``graphql`` extra;
* a direct ``gql`` or ``graphql-core`` requirement in the core dependencies or
  any optional extra, which duplicates the SDK extra.

Findings are warnings by default, so the fleet adopts the extra repository by
repository; ``--strict`` makes them failures. A repository that imports
neither module passes. The SDK itself is exempt.
"""

from __future__ import annotations

import argparse
import ast
import re
import tomllib
from collections.abc import Iterator
from pathlib import Path

from pipelines_hooks.core.distributions import SDK as SDK_ROLE
from pipelines_hooks.core.distributions import is_distribution, project_distribution, requirement_name

SDK = "agent-connector-sdk"  # legacy display/default spelling during the transition
MODULES = frozenset({"gql", "graphql"})
DIRECT = frozenset({"gql", "graphql-core"})
_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "build", "dist", ".pipeline-theme", "tests", "test"}
_REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[([^\]]*)\])?")


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _parse(requirement: str) -> tuple[str, frozenset[str]]:
    match = _REQUIREMENT.match(requirement)
    if not match:
        return "", frozenset()
    extras = frozenset(_normalize(extra.strip()) for extra in (match.group(2) or "").split(",") if extra.strip())
    return requirement_name(match.group(1)), extras


def _python_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root).parts
        if _SKIP_DIRS.intersection(relative[:-1]) or relative[-1].startswith("test_"):
            continue
        yield path


def importers(root: Path) -> list[str]:
    """Relative paths of non-test modules that import ``gql`` or ``graphql``."""
    found: list[str] = []
    for path in _python_files(root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            if any(name.split(".")[0] in MODULES for name in names):
                found.append(str(path.relative_to(root)))
                break
    return found


def findings(root: Path) -> list[str]:
    """Every declaration finding for a repository that imports GraphQL."""
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return []
    project = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {})
    if is_distribution(str(project.get("name", "")), SDK_ROLE):
        return []
    using = importers(root)
    if not using:
        return []
    problems: list[str] = []
    sdk = project_distribution(project, SDK_ROLE)
    core = [_parse(str(item)) for item in project.get("dependencies", [])]
    if not any(is_distribution(name, SDK_ROLE) and "graphql" in extras for name, extras in core):
        problems.append(f"{using[0]} imports GraphQL, but [project].dependencies has no {sdk}[graphql] requirement")
    sections = {"dependencies": project.get("dependencies", [])}
    sections.update(
        {f"optional-dependencies.{key}": value for key, value in project.get("optional-dependencies", {}).items()}
    )
    for section, items in sections.items():
        for item in items:
            name, _ = _parse(str(item))
            if name in DIRECT:
                problems.append(f"[project.{section}] declares {item!r} directly; declare GraphQL via {sdk}[graphql]")
    return problems


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="connector-graphql", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--strict", action="store_true", help="fail instead of warn")
    arguments = parser.parse_args(argv)
    problems = findings(arguments.root)
    level = "FAIL" if arguments.strict else "WARN"
    for problem in problems:
        print(f"connector-graphql: {level}: {problem}")
    return 1 if problems and arguments.strict else 0
