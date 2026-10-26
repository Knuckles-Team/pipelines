"""Bounded test-layout independence execution and evidence for PIPE-PAGES-R039."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import random
import selectors
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import sanitized_env
from pipelines_hooks.ci_replica.test_layout_inventory import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_OUTPUT_BYTES,
    MAX_STATE_FILES,
    MAX_TIMEOUT_SECONDS,
    ProjectInventory,
    ProjectLayout,
    TestLayoutPolicy,
    _declared_path,
    _project_path,
    inventory_project,
    load_policy,
    policy_digest,
    policy_path_in_source,
    selected_source,
)


def _copy_project(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, symlinks=True)


Collector = Callable[[Path, tuple[str, ...]], tuple[str, ...]]
Runner = Callable[[Path, tuple[str, ...], float], Mapping[str, object]]


@dataclass(frozen=True)
class _BoundedResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def _run_bounded(command: Sequence[str], cwd: Path, timeout: float) -> _BoundedResult:
    """Run one child with finite time and bounded stdout/stderr capture."""
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not 0 < float(timeout) <= MAX_TIMEOUT_SECONDS
    ):
        raise CannotRun(f"test-layout timeout must be in (0, {MAX_TIMEOUT_SECONDS:g}]")
    try:
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            env=sanitized_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise CannotRun(f"test-layout subprocess is unavailable: {exc}") from exc

    def kill() -> None:
        try:
            process.kill()
        except ProcessLookupError:
            pass

    if process.stdout is None or process.stderr is None:
        kill()
        process.wait()
        raise CannotRun("test-layout subprocess pipes are unavailable")
    stdout_stream, stderr_stream = process.stdout, process.stderr
    streams = {
        stdout_stream.fileno(): stdout_stream,
        stderr_stream.fileno(): stderr_stream,
    }
    stdout_fd, stderr_fd = stdout_stream.fileno(), stderr_stream.fileno()
    selector = selectors.DefaultSelector()
    for fd, stream in streams.items():
        selector.register(fd, selectors.EVENT_READ, stream)
    captured = {fd: bytearray() for fd in streams}
    timed_out = False
    try:
        deadline = time.monotonic() + float(timeout)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                kill()
                break
            for key, _events in selector.select(min(remaining, 0.05)):
                fd = int(key.fd)
                data = os.read(fd, MAX_OUTPUT_BYTES + 1 - len(captured[fd]))
                if not data:
                    selector.unregister(fd)
                    continue
                captured[fd].extend(data)
                if len(captured[fd]) > MAX_OUTPUT_BYTES:
                    kill()
                    stream_name = "stdout" if fd == process.stdout.fileno() else "stderr"
                    raise CannotRun(f"test-layout {stream_name} exceeded {MAX_OUTPUT_BYTES} captured bytes")
        if process.poll() is None:
            kill()
        try:
            returncode = process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            kill()
            returncode = process.wait(timeout=1)
    except BaseException:
        if process.poll() is None:
            kill()
        process.wait()
        raise
    finally:
        selector.close()
        for stream in streams.values():
            stream.close()

    def decode(value: bytearray) -> str:
        return bytes(value).decode("utf-8", errors="replace")

    return _BoundedResult(returncode, decode(captured[stdout_fd]), decode(captured[stderr_fd]), timed_out)


def _default_collector(
    project_root: Path, test_files: tuple[str, ...], timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> tuple[str, ...]:
    result = _run_bounded([sys.executable, "-m", "pytest", "--collect-only", "-q", *test_files], project_root, timeout)
    if result.timed_out:
        raise CannotRun("test-layout collection timed out")
    if result.returncode != 0:
        raise CannotRun(f"test-layout collection failed: {(result.stderr or result.stdout).strip()[:400]}")
    collected = tuple(line.strip() for line in result.stdout.splitlines() if "::" in line and not line.startswith("="))
    if not collected:
        raise CannotRun("test-layout collection returned no test cases")
    return collected


def _default_runner(project_root: Path, tests: tuple[str, ...], timeout: float) -> Mapping[str, object]:
    with tempfile.NamedTemporaryFile(dir=project_root, suffix=".xml", delete=False) as output:
        report = Path(output.name)
    try:
        result = _run_bounded(
            [sys.executable, "-m", "pytest", "-q", f"--junitxml={report}", *tests], project_root, timeout
        )
        if result.timed_out:
            return {test: "timeout" for test in tests}
        try:
            root = ElementTree.parse(report).getroot()
            cases = list(root.iter("testcase"))
        except (OSError, ElementTree.ParseError) as exc:
            raise CannotRun(f"test-layout runner produced missing or malformed JUnit: {report.name}") from exc
        if len(cases) != len(tests):
            raise CannotRun(
                f"test-layout runner produced incomplete JUnit: expected {len(tests)} cases, observed {len(cases)}"
            )
        outcomes: list[str] = []
        for case in cases:
            if case.find("error") is not None or case.find("failure") is not None:
                outcomes.append("failed")
            elif case.find("skipped") is not None:
                outcomes.append("skipped")
            else:
                outcomes.append("passed")
        if result.returncode not in (0, 1) or (
            result.returncode == 1 and all(status == "passed" for status in outcomes)
        ):
            raise CannotRun(f"test-layout runner exit {result.returncode} disagrees with JUnit outcomes")
        return dict(zip(tests, outcomes, strict=True))
    finally:
        report.unlink(missing_ok=True)


def _snapshot_state(project_root: Path, boundaries: tuple[str, ...]) -> dict[str, str]:
    paths: list[Path] = []
    for boundary in boundaries:
        path = _declared_path(project_root, boundary, "isolation_boundaries")
        if not path.exists():
            raise CannotRun(f"test-layout isolation boundary is unavailable: {boundary}")
        if path.is_symlink():
            raise CannotRun(f"test-layout isolation boundary is a symlink: {boundary}")
        paths.extend([path] if path.is_file() else sorted(item for item in path.rglob("*") if item.is_file()))
        if any(item.is_symlink() for item in paths):
            raise CannotRun(f"test-layout isolation boundary contains a symlink: {boundary}")
    if len(paths) > MAX_STATE_FILES:
        raise CannotRun(f"test-layout isolation observation exceeds {MAX_STATE_FILES} files")
    result: dict[str, str] = {}
    for path in sorted(set(paths)):
        relative = path.relative_to(project_root).as_posix()
        result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _normalise_outcomes(tests: tuple[str, ...], values: Mapping[str, object]) -> dict[str, str]:
    result: dict[str, str] = {}
    for test in tests:
        value = values.get(test)
        status = value if isinstance(value, str) else getattr(value, "status", None)
        result[test] = str(status or "missing")
    return result


@dataclass(frozen=True)
class OrderEvidence:
    name: str
    seed: int | None
    tests: tuple[str, ...]
    outcomes: Mapping[str, str]
    state_before: Mapping[str, str]
    state_after: Mapping[str, str]


@dataclass(frozen=True)
class ProjectEvidence:
    inventory: ProjectInventory
    collected_tests: tuple[str, ...]
    orders: tuple[OrderEvidence, ...]
    findings: tuple[str, ...]
    status: int


@dataclass(frozen=True)
class LayoutReport:
    source_ref: str
    policy_digest: str
    shuffle_seeds: tuple[int, int]
    timeout_seconds: float
    projects: tuple[ProjectEvidence, ...]
    findings: tuple[str, ...]
    status: int

    def to_dict(self) -> dict[str, object]:
        return {
            "version": 1,
            "source_ref": self.source_ref,
            "policy_digest": self.policy_digest,
            "shuffle_seeds": list(self.shuffle_seeds),
            "timeout_seconds": self.timeout_seconds,
            "status": self.status,
            "scope": "declared order, reverse order, and two fixed seeded permutations",
            "findings": list(self.findings),
            "projects": [_project_dict(project) for project in self.projects],
        }


def _project_dict(evidence: ProjectEvidence) -> dict[str, object]:
    inventory = evidence.inventory
    return {
        "name": inventory.project.name,
        "root": inventory.project.root,
        "source_digest": inventory.source_digest,
        "unit_modules": list(inventory.unit_modules),
        "integration_modules": list(inventory.integration_modules),
        "fixtures": list(inventory.fixtures),
        "required_modules": list(inventory.required_modules),
        "unit_module_roots": list(inventory.project.unit_module_roots),
        "integration_module_roots": list(inventory.project.integration_module_roots),
        "isolation_boundaries": list(inventory.project.isolation_boundaries),
        "reset_contracts": list(inventory.project.reset_contracts),
        "test_files": list(inventory.test_files),
        "collected_tests": list(evidence.collected_tests),
        "orders": [
            {
                "name": order.name,
                "seed": order.seed,
                "tests": list(order.tests),
                "outcomes": dict(order.outcomes),
                "state_before": dict(order.state_before),
                "state_after": dict(order.state_after),
            }
            for order in evidence.orders
        ],
        "findings": list(evidence.findings),
        "status": evidence.status,
    }


def _orders(tests: tuple[str, ...], seeds: tuple[int, int]) -> tuple[tuple[str, int | None, tuple[str, ...]], ...]:
    result: list[tuple[str, int | None, tuple[str, ...]]] = [("declared", None, tests), ("reverse", None, tests[::-1])]
    for seed in seeds:
        values = list(tests)
        random.Random(seed).shuffle(values)
        result.append((f"seed-{seed}", seed, tuple(values)))
    return tuple(result)


def _check(
    root: Path,
    policy: TestLayoutPolicy,
    *,
    source_root: Path,
    source_ref: str,
    collector: Collector | None = None,
    runner: Runner | None = None,
) -> LayoutReport:
    """Run the bounded layout check and return a source-bound evidence report."""
    if collector is None:
        parameters = inspect.signature(_default_collector).parameters.values()
        supports_timeout = any(
            parameter.kind is inspect.Parameter.VAR_POSITIONAL or parameter.name == "timeout"
            for parameter in parameters
        )
        collector = (
            (lambda project_root, test_files: _default_collector(project_root, test_files, policy.timeout_seconds))
            if supports_timeout
            else _default_collector
        )
    runner = runner or _default_runner
    projects: list[ProjectEvidence] = []
    all_findings: list[str] = []
    for project in policy.projects:
        try:
            inventory = inventory_project(root, project, source_root=source_root)
            project_root = _project_path(source_root, project)
            collected = tuple(collector(project_root, inventory.test_files))
            if not collected:
                raise CannotRun(f"test-layout collector returned no tests: {project.name}")
            collected_files = {test.split("::", 1)[0] for test in collected}
            unknown = sorted(collected_files - set(inventory.test_files))
            if unknown:
                raise CannotRun(f"test-layout collector returned undeclared files: {', '.join(unknown)}")
            missing = sorted(set(inventory.test_files) - collected_files)
            if missing:
                raise CannotRun(f"test-layout collector omitted declared tests: {', '.join(missing)}")
            orders: list[OrderEvidence] = []
            findings: list[str] = []
            for name, seed, test_order in _orders(collected, policy.shuffle_seeds):
                with tempfile.TemporaryDirectory(prefix="pipelines-test-layout-") as temporary:
                    isolated = Path(temporary) / "project"
                    _copy_project(project_root, isolated)
                    before = _snapshot_state(isolated, project.isolation_boundaries)
                    try:
                        values = runner(isolated, test_order, policy.timeout_seconds)
                    except TimeoutError:
                        values = {test: "timeout" for test in test_order}
                    outcomes = _normalise_outcomes(test_order, values)
                    after = _snapshot_state(isolated, project.isolation_boundaries)
                orders.append(OrderEvidence(name, seed, test_order, outcomes, before, after))
            baseline = orders[0].outcomes
            for order in orders:
                if "timeout" in order.outcomes.values() or "missing" in order.outcomes.values():
                    findings.append(f"{project.name}: incomplete or timed-out order {order.name}")
                elif any(status != "passed" for status in order.outcomes.values()):
                    findings.append(f"{project.name}: tests did not all pass in order {order.name}")
                if order.outcomes != baseline:
                    findings.append(f"{project.name}: test outcomes depend on order {order.name}")
                if order.state_after != order.state_before and not _state_change_allowed(order, project):
                    findings.append(f"{project.name}: state escaped its reset contract in order {order.name}")
            status = (
                2
                if any("incomplete" in finding or "timed-out" in finding for finding in findings)
                else int(bool(findings))
            )
        except CannotRun as exc:
            inventory = ProjectInventory(project, (), (), (), (), (), "unavailable")
            collected = ()
            orders = []
            findings = [f"{project.name}: {exc}"]
            detail = str(exc)
            status = (
                1
                if (
                    "required fixture" in detail
                    or "required module" in detail
                    or "declared module root" in detail
                    or "outside project inventory" in detail
                )
                else 2
            )
        evidence = ProjectEvidence(inventory, collected, tuple(orders), tuple(findings), status)
        projects.append(evidence)
        all_findings.extend(findings)
    return LayoutReport(
        source_ref,
        policy_digest(policy),
        policy.shuffle_seeds,
        policy.timeout_seconds,
        tuple(projects),
        tuple(all_findings),
        max((project.status for project in projects), default=2),
    )


def check(
    root: Path,
    policy: TestLayoutPolicy,
    *,
    collector: Collector | None = None,
    runner: Runner | None = None,
) -> LayoutReport:
    """Run the checker against one exact selected Git index snapshot."""
    with selected_source(root) as (source_root, source_ref):
        return _check(
            root,
            policy,
            source_root=source_root,
            source_ref=source_ref,
            collector=collector,
            runner=runner,
        )


def _state_change_allowed(order: OrderEvidence, project: ProjectLayout) -> bool:
    changed = {
        path
        for path in set(order.state_before) | set(order.state_after)
        if order.state_before.get(path) != order.state_after.get(path)
    }
    return all(
        any(path == contract or path.startswith(contract.rstrip("/") + "/") for contract in project.reset_contracts)
        for path in changed
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="test-layout", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--inventory", "--policy", "--config", dest="inventory", type=Path, default=None)
    parser.add_argument("--evidence", type=Path, default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = args.root.resolve()
    try:
        with selected_source(root) as (source_root, source_ref):
            policy = load_policy(policy_path_in_source(root, source_root, args.inventory))
            report = _check(root, policy, source_root=source_root, source_ref=source_ref)
    except CannotRun as exc:
        print(f"test-layout: CANNOT RUN: {exc}")
        return 2
    payload = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    if args.evidence is not None:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return report.status


if __name__ == "__main__":
    raise SystemExit(main())
