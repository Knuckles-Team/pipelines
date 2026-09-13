"""no-stub: production packages carry no stub markers and no unmarked NotImplementedError.

Fails on the placeholder markers in :data:`BANNED_SUBSTRINGS` (a mock string
return, a dummy embedding, an equal-weight fallback) and on any real
NotImplementedError raise (read from the AST, so a mention in a string or
comment is not a finding) unless it is inside an
``@abstractmethod``, carries ``# ABSTRACT-OK`` on its line, or is a declared
contract seam. Scans the declared packages, skipping ``tests`` and ``scripts``.
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

from pipelines_hooks.code.stub_rules import declared_seams, is_abstract, is_not_implemented, seam_constant
from pipelines_hooks.core.config import load_config
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.tracked import tracked_or_walked

BANNED_SUBSTRINGS = (
    '"[Mock]',
    "[Mock]'",
    "dummy_embedding",
    "Fallback equal-weight",
    "equal weighting since",
)
SKIP_DIRECTORIES = frozenset({"__pycache__", ".venv", "tests", "scripts"})


def _marker_findings(rel: str, lines: list[str]) -> list[str]:
    return [
        f"{rel}:{number}: stub marker {needle!r}"
        for number, line in enumerate(lines, 1)
        if not line.lstrip().startswith(("#", '"', "'"))
        for needle in BANNED_SUBSTRINGS
        if needle in line
    ]


def _unimplemented_raises(tree: ast.AST) -> list[ast.Raise]:
    """``raise NotImplementedError`` nodes outside any ``@abstractmethod``."""
    abstract = {
        id(node) for function in ast.walk(tree)
        if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)) and is_abstract(function)
        for node in ast.walk(function)
    }
    return [n for n in ast.walk(tree) if isinstance(n, ast.Raise) and is_not_implemented(n.exc) and id(n) not in abstract]


def _raise_findings(rel: str, tree: ast.AST, *, lines: list[str], seams: frozenset[str]) -> list[str]:
    findings = []
    for node in _unimplemented_raises(tree):
        if seam_constant(node) in seams:
            print(f"NOT DONE (declared contract seam): {rel}:{node.lineno}: {lines[node.lineno - 1].strip()}")
        elif "# ABSTRACT-OK" not in lines[node.lineno - 1]:
            findings.append(f"{rel}:{node.lineno}: raise NotImplementedError (mark abstract with # ABSTRACT-OK)")
    return findings


def scan(root: Path, packages: tuple[str, ...]) -> list[str]:
    seams = declared_seams(root)
    findings = []
    for path in (p for package in packages for p in tracked_or_walked(root / package, ("*.py",), root=root)):
        rel = path.relative_to(root).as_posix()
        if any(part in SKIP_DIRECTORIES for part in Path(rel).parts):
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        lines = source.splitlines()
        findings.extend(_marker_findings(rel, lines))
        try:
            findings.extend(_raise_findings(rel, ast.parse(source), lines=lines, seams=seams.get(rel, frozenset())))
        except SyntaxError as exc:
            findings.append(f"{rel}:{exc.lineno}: unparseable source cannot be proven stub-free")
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="no-stub", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = repo_root(parser.parse_args(argv).root)
    findings = scan(root, load_config(root).required_packages())
    for finding in sorted(findings):
        print(f"  - {finding}")
    if findings:
        print("No-stub gate FAILED.")
        return 1
    print("no-stub: OK: no stub markers in production code")
    return 0
