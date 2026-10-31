"""Compute every spec's status document (SPEC-STATUS-LIFECYCLE.md Sec1-4).

A pure function of git history, requirements.md, the test tree and the frozen
``.config/spec-legacy-landings.json``: no build, no network, nothing committed.
``status.json`` (schema_version 2) is read-time output, never tracked.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text
from pipelines_hooks.specs.aliases import canonical_lists, canonical_sets, load_aliases
from pipelines_hooks.specs.bindings import test_bindings
from pipelines_hooks.specs.git_log import landing_commits, reachable_shas, reverted_shas
from pipelines_hooks.specs.legacy import legacy_landings
from pipelines_hooks.specs.records import build_record, mentioned_tokens
from pipelines_hooks.specs.repository_identity import canonical_owner, repository_owner
from pipelines_hooks.specs.requirements_doc import Row, parse_rows
from pipelines_hooks.specs.rollup import apply_rollup, overall_state
from pipelines_hooks.specs.standard import check_title

SCHEMA_VERSION = 2


class Evidence(NamedTuple):
    """Everything a requirement row's delivery state is computed from."""

    landed_by: dict[str, set[str]]
    tested_by: dict[str, list[str]]
    legacy_by: dict[str, list[str]]


LEGACY_FILE = ".config/spec-legacy-landings.json"


def render(document: dict) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CannotRun(f"{path}: not valid JSON ({exc})") from exc
    return loaded if isinstance(loaded, dict) else {}


def _legacy_document(repo: Path) -> dict:
    """Frozen pre-trailer landings as a status-shaped document (``{id: [sha, ...]}`` on disk)."""
    frozen = _load_json(repo / LEGACY_FILE)
    return {"requirements": [{"id": rid, "landed_in": shas} for rid, shas in sorted(frozen.items())]}


def _requirement_state(rid: str, evidence: Evidence) -> tuple[list[str], list[str]]:
    landed = sorted(evidence.landed_by.get(rid, set()) | set(evidence.legacy_by.get(rid, [])))
    tests = sorted(set(evidence.tested_by.get(rid, [])))
    return landed, tests


def _spec_document(spec_dir: Path, *, rows: list[Row], evidence: Evidence, owner: str) -> dict:
    ids = [row.id for row in rows]
    state: dict[str, str] = {}
    records: dict[str, dict[str, object]] = {}
    for row in rows:
        landed, tests = _requirement_state(row.id, evidence)
        records[row.id] = build_record(row, landed, tests)
        state[row.id] = str(records[row.id]["delivery_state"])
    apply_rollup(ids, state, records)
    return {
        "schema_version": SCHEMA_VERSION,
        "spec_id": check_title(spec_dir)[0] or spec_dir.name,
        "owner_repo": owner,
        "delivery_state": overall_state(state),
        "requirement_ids": ids,
        "requirements": [records[rid] for rid in ids],
    }


def live_resolver(on_head: set[str], reverted: set[str]) -> Callable[[str], str | None]:
    """Map a recorded full SHA or SHA prefix to a reachable, non-reverted full SHA."""
    by_prefix = {sha[:12]: sha for sha in on_head}

    def resolve(recorded: str) -> str | None:
        full = recorded if recorded in on_head else by_prefix.get(recorded[:12]) if len(recorded) >= 12 else None
        return full if full and full not in reverted else None

    return resolve


def _history_evidence(
    repo: Path, head: str, aliases: dict[str, str]
) -> tuple[dict[str, set[str]], dict[str, list[str]]]:
    """Trailer landings and test bindings, keyed by canonical requirement ID."""
    landed_by = canonical_sets(mentioned_tokens(landing_commits(repo, head)), aliases)
    return landed_by, canonical_lists(test_bindings(repo), aliases)


_CACHE: dict[tuple[str, str], dict[Path, dict]] = {}


def computed(repo: Path, head: str = "HEAD") -> dict[Path, dict]:
    """:func:`generate`, memoized per process for gates that read status within one run."""
    key = (str(repo.resolve()), head)
    if key not in _CACHE:
        _CACHE[key] = generate(repo, head)
    return _CACHE[key]


