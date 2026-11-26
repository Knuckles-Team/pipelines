"""test-quality: placeholder tests, unjustified suppressions and a coverage floor.

A test whose body is only ``pass``, ``...`` or ``assert True`` proves nothing.
A suppression comment (``noqa``, ``type: ignore``, ``pragma: no cover``) or a
``skip``/``xfail`` mark in a test file must carry a reason of at least
``MIN_REASON`` characters. Measured coverage, read from a coverage.py JSON
report, must reach the threshold (default 80 percent). No report is exit 2: the
gate never passes without a measured percentage.
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import tokenize
from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.tracked import tracked_or_walked

RULES = (
    "placeholder-test",
    "unjustified-suppression",
    "coverage-below-threshold",
    "interface-violation",
    "missing-property-proof",
    "missing-integration-proof",
    "orphan-module",
    "outcome-not-observed",
    "isolation-violation",
    "handoff-receipt-invalid",
)
DEFAULT_COMPONENTS = ".pipelines/components.toml"
DEFAULT_OUTCOMES = ".pipelines/outcomes.toml"
DEFAULT_THRESHOLD = 80.0
MIN_REASON = 10
DEFAULT_REPORT = "coverage.json"
_SUPPRESSION_RE = re.compile(r"#\s*(?:noqa|type:\s*ignore|pragma:\s*no\s+cover)\b(?P<rest>.*)", re.I)
_REASON_RE = re.compile(r"--\s*(?P<reason>.*)$")


@dataclass(frozen=True)
class TestQualityFinding:
    """One located finding; ``rule`` is one of :data:`RULES`."""

    __test__ = False

    path: str
    line: int
    rule: str
    detail: str = ""

    def __post_init__(self) -> None:
        if self.rule not in RULES:
            raise ValueError(f"unknown test-quality rule {self.rule!r}; expected one of {', '.join(RULES)}")

    def render(self) -> str:
        return f"{self.path}:{self.line} {self.rule}" + (f" -- {self.detail}" if self.detail else "")


@dataclass(frozen=True)
class Scan:
    files: int
    findings: tuple[TestQualityFinding, ...]


def _is_placeholder(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    body = function.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    if not body:
        return True

    def trivial(node: ast.stmt) -> bool:
        if isinstance(node, ast.Pass):
            return True
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and node.value.value is Ellipsis:
            return True
        return isinstance(node, ast.Assert) and isinstance(node.test, ast.Constant) and node.test.value is True

    return all(trivial(node) for node in body)


def _skip_without_reason(node: ast.AST) -> int | None:
    """Line of a ``pytest.mark.skip``/``xfail`` decorator whose reason is missing or short."""
    target = node.func if isinstance(node, ast.Call) else node
    if not (isinstance(target, ast.Attribute) and target.attr in {"skip", "xfail"}):
        return None
    if not (isinstance(target.value, ast.Attribute) and target.value.attr == "mark"):
        return None
    reason = ""
    if isinstance(node, ast.Call):
        for keyword in node.keywords:
            if keyword.arg == "reason" and isinstance(keyword.value, ast.Constant):
                reason = str(keyword.value.value)
    return None if len(reason.strip()) >= MIN_REASON else getattr(node, "lineno", 1)


def _comment_suppressions(source: str, rel: str) -> list[TestQualityFinding]:
    found: list[TestQualityFinding] = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.COMMENT:
            continue
        match = _SUPPRESSION_RE.search(token.string)
        if not match:
            continue
        reason = _REASON_RE.search(match.group("rest"))
        if not reason or len(reason.group("reason").strip()) < MIN_REASON:
            found.append(TestQualityFinding(rel, token.start[0], "unjustified-suppression"))
    return found


def scan(root: Path, threshold: float = DEFAULT_THRESHOLD, *, coverage_report: str = DEFAULT_REPORT) -> Scan:
    """Scan every tracked test file and compare measured coverage with ``threshold``."""
    findings: list[TestQualityFinding] = []
    files = tracked_or_walked(root, ("test_*.py", "*_test.py"), root=root)
    for path in sorted(files):
        rel = path.relative_to(root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=rel)
            findings.extend(_comment_suppressions(source, rel))
        except (SyntaxError, UnicodeError, tokenize.TokenError) as exc:
            raise CannotRun(f"test-quality: cannot parse {rel}: {exc}") from exc
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test") and _is_placeholder(node):
                    findings.append(TestQualityFinding(rel, node.lineno, "placeholder-test"))
                findings.extend(
                    TestQualityFinding(rel, line, "unjustified-suppression")
                    for decorator in node.decorator_list
                    if (line := _skip_without_reason(decorator)) is not None
                )
    percent = measured_coverage(root, coverage_report)
    if percent < threshold:
        findings.append(TestQualityFinding(coverage_report, 1, "coverage-below-threshold"))
    return Scan(len(files), tuple(sorted(findings, key=lambda f: (f.path, f.line, f.rule))))


def measured_coverage(root: Path, report: str = DEFAULT_REPORT) -> float:
    """The measured percentage from a coverage.py JSON report; absent or malformed is CannotRun."""
    path = root / report
    if not path.is_file():
        raise CannotRun(f"test-quality: no coverage report at {report}; run the tests with coverage first")
    try:
        percent = json.loads(path.read_text(encoding="utf-8"))["totals"]["percent_covered"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CannotRun(f"test-quality: {report} is not a coverage.py JSON report: {exc}") from exc
    if isinstance(percent, bool) or not isinstance(percent, (int, float)):
        raise CannotRun(f"test-quality: {report} has no numeric totals.percent_covered")
    return float(percent)


def extension_findings(root: Path, args: argparse.Namespace) -> tuple[list[TestQualityFinding], dict[str, object]]:
    """Boundary, outcome, closure and unit-profile passes; each runs only when declared or selected."""
    from pipelines_hooks.code import boundaries, coverage_closure, graph_workflow_receipt, outcomes, unit_profile

    found: list[TestQualityFinding] = []
    evidence: dict[str, object] = {}
    components = args.components or (root / DEFAULT_COMPONENTS if (root / DEFAULT_COMPONENTS).is_file() else None)
    if components:
        boundary = boundaries.check(root, root / components)
        found += [TestQualityFinding(f.path, f.line, f.rule, f.detail) for f in boundary.findings]
        evidence["boundaries"] = boundary.evidence
    contract = args.outcomes or (root / DEFAULT_OUTCOMES if (root / DEFAULT_OUTCOMES).is_file() else None)
    if contract:
        proof = outcomes.check(root, root / contract)
        found += [TestQualityFinding(*t) for t in proof.findings]
        evidence["outcomes"] = proof.evidence
    if args.closure:
        closure = coverage_closure.check(root, root / args.closure)
        found += [TestQualityFinding(*t) for t in closure.findings]
        evidence["closure"] = closure.projects
    if args.unit_profile:
        unit = unit_profile.check(root, root / args.unit_profile)
        found += [TestQualityFinding(*t) for t in unit.findings]
        evidence["unit_profile"] = unit.evidence
    if args.graph_workflow_receipt:
        handoff = graph_workflow_receipt.check(args.graph_workflow_receipt, dict(args.expect_revision or []))
        found += [TestQualityFinding(*t[:2], "handoff-receipt-invalid", t[2]) for t in handoff.findings]
        evidence["graph_workflow"] = handoff.evidence
    return found, evidence


def _revision(text: str) -> tuple[str, str]:
    name, _, revision = text.partition("=")
    if not name or not revision:
        raise argparse.ArgumentTypeError("expected producer=revision")
    return name, revision


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="test-quality", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--coverage-report", default=DEFAULT_REPORT)
    parser.add_argument("--components", type=Path, help=f"component declaration (default {DEFAULT_COMPONENTS})")
    parser.add_argument("--outcomes", type=Path, help=f"outcome contract (default {DEFAULT_OUTCOMES})")
    parser.add_argument("--closure", type=Path, help="coverage closure policy: zero uncovered executable lines")
    parser.add_argument("--unit-profile", type=Path, help="hermetic unit profile policy")
    parser.add_argument(
        "--graph-workflow-receipt", type=Path, help="owner acceptance receipt of a graph-to-ingestion run"
    )
    parser.add_argument(
        "--expect-revision", type=_revision, action="append", help="producer=revision the receipt binds"
    )
    parser.add_argument(
        "--require-declared",
        action="store_true",
        help="a consumer without a component declaration and an outcome contract is exit 2, never a pass",
    )
    parser.add_argument("--evidence", type=Path, help="write the structured evidence JSON here")
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    if args.require_declared:
        for given, default, what in (
            (args.components, DEFAULT_COMPONENTS, "component declaration"),
            (args.outcomes, DEFAULT_OUTCOMES, "outcome contract"),
        ):
            if not (root / (given or default)).is_file():
                raise CannotRun(
                    f"test-quality: {root.name} has no {what} at {given or default}; --require-declared refuses"
                )
    result = scan(root, args.threshold, coverage_report=args.coverage_report)
    percent = measured_coverage(root, args.coverage_report)
    placeholders = sum(1 for finding in result.findings if finding.rule == "placeholder-test")
    print(
        f"test-quality: files {result.files}, placeholders {placeholders}, "
        f"coverage {percent:g}%, threshold {args.threshold:g}%"
    )
    extra, evidence = extension_findings(root, args)
    findings = sorted([*result.findings, *extra], key=lambda f: (f.path, f.line, f.rule))
    for finding in findings:
        print(f"  {finding.render()}")
    if args.evidence:
        args.evidence.write_text(json.dumps(evidence, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return 1 if findings else 0
