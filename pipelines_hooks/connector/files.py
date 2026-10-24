"""connector-files: standard connector files are provided by pipelines, never committed.

A connector commits its own version in ``pyproject.toml``, its code, tests, specs and
content. These are rendered, generated or provided centrally and are findings when tracked:

* ``docker/{Dockerfile,debug.Dockerfile,mcp.compose.yml,agent.compose.yml}`` (``connector-render``);
* ``<pkg>/ontology/shapes/connector.shacl.ttl`` and ``<pkg>/ontology/certification.json`` (``connector-generate``);
* ``scripts/security_sanitizer.py`` (the shared ``security-sanitizer`` gate inside ``secrets``);
* ``.codespellignore`` (the shared default list plus ``[tool.pipelines.codespell] ignore_words``);
* ``.bumpversion.cfg`` (the version is ``pyproject.toml`` alone; ``connector-version`` bumps it);
* a ``__version__ = "<project version>"`` literal in a tracked Python file (read package metadata).
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from pipelines_hooks.connector import project
from pipelines_hooks.core.gitenv import nul_split, repo_root, run_git

CENTRAL = {
    "docker/Dockerfile": "rendered at build time by connector-render",
    "docker/debug.Dockerfile": "rendered at build time by connector-render",
    "docker/mcp.compose.yml": "rendered at build time by connector-render",
    "docker/agent.compose.yml": "rendered at build time by connector-render",
    "scripts/security_sanitizer.py": "provided by the shared security-sanitizer gate (the secrets hook)",
    ".codespellignore": "provided as the shared default; extra words go in [tool.pipelines.codespell] ignore_words",
    ".bumpversion.cfg": "not needed: pyproject.toml holds the only version (pipelines-connector version bump)",
}


def tracked(root: Path) -> list[str]:
    result = run_git(root, ("ls-files", "-z"))
    return nul_split(result.stdout) if result.returncode == 0 else []


def findings(root: Path) -> list[str]:
    """One line per central file that is tracked in the repository at ``root``."""
    pyproject = project.load(root)
    files = tracked(root)
    package = project.package_dir(root, pyproject).name
    central = dict(CENTRAL)
    central[f"{package}/ontology/shapes/connector.shacl.ttl"] = "generated at release by connector-generate"
    central[f"{package}/ontology/certification.json"] = "generated at release by connector-generate"
    out = [f"{name} is committed: {why}" for name, why in central.items() if name in files]
    version = str(pyproject.get("project", {}).get("version", ""))
    literal = re.compile(r"""^\s*__version__\s*=\s*['"]""" + re.escape(version) + r"""['"]""", re.M)
    if version:
        for name in files:
            if (
                name.endswith(".py")
                and (root / name).is_file()
                and literal.search((root / name).read_text("utf-8", "replace"))
            ):
                out.append(f"{name} spells the package version; read importlib.metadata.version instead")
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="connector-files", description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = repo_root(parser.parse_args(argv).root)
    found = findings(root)
    for line in found:
        print(f"connector-files: {line}")
    if not found:
        print("connector-files: OK: no standard file is committed")
    return 1 if found else 0
