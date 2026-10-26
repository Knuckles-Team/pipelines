"""The opt-in structural part of the shared KISS policy.

The pinned KISS scanner has useful positional-argument and try-body rules, but
its measurements do not cover the complete Python signature required by the
shared policy.  This adapter measures the complete Python AST directly and
keeps the scanner's existing predicates separate.  Consumers opt in with
``structural = true`` in ``[tool.pipelines_hooks.kiss]`` and must provide an
explicit, versioned ``[structural]`` table in ``.config/kiss.toml``.

The adapter deliberately supports Python only in version 1.  A configured
repository containing Rust source therefore fails closed until a versioned
Rust adapter exists; it is never treated as measured clean.
"""

from __future__ import annotations

import ast
import hashlib
import json
import tomllib
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable

from pipelines_hooks.core.config import load_config
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import git_text
from pipelines_hooks.core.layout import KISS_CONFIG, located

POLICY_VERSION = 1
ADAPTER_VERSION = "python-ast/v1"


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _digest_json(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _digest_bytes(encoded)


def _scanner_digest() -> str:
    """Bind evidence to this adapter's exact source when it is on disk."""
    try:
        return _digest_bytes(Path(__file__).read_bytes())
    except OSError:
        return _digest_json({"adapter": ADAPTER_VERSION})


@dataclass(frozen=True)
class StructuralPolicy:
    """Versioned limits for the complete Python signature and direct try body."""

    version: int
    max_function_arguments: int
    max_try_body_statements: int
    config_digest: str

    def validate(self) -> None:
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version != POLICY_VERSION:
            raise CannotRun(f"unsupported KISS structural policy version: {self.version!r}")
        for name, value in (
            ("max_function_arguments", self.max_function_arguments),
            ("max_try_body_statements", self.max_try_body_statements),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise CannotRun(f"KISS structural {name} must be a nonnegative integer")
        if not isinstance(self.config_digest, str) or not self.config_digest:
            raise CannotRun("KISS structural config digest is missing")

    @property
    def policy_digest(self) -> str:
        return _digest_json(
            {
                "version": self.version,
                "max_function_arguments": self.max_function_arguments,
                "max_try_body_statements": self.max_try_body_statements,
            }
        )


@dataclass(frozen=True)
class FunctionMeasurement:
    path: str
    qualified_name: str
    ordinal: int
    line: int
    count: int
    limit: int
    source_digest: str

    @property
    def violates(self) -> bool:
        return self.count > self.limit


@dataclass(frozen=True)
class TryMeasurement:
    path: str
    qualified_name: str
    line: int
    ordinal: int
    count: int
    limit: int
    source_digest: str

    @property
    def violates(self) -> bool:
        return self.count > self.limit


@dataclass(frozen=True)
class StructuralViolation:
    kind: str
    path: str
    qualified_name: str
    line: int
    measured: int
    limit: int
    ordinal: int | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class StructuralReport:
    """A bounded structural census and its evidence."""

    policy: StructuralPolicy
    source_snapshot: str
    checked_sources: tuple[str, ...]
    functions: tuple[FunctionMeasurement, ...]
    try_bodies: tuple[TryMeasurement, ...]
    violations: tuple[StructuralViolation, ...]
    scanner_version: str = ADAPTER_VERSION
    scanner_digest: str = ""

    @property
    def clean(self) -> bool:
        return not self.violations

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": "kiss-structural/v1",
            "scanner": {"version": self.scanner_version, "digest": self.scanner_digest},
            "policy": {
                "version": self.policy.version,
                "max_function_arguments": self.policy.max_function_arguments,
                "max_try_body_statements": self.policy.max_try_body_statements,
                "digest": self.policy.policy_digest,
                "config_digest": self.policy.config_digest,
            },
            "source_snapshot": self.source_snapshot,
            "checked_source_count": len(self.checked_sources),
            "checked_sources": list(self.checked_sources),
            "functions": [asdict(item) for item in self.functions],
            "try_bodies": [asdict(item) for item in self.try_bodies],
            "violations": [item.as_dict() for item in self.violations],
        }


def adopted(root: Path) -> bool:
    """Whether the consuming repository opted into this adapter."""
    section = load_config(root).section("kiss")
    value = section.get("structural", False)
    if not isinstance(value, bool):
        raise CannotRun("[tool.pipelines_hooks.kiss] structural must be a boolean")
    return value


def load_policy(root: Path) -> StructuralPolicy:
    """Read and validate the explicit structural table from a repository tree."""
    config_path = located(root, KISS_CONFIG)
    try:
        raw = config_path.read_bytes()
        document = tomllib.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"cannot read {KISS_CONFIG}: {exc}") from exc
    table = document.get("structural")
    if not isinstance(table, Mapping):
        raise CannotRun(f"{KISS_CONFIG} requires a [structural] table when KISS structural limits are adopted")
    expected = {"version", "max_function_arguments", "max_try_body_statements"}
    unknown = sorted(set(table) - expected)
    if unknown:
        raise CannotRun(f"[structural] has unknown key(s): {', '.join(unknown)}")
    missing = sorted(expected - set(table))
    if missing:
        raise CannotRun(f"[structural] is missing required key(s): {', '.join(missing)}")
    policy = StructuralPolicy(
        version=table["version"],
        max_function_arguments=table["max_function_arguments"],
        max_try_body_statements=table["max_try_body_statements"],
        config_digest=_digest_bytes(raw),
    )
    policy.validate()
    return policy


