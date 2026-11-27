"""Name the two things ``connector-release-sign`` needs from a connector checkout (PIPE-RELEASE-R019).

``package-root`` is the connector package directory that receives ``release.json``: the first entry of
``[tool.pipelines_hooks].packages``, else the project name with ``-`` as ``_``. ``script`` is the console
script that starts the connector over stdio: the project name, else ``<name>-mcp``, else the one script ending in
``-mcp``. Anything else is refused, so a release never signs the wrong server.

Usage: ``release_sign_plan.py ROOT package-root|script``. The value goes to stdout; a refusal exits 2.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path


def plan(root: Path) -> dict[str, str]:
    """``{"package-root": ..., "script": ...}`` for the connector at ``root``; ``ValueError`` when ambiguous."""
    try:
        pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"cannot read pyproject.toml: {exc}") from exc
    name = str(pyproject.get("project", {}).get("name", ""))
    scripts = pyproject.get("project", {}).get("scripts", {})
    packages = pyproject.get("tool", {}).get("pipelines_hooks", {}).get("packages") or [name.replace("-", "_")]
    package = str(packages[0])
    if not (root / package).is_dir():
        raise ValueError(f"package directory {package} does not exist")
    candidates = [s for s in (name, f"{name}-mcp") if s in scripts] or [s for s in scripts if s.endswith("-mcp")]
    if len(candidates) != 1:
        raise ValueError(f"cannot pick the connector's stdio script from {sorted(scripts)}")
    return {"package-root": package, "script": candidates[0]}


def main(argv: list[str]) -> int:
    """Print one field of the plan; exit 2 on a refusal."""
    if len(argv) != 3 or argv[2] not in {"package-root", "script"}:
        print("usage: release_sign_plan.py ROOT package-root|script", file=sys.stderr)
        return 2
    try:
        print(plan(Path(argv[1]))[argv[2]])
    except ValueError as exc:
        print(f"release_sign_plan: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
