"""Scan the added lines of ``git log -p`` patch text (or plain text) for credentials."""

from __future__ import annotations

from collections.abc import Iterator

from pipelines_hooks.security.credential_patterns import CREDENTIAL_PATTERNS
from pipelines_hooks.security.entropy import high_entropy_tokens, is_lockfile
from pipelines_hooks.security.marker import is_exempt
from pipelines_hooks.security.placeholders import only_placeholder_uri_secrets

COMMIT_MARK = "\x00COMMIT\x00"
#: Patterns that match a credential embedded in a URI: a documented placeholder secret is an example.
URI_PATTERNS = frozenset({"db_url_with_password", "basic_auth_url"})


def _hit(name: str, content: str) -> bool:
    if not CREDENTIAL_PATTERNS[name].search(content):
        return False
    return not (name in URI_PATTERNS and only_placeholder_uri_secrets(content))


def added_lines(patch_lines: list[str]) -> Iterator[tuple[str, str, str]]:
    """``(commit, file, content)`` for every added line; ``+++``/``---`` headers skipped."""
    commit, file = "?", "?"
    for line in patch_lines:
        if line.startswith(COMMIT_MARK):
            commit = line.split(COMMIT_MARK, 1)[1].strip() or "?"
        elif line.startswith("+++ "):
            file = line[4:].strip()
        elif line.startswith("+") and not line.startswith("+++"):
            yield commit, file, line[1:]


def scan_credentials(patch_lines: list[str]) -> list[dict[str, str]]:
    """One hit per (commit, file, pattern); a justified marker exempts its own line."""
    hits: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for commit, file, content in added_lines(patch_lines):
        if is_exempt(content):
            continue
        for name in CREDENTIAL_PATTERNS:
            if _hit(name, content) and (commit, file, name) not in seen:
                seen.add((commit, file, name))
                hits.append({"commit": commit, "file": file, "pattern": name, "context": content.strip()[:160]})
    return hits


def scan_entropy(patch_lines: list[str]) -> list[dict[str, object]]:
    """Informational high-entropy candidates, lockfiles excluded."""
    hits: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for commit, file, content in added_lines(patch_lines):
        if is_lockfile(file):
            continue
        for token, entropy in high_entropy_tokens(content):
            if (commit, file, token[:12]) not in seen:
                seen.add((commit, file, token[:12]))
                hits.append({"commit": commit, "file": file, "entropy": round(entropy, 2), "token_preview": token[:12] + "..."})
    return hits


def scan_text_for_credentials(text: str, label: str = "<text>") -> list[dict[str, str]]:
    """The same credential table over PLAIN TEXT (a transcript, a saved log).

    A secret can leak through an exported session transcript no git scan can
    see; this is the reusable pre-persist check for that surface. The text is
    wrapped as a one-commit, one-file patch so exactly one scanner exists.
    """
    patch = [COMMIT_MARK + "text", f"+++ {label}", *("+" + line for line in text.splitlines())]
    return scan_credentials(patch)
