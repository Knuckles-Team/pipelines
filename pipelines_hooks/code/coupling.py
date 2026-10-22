"""Check configured static import boundaries in tracked consumer packages.

This AST check does not resolve dynamic imports or prove runtime isolation.
"""

from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path

from pipelines_hooks.core.config import load_config, string_tuple
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.paths import relative_to_root, under_any
from pipelines_hooks.core.tracked import tracked_paths


def _prefixes(value: object, label: str) -> tuple[str, ...]:
    prefixes = string_tuple(value, label)
    if any(not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", item) for item in prefixes):
        raise CannotRun(f"{label} must contain dotted Python module names")
    return prefixes


def _matches(module: str, prefixes: tuple[str, ...]) -> bool:
    return any(module == prefix or module.startswith(prefix + ".") for prefix in prefixes)


def _imports(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            # Include the imported member: `from arbora import client` is legal,
            # but `from arbora import runtime` must not bypass a denied parent.
            for alias in node.names:
                yield node.lineno, node.module + "." + alias.name


def scan(root: Path) -> list[str]:
    root = root.resolve()
    if repo_root(root).resolve() != root:
        raise CannotRun("--root must identify the consumer repository root")
    config = load_config(root)
    section = config.section("coupling")
    denied = _prefixes(section.get("forbidden", []), "coupling.forbidden")
    allowed = _prefixes(section.get("allowed", []), "coupling.allowed")
    if not denied:
        raise CannotRun("coupling.forbidden must declare the consumer boundary")
    if any(not _matches(prefix, denied) or prefix in denied for prefix in allowed):
        raise CannotRun("coupling.allowed must name strict submodules of forbidden prefixes")
    packages = []
    for package in config.required_packages():
        try:
            relative = relative_to_root(package, root)
        except ValueError as exc:
            raise CannotRun(str(exc)) from exc
        if not relative or not (root / relative).is_dir():
            raise CannotRun(f"package directory is missing or invalid: {package}")
        packages.append(relative)
    files = [
        p for p in tracked_paths(root, preserve_index=False) if p.endswith(".py") and under_any(p, tuple(packages))
    ]
    if any(not any(under_any(p, (package,)) for p in files) for package in packages):
        raise CannotRun("every configured package must contain tracked Python source")
    findings = []
    for relative in files:
        path = root / relative
        if not path.exists() and not path.is_symlink():
            continue  # tracked deletion is not surviving source
        if not path.resolve().is_relative_to(root):
            raise CannotRun(f"source escapes the consumer repository: {relative}")
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        except (OSError, UnicodeError, SyntaxError) as exc:
            raise CannotRun(f"cannot parse {relative}: {exc}") from exc
        for line, module in _imports(tree):
            if _matches(module, denied) and not _matches(module, allowed):
                findings.append(f"{relative}:{line}: prohibited import {module}")
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    findings = scan(args.root)
    for finding in findings:
        print(finding)
    return 1 if findings else 0
