"""Prove secret-history catches a planted secret and honours only the justified marker.

A gate nobody proved catches a violation is not a gate. The planted values are
assembled at runtime, so this module's own source contains no credential shape.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from pipelines_hooks.core.gitenv import sanitized_env
from pipelines_hooks.security.history_scan import scan_text_for_credentials

_MARK = "# sanitizer" + ":ignore"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=gate", "-c", "user.email=gate@example.invalid", *args],
        cwd=str(repo), env=sanitized_env(), check=True, capture_output=True,
    )


def _planted_lines() -> list[str]:
    return [
        "AWS_ACCESS_KEY_ID = '" + "AKIA" + "ABCDEFGHIJKLMNOP" + "'",
        "GITHUB_TOKEN = '" + "ghp" + "_" + "a" * 36 + "'",
        "-----BEGIN " + "RSA PRIVATE KEY" + "-----",
        "EPISTEMIC_GRAPH_SIGNER" + '_KEYS_JSON={"agent:x": "' + "f" * 32 + '"}',
    ]


def _commit_leak(repo: Path, *, branch: str, lines: list[str]) -> None:
    _git(repo, "checkout", "-q", "-B", branch, "base")
    (repo / "leak.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
    _git(repo, "add", "leak.py")
    _git(repo, "commit", "-q", "-m", branch)


def _run_scan(repo: Path) -> tuple[int, dict[str, object]]:
    from pipelines_hooks.security.secret_history import check

    return check(repo, "base")


def _repository_checks() -> dict[str, bool]:
    with tempfile.TemporaryDirectory(prefix="secret-history-selfcheck-") as raw:
        repo = Path(raw)
        _git(repo, "init", "-q", "-b", "main")
        (repo / "README.md").write_text("base\n", encoding="utf-8")
        _git(repo, "add", "README.md")
        _git(repo, "commit", "-q", "-m", "base")
        _git(repo, "branch", "base")
        _commit_leak(repo, branch="planted", lines=_planted_lines())
        rc_bad, bad = _run_scan(repo)
        _commit_leak(repo, branch="justified", lines=[f"{_planted_lines()[0]}  {_MARK} - synthetic self-check fixture"])
        rc_justified, _justified = _run_scan(repo)
        _commit_leak(repo, branch="bare", lines=[f"{_planted_lines()[0]}  {_MARK}"])
        rc_bare, _bare = _run_scan(repo)
    patterns = {hit["pattern"] for hit in bad["credentialHits"]}
    return {
        "caughtPlantedCredential": rc_bad == 1 and len(patterns) >= 4,
        "honoredJustifiedMarker": rc_justified == 0,
        "rejectedBareMarker": rc_bare == 1,
    }


def self_check() -> tuple[int, dict[str, object]]:
    text_hits = scan_text_for_credentials("Session log:\n" + _planted_lines()[3] + "\n", label="t.txt")
    checks = {
        **_repository_checks(),
        "textModeCaughtPlantedCredential": any(h["pattern"] == "engine_signer_credential_assignment" for h in text_hits),
        "textModeCleanOnMention": scan_text_for_credentials("rotated the signer_key successfully\n") == [],
    }
    ok = all(checks.values())
    return (0 if ok else 1), {"ok": ok, "selfCheck": True, **checks}
