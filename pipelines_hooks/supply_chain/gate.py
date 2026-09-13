"""supply-chain gate: one repository, a fleet of nested repositories, or a source snapshot.

    pipelines-hook supply-chain .
    pipelines-hook supply-chain --fleet-root ../
    pipelines-hook supply-chain --source-snapshot-root ../agents --snapshot-workspace <workspace.yml>
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.supply_chain import containers, precommit, workflows
from pipelines_hooks.supply_chain.dependencies import dependency_findings, installer_findings
from pipelines_hooks.supply_chain.finding import Finding, Source
from pipelines_hooks.supply_chain.inventory import asset_kinds, discover_repositories, read_source, repository_label, source_files
from pipelines_hooks.supply_chain.secrets import content_finding, secret_findings, sensitive_file_findings
from pipelines_hooks.supply_chain.snapshot import SnapshotBudget, read_snapshot_bytes, read_snapshot_source, resolve_snapshot_repositories, snapshot_source_files

RULES: dict[str, Callable[[Source], list[Finding]]] = {
    "workflow": workflows.workflow_findings,
    "precommit": precommit.precommit_findings,
    "docker": containers.docker_findings,
    "compose": containers.compose_findings,
    "installer": installer_findings,
}


def snapshot_secret_findings(label: str, repository: Path, sources: tuple[Path, ...]) -> list[Finding]:
    """The Git secret policy applied to a no-Git source inventory."""
    findings = sensitive_file_findings(label, repository, sources)
    for path in sources:
        content = read_snapshot_bytes(path)
        if b"\0" in content:
            continue
        relative = path.relative_to(repository).as_posix()
        for number, value in enumerate(content.decode("utf-8", errors="replace").splitlines(), 1):
            finding = content_finding(label, path=relative, line=number, content=value)
            findings.extend([finding] if finding else [])
    return findings


def _asset_findings(label: str, path: Path, *, relative: Path, reader: Callable[[Path], str]) -> list[Finding] | None:
    """Rule findings for one workflow/container asset, ``None`` when it is not one."""
    kinds = asset_kinds(relative)
    if not kinds:
        return None
    try:
        source = Source(label, relative.as_posix(), reader(path))
    except CannotRun as error:
        return [Finding(label, relative.as_posix(), 0, "SC-SRC-001", str(error))]
    return [finding for kind in kinds for finding in RULES[kind](source)]


def inspect(repository: Path, fleet_root: Path, *, snapshot: SnapshotBudget | None) -> tuple[list[Finding], int]:
    """Findings and the count of inspected workflow/container assets for one repository.

    A tracked path deleted in the working tree is not executable source and is
    skipped; in snapshot mode every inventoried file must still exist.
    """
    label = repository_label(repository, fleet_root)
    if snapshot is None:
        sources, reader, secrets = source_files(repository), read_source, secret_findings
        present = [path for path in sources if path.exists()]
    else:
        sources, reader, secrets = snapshot_source_files(repository, snapshot), read_snapshot_source, snapshot_secret_findings
        present = list(sources)
    findings = dependency_findings(label, repository, sources, reader=reader) + secrets(label, repository, sources)
    assets = [_asset_findings(label, path, relative=path.relative_to(repository), reader=reader) for path in present]
    inspected = [found for found in assets if found is not None]
    return findings + [f for found in inspected for f in found], len(inspected)


def _repositories(arguments: argparse.Namespace) -> tuple[Path, tuple[Path, ...], SnapshotBudget | None]:
    if arguments.source_snapshot_root:
        root, repositories = resolve_snapshot_repositories(Path(arguments.source_snapshot_root), Path(arguments.snapshot_workspace))
        return root, repositories, SnapshotBudget()
    fleet_root = Path(arguments.fleet_root or arguments.root).resolve()
    repositories = discover_repositories(fleet_root)
    if not repositories:
        raise CannotRun("no Git repositories were discovered")
    return fleet_root, repositories, None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="supply-chain", description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--root", dest="root", help="alias of the positional repository root")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fleet-root")
    mode.add_argument("--source-snapshot-root")
    parser.add_argument("--snapshot-workspace")
    arguments = parser.parse_args(argv)
    if (arguments.source_snapshot_root is None) != (arguments.snapshot_workspace is None):
        parser.error("--source-snapshot-root and --snapshot-workspace must be used together")
    fleet_root, repositories, budget = _repositories(arguments)
    results = [inspect(repository, fleet_root, snapshot=budget) for repository in repositories]
    findings = sorted({f for found, _ in results for f in found})
    for finding in findings:
        print(f"  FAIL {finding.render()}")
    if findings:
        print(f"supply-chain: FAILED ({len(findings)} findings across {len(repositories)} repositories)", file=sys.stderr)
        return 1
    print(f"supply-chain: clean ({len(repositories)} repositories, {sum(n for _, n in results)} workflow/container assets)")
    return 0
