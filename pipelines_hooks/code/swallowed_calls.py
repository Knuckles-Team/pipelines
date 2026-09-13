"""Log-call analysis for exception handlers: does a handler keep the real cause?

Cause-preserving logging passes the bound exception itself (or ``str``/``repr``
of it) or calls ``logger.exception``. ``exc_info=True`` is not recognised: a
process-wide log-privacy factory in the fleet nulls ``record.exc_info``, so
passing the exception object is the only convention that reaches the output.
"""

from __future__ import annotations

import ast
import re

LOG_METHODS = frozenset({"debug", "info", "warning", "error", "exception", "critical", "warn"})


def log_method(call: ast.Call) -> str | None:
    """``level`` for ``<something with 'log' in its name>.<level>(...)``, else ``None``."""
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr not in LOG_METHODS:
        return None
    base = func.value
    base_name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", None)
    return func.attr if base_name and "log" in base_name.lower() else None


def log_calls(body: list[ast.stmt]) -> list[ast.Call]:
    return [n for n in ast.walk(ast.Module(body=body, type_ignores=[])) if isinstance(n, ast.Call) and log_method(n)]


def _arguments_source(call: ast.Call, source: str) -> str:
    values = [*call.args, *(keyword.value for keyword in call.keywords)]
    return " ".join(ast.get_source_segment(source, value) or "" for value in values)


def _preserves_cause(call: ast.Call, bound: str, source: str) -> bool:
    joined = _arguments_source(call, source)
    name = re.escape(bound)
    if not re.search(rf"\b{name}\b", joined):
        return False
    type_wrapped = re.search(rf"type\(\s*{name}\s*\)|{name}\.__class__", joined)
    return not type_wrapped or bool(re.search(rf"str\(\s*{name}\s*\)|repr\(\s*{name}\s*\)", joined))


def cause_level(body: list[ast.stmt], bound: str | None, source: str) -> str:
    """``loud`` (a non-DEBUG call keeps the cause), ``debug_only``, or ``none``."""
    levels = set()
    for call in log_calls(body):
        method = log_method(call)
        if method == "exception":
            levels.add("loud")
        elif bound is not None and _preserves_cause(call, bound, source):
            levels.add("debug_only" if method == "debug" else "loud")
    return "loud" if "loud" in levels else ("debug_only" if levels else "none")


def _drops_to_type_name(call: ast.Call, bound: str, source: str) -> bool:
    """A call naming the exception CLASS and never the exception itself."""
    name = re.escape(bound)
    type_name = re.compile(rf"type\(\s*{name}\s*\)\.__name__|{name}\.__class__\.__name__")
    joined = _arguments_source(call, source)
    if not type_name.search(joined):
        return False
    return not re.search(rf"(?<![\w.]){name}(?![\w(])", type_name.sub("", joined))


def type_name_only(body: list[ast.stmt], bound: str | None, source: str) -> bool:
    """At least one log call exists and EVERY one drops the cause to a type name."""
    calls = log_calls(body)
    return bool(bound and calls and all(_drops_to_type_name(call, bound, source) for call in calls))
