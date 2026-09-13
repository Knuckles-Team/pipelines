"""stdout-writes: no ``print()`` or ``sys.stdout.write()`` in a served stdio surface.

On the stdio transport real stdout IS the JSON-RPC channel, and code that runs
before serving starts has no runtime protection, so the fix is never writing to
stdout there. ``[tool.pipelines_hooks.stdout_writes] served_paths`` names the
served surface; a repository that serves nothing over stdio does not adopt
this hook. ``print(..., file=<not sys.stdout>)`` is not a stdout write.
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

from pipelines_hooks.core.config import load_config, string_tuple
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.tracked import tracked_or_walked


def _is_sys_stdout(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "stdout" and getattr(node.value, "id", None) == "sys"


def stdout_write(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name) and func.id == "print":
        target = next((keyword.value for keyword in call.keywords if keyword.arg == "file"), None)
        return "print(...)" if target is None or _is_sys_stdout(target) else None
    if isinstance(func, ast.Attribute) and func.attr == "write" and _is_sys_stdout(func.value):
        return "sys.stdout.write(...)"
    return None


def scan(root: Path) -> list[str]:
    served = string_tuple(load_config(root).section("stdout_writes").get("served_paths", []), "stdout_writes.served_paths")
    if not served:
        raise CannotRun("[tool.pipelines_hooks.stdout_writes] declares no served_paths")
    errors = []
    for path in (p for base in served for p in tracked_or_walked(root / base, ("*.py",), root=root)):
        rel = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except (SyntaxError, UnicodeError) as exc:
            raise CannotRun(f"cannot parse {rel}: {exc}") from exc
        errors.extend(
            f"{rel}:{node.lineno}: {kind} writes to stdout"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and (kind := stdout_write(node))
        )
    return errors


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="stdout-writes", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    errors = scan(repo_root(parser.parse_args(argv).root))
    for error in errors:
        print(f"  {error}")
    if errors:
        print("Stdout write(s) found in the served surface: route diagnostics through logging (stderr).")
        return 1
    print("stdout-writes: OK: no stdout writes in the served surface")
    return 0
