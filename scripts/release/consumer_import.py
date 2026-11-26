"""After an engine release, prove the newest released SDK still imports against it (PIPE-RELEASE-R024).

The check installs the new engine and the newest released SDK into a fresh environment and imports every public module
of the SDK. A removed engine symbol that the SDK uses fails the check and names the symbol. A released package that
depends on the engine should declare a ceiling at the next breaking engine release; the check reports a missing one.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path

from packaging.requirements import Requirement

from .errors import ReleaseError

_SYMBOL = re.compile(r"cannot import name '([^']+)'|has no attribute '([^']+)'|No module named '([^']+)'")
_PROBE = """
import importlib, importlib.metadata, json, pkgutil, sys
root = importlib.import_module(sys.argv[1])
failures = []
names = [root.__name__]
for info in pkgutil.walk_packages(getattr(root, "__path__", []), root.__name__ + "."):
    if not any(part.startswith("_") for part in info.name.split(".")):
        names.append(info.name)
for name in names:
    try:
        importlib.import_module(name)
    except Exception as exc:
        failures.append({"module": name, "error": f"{type(exc).__name__}: {exc}"})
print(json.dumps({"failures": failures, "requires": importlib.metadata.requires(sys.argv[2]) or []}))
"""

Install = Callable[[Path, list[str]], None]
Probe = Callable[[Path, str, str], dict]


def removed_symbol(error: str) -> str:
    """The symbol an import error names (the missing name, else the whole message)."""
    found = _SYMBOL.search(error)
    return next((g for g in found.groups() if g), error) if found else error


def missing_ceiling(requires: Iterable[str], engine: str) -> bool:
    """True when the package depends on the engine without an upper bound (``<`` or ``<=`` or ``~=`` or ``==``)."""
    for text in requires:
        req = Requirement(text)
        if req.name.lower().replace("_", "-") == engine.lower().replace("_", "-") and req.marker is None:
            return not any(s.operator in ("<", "<=", "~=", "==") for s in req.specifier)
    return False


def _install(venv: Path, specs: list[str]) -> None:
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    subprocess.run([str(venv / "bin/python"), "-m", "pip", "install", "--quiet", *specs], check=True)


def _probe(venv: Path, package: str, distribution: str) -> dict:
    done = subprocess.run(
        [str(venv / "bin/python"), "-I", "-c", _PROBE, package, distribution],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode:
        raise ReleaseError(f"the import probe failed: {done.stderr.strip()[-300:]}")
    return json.loads(done.stdout)


def check_consumer_import(
    engine: str, sdk: str, package: str, *, install: Install = _install, probe: Probe = _probe
) -> list[str]:
    """Findings (a missing ceiling); raises ``ReleaseError`` naming the removed symbol when the SDK fails to import.

    ``engine`` and ``sdk`` are pip requirement specs; ``package`` is the SDK's top-level import name.
    """
    engine_name = Requirement(engine).name
    sdk_name = Requirement(sdk).name
    with tempfile.TemporaryDirectory(prefix="consumer-import-") as tmp:
        venv = Path(tmp) / "venv"
        install(venv, [engine, sdk])
        result = probe(venv, package, sdk_name)
    if result["failures"]:
        first = result["failures"][0]
        raise ReleaseError(
            f"removed symbol {removed_symbol(first['error'])}: {first['module']} fails to import: {first['error']}"
        )
    return (
        [f"{sdk_name} declares no ceiling on {engine_name}"] if missing_ceiling(result["requires"], engine_name) else []
    )
