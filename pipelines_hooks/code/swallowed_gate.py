"""swallowed-errors: no cause-dropping exception handler ADDED by a change.

A handler that does not re-raise is a violation unless it already has a trail
back to the real cause: a justified ``# noqa: BLE001 - <reason>`` on the
``except`` line (a bare marker is not accepted), or cause-preserving logging at
a level someone watches. Flagged shapes:

* ``bare_except`` -- ``except:`` also catches SystemExit/KeyboardInterrupt;
  enforced at an absolute zero;
* ``pass`` -- ``except <Type>: pass``;
* ``return_none`` -- a lone bare ``return`` with no log call;
* ``log_type_name_only`` -- every log call reduces the exception to its class name;
* ``debug_only_swallow`` -- the only cause-preserving log call is at DEBUG,
  which is off in production.

A typed, narrow fallback doing ordinary control flow is not flagged.
"""

from __future__ import annotations

import ast
import re

from pipelines_hooks.code import sitegate
from pipelines_hooks.code.swallowed_calls import cause_level, log_calls, type_name_only

JUSTIFIED_RE = re.compile(r"#\s*noqa:\s*BLE001\s*[-—:]\s*\S")


def _body_shape(body: list[ast.stmt], bound: str | None, source: str) -> str | None:
    lone = body[0] if len(body) == 1 else None
    if isinstance(lone, ast.Pass):
        return "pass"
    if isinstance(lone, ast.Return) and lone.value is None:
        return None if log_calls(body) else "return_none"
    return "log_type_name_only" if type_name_only(body, bound, source) else None


def handler_shape(node: ast.ExceptHandler, except_line: str, source: str) -> str | None:
    """The violation shape of one handler, or ``None``."""
    if JUSTIFIED_RE.search(except_line):
        return None
    if node.type is None:
        return "bare_except"
    if any(isinstance(n, ast.Raise) for n in ast.walk(ast.Module(body=node.body, type_ignores=[]))):
        return None
    level = cause_level(node.body, node.name, source)
    if level != "none":
        return None if level == "loud" else "debug_only_swallow"
    return _body_shape(node.body, node.name, source)


def scan_source(rel: str, source: str) -> list[sitegate.Site]:
    """Every violating handler; the diff key is (caught types, shape, except-line text)."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    lines = source.splitlines()
    sites = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        text = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
        shape = handler_shape(node, text, source)
        if shape:
            caught = "<bare>" if node.type is None else re.sub(r"\s+", " ", ast.unparse(node.type))
            sites.append(sitegate.Site(rel, node.lineno, shape, f"[{shape}] except {caught}: {text.strip()}"))
    return sites


GATE = sitegate.SiteGate(
    name="swallowed-errors",
    scan_source=scan_source,
    hard_zero=frozenset({"bare_except"}),
    include=lambda rel: True,
    remedy=(
        "Each handler must log the real cause at a level someone watches (pass the exception, not "
        "type(exc).__name__, and not ONLY at logger.debug), re-raise, or document a deliberate "
        "best-effort swallow with `# noqa: BLE001 - <reason>`."
    ),
)


def main(argv: list[str]) -> int:
    return sitegate.run(GATE, argv)
