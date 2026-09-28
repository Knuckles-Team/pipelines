"""A README must tell a new reader how to install or start the project (lenient)."""

from __future__ import annotations

import re

from pipelines_hooks.docs.public_surface_constants import HEADING_RE, QUICK_START_HEADING_RE

_FENCED_CODE = re.compile(r"(?ms)^ {0,3}(`{3,}|~{3,})[^\n]*\n(.*?)^ {0,3}\1[ \t]*$")
_INSTALL_COMMAND = re.compile(
    r"^\s*(?:[$>]\s*)?(?:"
    r"python(?:\d+(?:\.\d+)?)?\s+-m\s+pip\s+install|pip\d*\s+install|"
    r"uv\s+(?:sync|pip\s+install|tool\s+install|add)|uvx\b|pipx\s+(?:install|run)|"
    r"cargo\s+(?:install|build|add)|npm\s+(?:install|ci|i)\b|pnpm\s+(?:install|i|add)\b|"
    r"yarn\s+(?:install|add)|bun\s+(?:install|add)|git\s+clone|docker\s+(?:pull|build|run)|"
    r"docker\s+compose\s+(?:build|up)|helm\s+install|kubectl\s+apply|brew\s+install|make\b|"
    r"scripts/bootstrap\.sh|\./scripts/bootstrap\.sh)",
    re.IGNORECASE | re.MULTILINE,
)


def _outside_fences(text: str) -> str:
    return _FENCED_CODE.sub("", text)


def findings(readme: str) -> list[str]:
    """Empty when a quick-start/install heading or a fenced install command exists."""
    headings = [match.group(2) for match in HEADING_RE.finditer(_outside_fences(readme))]
    if any(QUICK_START_HEADING_RE.search(heading) for heading in headings):
        return []
    if any(_INSTALL_COMMAND.search(block) for _, block in _FENCED_CODE.findall(readme)):
        return []
    return ["README.md has no quick start: add an Install/Quick start/Usage section or a fenced install command"]
