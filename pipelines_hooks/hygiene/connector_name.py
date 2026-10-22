"""connector-name: every connector name literal agrees with the declared fleet name.

A connector declares its fleet name (the name arbora onboards it under and
epistemic-graph files its pack under, for example ``searxng-mcp``) once, as
the single entry point of the ``agent_connector_sdk.connector`` group in
``pyproject.toml``. This gate reads that declaration and every literal that
also names the connector:

* ``connector`` in each packaged ``connector_manifest.yml``;
* ``connector`` in each ``connectors/tool_schema_fingerprints.json``;
* ``connector="..."`` in a ``ConnectorContent(...)`` or ``IngestBinding(...)`` call.

A literal that disagrees with the declaration fails the gate. A repository
that declares no name but carries a literal gets a warning only, so the
fleet can adopt the declaration repository by repository; ``--strict`` makes
that warning a failure. A repository with neither passes.
"""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from collections.abc import Iterator
from pathlib import Path

GROUP = "agent_connector_sdk.connector"
_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "build", "dist", ".pipeline-theme", "tests"}
_MANIFEST_CONNECTOR = re.compile(r"""^\s*["']?connector["']?\s*:\s*["']?([^"',\s]+)""", re.MULTILINE)
_CALL = re.compile(r"\b(?:ConnectorContent|IngestBinding)\s*\(")
_CONNECTOR_KWARG = re.compile(r"""\bconnector\s*=\s*["']([^"']+)["']""")


def declared_name(root: Path) -> str | None:
    """The fleet name ``pyproject.toml`` declares, or ``None``."""
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return None
    document = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    group = document.get("project", {}).get("entry-points", {}).get(GROUP, {})
    if len(group) > 1:
        raise ValueError(f"pyproject.toml declares {len(group)} {GROUP} names; exactly one is allowed")
    return next(iter(group), None)


def _files(root: Path, pattern: str) -> Iterator[Path]:
    for path in sorted(root.rglob(pattern)):
        if not _SKIP_DIRS.intersection(path.relative_to(root).parts[:-1]):
            yield path


def _call_literals(text: str) -> Iterator[str]:
    for call in _CALL.finditer(text):
        window = text[call.end() : call.end() + 400]
        depth, end = 1, len(window)
        for index, char in enumerate(window):
            depth += {"(": 1, ")": -1}.get(char, 0)
            if depth == 0:
                end = index
                break
        match = _CONNECTOR_KWARG.search(window[:end])
        if match:
            yield match.group(1)


def literals(root: Path) -> list[tuple[str, str]]:
    """Every ``(relative path, name)`` literal that names the connector."""
    found: list[tuple[str, str]] = []
    for path in _files(root, "connector_manifest.yml"):
        match = _MANIFEST_CONNECTOR.search(path.read_text(encoding="utf-8", errors="replace"))
        if match:
            found.append((str(path.relative_to(root)), match.group(1)))
    for path in _files(root, "tool_schema_fingerprints.json"):
        try:
            name = json.loads(path.read_text(encoding="utf-8")).get("connector")
        except (ValueError, AttributeError):
            continue
        if isinstance(name, str):
            found.append((str(path.relative_to(root)), name))
    for path in _files(root, "*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        found.extend((str(path.relative_to(root)), name) for name in _call_literals(text))
    return found


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="connector-name", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--strict", action="store_true", help="fail an undeclared connector")
    arguments = parser.parse_args(argv)
    root: Path = arguments.root
    try:
        declared = declared_name(root)
    except ValueError as exc:
        print(f"connector-name: FAIL: {exc}")
        return 1
    found = literals(root)
    if declared is None:
        if not found:
            return 0
        names = sorted({name for _, name in found})
        level = "FAIL" if arguments.strict else "WARN"
        print(f"connector-name: {level}: no {GROUP} entry point declares the fleet name; literals name {names}")
        return 1 if arguments.strict else 0
    wrong = [(path, name) for path, name in found if name != declared]
    for path, name in wrong:
        print(f"connector-name: FAIL {path}: names {name!r}, the declared fleet name is {declared!r}")
    return 1 if wrong else 0