def generate(repo: Path, head: str) -> dict[Path, dict]:
    """``specs/<dir>/status.json`` path -> computed document for every authored spec."""
    requirements_paths = sorted(repo.glob("specs/*/requirements.md"))
    if not requirements_paths:
        return {}
    if git_text(repo, ("rev-parse", "--is-shallow-repository")).strip() == "true":
        raise CannotRun(
            "spec-status needs complete Git history to validate landing receipts; "
            "fetch full history (git fetch --unshallow or checkout fetch-depth: 0)"
        )
    aliases = load_aliases(repo)
    landed_by, tested_by = _history_evidence(repo, head, aliases)
    resolve = live_resolver(reachable_shas(repo, head), reverted_shas(repo, head))
    legacy_by = canonical_lists(legacy_landings(_legacy_document(repo), resolve), aliases)
    evidence = Evidence(landed_by, tested_by, legacy_by)
    owner = repository_owner(repo) or canonical_owner(repo.resolve().name) or repo.resolve().name
    result: dict[Path, dict] = {}
    for requirements_path in requirements_paths:
        spec_dir = requirements_path.parent
        rows = parse_rows(requirements_path.read_text(encoding="utf-8"))
        result[spec_dir / "status.json"] = _spec_document(spec_dir, rows=rows, evidence=evidence, owner=owner)
    return result


def freeze_legacy(repo: Path, head: str) -> int:
    """Cutover: write the landings tracked status.json files carry that trailers do not.

    Reads the committed copies (``git show HEAD:``), so it works before they are deleted.
    """
    aliases = load_aliases(repo)
    landed_by, _ = _history_evidence(repo, head, aliases)
    resolve = live_resolver(reachable_shas(repo, head), reverted_shas(repo, head))
    frozen: dict[str, set[str]] = dict((k, set(v)) for k, v in _load_json(repo / LEGACY_FILE).items())
    tracked = [p for p in git_text(repo, ("ls-files", "--", "specs/*/status.json")).splitlines() if p]
    for path in tracked:
        try:
            old = json.loads(git_text(repo, ("show", f"{head}:{path}")) or "{}")
        except json.JSONDecodeError:
            continue
        for rid, shas in canonical_lists(
            legacy_landings(old if isinstance(old, dict) else {}, resolve), aliases
        ).items():
            extra = {sha[:12] for sha in shas if sha not in landed_by.get(rid, set())}
            if rid and extra:
                frozen.setdefault(rid, set()).update(extra)
    target = repo / LEGACY_FILE
    if frozen:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render({k: sorted(v) for k, v in sorted(frozen.items())}), encoding="utf-8")
    return sum(len(v) for v in frozen.values())


def generate_at(source: str, commit: str) -> dict[str, dict]:
    """Status documents of ``source`` (a local repository path or clone URL) at ``commit``.

    Readers that see a repository only as a commit (the architecture explorer, the
    story chart) compute status from a throwaway clone: blobless for a URL, object-
    sharing for a local path; the source repository is never written.
    Keys are repository-relative ``specs/<dir>/status.json`` paths.
    """
    import subprocess
    import tempfile

    from pipelines_hooks.core.gitenv import sanitized_env

    env = sanitized_env()
    with tempfile.TemporaryDirectory(prefix="spec-status-") as tmp:
        local = Path(source).is_dir()
        clone = [
            "git",
            "clone",
            "-q",
            "--no-checkout",
            *(["--shared"] if local else ["--filter=blob:none"]),
            source,
            tmp,
        ]
        subprocess.run(clone, env=env, check=True, capture_output=True, timeout=600)
        if local:  # keep the source's own identity (its origin), not the local path
            origin = subprocess.run(
                ["git", "-C", source, "remote", "get-url", "origin"], env=env, capture_output=True, text=True
            ).stdout.strip()
            if origin:
                subprocess.run(["git", "-C", tmp, "remote", "set-url", "origin", origin], env=env, check=True)
            else:
                subprocess.run(["git", "-C", tmp, "remote", "remove", "origin"], env=env, check=True)
        subprocess.run(
            ["git", "-C", tmp, "-c", "advice.detachedHead=false", "checkout", "-q", "--detach", commit],
            env=env,
            check=True,
            capture_output=True,
            timeout=600,
        )
        root = Path(tmp)
        return {str(path.relative_to(root)): doc for path, doc in generate(root, "HEAD").items()}
