"""stubs: no function or class without an implementation, and no deferred-work comment.

AST stubs: a function or base-less class whose body is only docstrings, ``...``,
``pass`` or ``raise NotImplementedError``. Not a stub: an abstract method, any
member of an ``ABC``/``Protocol`` class, an exception class, a file whose name
says ``interface``/``protocol``, a function carrying ``# ABSTRACT-OK``, or a
declared contract seam (printed as NOT DONE). Test files are exempt from the
AST pass, not from the comment pass. Comments are read as real tokens only.
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

from pipelines_hooks.code.stub_rules import declared_seams, is_abstract, is_stub_body, seam_constant, todo_comments
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.tracked import tracked_paths


class StubVisitor(ast.NodeVisitor):
    """Collects stub findings for one parsed file."""

    def __init__(self, lines: list[str], *, seams: frozenset[str], interface_file: bool) -> None:
        self.lines, self.seams, self.interface_file = lines, seams, interface_file
        self.in_abc = False
        self.findings: list[tuple[int, str]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        names = [base.id for base in node.bases if isinstance(base, ast.Name)]
        if any("Error" in n or "Exception" in n for n in [*names, node.name]):
            return
        outer = self.in_abc
        self.in_abc = outer or any(n in ("ABC", "Protocol") for n in names)
        if not node.bases and is_stub_body(node.body):
            self.findings.append((node.lineno, f"Class '{node.name}' has no implementation (is a stub)."))
        self.generic_visit(node)
        self.in_abc = outer

    def _declared_seam(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        """A body of (docstring +) ``raise NotImplementedError(DECLARED_CONST)`` only."""
        raises = [n for n in node.body if isinstance(n, ast.Raise)]
        return bool(raises) and len(node.body) - len(raises) <= 1 and seam_constant(raises[0]) in self.seams

    def _exempt(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        marked = any("# ABSTRACT-OK" in line for line in self.lines[node.lineno - 1 : node.end_lineno])
        return is_abstract(node) or self.interface_file or self.in_abc or marked

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if self._declared_seam(node):
            print(f"NOT DONE (declared contract seam): line {node.lineno}: {node.name}")
            return
        if self._exempt(node):
            return
        if is_stub_body(node.body):
            self.findings.append((node.lineno, f"Function '{node.name}' has no implementation (is a stub)."))
        self.generic_visit(node)

    visit_FunctionDef = _function
    visit_AsyncFunctionDef = _function


def check_file(path: Path, rel: str, seams: frozenset[str]) -> list[tuple[int, str]]:
    source = path.read_text(encoding="utf-8", errors="replace")
    findings = [(line, f"Found '{keyword}' comment") for line, keyword in todo_comments(source)]
    name = Path(rel).name.lower()
    if name.startswith("test_") or "conftest" in name or "tests" in Path(rel).parts:
        return findings
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [*findings, (exc.lineno or 0, f"SyntaxError: {exc.msg}")]
    visitor = StubVisitor(source.splitlines(), seams=seams, interface_file="interface" in name or "protocol" in name)
    visitor.visit(tree)
    return sorted(set(findings + visitor.findings))


def python_files(root: Path, files: list[str]) -> list[str]:
    """The given Python files, or every tracked one outside hidden directories."""
    selected = [name for name in files if name.endswith(".py")]
    tracked = [p for p in tracked_paths(root) if p.endswith(".py") and not any(part.startswith(".") for part in Path(p).parts[:-1])]
    return [name for name in (selected or tracked) if (root / name).is_file()]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="stubs", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    seams = declared_seams(root)
    names = python_files(root, args.files)
    lines = [f"{rel}:{line}: {message}" for rel in names for line, message in check_file(root / rel, rel, seams.get(rel, frozenset()))]
    print("\n".join(lines))
    if lines:
        print(f"STUB & TODO VERIFICATION FAILED: {len(lines)} active stub/TODO item(s)")
        return 1
    print(f"stubs: OK: {len(names)} file(s), no active stubs or deferred work items")
    return 0
