"""Check that a declared environment repository holds no custom code (PIPE-GATES-R089).

An environment repository carries configuration, manifests and declarative
files. A tracked executable script (executable bit or a shebang, outside
``tests``) is allowed only as a thin wrapper: it invokes a published command
with configuration, stays within ``MAX_BODY_LINES`` and has no loop, conditional,
function or short-circuit that encodes behaviour. Behaviour belongs in an
owned ecosystem feature, not here. There is no allowance list.
"""

from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path

from pipelines_hooks.core.config import load_config
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text, nul_split, repo_root
from pipelines_hooks.core.tracked import SKIP_DIRECTORIES

#: Most code lines (not blank, not comment) a thin wrapper may have.
MAX_BODY_LINES = 12
_BEHAVIOUR_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
    ast.IfExp,
    ast.BoolOp,
    ast.Match,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)
_SHELL_BEHAVIOUR = re.compile(
    r"^\s*(?:if|for|while|until|case|select|function)\b|\b(?:then|elif|done|fi|esac)\b|&&|\|\||^\s*\w+\s*\(\)\s*\{"
)


def _scripts(root: Path) -> list[tuple[str, str]]:
    """Tracked (path, text) pairs that are executable or start with a shebang."""
    scripts = []
    for entry in nul_split(git_text(root, ("ls-files", "-s", "-z"), preserve_index=False)):
        meta, _, relative = entry.partition("\t")
        parts = relative.split("/")
        if SKIP_DIRECTORIES & set(parts) or {"tests", "test"} & set(parts[:-1]):
            continue
        path = root / relative
        if not path.is_file() or path.is_symlink():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue  # binary payloads are not scripts
        if meta.startswith("100755") or text.startswith("#!"):
            scripts.append((relative, text))
    return scripts


def _code_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def _python_reason(text: str, relative: str) -> str | None:
    try:
        tree = ast.parse(text, filename=relative)
    except SyntaxError as exc:
        raise CannotRun(f"cannot parse {relative}: {exc}") from exc
    for node in ast.walk(tree):
        if isinstance(node, _BEHAVIOUR_NODES):
            return f"{type(node).__name__} at line {getattr(node, 'lineno', 1)}"
    return None


def _reason(relative: str, text: str) -> str | None:
    """Why this script is not a thin wrapper, or None when it is."""
    lines = _code_lines(text)
    is_python = relative.endswith(".py") or "python" in (text.splitlines() or [""])[0]
    reason = _python_reason(text, relative) if is_python else None
    if is_python is False:
        for number, line in enumerate(text.splitlines(), 1):
            if not line.lstrip().startswith("#") and _SHELL_BEHAVIOUR.search(line):
                reason = f"control flow at line {number}"
                break
    if reason is None and len(lines) > MAX_BODY_LINES:
        reason = f"{len(lines)} code lines, over the {MAX_BODY_LINES} line bound"
    return reason


def scan(root: Path) -> list[str]:
    root = root.resolve()
    if repo_root(root).resolve() != root:
        raise CannotRun("--root must identify the consumer repository root")
    section = load_config(root).section("environment_config_only")
    declared = section.get("declared", False)
    if not isinstance(declared, bool):
        raise CannotRun("environment_config_only.declared must be true or false")
    if not declared:
        return []
    findings = []
    for relative, text in _scripts(root):
        reason = _reason(relative, text)
        if reason:
            findings.append(
                f"{relative}: custom code in an environment repository ({reason}); "
                "file the behaviour as an owned ecosystem feature and call its published command"
            )
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    findings = scan(args.root)
    for finding in findings:
        print(finding)
    return 1 if findings else 0
