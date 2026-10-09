"""Shared regex vocabulary for the generated spec-status lifecycle (SPEC-STATUS-LIFECYCLE.md)."""

from __future__ import annotations

import re

#: SPECIFIED < LANDED < VERIFIED; RETIRED is excluded from rollup comparisons.
ORDER = {"SPECIFIED": 0, "LANDED": 1, "VERIFIED": 2}

ID = r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-R?\d{2,3}(?:\.\d+)*"
ROW_RE = re.compile(r"^\|\s*`?(" + ID + r")`?\s*\|(.*)$")
RANGE_RE = re.compile(
    r"([A-Z][A-Z0-9-]*-)R(\d{3})\s*(?:\.\.|–|—|-|through|to)\s*R?(\d{3})"
)
BIND_RE = re.compile(
    r"(?://|#)\s*spec:\s*(" + ID + r"(?:\s*,\s*" + ID + r")*)|mark\.spec\(([^)]*)\)"
)
#: Exact-token match: ``R019`` never matches ``R019.1`` -- the trailing group is greedy.
TOKEN_RE = re.compile(r"(?<![A-Za-z0-9-])(" + ID + r")(?![0-9])")
NON_PRODUCT_PREFIXES = ("specs/", "docs/", ".github/")
#: A ``R019..R021``-style range spans at most this many requirement IDs.
MAX_RANGE_SPAN = 60


#: ``X-R001.1, R001.2``: a bare ``R###`` inherits the nearest preceding full prefix on its line.
SHORTHAND_RE = re.compile(
    r"(?<![A-Za-z0-9-])([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-)R\d{3}"
    r"|(?<![A-Za-z0-9-])(R\d{3}(?:\.\d+)*)(?![0-9])"
)


def _line_shorthand(line: str) -> list[str]:
    """Full IDs for the bare ``R###`` tokens in one line (none before the first prefix)."""
    prefix, found = None, []
    for match in SHORTHAND_RE.finditer(line):
        if match.group(1):
            prefix = match.group(1)
        elif prefix:
            found.append(prefix + match.group(2))
    return found


def expand_ranges(text: str) -> str:
    """Append the IDs any ``R019..R021`` range spans and any same-line shorthand names."""
    extra: list[str] = []
    for line in text.splitlines():
        extra += _line_shorthand(line)
    for prefix, start, end in RANGE_RE.findall(text):
        start_n, end_n = int(start), int(end)
        if 0 < end_n - start_n <= MAX_RANGE_SPAN:
            extra += [f"{prefix}R{n:03d}" for n in range(start_n, end_n + 1)]
    return text + "\n" + " ".join(extra)


def is_product_path(path: str) -> bool:
    """A commit touching only specs/docs/.github or a markdown file delivers nothing."""
    return not path.startswith(NON_PRODUCT_PREFIXES) and not path.endswith(".md")
