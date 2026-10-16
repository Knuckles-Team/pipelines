"""Validate explicit, evidence-only withdrawals without exempting feature work."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text, sanitized_env
from pipelines_hooks.specs.trailer_ids import named_ids
from pipelines_hooks.specs.withdrawal_source import source_withdrawal_only

_RECORD = "\x01"
_FIELD = "\x02"


def _declarations(root: Path, base: str | None) -> list[tuple[set[str], str]]:
    fmt = "%x01%(trailers:key=Spec-Withdraw,valueonly,separator=,)%x02%(trailers:key=Spec-Withdrawal-Reason,valueonly,separator= )"
    rev_range = f"{base}..HEAD" if base else "HEAD"
    raw = git_text(root, ("log", "--no-merges", f"--format={fmt}", rev_range))
    result = []
    for record in raw.split(_RECORD):
        ids, _, reason = record.strip().partition(_FIELD)
        if ids or reason:
            result.append((set(named_ids([ids])), reason.strip()))
    return result


def _owners(root: Path, ids: set[str]) -> dict[str, str]:
    owners = {}
    for path in root.glob("specs/*/requirements.md"):
        text = path.read_text(encoding="utf-8")
        for rid in ids:
            if re.search(rf"(?m)^\|\s*`{re.escape(rid)}`\s*\|", text):
                if rid in owners:
                    raise ValueError(f"ambiguous requirement owner: {rid}")
                owners[rid] = path.parent.relative_to(root).as_posix()
    return owners


def _added_only(before: str, after: str) -> bool:
    remaining = iter(after.splitlines(keepends=True))
    return all(
        any(line == candidate for candidate in remaining)
        for line in before.splitlines(keepends=True)
    )


def _tasks_only(before: str, after: str, ids: set[str]) -> bool:
    for rid in ids:
        before = before.replace(f"[x] **{rid}:**", f"[ ] **{rid}:**")
    return before == after


def _blob(root: Path, revision: str, path: str) -> str:
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


def _changes(root: Path, base: str) -> list[tuple[str, str, str]]:
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
        before = _blob(root, base, path)
        after = _blob(root, "HEAD", path)
        changes.append((path, before, after))
    return changes


def _validate_changes(
    root: Path, base: str, ids: set[str], owners: dict[str, str]
) -> None:
    removed = set()
    directories = set(owners.values())
    for path, before, after in _changes(root, base):
        parent, _, name = path.rpartition("/")
        if parent in directories and name == "plan.md" and _added_only(before, after):
            continue
        if (
            parent in directories
            and name == "tasks.md"
            and _tasks_only(before, after, ids)
        ):
            continue
        if parent in directories and name == "status.json":
            # The independent spec-status gate still requires canonical generation.
            continue
        if not path.endswith(".rs") or not source_withdrawal_only(before, after, ids):
            raise ValueError(f"withdrawal changes non-evidence content: {path}")
        removed.update(
            rid
            for rid in ids
            if re.search(rf"(?m)^\s*// spec: {re.escape(rid)}\s*$", before)
        )
    if removed != ids:
        raise ValueError(
            "each withdrawn ID must remove an existing Rust comment binding"
        )


def withdrawals(
    root: Path, base: str | None, named: set[str], known: set[str], bound: set[str]
) -> tuple[set[str], list[str]]:
    """Return exempt IDs only after every evidence-only constraint passes."""
    declarations = _declarations(root, base)
    if not declarations:
        return set(), []
    try:
        if base is None:
            raise ValueError("withdrawal requires an explicit resolvable base")
        ids = set().union(*(item[0] for item in declarations))
        if not ids or not ids <= named or not ids <= known:
            raise ValueError(
                "withdrawn IDs must be known and retained in Spec trailers"
            )
        if ids & bound:
            raise ValueError("withdrawn IDs still have acceptance bindings")
        owners = _owners(root, ids)
        for requested, reason in declarations:
            if not requested or len(reason) < 20:
                raise ValueError(
                    "every withdrawal needs IDs and a descriptive reason (20+ characters)"
                )
            for rid in requested:
                text = _blob(root, "HEAD", f"{owners[rid]}/plan.md")
                if rid not in text or reason not in text:
                    raise ValueError(
                        f"owning plan must retain {rid} and its exact withdrawal reason"
                    )
        merge_base = git_text(root, ("merge-base", base, "HEAD")).strip()
        _validate_changes(root, merge_base, ids, owners)
    except (ValueError, KeyError) as exc:
        return set(), [f"spec-trailers: FAIL: invalid evidence withdrawal: {exc}"]
    return ids, []
