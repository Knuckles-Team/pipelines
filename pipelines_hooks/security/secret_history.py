"""secret-history: no credential-shaped content in the not-yet-published commit range.

A credential in ANY commit's patch text is public the moment the range is
pushed, even if a later commit deletes it. This scans the ADDED lines of
``<base>..HEAD`` against :mod:`credential_patterns` (hard failures) and a
high-entropy sweep (informational). There is no allowlist file; the only
exemption is the justified inline marker (:mod:`pipelines_hooks.security.marker`).

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
from pipelines_hooks.security.history_scan import scan_credentials, scan_entropy, scan_text_for_credentials

REMEDY = (
    "Remove the secret and rotate it if it is live (history is not rewritten; this is "
    "a go-forward fix), or, if review confirms a synthetic fixture, add "
    "'# sanitizer:ignore - <reason>' to that exact line."
)


def check(root: Path, base: str | None) -> tuple[int, dict[str, object]]:
    """Scan ``base..HEAD`` (all history when ``base`` is ``None``)."""
    rev_range = f"{base}..HEAD" if base else "HEAD"
    patch = git_text(root, ("log", "-p", "--format=%x00COMMIT%x00%H", rev_range)).splitlines()
    credentials = scan_credentials(patch)
    entropy = scan_entropy(patch)
    result: dict[str, object] = {
        "ok": not credentials,
        "range": rev_range if base else "full history (no published base)",
        "addedLines": sum(1 for line in patch if line.startswith("+") and not line.startswith("+++")),
        "credentialHits": credentials,
        "entropyCandidateCount": len(entropy),
        "entropySample": entropy[:20],
    }
    if credentials:
        result["error"] = f"{len(credentials)} credential-shaped hit(s) in {rev_range}. {REMEDY}"
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
