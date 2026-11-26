"""states-agree: the engine's states of a revision equal the generator's (PIPE-GATES-R004.5).

The check reads the engine states through the served ``spec.status``
operation and compares them with the shared generator's states. A mismatch
fails and names each row and each side. An unreachable engine is an
advisory finding, never a failure: the page and the graph are compared
only when both can be read.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text, repo_root
from pipelines_hooks.core.settings import setting
from pipelines_hooks.specs.engine_state import generated_states
from pipelines_hooks.specs.generator import generate
from pipelines_hooks.verdict_publish import post_operation, target_from_environment

#: The served operation that answers the engine's state of each row.
STATUS_OPERATION = "spec.status"


def local_states(root: Path, head: str) -> dict[str, str]:
    """The generator's state of every row at ``head``, by row ID (the reader of ``engine_state``)."""
    return generated_states(generate(root, head))


def engine_states(answer: Any) -> dict[str, str]:
    """The engine's state of every row, by row ID, from one ``spec.status`` answer."""
    rows = answer.get("rows") if isinstance(answer, Mapping) else None
    if not isinstance(rows, list):
        raise CannotRun("states-agree: the spec.status answer carries no rows")
    return {
        str(row["id"]): str(row["state"]) for row in rows if isinstance(row, Mapping) and "id" in row and "state" in row
    }


def disagreements(local: Mapping[str, str], engine: Mapping[str, str]) -> list[str]:
    """One finding per row whose states differ or that one side lacks, naming both sides."""
    findings = []
    for row_id in sorted(set(local) | set(engine)):
        generator, graph = local.get(row_id, "(absent)"), engine.get(row_id, "(absent)")
        if generator != graph:
            findings.append(f"{row_id}: generator says {generator}, engine says {graph}")
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="states-agree", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    target = target_from_environment()
    if target is None:
        print("states-agree: ADVISORY: no arbora endpoint is configured; the graph was not compared")
        return 0
    revision = git_text(root, ("rev-parse", "--verify", f"{args.head}^{{commit}}")).strip()
    repository = setting("GITHUB_REPOSITORY") or root.name
    try:
        answer = post_operation(
            target.endpoint, target.token, STATUS_OPERATION, {"repository": repository, "rev": revision}
        )
    except OSError as exc:
        print(f"states-agree: ADVISORY: the engine is unreachable ({exc}); the graph was not compared")
        return 0
    found = disagreements(local_states(root, revision), engine_states(answer))
    if found:
        print("FAIL: the engine and the generator disagree on these rows:")
        for finding in found:
            print(f"    {finding}")
        return 1
    print(f"states-agree: OK: engine and generator agree at {revision[:12]}")
    return 0
