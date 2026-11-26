"""Prove secret-history catches a planted secret and honours only the justified marker.

A gate nobody proved catches a violation is not a gate. The planted values are
assembled at runtime, so this module's own source contains no credential shape.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from pipelines_hooks.core.gitenv import sanitized_env
from pipelines_hooks.security.history_scan import scan_text_for_credentials

_MARK = "# sanitizer" + ":ignore"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=gate", "-c", "user.email=gate@example.invalid", *args],
        cwd=str(repo),
        env=sanitized_env(),
        check=True,
        capture_output=True,
    )


def _planted_lines() -> list[str]:
    return [
        "AWS_ACCESS_KEY_ID = '" + "AKIA" + "ABCDEFGHIJKLMNOP" + "'",
        "GITHUB_TOKEN = '" + "ghp" + "_" + "a" * 36 + "'",
        "-----BEGIN " + "RSA PRIVATE KEY" + "-----",
        "MEDULLA_SIGNER" + '_KEYS_JSON={"agent:x": "' + "f" * 32 + '"}',
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
    hits = bad["credentialHits"]
    patterns = {hit["pattern"] for hit in hits} if isinstance(hits, list) else set()
    return {
        "caughtPlantedCredential": rc_bad == 1 and len(patterns) >= 4,
        "honoredJustifiedMarker": rc_justified == 0,
        "rejectedBareMarker": rc_bare == 1,
    }


def _exception_checks() -> dict[str, bool]:
    """A pinned exception exempts its one occurrence and nothing else."""
    from pipelines_hooks.security.history_exceptions import EXCEPTIONS, line_digest, load_exceptions, pin_problem
    from pipelines_hooks.security.secret_history import check

    line = _planted_lines()[0]
    with tempfile.TemporaryDirectory(prefix="secret-history-exceptions-") as raw:
        repo = Path(raw)
        _git(repo, "init", "-q", "-b", "main")
        (repo / "README.md").write_text("base\n", encoding="utf-8")
        _git(repo, "add", "README.md")
        _git(repo, "commit", "-q", "-m", "base")
        _git(repo, "branch", "base")
        for name in ("pinned.py", "other.py"):
            (repo / name).write_text(line + "\n", encoding="utf-8")
            _git(repo, "add", name)
            _git(repo, "commit", "-q", "-m", name)
        commits = subprocess.run(
            ["git", "rev-list", "--reverse", "base..HEAD"],
            cwd=str(repo),
            env=sanitized_env(),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        entry = (
            "[[exception]]\n"
            f'commit = "{commits[0]}"\nfile = "pinned.py"\nline_digest = "{line_digest(line)}"\n'
            'reason = "synthetic self-check line that stands in for a shape-based historical match only"\n'
            'reviewed_on = "2026-01-01"\n'
        )
        (repo / ".config").mkdir()
        (repo / EXCEPTIONS).write_text(entry, encoding="utf-8")
        rc_only_other, only_other = check(repo, "base")
        hits = only_other["credentialHits"]
        files = {hit["file"].removeprefix("b/") for hit in hits} if isinstance(hits, list) else set()
        (repo / EXCEPTIONS).write_text(entry.replace('"pinned.py"', '"renamed.py"'), encoding="utf-8")
        rc_wrong_file, _wrong = check(repo, "base")
        (repo / EXCEPTIONS).write_text(entry, encoding="utf-8")
        problem = pin_problem(repo, load_exceptions(repo)[0])
    return {
        "exceptionExemptsOnlyItsPinnedOccurrence": rc_only_other == 1 and files == {"other.py"},
        "exceptionWithAWrongPinExemptsNothing": rc_wrong_file == 1,
        "exceptionPinVerifies": problem is None,
    }


def _repository_exception_checks(root: Path) -> dict[str, bool]:
    """Every entry of ``root`` still points at a real credential-shaped occurrence."""
    from pipelines_hooks.security.history_exceptions import load_exceptions, pin_problem

    problems = [problem for entry in load_exceptions(root) if (problem := pin_problem(root, entry)) is not None]
    for problem in problems:
        print(f"secret-history --self-check: {problem}", file=sys.stderr)
    return {"repositoryExceptionsMatchTheirPins": not problems}


def self_check(root: Path | None = None) -> tuple[int, dict[str, object]]:
    text_hits = scan_text_for_credentials("Session log:\n" + _planted_lines()[3] + "\n", label="t.txt")
    checks = {
        **_repository_checks(),
        **_exception_checks(),
        **({} if root is None else _repository_exception_checks(root)),
        "textModeCaughtPlantedCredential": any(
            h["pattern"] == "engine_signer_credential_assignment" for h in text_hits
        ),
        "textModeCleanOnMention": scan_text_for_credentials("rotated the signer_key successfully\n") == [],
    }
    ok = all(checks.values())
    return (0 if ok else 1), {"ok": ok, "selfCheck": True, **checks}
