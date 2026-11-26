"""Prove each declared coding harness bundle on the tagged commit (PIPE-RELEASE-R028.1, R028.3).

A repository declares its bundles in ``pyproject.toml``::

    [tool.pipelines.harness_bundles]
    command = "mytool bundle"            # run as: <command> --harness <id> --out <tmp>
    output = "harness-bundles"           # the generated-output directory the untracked gate watches
    catalog = "catalog/entries.json"     # optional: a tracked file of command or pinned-package sources

    [tool.pipelines.harness_bundles.profiles.claude]
    validator = "claude plugin validate --strict {out}"   # optional; {out} is the temporary tree
    structural = ["plugin.json"]                          # the check that runs when the validator is not installed

The proof builds each profile into a temporary tree, validates it, scans it for credentials and deletes it. Nothing is
uploaded. ``CATALOG_SOURCE_INVALID`` names a catalog entry that is not a command source running the released command or a
package source pinned to the tag version.
"""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipelines_hooks.connector.secret_scan import VALUE_PATTERNS  # noqa: E402

TABLE = ("tool", "pipelines", "harness_bundles")
_MAX_FILE = 2_000_000


def load_declaration(root: Path) -> dict | None:
    """The declared ``[tool.pipelines.harness_bundles]`` table, or None when the repository declares none."""
    document = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    node = document
    for key in TABLE:
        node = node.get(key) if isinstance(node, dict) else None
        if node is None:
            return None
    if not isinstance(node.get("command"), str) or not isinstance(node.get("profiles"), dict) or not node["profiles"]:
        raise ValueError("harness_bundles needs a command and at least one profile")
    return node


def _tree_tokens(out: Path) -> list[str]:
    found = []
    for path in sorted(p for p in out.rglob("*") if p.is_file()):
        text = path.read_bytes()[:_MAX_FILE].decode("utf-8", "replace")
        found += [f"{path.relative_to(out)}: {name}" for name, pattern in VALUE_PATTERNS if pattern.search(text)]
    return found


def _structural(out: Path, required: list[str]) -> list[str]:
    if not required:
        return [] if any(out.iterdir()) else ["the bundle is empty"]
    return [f"missing {name}" for name in required if not (out / name).exists()]


def prove(profile_id: str, profile: dict, command: str, workdir: Path) -> list[str]:
    """Problems for one profile: build, validate (or the structural check), credential scan. The tree is deleted."""
    with tempfile.TemporaryDirectory(prefix="harness-bundle-") as tmp:
        out = Path(tmp) / profile_id
        build = subprocess.run(
            [*shlex.split(command), "--harness", profile_id, "--out", str(out)], cwd=workdir, check=False
        )
        if build.returncode:
            return [f"{profile_id}: the bundle command exited {build.returncode}"]
        if not out.is_dir():
            return [f"{profile_id}: the bundle command wrote no tree"]
        validator = shlex.split(profile.get("validator", "").replace("{out}", str(out)))
        if validator and shutil.which(validator[0]):
            checked = subprocess.run(validator, cwd=workdir, check=False)
            problems = [f"{profile_id}: the validator exited {checked.returncode}"] if checked.returncode else []
        else:
            problems = [f"{profile_id}: {p}" for p in _structural(out, list(profile.get("structural", [])))]
        problems += [f"{profile_id}: credential in {t}" for t in _tree_tokens(out)]
    return problems


def check_catalog(path: Path, version: str, command: str) -> list[str]:
    """``CATALOG_SOURCE_INVALID`` findings for a declared catalog file."""
    entries = json.loads(path.read_text(encoding="utf-8")).get("entries", [])
    problems = []
    for index, entry in enumerate(entries):
        source = entry.get("source") if isinstance(entry, dict) else None
        label = f"{path.name}[{index}] {entry.get('name', '?') if isinstance(entry, dict) else '?'}"
        if not isinstance(source, dict):
            problems.append(f"CATALOG_SOURCE_INVALID {label}: a relative path or committed tree is not a source")
        elif source.get("type") == "command":
            if not str(source.get("command", "")).startswith(command):
                problems.append(f"CATALOG_SOURCE_INVALID {label}: the command is not the released bundle command")
        elif source.get("type") == "package":
            if source.get("version") != version:
                problems.append(f"CATALOG_SOURCE_INVALID {label}: version {source.get('version')} is not {version}")
        else:
            problems.append(f"CATALOG_SOURCE_INVALID {label}: source type {source.get('type')} is not allowed")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path.cwd())
    ap.add_argument("--version", default="", help="the tag version; defaults to [project].version")
    args = ap.parse_args(argv)
    try:
        declaration = load_declaration(args.root)
        if declaration is None:
            print("no harness bundles declared")
            return 0
        version = args.version or tomllib.loads((args.root / "pyproject.toml").read_text())["project"]["version"]
        problems: list[str] = []
        for profile_id, profile in sorted(declaration["profiles"].items()):
            problems += prove(profile_id, profile, declaration["command"], args.root)
        catalog = declaration.get("catalog")
        if catalog:
            problems += check_catalog(args.root / catalog, version, declaration["command"])
    except (OSError, ValueError, KeyError) as exc:
        print(f"CANNOT RUN: {exc}", file=sys.stderr)
        return 2
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
