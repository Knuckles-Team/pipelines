"""Markdown text checks for the public documentation gate."""

from __future__ import annotations

import re

from pipelines_hooks.docs.public_surface_config import PublicSurfaceConfig
from pipelines_hooks.docs.public_surface_constants import (
    ABSOLUTE_WORKSPACE_PATH_RE,
    AGENTS_HEADINGS,
    AGENTS_MAX_CHARS,
    AGENTS_MAX_LINES,
    AGENTS_MIN_CHARS,
    GITHUB_BADGES,
    HISTORY_PATTERNS,
    IMAGE_RE,
    MCP_BADGE,
    PYPI_BADGES,
    README_HEADINGS,
    README_MAX_CHARS,
    README_MAX_LINES,
    README_MIN_CHARS,
    HEADING_RE,
)


def heading_names(text: str) -> set[str]:
    return {
        re.sub(r"\s+", " ", match.group(2).strip(" #\t").lower())
        for match in HEADING_RE.finditer(text)
    }


def required_headings(text: str, *, agents: bool) -> list[str]:
    required = AGENTS_HEADINGS if agents else README_HEADINGS
    return [heading for heading in required if heading not in heading_names(text)]


def line_findings(name: str, text: str, *, agents: bool) -> list[str]:
    if agents:
        minimum, maximum, max_lines = AGENTS_MIN_CHARS, AGENTS_MAX_CHARS, AGENTS_MAX_LINES
    else:
        minimum, maximum, max_lines = README_MIN_CHARS, README_MAX_CHARS, README_MAX_LINES
    findings: list[str] = []
    chars = len(text)
    lines = len(text.splitlines())
    if chars < minimum or chars > maximum:
        findings.append(f"{name} is {chars} characters; expected {minimum}..{maximum}")
    if lines > max_lines:
        findings.append(f"{name} is {lines} lines; maximum is {max_lines}")
    return findings


def h1_count(text: str) -> int:
    return sum(1 for line in text.splitlines() if re.match(r"^ {0,3}#(?!#)[ \t]+", line))


def _badge_pairs(text: str) -> list[tuple[str, str]]:
    return [
        (match.group(1).strip(), match.group(2).strip("<>"))
        for match in IMAGE_RE.finditer(text)
    ]


def _expected_badges(config: PublicSurfaceConfig) -> dict[str, str]:
    definitions = list(GITHUB_BADGES)
    if config.distribution:
        definitions.extend(PYPI_BADGES)
    expected = {
        alt: url.format(repository=config.repository, distribution=config.distribution or "")
        for alt, url in definitions
    }
    if config.mcp_server:
        expected[MCP_BADGE[0]] = MCP_BADGE[1]
    return expected


def _badge_mismatch(expected: dict[str, str], pairs: list[tuple[str, str]]) -> list[str]:
    actual: dict[str, list[str]] = {}
    for alt, url in pairs:
        actual.setdefault(alt, []).append(url)
    findings: list[str] = []
    for alt, url in expected.items():
        values = actual.get(alt, [])
        if not values:
            findings.append(f"README is missing badge {alt!r} with the canonical offline URL")
        elif values != [url]:
            findings.append(f"README badge {alt!r} must use exactly {url!r}")
    return findings


def badge_findings(text: str, config: PublicSurfaceConfig) -> list[str]:
    pairs = _badge_pairs(text)
    findings = _badge_mismatch(_expected_badges(config), pairs)
    if not config.mcp_server and any(url.startswith(MCP_BADGE[1].split("?")[0]) for _, url in pairs):
        findings.append("README must not advertise the MCP Server badge when mcp_server=false")
    return findings


def forbidden_findings(name: str, text: str) -> list[str]:
    findings: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if ABSOLUTE_WORKSPACE_PATH_RE.search(line):
            findings.append(f"{name}:{line_number} contains an absolute workspace path")
        if "file://" in line.lower():
            findings.append(f"{name}:{line_number} contains a file:// URL")
        if any(pattern.search(line) for pattern in HISTORY_PATTERNS):
            findings.append(f"{name}:{line_number} exposes internal planning/history language")
    return findings
