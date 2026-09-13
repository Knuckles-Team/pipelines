"""Tracked credential files (SC-SEC-001) and credential material (SC-SEC-002)."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path, PurePosixPath

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import sanitized_env
from pipelines_hooks.security.marker import is_exempt
from pipelines_hooks.supply_chain.finding import Finding

SENSITIVE_FILE_NAMES = frozenset({".env", ".netrc", ".pypirc", "id_dsa", "id_ecdsa", "id_ed25519", "id_rsa"})
SENSITIVE_FILE_SUFFIXES = frozenset({".cer", ".jks", ".key", ".keystore", ".p12", ".pem", ".pfx"})
_TOKEN_BODY = r"(?:AKIA|ASIA)[A-Z0-9]{16}|github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|sk-lf-[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{32,}|xox[baprs]-[A-Za-z0-9-]{20,}"
#: POSIX ERE for ``git grep -E``, which has no ``(?:`` groups: the same body with plain groups.
SECRET_MATERIAL_PATTERN = r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----|(^|[^A-Za-z0-9])(" + _TOKEN_BODY.replace("(?:", "(") + ")"
SECRET_MATERIAL_RE = re.compile(SECRET_MATERIAL_PATTERN)
TOKEN_VALUE_RE = re.compile(_TOKEN_BODY)
SYNTHETIC_TOKEN_MARKERS = frozenset(
    {"change-me", "changeme", "dummy", "example", "fake", "placeholder", "redacted", "replace-me", "sample", "set-me", "test", "your-", "xxxxx"}
)
MAX_SECRET_SCAN_BYTES = 16 * 1024 * 1024
_TOKEN_PREFIX_RE = re.compile(r"^(?:AKIA|ASIA|github_pat_|gh[pousr]_|sk-lf-|sk-|xox[baprs]-)")


def _credible(token: str) -> bool:
    folded = token.casefold()
    return not any(marker in folded for marker in SYNTHETIC_TOKEN_MARKERS) and len(set(_TOKEN_PREFIX_RE.sub("", folded))) > 4


def content_finding(label: str, *, path: str, line: int, content: str) -> Finding | None:
    """One line under the shared credential-material policy (justified marker exempts)."""
    if is_exempt(content):
        return None
    private_key = re.search(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----", content) is not None
    if not private_key and not any(_credible(token) for token in TOKEN_VALUE_RE.findall(content)):
        return None
    return Finding(label, PurePosixPath(path).as_posix(), line, "SC-SEC-002", "tracked source resembles live credential or private-key material")


def sensitive_file_findings(label: str, repository: Path, sources: tuple[Path, ...]) -> list[Finding]:
    return [
        Finding(label, p.relative_to(repository).as_posix(), 0, "SC-SEC-001", "tracked credential, private-key, or environment trust file is forbidden")
        for p in sources
        if p.name.casefold() in SENSITIVE_FILE_NAMES or p.suffix.casefold() in SENSITIVE_FILE_SUFFIXES
    ]


def _grep(label: str, repository: Path) -> bytes:
    command = ["git", "grep", "-I", "-n", "-E", "-e", SECRET_MATERIAL_PATTERN, "--", "."]
    try:
        result = subprocess.run(command, cwd=str(repository), env=sanitized_env(), capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        raise CannotRun(f"{label}: Git secret scan is unavailable or exceeded its time bound") from None
    if result.returncode not in {0, 1} or len(result.stdout) > MAX_SECRET_SCAN_BYTES:
        raise CannotRun(f"{label}: Git secret scan failed or exceeded its output bound")
    return result.stdout


def secret_findings(label: str, repository: Path, sources: tuple[Path, ...]) -> list[Finding]:
    findings = sensitive_file_findings(label, repository, sources)
    for raw in _grep(label, repository).splitlines():
        parts = raw.split(b":", 2)
        if len(parts) < 3 or not parts[1].isdigit():
            raise CannotRun("Git secret scan returned an invalid location")
        content = parts[2].decode("utf-8", errors="replace")
        finding = content_finding(label, path=os.fsdecode(parts[0]), line=int(parts[1]), content=content)
        findings.extend([finding] if finding else [])
    return findings
