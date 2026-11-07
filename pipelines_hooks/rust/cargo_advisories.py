"""cargo-advisories: Rust dependency advisories fail closed, with an auditable ledger.

Every advisory is a failure unless ``deny.toml`` ignores it AND the ledger holds
a justified, unexpired acceptance (``RUSTSEC-YYYY-NNNN expires=YYYY-MM-DD # reason``,
at most 90 days ahead). Both lists must agree: an ignore without a ledger line
and a ledger line without an ignore both fail. The enforcing run is
``cargo deny check advisories`` on the pinned ``cargo-deny``.

``[tool.pipelines_hooks.cargo_advisories]`` keys: ``deny_config`` (default
``.config/deny.toml``), ``ledger`` (default ``.config/cargo-audit-allow.txt``),
``cargo_deny_version`` (required), ``max_acceptance_days`` (default 90).
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

from pipelines_hooks.core.config import load_config
from pipelines_hooks.core.errors import CannotRun, Unavailable
from pipelines_hooks.core.gitenv import repo_root, sanitized_env

_ADVISORY = re.compile(r"^RUSTSEC-\d{4}-\d{3,}$")
_EXPIRY = re.compile(r"^expires=(\d{4}-\d{2}-\d{2})$")


def ignored_ids(deny: Path) -> tuple[set[str], list[str]]:
    """The advisory ids ``[advisories].ignore`` lists, and the entries it cannot read."""
    try:
        document = tomllib.loads(deny.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"cannot read {deny}: {exc}") from exc
    ids: set[str] = set()
    problems: list[str] = []
    for entry in document.get("advisories", {}).get("ignore", []):
        if isinstance(entry, str):
            ids.add(entry)
        elif isinstance(entry, dict) and isinstance(entry.get("id"), str):
            ids.add(entry["id"])
        else:
            problems.append(f"{deny} has an [advisories].ignore entry in an unrecognised shape: {entry!r}")
    return ids, problems


def read_ledger(path: Path, today: dt.date, horizon: int) -> tuple[dict[str, dt.date], list[str]]:
    """The accepted advisories with their expiry, and one problem per bad line."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    ledger: dict[str, dt.date] = {}
    problems: list[str] = []
    for number, raw in enumerate(lines, 1):
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        declaration, hash_mark, why = text.partition("#")
        fields = declaration.split()
        if not hash_mark or len(fields) != 2 or len(why.strip()) < 12:
            problems.append(f"{path} line {number} is not 'RUSTSEC-ID expires=YYYY-MM-DD # reason (>=12 chars)'")
            continue
        advisory, expiry = fields
        match = _EXPIRY.fullmatch(expiry)
        if not _ADVISORY.fullmatch(advisory) or match is None:
            problems.append(f"{path} line {number} is invalid: {text!r}")
            continue
        try:
            expires = dt.date.fromisoformat(match.group(1))
        except ValueError:
            problems.append(f"{path} line {number} has an invalid date")
            continue
        if expires < today:
            problems.append(f"{path} line {number} ({advisory}) expired on {expires}")
        elif expires > today + dt.timedelta(days=horizon):
            problems.append(f"{path} line {number} ({advisory}) exceeds the {horizon}-day review horizon")
        elif advisory in ledger:
            problems.append(f"{path} line {number} duplicates {advisory}")
        else:
            ledger[advisory] = expires
    return ledger, problems


def cross_check(ignored: set[str], ledger: dict[str, dt.date], deny: Path, path: Path) -> list[str]:
    """Ignores without a live acceptance, and acceptances nobody uses."""
    return [
        f"{deny} ignores {i} with no justified, unexpired {path} entry" for i in sorted(ignored - ledger.keys())
    ] + [
        f"{path} accepts {i} but {deny} does not ignore it (stale acceptance)" for i in sorted(ledger.keys() - ignored)
    ]


def verified_cargo_deny(version: str) -> str:
    """The installed ``cargo-deny`` at the pinned version."""
    binary = shutil.which("cargo-deny")
    if binary is None:
        raise Unavailable(
            f"cargo-deny is not installed; install the pinned {version} binary",
            remedy=f"cargo install --locked --version {version} cargo-deny",
        )
    got = subprocess.run(
        [binary, "--version"], capture_output=True, text=True, env=sanitized_env(), check=False
    ).stdout.strip()
    if got != f"cargo-deny {version}":
        raise CannotRun(f"cargo-deny version drift: expected {version}, got {got!r}")
    return binary


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="cargo-advisories", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = repo_root(parser.parse_args(argv).root)
    section = load_config(root).section("cargo_advisories")
    version = section.get("cargo_deny_version")
    if not isinstance(version, str) or not version:
        raise CannotRun("[tool.pipelines_hooks.cargo_advisories] cargo_deny_version is required")
    horizon = section.get("max_acceptance_days", 90)
    if not isinstance(horizon, int) or horizon < 1:
        raise CannotRun("[tool.pipelines_hooks.cargo_advisories] max_acceptance_days must be a positive integer")
    deny = root / str(section.get("deny_config", ".config/deny.toml"))
    ledger_path = root / str(section.get("ledger", ".config/cargo-audit-allow.txt"))
    binary = verified_cargo_deny(version)
    if not deny.is_file():
        raise CannotRun(f"{deny.relative_to(root)} is missing")
    ignored, problems = ignored_ids(deny)
    ledger, ledger_problems = read_ledger(ledger_path, dt.date.today(), horizon)
    problems += ledger_problems + cross_check(ignored, ledger, deny.relative_to(root), ledger_path.relative_to(root))
    for problem in problems:
        print(f"cargo-advisories: {problem}")
    if problems:
        return 1
    print(f"cargo-advisories: ledger consistent ({len(ledger)} accepted advisories)")
    return subprocess.run([binary, "--config", str(deny), "check", "advisories"], cwd=root, check=False).returncode
