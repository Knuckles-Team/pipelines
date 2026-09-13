"""The security-sanitizer's reviewed patterns and garbage rules.

Written so that no line of this module matches its own secret patterns: the
sanitizer scans its own source with no file-name exemption.
"""

from __future__ import annotations

import re

MAX_SCAN_BYTES = 8 * 1024 * 1024

#: Root-level ``.txt`` files that are canonical inputs, not scratch.
ALLOWED_TXT_NAMES = frozenset(
    {"requirements.txt", "requirements-dev.txt", "llms.txt", "overrides.txt", ".security-audit-allow.txt", ".cargo-audit-allow.txt"}
)
TRANSIENT_PY_PATTERNS = tuple(re.compile(p) for p in (r"^test_.*\.py$", r"^fix_.*\.py$", r"^debug_.*\.py$", r"^scratch_.*\.py$", r"^temp_.*\.py$"))
TRANSIENT_NOTE_PATTERNS = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (r".*[-_ ]BASELINE[-_ ]NOTES\.md$", r".*[-_ ]WORKING[-_ ]NOTES\.md$", r".*[-_ ]HANDOFF[-_ ]NOTES\.md$", r".*[-_ ]SCRATCHPAD\.md$")
)
SECRET_PATTERNS = (
    ("GitHub PAT", re.compile(r"ghp_[A-Za-z0-9_]{36,255}")),
    ("GitHub Fine-grained PAT", re.compile(r"github_pat_[A-Za-z0-9_]{82,255}")),
    ("GitLab PAT", re.compile(r"glpat-[A-Za-z0-9\-]{20,255}")),
    ("Private key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("Langfuse secret", re.compile(r"\bsk-lf-[A-Za-z0-9_-]{16,}\b")),
    ("Generic Secret Assignment", re.compile(r"secret[A-Za-z0-9_]*\s*[:=]\s*['\"][A-Za-z0-9_\-\.\~\*]{16,255}['\"]", re.IGNORECASE)),
    ("Generic Token Assignment", re.compile(r"token\s*[:=]\s*['\"][A-Za-z0-9_\-\.\~\*]{16,255}['\"]", re.IGNORECASE)),
)
#: Generated trees only; hidden source directories such as ``.github`` stay in.
EXCLUDED_DIRS = frozenset(
    {".git", ".venv", "venv", "node_modules", "build", "dist", "__pycache__", ".tox", ".specify",
     ".mypy_cache", ".pytest_cache", ".ruff_cache", ".cache", "target", "target-isolated"}
)
EXCLUDED_EXTENSIONS = frozenset(
    ".png .jpg .jpeg .gif .webp .ico .pyc .db .kuzu .sqlite .sqlite3 .zip .tar.gz .tgz .bz2 .xz "
    ".pdf .bin .exe .dll .so .dylib .woff .woff2 .eot .ttf .mp4 .mp3 .wav .lock .svg".split()
)
PLACEHOLDER_VALUES = frozenset(
    {"1234567890", "abcdef12345", "abc123youandme", "askdfalskdvjas", "test_token", "test_secret",
     "glpat-askdfalskdvjas", "github_pat_12345", "glpat-abc123youandme", "github_pat_...",
     "glpat-*************", "ghp_*************", "github_pat_*************", "token_*************",
     "secret_*************", "glpat-abc", "ghp_abc", "github_pat_abc", "${env:"}
)
PLACEHOLDER_PREFIXES = ("your_", "your-", "dummy", "example", "mock")


def is_placeholder(match: str) -> bool:
    """Only the quoted VALUE is judged, so a name like ``secret_example`` cannot hide a credential."""
    assignment = re.search(r"['\"]([^'\"]+)['\"]\s*$", match)
    candidate = (assignment.group(1) if assignment else match).strip()
    lowered = candidate.lower()
    if not candidate or "*" in candidate or lowered in PLACEHOLDER_VALUES or lowered.startswith(PLACEHOLDER_PREFIXES):
        return True
    compact = re.sub(r"[^A-Za-z0-9]", "", candidate).lower()
    return len(compact) >= 8 and len(set(compact)) == 1
