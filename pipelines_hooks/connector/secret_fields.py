"""secret-fields: a connector's served surface never carries credential material.

Three checks, one report (``reference/connector-surface.md``, constitution Article XX):

1. Response models (``BaseModel``, ``TypedDict``, dataclasses, outside input
   models) in the connector package: a secret-named field is marked redacted or
   secret-bearing (``secret_scan``).
2. JSON schemas tracked in the package, and with ``--probe`` the output schema
   of every tool the built server registers (the served-tools probe of
   ``served_tools``): a secret-named property carries ``x-redacted``,
   ``x-secret-bearing`` or ``writeOnly``.
3. Recorded tool outputs (tracked ``.json``/``.yaml``/``.yml`` under ``tests/``):
   no credential-shaped value and no filled secret-named key.

A finding line is ``<file>:<line> <code> <field or kind>``; a value is never
printed. Policy ``[tool.pipelines_hooks.secret_fields]``: ``mode`` is ``staged``
(print, exit 0; the default while the fleet is cleaned) or ``blocking`` (exit
1 on any finding); ``exclude`` is an array of glob patterns. No baseline and no
allowance. Exit 2: the gate could not run (a ``--probe`` that cannot build the
server is ``Unavailable``: SKIPPED locally, exit 2 in CI).
"""

from __future__ import annotations

import argparse
import json
import subprocess
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

from pipelines_hooks.connector import secret_scan
from pipelines_hooks.connector.secret_scan import Leak
from pipelines_hooks.connector.served_tools import TIMEOUT_SECONDS, connector_package, interpreter
from pipelines_hooks.core.config import load_config, string_tuple
from pipelines_hooks.core.errors import CannotRun, Unavailable
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.tracked import tracked_paths

MARKER = "PIPELINES-SERVED-OUTPUTS:"
PROBE = (
    """
import json, sys
from scion_sdk.connector import build_server
from scion_sdk.mcp.tool_surface import registered_tools
_, mcp = build_server(sys.argv[1], command_args=["--transport", "stdio"])
out = {name: (getattr(tool, "output_schema", None) or {}) for name, tool in sorted(registered_tools(mcp).items())}
print("%s" + json.dumps(out))
"""
    % MARKER
)
RECORDED_SUFFIXES = (".json", ".yaml", ".yml")


def _policy(root: Path) -> tuple[str, tuple[str, ...]]:
    section = load_config(root).section("secret_fields")
    mode = section.get("mode", "staged")
    if mode not in {"staged", "blocking"}:
        raise CannotRun("[tool.pipelines_hooks.secret_fields] mode must be staged or blocking")
    exclude = string_tuple(section["exclude"], "secret_fields.exclude") if section.get("exclude") else ()
    return str(mode), exclude


def _read(root: Path, path: str) -> str:
    try:
        return (root / path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CannotRun(f"cannot read {path}: {exc}") from exc


def _input_module(parts: tuple[str, ...]) -> bool:
    """Request-model modules and bundled skill scripts are not served responses."""
    return "skills" in parts or any(word in parts[-1] for word in ("input", "request", "params"))


def static_leaks(root: Path, package: str, exclude: tuple[str, ...]) -> list[Leak]:
    """Checks 1 and 2 (tracked schemas) and 3 over the tracked files."""
    found: list[Leak] = []
    for path in tracked_paths(root):
        if any(fnmatch(path, pattern) for pattern in exclude):
            continue
        parts = PurePosixPath(path).parts
        if parts[0] == package and path.endswith(".py") and not _input_module(parts):
            found += secret_scan.model_leaks(path, _read(root, path))
        elif parts[0] == package and path.endswith(".json"):
            try:
                found += secret_scan.schema_leaks(path, json.loads(_read(root, path)))
            except ValueError:
                continue
        elif parts[0] == "tests" and path.endswith(RECORDED_SUFFIXES):
            found += secret_scan.recorded_leaks(path, _read(root, path))
    return found


def served_output_leaks(root: Path, package: str) -> list[Leak]:
    """Check 2 over the output schema of every tool the built server registers."""
    command = [*interpreter(root), "-c", PROBE, package]
    try:
        done = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Unavailable(f"secret-fields: cannot start the connector interpreter: {exc}") from None
    lines = [line for line in done.stdout.splitlines() if line.startswith(MARKER)]
    if done.returncode or not lines:
        reason = (done.stderr.strip().splitlines() or ["no output"])[-1][:300]
        raise Unavailable(f"secret-fields: the server of {package} did not build: {reason}")
    schemas = json.loads(lines[-1][len(MARKER) :])
    return [
        Leak(f"tool:{name}", 1, "SF-SERVED-OUTPUT-FIELD", leak.detail)
        for name, schema in schemas.items()
        for leak in secret_scan.schema_leaks(name, schema)
    ]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="secret-fields", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--probe", action="store_true", help="also build the server and check served output schemas")
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    package = connector_package(root)
    if package is None:
        print("secret-fields: not a connector (no scion_sdk.connector entry point); nothing to check")
        return 0
    mode, exclude = _policy(root)
    found = static_leaks(root, package, exclude)
    if args.probe:
        found += served_output_leaks(root, package)
    for leak in found:
        print(leak.render())
    print(f"secret-fields: {len(found)} finding(s) in {package} (mode {mode})")
    return 1 if found and mode == "blocking" else 0