class _Measurements(ast.NodeVisitor):
    """Collect complete function signatures and direct try-body counts."""

    def __init__(self, path: str, source: str, policy: StructuralPolicy) -> None:
        self.path = path
        self.source = source
        self.policy = policy
        self.classes: list[str] = []
        self.functions_stack: list[str] = []
        self.functions: list[FunctionMeasurement] = []
        self.try_bodies: list[TryMeasurement] = []
        self._function_ordinals: dict[str, int] = {}
        self._try_ordinals: dict[str, int] = {}

    def _qualified(self, leaf: str | None = None) -> str:
        parts = [*self.classes, *self.functions_stack]
        if leaf is not None:
            parts.append(leaf)
        return ".".join(parts) if parts else "<module>"

    def _segment_digest(self, node: ast.AST) -> str:
        segment = ast.get_source_segment(self.source, node)
        if segment is None:
            segment = ast.dump(node, include_attributes=False)
        return _digest_bytes(segment.encode("utf-8"))

    @staticmethod
    def _argument_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
        args = node.args
        return (
            len(args.posonlyargs)
            + len(args.args)
            + len(args.kwonlyargs)
            + int(args.vararg is not None)
            + int(args.kwarg is not None)
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes.append(node.name)
        self.generic_visit(node)
        self.classes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualified = self._qualified(node.name)
        ordinal = self._function_ordinals.get(qualified, 0)
        self._function_ordinals[qualified] = ordinal + 1
        self.functions.append(
            FunctionMeasurement(
                path=self.path,
                qualified_name=qualified,
                ordinal=ordinal,
                line=node.lineno,
                count=self._argument_count(node),
                limit=self.policy.max_function_arguments,
                source_digest=self._segment_digest(node),
            )
        )
        self.functions_stack.append(node.name)
        self.generic_visit(node)
        self.functions_stack.pop()

    def visit_Try(self, node: ast.Try) -> None:
        self._visit_try(node)

    def visit_TryStar(self, node: ast.TryStar) -> None:
        """Treat ``except*`` blocks like ordinary try bodies when available."""
        self._visit_try(node)

    def _visit_try(self, node: ast.Try | ast.TryStar) -> None:
        qualified = self._qualified()
        ordinal = self._try_ordinals.get(qualified, 0)
        self._try_ordinals[qualified] = ordinal + 1
        self.try_bodies.append(
            TryMeasurement(
                path=self.path,
                qualified_name=qualified,
                line=node.lineno,
                ordinal=ordinal,
                count=len(node.body),
                limit=self.policy.max_try_body_statements,
                source_digest=self._segment_digest(node),
            )
        )
        self.generic_visit(node)


def _measure_file(
    path: str, source: str, policy: StructuralPolicy
) -> tuple[list[FunctionMeasurement], list[TryMeasurement]]:
    if not path.endswith(".py"):
        raise CannotRun(f"KISS structural policy has no versioned adapter for source {path}")
    try:
        tree = ast.parse(source, filename=path)
    except (SyntaxError, ValueError, TypeError, UnicodeError) as exc:
        raise CannotRun(f"KISS structural source measurement failed for {path}: {exc}") from exc
    visitor = _Measurements(path, source, policy)
    visitor.visit(tree)
    return visitor.functions, visitor.try_bodies


def load_sources(root: Path, paths: Iterable[str]) -> dict[str, str]:
    """Read repository-relative source bytes as UTF-8, refusing symlinks."""
    sources: dict[str, str] = {}
    for path in sorted(set(paths)):
        file = root / path
        if file.is_symlink():
            raise CannotRun(f"KISS structural source is a symlink: {path}")
        try:
            sources[path] = file.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise CannotRun(f"KISS structural source is unreadable: {path}: {exc}") from exc
    return sources


def inspect_sources(
    sources: Mapping[str, str],
    policy: StructuralPolicy,
    *,
    source_snapshot: str = "unbound",
) -> StructuralReport:
    """Measure a deterministic source mapping without touching Git or a scanner."""
    policy.validate()
    functions: list[FunctionMeasurement] = []
    try_bodies: list[TryMeasurement] = []
    for path in sorted(sources):
        if Path(path).is_absolute() or ".." in Path(path).parts:
            raise CannotRun(f"KISS structural source path is not repository-relative: {path!r}")
        measured_functions, measured_try_bodies = _measure_file(path, sources[path], policy)
        functions.extend(measured_functions)
        try_bodies.extend(measured_try_bodies)
    violations = [
        StructuralViolation(
            kind="function-arguments",
            path=item.path,
            qualified_name=item.qualified_name,
            ordinal=item.ordinal,
            line=item.line,
            measured=item.count,
            limit=item.limit,
        )
        for item in functions
        if item.violates
    ]
    violations.extend(
        StructuralViolation(
            kind="try-body-statements",
            path=item.path,
            qualified_name=item.qualified_name,
            line=item.line,
            measured=item.count,
            limit=item.limit,
            ordinal=item.ordinal,
        )
        for item in try_bodies
        if item.violates
    )
    violations.sort(key=lambda item: (item.path, item.line, item.kind, item.qualified_name))
    return StructuralReport(
        policy=policy,
        source_snapshot=source_snapshot,
        checked_sources=tuple(sorted(sources)),
        functions=tuple(sorted(functions, key=lambda item: (item.path, item.line, item.qualified_name))),
        try_bodies=tuple(sorted(try_bodies, key=lambda item: (item.path, item.line, item.ordinal))),
        violations=tuple(violations),
        scanner_digest=_scanner_digest(),
    )


def scan(
    root: Path, paths: Iterable[str], policy: StructuralPolicy, *, source_snapshot: str = "unbound"
) -> StructuralReport:
    """Measure source files in a repository tree."""
    return inspect_sources(load_sources(root, paths), policy, source_snapshot=source_snapshot)


def _measurement_key(item: FunctionMeasurement | TryMeasurement) -> tuple[object, ...]:
    if isinstance(item, FunctionMeasurement):
        return ("function", item.path, item.qualified_name, item.ordinal)
    return ("try", item.path, item.qualified_name, item.ordinal)


def staged_report(
    staged_sources: Mapping[str, str],
    head_sources: Mapping[str, str],
    policy: StructuralPolicy,
    *,
    source_snapshot: str = "unbound",
) -> StructuralReport:
    """Return staged measurements, retaining only newly introduced violations."""
    staged = inspect_sources(staged_sources, policy, source_snapshot=source_snapshot)
    head = inspect_sources(head_sources, policy, source_snapshot="head") if head_sources else None
    if head is None:
        return staged
    head_measurements_list: list[FunctionMeasurement | TryMeasurement] = [*head.functions, *head.try_bodies]
    head_measurements = {_measurement_key(item): item.source_digest for item in head_measurements_list}
    staged_measurements: list[FunctionMeasurement | TryMeasurement] = [*staged.functions, *staged.try_bodies]
    attributable: list[StructuralViolation] = []
    for violation in staged.violations:
        matching = next(
            (
                item
                for item in staged_measurements
                if item.path == violation.path
                and item.qualified_name == violation.qualified_name
                and (
                    (violation.kind == "function-arguments" and isinstance(item, FunctionMeasurement))
                    or (violation.kind == "try-body-statements" and isinstance(item, TryMeasurement))
                )
                and item.ordinal == violation.ordinal
            ),
            None,
        )
        if matching is None or head_measurements.get(_measurement_key(matching)) != matching.source_digest:
            attributable.append(violation)
    return replace(staged, violations=tuple(attributable))


def source_snapshot(root: Path, *, staged: bool = False) -> str:
    """Bind evidence to HEAD or the materialized staged index."""
    args = ("write-tree",) if staged else ("rev-parse", "HEAD")
    return git_text(root, args, preserve_index=True).strip()


def render(report: StructuralReport) -> list[str]:
    """Human-readable evidence shared by staged and census callers."""
    lines = [
        "structural: "
        f"scanner={report.scanner_version} scanner_digest={report.scanner_digest} "
        f"policy=v{report.policy.version} policy_digest={report.policy.policy_digest} "
        f"config_digest={report.policy.config_digest} source_snapshot={report.source_snapshot} "
        f"checked_sources={len(report.checked_sources)}",
    ]
    for function_item in report.functions:
        lines.append(
            f"structural function {function_item.path}:{function_item.line} {function_item.qualified_name}: "
            f"count={function_item.count} limit={function_item.limit} digest={function_item.source_digest}"
        )
    for try_item in report.try_bodies:
        lines.append(
            f"structural try {try_item.path}:{try_item.line} {try_item.qualified_name}#{try_item.ordinal}: "
            f"count={try_item.count} limit={try_item.limit} digest={try_item.source_digest}"
        )
    for violation in report.violations:
        lines.append(
            f"STRUCTURAL VIOLATION {violation.kind} {violation.path}:{violation.line} {violation.qualified_name}: "
            f"measured={violation.measured} limit={violation.limit}"
        )
    lines.append(
        f"structural: {len(report.functions)} function(s), {len(report.try_bodies)} try body(ies), "
        f"{len(report.violations)} violation(s)"
    )
    return lines


def adopted_policy(root: Path) -> StructuralPolicy | None:
    """Return the explicit policy only for an opted-in consuming repository."""
    return load_policy(root) if adopted(root) else None
