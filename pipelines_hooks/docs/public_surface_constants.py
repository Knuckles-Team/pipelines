"""Markdown patterns shared by the public documentation gate."""

from __future__ import annotations

import re

HEADING_RE = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(\s*(<[^>]+>|[^\s)]+)(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)")
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(\s*([^\s)]+|<[^>]+>)")
WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")
#: A heading that introduces the first-run path (any level, case-insensitive).
QUICK_START_HEADING_RE = re.compile(
    r"\b(?:quick[ -]?start|getting started|install(?:ation|ing)?|setup|set up|usage)\b", re.IGNORECASE
)
