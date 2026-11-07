"""pr-text: pull request and commit text is self-evident to a reader with no other context.

The text of a pull request title or body, a review or issue comment and a commit
message states what changed, why, the behaviour impact and how it was verified.
It holds no internal reference: a hostname, a private domain, a local path, an
internal tool or script name, a private repository name, workflow jargon or a
pointer to a private handoff document. A spec row ID appears with its one-line
meaning, never bare (constitution Article XXXII, ``reference/delivery-practice.md``).

Staged (default): findings are reported, as GitHub warnings in CI, and the exit
status is 0. ``--strict`` (or ``PR_TEXT_STRICT=true``) makes findings blocking.
Text comes from ``--title``/``--body`` (or ``PR_TITLE``/``PR_BODY``) and from
each ``--file`` (a commit message file, so the same mode runs at ``commit-msg``).
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

#: The internal-reference pattern `scripts/check_public_specs.py` applies to public specs.
PRIVATE = re.compile(r"plans/|gitlab|homelab|(?:file://|/(?:home|Users|tmp|workspace)/)|\.arpa\b", re.I)
#: Hostnames, private domains, machine roles and local paths the public pattern does not cover.
HOSTS = re.compile(
    r"\b[\w-]+\.(?:lan|local|internal|home|corp)\b|(?<![-\w.])(?:R[WX]?\d{3,4}|GB10)\b|/(?:srv|mnt|var/tmp|opt)/|~/\.(?:local|config|claude)\b"
)
#: Internal tool, script and private-repository names.
TOOLS = re.compile(
    r"\b(?:local-ci|eg-bulk-merge|rm_gates|rm_worktree|medulla-lane-run|py-remote-run|medulla-land-gate"
    r"|gh-preflight|core_bare_watchdog|inventory/operations)\b"
)
#: Workflow jargon an outside reader cannot decode.
JARGON = re.compile(r"\b(?:lanes?|ledgers?|feeders?|trains?|waves?|buffer(?:ed)?)\b", re.I)
#: Pointers to private handoff documents.
HANDOFF = re.compile(r"\b(?:HANDOFF|WRAPUP|DELIVERY-PLAN|REVIEW-HOTSPOTS|CONTRACT-REQUEST|STATE\.md)\b")
#: A spec row ID, such as ``PIPE-GATES-R099`` or ``PIPE-GATES-R086.3``.
ROW_ID = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-R\d+(?:\.\d+)?\b")
#: A row ID is explained when its meaning follows: ``ID (words)``, ``ID: words`` or ``ID - words``.
EXPLAINED = re.compile(r"[`*]*\s*(?:\([^)]*\w+\s+\w+\s+\w+[^)]*\)|[:–—-]\s*\w+\s+\w+\s+\w+)")
TRAILER = re.compile(r"^(?:Spec|Co-Authored-By|Signed-off-by|Fixes|Closes|Refs):", re.I)

KINDS = (
    ("private reference", PRIVATE),
    ("hostname or local path", HOSTS),
    ("internal tool or script name", TOOLS),
    ("internal workflow jargon", JARGON),
    ("private handoff document", HANDOFF),
)


def findings(label: str, text: str, private_repos: tuple[str, ...] = ()) -> list[str]:
    """Every finding for one text (an empty list means self-evident)."""
    kinds = list(KINDS)
    if private_repos:
        kinds.append(("private repository name", re.compile(r"\b(?:%s)\b" % "|".join(map(re.escape, private_repos)))))
    found: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        if TRAILER.match(line.strip()):
            continue
        for kind, pattern in kinds:
            found.extend(f"{label}:{number}: {kind}: {m.group(0)!r}" for m in pattern.finditer(line))
        for match in ROW_ID.finditer(line):
            if not EXPLAINED.match(line[match.end() :]):
                found.append(f"{label}:{number}: bare row ID {match.group(0)!r}: add its one-line meaning")
    return found


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="pr-text", description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, help="commit message files (commit-msg stage)")
    parser.add_argument("--title", default=os.environ.get("PR_TITLE", ""))
    parser.add_argument("--body", default=os.environ.get("PR_BODY", ""))
    parser.add_argument("--private-repo", action="append", default=[], help="private repository name to refuse")
    parser.add_argument("--strict", action="store_true", help="fail on findings instead of warning")
    arguments = parser.parse_args(argv)
    strict = arguments.strict or os.environ.get("PR_TEXT_STRICT", "").lower() == "true"
    repos = tuple(arguments.private_repo)
    texts = [("title", arguments.title), ("body", arguments.body)]
    texts += [(str(path), path.read_text(encoding="utf-8")) for path in arguments.files]
    found = [item for label, text in texts for item in findings(label, text, repos)]
    if not found:
        print("pr-text: self-evident (no internal reference, jargon or bare row ID)")
        return 0
    level = "FAIL" if strict else "WARN"
    print(f"{level}: pr-text (reference/delivery-practice.md, Pull requests, comments and commit messages):")
    for item in found:
        print(f"  {item}")
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::{'error' if strict else 'warning'}::pr-text: {item}")
    return 1 if strict else 0
