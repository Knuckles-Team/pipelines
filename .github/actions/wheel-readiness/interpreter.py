"""The Python minor version the readiness proof runs on for this repository.

Default 3.14, the fleet standard. A repository whose runtime dependency truly
blocks 3.14 declares ``[tool.pipelines] readiness-python = "3.12"`` (or
"3.13") in its pyproject.toml; nothing below the 3.12 floor is accepted.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

DEFAULT = "3.14"
SUPPORTED = ("3.12", "3.13", "3.14")


def readiness_python(project: Path | None = None) -> str:
    path = (project or Path.cwd()) / "pyproject.toml"
    if not path.is_file():
        return DEFAULT
    section = tomllib.loads(path.read_text()).get("tool", {}).get("pipelines", {})
    value = section.get("readiness-python", DEFAULT) if isinstance(section, dict) else DEFAULT
    if value not in SUPPORTED:
        raise ValueError(f"readiness-python must be one of {', '.join(SUPPORTED)}")
    return value


if __name__ == "__main__":
    try:
        print(readiness_python())
    except (ValueError, tomllib.TOMLDecodeError) as error:
        print(f"Release readiness blocked: {error}", file=sys.stderr)
        raise SystemExit(1) from error
