"""Read committed withdrawal declarations and exact source bytes from Git."""

from __future__ import annotations

import subprocess
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text, sanitized_env
from pipelines_hooks.specs.trailer_ids import named_ids

_RECORD = "\x01"
_FIELD = "\x02"


def declarations(root: Path, base: str | None) -> list[tuple[set[str], str]]:
    fmt = "%x01%(trailers:key=Spec-Withdraw,valueonly,separator=,)%x02%(trailers:key=Spec-Withdrawal-Reason,valueonly,separator= )"
    rev_range = f"{base}..HEAD" if base else "HEAD"
    raw = git_text(root, ("log", "--no-merges", f"--format={fmt}", rev_range))
    result = []
    for record in raw.split(_RECORD):
        ids, _, reason = record.strip().partition(_FIELD)
        if ids or reason:
            result.append((set(named_ids([ids])), reason.strip()))
    return result


def blob(root: Path, revision: str, path: str) -> str:
    try:
        result = subprocess.run(
            ["git", "cat-file", "blob", f"{revision}:{path}"],
            cwd=root,
            env=sanitized_env(),
            capture_output=True,
            check=True,
            timeout=60,
        )
        return result.stdout.decode("utf-8")
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise CannotRun(
            f"cannot read withdrawal blob {revision}:{path}: {exc}"
        ) from exc


def changes(root: Path, base: str) -> list[tuple[str, str, str]]:
    raw = git_text(root, ("diff", "--raw", "--no-renames", "-z", base, "HEAD"))
    parts = raw.split("\0")
    changes = []
    for index in range(0, len(parts) - 1, 2):
        metadata, path = parts[index : index + 2]
        fields = metadata.split()
        if fields[0] != ":100644" or fields[1] != "100644" or fields[4] != "M":
            raise ValueError(
                "withdrawal requires existing regular files with unchanged modes"
            )
        before = blob(root, base, path)
        after = blob(root, "HEAD", path)
        changes.append((path, before, after))
    return changes
