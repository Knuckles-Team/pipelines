"""``pipelines-hook <gate> [args]``: the single entry point of every shared hook."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Sequence

from pipelines_hooks.core.errors import CannotRun, Unavailable
from pipelines_hooks.core.settings import setting

#: Hook id -> module exposing ``main(argv: list[str]) -> int``.
GATES: dict[str, str] = {
    "validate": "pipelines_hooks.validation.cli",
    "dependency-readiness": "pipelines_hooks.release.dependency_readiness",
    "complexity-staged": "pipelines_hooks.complexity.staged",
    "complexity-census": "pipelines_hooks.complexity.census",
    "kiss-staged": "pipelines_hooks.kiss.staged",
    "kiss-census": "pipelines_hooks.kiss.census",
    "dupehound-changed": "pipelines_hooks.clones.dupehound_gate",
    "jscpd-differential": "pipelines_hooks.clones.jscpd_gate",
    "jscpd-census": "pipelines_hooks.clones.jscpd_census",
    "scanner-versions": "pipelines_hooks.core.versions_gate",
    "secret-history": "pipelines_hooks.security.secret_history",
    "security-sanitizer": "pipelines_hooks.security.sanitizer",
    "tracked-privacy": "pipelines_hooks.privacy.gate",
    "commit-identity": "pipelines_hooks.identity.commit_gate",
    "commit-identity-range": "pipelines_hooks.identity.range_gate",
    "supply-chain": "pipelines_hooks.supply_chain.gate",
    "root-hygiene": "pipelines_hooks.hygiene.root",
    "gitignore-convergence": "pipelines_hooks.hygiene.gitignore",
    "sprawl": "pipelines_hooks.hygiene.sprawl",
    "pre-commit-patch-safety": "pipelines_hooks.hygiene.patch_safety",
    "mermaid": "pipelines_hooks.hygiene.mermaid",
    "lockfile-version-mirrors": "pipelines_hooks.hygiene.lockfile_version_mirrors",
    "coupling": "pipelines_hooks.code.coupling",
    "uv-lock-check": "pipelines_hooks.hygiene.uv_lock",
    "connector-name": "pipelines_hooks.hygiene.connector_name",
    "connector-graphql": "pipelines_hooks.hygiene.connector_graphql",
    "agent-contract": "pipelines_hooks.hygiene.agent_contract",
    "no-legacy-concepts": "pipelines_hooks.code.no_legacy_concepts",
    "no-stub": "pipelines_hooks.code.no_stub",
    "stubs": "pipelines_hooks.code.stubs",
    "swallowed-errors": "pipelines_hooks.code.swallowed_gate",
    "event-loop-blocking": "pipelines_hooks.code.event_loop_gate",
    "import-cycles": "pipelines_hooks.code.import_cycles",
    "env-sprawl": "pipelines_hooks.code.env_sprawl",
    "stdout-writes": "pipelines_hooks.code.stdout_writes",
    "public-surface": "pipelines_hooks.docs.public_surface",
    "spec-decomposition": "pipelines_hooks.specs.decomposition",
    "spec-standard": "pipelines_hooks.specs.standard",
    "ste-staged": "pipelines_hooks.ste.staged",
    "ste-census": "pipelines_hooks.ste.census",
    "ste-staleness-staged": "pipelines_hooks.ste.staleness_staged",
    "ste-staleness-census": "pipelines_hooks.ste.staleness_census",
    "pr-test-scope": "pipelines_hooks.ci_replica.test_scope",
    "fast-tests": "pipelines_hooks.ci_replica.fast_tests",
    "spec-status": "pipelines_hooks.specs.status",
    "spec-trailers": "pipelines_hooks.specs.trailers",
    "gate-set": "pipelines_hooks.gate_runner",
}

#: Grouped checks of the gate standard (reference/gate-standard.md): one hook id
#: runs its member gates in order, with each member's default arguments.
GROUPS: dict[str, tuple[str, ...]] = {
    "secrets": ("security-sanitizer", "secret-history", "tracked-privacy", "commit-identity", "commit-identity-range"),
    "spec": ("spec-standard", "spec-decomposition", "spec-status", "spec-trailers"),
}

#: Group members that check a commit range. They run only when a range is
#: known (``PRE_COMMIT_FROM_REF``: a push, or CI's ``--from-ref``); at the
#: commit stage the unpublished range is not yet defined.
RANGE_MEMBERS = frozenset({"secret-history", "commit-identity-range", "spec-trailers"})

#: Standard names that are another name for one existing gate.
ALIASES: dict[str, str] = {"tests-fast": "fast-tests"}


def in_ci() -> bool:
    """True under a CI runner (GitHub Actions and most CI systems export ``CI``)."""
    return setting("CI").casefold() not in {"", "0", "false", "no"}


def run_gate(gate: str, argv: Sequence[str]) -> int:
    """Run one gate, mapping :class:`CannotRun` to exit status 2.

    A missing prerequisite (:class:`Unavailable`) fails closed only in CI;
    locally it is reported as skipped with the command that installs it.
    """
    module = importlib.import_module(GATES[gate])
    try:
        return int(module.main(list(argv)))
    except Unavailable as exc:
        if in_ci():
            print(f"{gate}: CANNOT RUN: {exc}", file=sys.stderr)
            return 2
        print(f"SKIPPED ({gate}): {exc}; run {exc.remedy}", file=sys.stderr)
        return 0
    except CannotRun as exc:
        print(f"{gate}: CANNOT RUN: {exc}", file=sys.stderr)
        return 2


def run_group(group: str, argv: Sequence[str]) -> int:
    """Run every member gate of one grouped check; the worst exit status wins.

    Members named in pre-commit's ``SKIP`` list are skipped, so a caller can
    still drop one member (for example ``spec-trailers`` on a main push).
    Range members run only when a range is known (:data:`RANGE_MEMBERS`).
    """
    if argv:
        print(f"{group}: CANNOT RUN: a grouped check takes no arguments ({' '.join(argv)})", file=sys.stderr)
        return 2
    skipped = {name.strip() for name in setting("SKIP").split(",") if name.strip()}
    status = 0
    for gate in GROUPS[group]:
        if gate in skipped:
            print(f"{group}: {gate} skipped (SKIP)")
            continue
        if gate in RANGE_MEMBERS and not setting("PRE_COMMIT_FROM_REF"):
            print(f"{group}: {gate} runs at push (no commit range at this stage)")
            continue
        status = max(status, run_gate(gate, []))
    return status


def _usage() -> int:
    print("usage: pipelines-hook <gate> [args]; gates:", file=sys.stderr)
    for name in sorted({*GATES, *GROUPS, *ALIASES}):
        print(f"  {name}", file=sys.stderr)
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        return _usage()
    name, rest = ALIASES.get(arguments[0], arguments[0]), arguments[1:]
    if name in GROUPS:
        return run_group(name, rest)
    if name not in GATES:
        return _usage()
    return run_gate(name, rest)


if __name__ == "__main__":
    raise SystemExit(main())
