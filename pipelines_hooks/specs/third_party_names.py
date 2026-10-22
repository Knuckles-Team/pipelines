"""Third-party product and project names in spec text (spec-standard check).

Spec text names our own capability by intent (PIPE-GATES-R005). The denylist and
the per-repository tables live in ``third_party_names.toml`` beside this module. A
connector may name its own target system through the ``[allow]`` table.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.specs.repository_identity import remote_owner

CONFIG = Path(__file__).with_name("third_party_names.toml")

#: Recorded evidence and generated status are data, not authored spec text.
SKIP_DIRS = frozenset({"evidence"})

_FENCE_RE = re.compile(r"^\s*(```|~~~)")
#: Inline code, link targets, URLs and spec or row IDs (``CONN-LANGFUSE-AGENT-R001``).
_MASK_RE = re.compile(
    r"`[^`\n]*`|\]\([^)\s]*\)|<[a-z]+://[^>\s]*>|\b[a-z][a-z0-9+.-]*://\S+"
    r"|\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+(?:\.\d+)*\b"
)
_IDENT_PUNCT = "-_./"


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    term: str

    def render(self, root: Path) -> str:
        rel = self.path.relative_to(root).as_posix()
        return f"{rel}:{self.line}: names third-party product '{self.term}'; describe the capability instead"


def _config(config: Path) -> dict:
    return tomllib.loads(config.read_text(encoding="utf-8"))


def load_terms(repo: str | None, config: Path = CONFIG) -> list[str]:
    """The denylist minus this repository's allowed target-system names."""
    data = _config(config)
    allowed = {t.lower() for t in data.get("allow", {}).get(repo or "", [])}
    return [t for t in data["names"]["terms"] if t.lower() not in allowed]


def compile_terms(terms: Iterable[str]) -> re.Pattern[str] | None:
    alternatives = sorted((re.escape(t).replace(r"\ ", r"\s+") for t in terms), key=len, reverse=True)
    if not alternatives:
        return None
    return re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(alternatives) + r")(?![A-Za-z0-9])", re.IGNORECASE)


def _is_identifier(line: str, start: int, end: int, canonical: dict[str, str]) -> bool:
    """An all-lowercase match is one of our identifiers, not the product's name.

    A connector ID such as ``langfuse`` is lowercase where the product is spelled
    ``Langfuse``. A term whose own spelling is lowercase (``harness2``) is an
    identifier only when glued to identifier punctuation (``-``, ``_``, ``.``, ``/``).
    """
    text = line[start:end]
    if text != text.lower():
        return False
    if canonical.get(" ".join(text.split()), text) != text:
        return True
    before = line[start - 1] if start else ""
    after = line[end] if end < len(line) else ""
    return bool(before and before in _IDENT_PUNCT) or bool(after and after in _IDENT_PUNCT)


def _prose_lines(text: str) -> Iterator[tuple[int, str]]:
    """Lines outside fenced code, with inline code, URLs and link targets masked."""
    fenced = False
    for number, line in enumerate(text.splitlines(), 1):
        if _FENCE_RE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            yield number, _MASK_RE.sub(lambda m: " " * len(m.group(0)), line)


def scan_text(path: Path, text: str, pattern: re.Pattern[str], terms: Iterable[str] = ()) -> list[Finding]:
    canonical = {t.lower(): t for t in terms}
    return [
        Finding(path, number, match.group(0))
        for number, line in _prose_lines(text)
        for match in pattern.finditer(line)
        if not _is_identifier(line, match.start(), match.end(), canonical)
    ]


def spec_text_files(root: Path) -> list[Path]:
    specs = root / "specs"
    return sorted(
        p for p in specs.rglob("*.md") if p.is_file() and not SKIP_DIRS.intersection(p.relative_to(specs).parts[:-1])
    )


def check_repository(root: Path, repo: str | None = None) -> list[str]:
    """Rendered findings for every authored Markdown file under ``specs/``."""
    terms = load_terms(repo if repo is not None else remote_owner(root))
    pattern = compile_terms(terms)
    if pattern is None:
        return []
    found: list[Finding] = []
    for path in spec_text_files(root):
        found += scan_text(path, path.read_text(encoding="utf-8", errors="replace"), pattern, terms)
    return [f"spec-standard: {f.render(root)}" for f in found]
