"""Stable constants for the public documentation contract."""

from __future__ import annotations

import re

README_MIN_CHARS = 1_500
README_MAX_CHARS = 24_000
README_MAX_LINES = 200
AGENTS_MIN_CHARS = 1_200
AGENTS_MAX_CHARS = 24_000
AGENTS_MAX_LINES = 240

README_HEADINGS = (
    "overview",
    "key capabilities",
    "quick start",
    "architecture",
    "documentation",
    "development",
    "license",
)
AGENTS_HEADINGS = (
    "what this repository owns",
    "architecture and module map",
    "commands",
    "quality gates",
    "development rules",
    "documentation",
    "branching & isolation",
)

REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
DISTRIBUTION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
HEADING_RE = re.compile(
    r"^ {0,3}(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE
)
IMAGE_RE = re.compile(
    r"!\[([^\]]*)\]\(\s*(<[^>]+>|[^\s)]+)"
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)"
)
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(\s*([^\s)]+|<[^>]+>)")
WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")
ABSOLUTE_WORKSPACE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9])/(?:home|tmp|private/tmp|workspace|Users|mnt)/[^\s`)>\]]+",
    re.IGNORECASE,
)

HISTORY_PATTERNS = (
    re.compile(r"\b(?:migration|migrations)[ \t]+waves?\b", re.IGNORECASE),
    re.compile(r"\brefactor[ -]+program\b", re.IGNORECASE),
    re.compile(
        r"\b(?:legacy|historical|superseded|formerly|previously)\b", re.IGNORECASE
    ),
    re.compile(r"\b(?:before|after)[ \t]+the[ \t]+refactor\b", re.IGNORECASE),
    re.compile(
        r"\b(?:old|former)[ \t]+(?:architecture|path|implementation)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bused[ \t]+to\b", re.IGNORECASE),
    re.compile(r"\bRF-ADR(?:-|\b)", re.IGNORECASE),
    re.compile(r"\bCHECKPOINT-\d{4}-\d{2}-\d{2}\b", re.IGNORECASE),
    re.compile(
        r"(?:^|[\s`(])plans/(?:refactor|_archive)(?:[/)`\s]|$)", re.IGNORECASE
    ),
    re.compile(r"(?:^|[\s`(])\.specify(?:[/)`\s]|$)", re.IGNORECASE),
)

GITHUB_BADGES: tuple[tuple[str, str], ...] = (
    ("GitHub Repo stars", "https://img.shields.io/github/stars/{repository}"),
    ("GitHub forks", "https://img.shields.io/github/forks/{repository}"),
    ("GitHub contributors", "https://img.shields.io/github/contributors/{repository}"),
    ("GitHub license", "https://img.shields.io/github/license/{repository}"),
    (
        "GitHub last commit (by committer)",
        "https://img.shields.io/github/last-commit/{repository}",
    ),
    ("GitHub pull requests", "https://img.shields.io/github/issues-pr/{repository}"),
    (
        "GitHub closed pull requests",
        "https://img.shields.io/github/issues-pr-closed/{repository}",
    ),
    ("GitHub issues", "https://img.shields.io/github/issues/{repository}"),
    ("GitHub top language", "https://img.shields.io/github/languages/top/{repository}"),
    ("GitHub language count", "https://img.shields.io/github/languages/count/{repository}"),
    ("GitHub repo size", "https://img.shields.io/github/repo-size/{repository}"),
    (
        "GitHub repo file count (file type)",
        "https://img.shields.io/github/directory-file-count/{repository}",
    ),
)
PYPI_BADGES: tuple[tuple[str, str], ...] = (
    ("PyPI - Version", "https://img.shields.io/pypi/v/{distribution}"),
    ("PyPI - Downloads", "https://img.shields.io/pypi/dd/{distribution}"),
    ("PyPI - License", "https://img.shields.io/pypi/l/{distribution}"),
    ("PyPI - Wheel", "https://img.shields.io/pypi/wheel/{distribution}"),
    (
        "PyPI - Implementation",
        "https://img.shields.io/pypi/implementation/{distribution}",
    ),
)
MCP_BADGE = ("MCP Server", "https://badge.mcpx.dev?type=server")
