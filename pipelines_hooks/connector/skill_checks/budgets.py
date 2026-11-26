"""Skill size-budget and connector-file check (US-CONTENT-R011, run by PIPE-GATES-R016.120).

A ``description`` above 400 characters (about 100 tokens) fails ``DESCRIPTION_TOO_LONG``. A ``SKILL.md`` body
above 500 lines fails ``BODY_TOO_LONG``. A document that ``SKILL.md`` links from outside ``references/`` fails
``REFERENCE_NOT_STAGED``. A skill folder with a ``.mcp.json`` or an MCP server entry fails
``SKILL_HAS_CONNECTOR_FILE``. The check has no baseline and no suppression.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

MAX_DESCRIPTION, MAX_BODY_LINES = 400, 500
_LINK = re.compile(r"\]\(([^)\s#]+)(?:#[^)]*)?\)")
_DOC_SUFFIXES = {".md", ".txt", ".rst"}
_SERVER_ENTRY = re.compile(r'"mcpServers"|^\s*mcp_servers\s*:|^\s*mcpServers\s*:', re.MULTILINE)
_SCANNED = {".json", ".yml", ".yaml", ".toml", ".md"}


def _split(text: str) -> tuple[dict[str, object], str, int]:
    """Frontmatter mapping, body text and the 1-based line the body starts on."""
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                try:
                    meta = yaml.safe_load("\n".join(lines[1:i])) or {}
                except yaml.YAMLError:
                    meta = {}
                return (meta if isinstance(meta, dict) else {}), "\n".join(lines[i + 1 :]), i + 2
    return {}, text, 1


def lint_folder(folder: Path) -> list[tuple[Path, int, str]]:
    """Findings ``(file, line, code)`` for one skill folder that holds a ``SKILL.md``."""
    skill = folder / "SKILL.md"
    meta, body, first = _split(skill.read_text(encoding="utf-8"))
    found: list[tuple[Path, int, str]] = []
    if len(str(meta.get("description", ""))) > MAX_DESCRIPTION:
        found.append((skill, 1, "DESCRIPTION_TOO_LONG"))
    lines = body.splitlines()
    if len(lines) > MAX_BODY_LINES:
        found.append((skill, first + MAX_BODY_LINES, "BODY_TOO_LONG"))
    for offset, line in enumerate(lines):
        for target in _LINK.findall(line):
            if "://" in target or target.startswith(("mailto:", "/")):
                continue
            path = (folder / target).resolve()
            staged = (folder / "references").resolve()
            if path.suffix in _DOC_SUFFIXES and path.is_file() and staged not in path.parents:
                found.append((skill, first + offset, "REFERENCE_NOT_STAGED"))
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        if path.name == ".mcp.json" or (path.suffix in _SCANNED and _has_server_entry(path)):
            found.append((path, 1, "SKILL_HAS_CONNECTOR_FILE"))
    return found


def _has_server_entry(path: Path) -> bool:
    try:
        return bool(_SERVER_ENTRY.search(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError):
        return False


def lint_tree(skills: Path) -> list[str]:
    """One ``<path>:<line>: <code>`` line per finding under ``skills``."""
    return [
        f"{p}:{n}: {code}"
        for d in sorted(skills.iterdir())
        if (d / "SKILL.md").is_file()
        for p, n, code in lint_folder(d)
    ]


def main(argv: list[str] | None = None) -> int:
    """Exit 0 when clean, 1 on a finding and 2 when the directory cannot be read."""
    args = list(sys.argv[1:] if argv is None else argv)
    root = Path(args[args.index("--root") + 1]) if "--root" in args else Path("universal_skills/skills")
    if not root.is_dir():
        print(f"{root}: unreadable", file=sys.stderr)
        return 2
    found = lint_tree(root)
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
