"""Dependency-update bots exempt from the ``Spec:`` trailer: ``.config/spec-bots.toml``.

A commit from a configured bot that changes only dependency manifests and lock
files is treated as ``Spec: none (deps)``. The file lists exact identities, no
wildcard and no pattern::

    [[dependency_bot]]
    name = "example-bot[bot]"
    email = "1234+example-bot[bot]@users.noreply.example.invalid"

A missing file means no bot is exempt. A path outside the dependency class
(see :func:`pipelines_hooks.ci_replica.change_scope.classify`) keeps the
commit fully checked, so the exemption never widens past manifests and locks.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from pipelines_hooks.ci_replica.change_scope import classify
from pipelines_hooks.core.errors import CannotRun

BOT_FILE = ".config/spec-bots.toml"
MAX_BYTES = 64 * 1024
MAX_BOTS = 64

Bot = tuple[str, str]


def load_bots(root: Path) -> frozenset[Bot]:
    """The exact ``(name, email)`` pairs of the repository's dependency bots."""
    path = root / BOT_FILE
    if not path.is_file():
        return frozenset()
    try:
        if path.stat().st_size > MAX_BYTES:
            raise CannotRun(f"{path}: spec bot file exceeds {MAX_BYTES} bytes")
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"{path}: unreadable spec bot file ({exc})") from exc
    entries = document.get("dependency_bot", [])
    if set(document) - {"dependency_bot"} or not isinstance(entries, list) or len(entries) > MAX_BOTS:
        raise CannotRun(f"{path}: expected at most {MAX_BOTS} [[dependency_bot]] tables and nothing else")
    bots: set[Bot] = set()
    for entry in entries:
        valid = isinstance(entry, dict) and set(entry) == {"name", "email"}
        if not valid or not all(isinstance(entry[key], str) and entry[key].strip() for key in ("name", "email")):
            raise CannotRun(f"{path}: each [[dependency_bot]] needs a non-empty name and email and no other key")
        bots.add((entry["name"], entry["email"]))
    return frozenset(bots)


def is_dependency_only_bot_commit(bots: frozenset[Bot], author: Bot, paths: tuple[str, ...]) -> bool:
    """True for a configured bot's commit whose every changed path is a dependency manifest or lock."""
    return bool(paths) and author in bots and all(classify(path) == "deps" for path in paths)
