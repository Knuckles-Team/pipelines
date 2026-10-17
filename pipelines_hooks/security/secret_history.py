"""secret-history: no credential-shaped content in the not-yet-published commit range.

Two scans of ADDED lines against :mod:`credential_patterns` (hard failures),
plus a high-entropy sweep (informational):

* the net diff ``git diff <base>...HEAD``: a credential still in the final
  change is caught, and a justified marker on that line exempts it;
* each commit not reachable from any remote ref (``git rev-list HEAD --not
  --remotes``): a credential added and then removed inside commits that were
  never pushed is caught too, because pushing them would publish it.

Commits already on a remote are not rescanned one by one: they are published,
and blocking a merge cannot unpublish them, so a per-commit scan of them only
makes a permanent false block. Their content still counts through the net diff.
There is no allowlist file; the only exemption is the justified inline marker
(:mod:`pipelines_hooks.security.marker`).

The base is ``--base``, then the remote revision pre-commit is pushing over,
then ``origin/main``. Without any of them the whole history is unpublished and
all of it is scanned -- never a guessed, narrower range.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pipelines_hooks.core.baseref import upstream_base
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text
from pipelines_hooks.security.history_scan import COMMIT_MARK, scan_credentials, scan_entropy, scan_text_for_credentials

REMEDY = (
    "Remove the secret and rotate it if it is live (history is not rewritten; this is "
    "a go-forward fix), or, if review confirms a synthetic fixture, add "
    "'# sanitizer:ignore - <reason>' to that exact line."
)


def _unpublished_patch(root: Path, base: str) -> list[str]:
    """``git log -p`` of the commits in ``base..HEAD`` that no remote ref reaches."""
    args = ("log", "-p", "--format=%x00COMMIT%x00%H", "HEAD", "--not", "--remotes", base)
    return git_text(root, args).splitlines()


def _net_patch(root: Path, base: str) -> list[str]:
    """The net change ``base...HEAD``, labelled as one pseudo-commit ``net-diff``."""
    diff = git_text(root, ("diff", "--no-color", "--no-ext-diff", "-U0", f"{base}...HEAD")).splitlines()
    return [f"{COMMIT_MARK}net-diff", *diff]


def _merge_hits(*groups: list[dict[str, str]]) -> list[dict[str, str]]:
    """Hits from both scans, one per (file, pattern, context)."""
    merged: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for group in groups:
        for hit in group:
            key = (hit["file"], hit["pattern"], hit["context"])
            if key not in seen:
                seen.add(key)
                merged.append(hit)
    return merged


def _full_history_scan(root: Path) -> tuple[list[str], list[dict[str, str]], dict[str, object]]:
    patch = git_text(root, ("log", "-p", "--format=%x00COMMIT%x00%H", "HEAD")).splitlines()
    return patch, scan_credentials(patch), {"range": "full history (no published base)"}


def _ranged_scan(root: Path, base: str) -> tuple[list[str], list[dict[str, str]], dict[str, object]]:
    net = _net_patch(root, base)
    unpublished = _unpublished_patch(root, base)
    total = int(git_text(root, ("rev-list", "--count", f"{base}..HEAD")).strip() or 0)
    scanned = sum(1 for line in unpublished if line.startswith(COMMIT_MARK))
    scope: dict[str, object] = {
        "range": f"{base}..HEAD",
        "netDiff": f"{base}...HEAD",
        "unpublishedCommitsScanned": scanned,
        "publishedCommitsNotRescanned": total - scanned,
    }
    return [*net, *unpublished], _merge_hits(scan_credentials(net), scan_credentials(unpublished)), scope


def check(root: Path, base: str | None) -> tuple[int, dict[str, object]]:
    """Scan the net diff and the unpublished commits of ``base..HEAD`` (all history when ``base`` is ``None``)."""
    patch, credentials, scope = _full_history_scan(root) if base is None else _ranged_scan(root, base)
    entropy = scan_entropy(patch)
    result: dict[str, object] = {
        "ok": not credentials,
        **scope,
        "addedLines": sum(1 for line in patch if line.startswith("+") and not line.startswith("+++")),
        "credentialHits": credentials,
        "entropyCandidateCount": len(entropy),
        "entropySample": entropy[:20],
    }
    if credentials:
        result["error"] = f"{len(credentials)} credential-shaped hit(s) in {scope['range']}. {REMEDY}"
    return (1 if credentials else 0), result


def _text_mode(path: Path) -> tuple[int, dict[str, object]]:
    try:
        text = sys.stdin.read() if str(path) == "-" else path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise CannotRun(f"cannot read {path}: {exc}") from exc
    hits = scan_text_for_credentials(text, label=str(path))
    return (1 if hits else 0), {"ok": not hits, "textFile": str(path), "credentialHits": hits}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="secret-history", description=__doc__)
    parser.add_argument("--repository-root", "--root", dest="root", type=Path, default=Path.cwd())
    parser.add_argument("--base", default=None, help="base revision (default: see module docstring)")
    parser.add_argument("--self-check", action="store_true", help="prove the gate catches a planted secret")
    parser.add_argument("--text-file", type=Path, default=None, help="scan a plain-text file ('-' for stdin)")
    args = parser.parse_args(argv)
    if args.self_check:
        from pipelines_hooks.security.history_selfcheck import self_check

        rc, result = self_check()
    elif args.text_file is not None:
        rc, result = _text_mode(args.text_file)
    else:
        root = args.root.resolve()
        rc, result = check(root, upstream_base(root, args.base))
    print(json.dumps(result, indent=2))
    return rc
