"""Local-link and offline URL validation for the public documentation gate."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from pipelines_hooks.docs.public_surface_constants import IMAGE_RE, LINK_RE, WINDOWS_ABSOLUTE_RE


_FENCED_RE = re.compile(r"(?ms)^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?^ {0,3}\1[ \t]*$")


def link_destination(raw: str) -> str:
    """Extract a Markdown link destination, including angle-bracket URLs."""
    value = raw.strip()
    if value.startswith("<") and ">" in value:
        return value[1 : value.index(">")]
    return value


def _destinations(text: str) -> list[str]:
    """Link and image destinations, outside inline code spans."""
    prose = re.sub(r"`[^`\n]*`", "", _FENCED_RE.sub("", text))
    return [link_destination(m.group(1)) for pattern in (LINK_RE, IMAGE_RE) for m in pattern.finditer(prose)]


def local_link_findings(root: Path, text: str, *, name: str = "README.md") -> list[str]:
    """Reject local links and images that escape the repository or point nowhere."""
    findings: list[str] = []
    root = root.resolve()
    for destination in _destinations(text):
        parsed = urlsplit(destination)
        if parsed.scheme or parsed.netloc:
            if parsed.scheme.lower() not in {"http", "https", "mailto", "tel"}:
                findings.append(f"{name} link uses a forbidden URL scheme: {destination!r}")
            continue
        path = unquote(parsed.path)
        if not path:
            continue
        portable_path = path.replace("\\", "/")
        if portable_path.startswith("/") or WINDOWS_ABSOLUTE_RE.match(portable_path):
            findings.append(f"{name} local link is absolute: {destination!r}")
            continue
        target = (root / portable_path).resolve()
        if not target.is_relative_to(root):
            findings.append(f"{name} local link escapes the repository: {destination!r}")
        elif not target.exists():
            findings.append(f"{name} local link does not exist: {destination!r}")
    return findings
