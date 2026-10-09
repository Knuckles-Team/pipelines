"""``pipelines-hook <gate> [args]``: the single entry point of every shared hook."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Sequence

from pipelines_hooks.core.errors import CannotRun, Unavailable
from pipelines_hooks.core.settings import setting

#: Hook id -> module exposing ``main(argv: list[str]) -> int``.
GATES: dict[str, str] = {
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
    "no-stub": "pipelines_hooks.code.no_stub",
    "stubs": "pipelines_hooks.code.stubs",
    "swallowed-errors": "pipelines_hooks.code.swallowed_gate",
    "event-loop-blocking": "pipelines_hooks.code.event_loop_gate",
    "import-cycles": "pipelines_hooks.code.import_cycles",
    "env-sprawl": "pipelines_hooks.code.env_sprawl",
    "stdout-writes": "pipelines_hooks.code.stdout_writes",
    "public-surface": "pipelines_hooks.docs.public_surface",
    "spec-decomposition": "pipelines_hooks.specs.decomposition",
    "ste-staged": "pipelines_hooks.ste.staged",
    "ste-census": "pipelines_hooks.ste.census",
    "ste-staleness-staged": "pipelines_hooks.ste.staleness_staged",
    "ste-staleness-census": "pipelines_hooks.ste.staleness_census",
    "pr-test-scope": "pipelines_hooks.ci_replica.test_scope",
    "spec-status": "pipelines_hooks.specs.status",
}


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


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] not in GATES:
        print("usage: pipelines-hook <gate> [args]; gates:", file=sys.stderr)
        for name in sorted(GATES):
            print(f"  {name}", file=sys.stderr)
        return 2
    return run_gate(arguments[0], arguments[1:])


if __name__ == "__main__":
    raise SystemExit(main())
