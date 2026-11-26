"""One versioned, validated report shared by every repository-validation producer.

``ValidationReport`` nests repository and snapshot identity, categories, the executed
analyzer or test identity and stable rule records.  Each rule outcome is ``pass``,
``fail`` or ``skip`` and carries a reason; a fail keeps located evidence.  The
invocation status (``complete`` or ``cannot-run``) is recorded separately, so a skip
cannot masquerade as a pass.  Counts and the verdict are recomputed on import: a
tampered or truncated document is refused, never trusted.  Markdown is rendered from
the same object and is never read back as evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from pipelines_hooks.core.errors import CannotRun

SCHEMA_VERSION: Literal["validation-report-v1"] = "validation-report-v1"
MAX_REPORT_BYTES = 4 * 1024 * 1024
MAX_DETAIL = 1000
Outcome = Literal["pass", "fail", "skip"]
Verdict = Literal["pass", "fail", "cannot-run"]
_SECRET_RE = re.compile(
    r"(?i)((?:token|secret|passwd|password|api[_-]?key|authorization)\s*[=:]\s*)\S+"
    r"|\b(?:gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)


def redact(text: str) -> str:
    """Bound a diagnostic and replace credential-shaped payloads."""
    cleaned = _SECRET_RE.sub(lambda m: f"{m.group(1) or ''}[REDACTED]", text)
    return cleaned if len(cleaned) <= MAX_DETAIL else cleaned[:MAX_DETAIL] + "...[truncated]"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Evidence(_Model):
    """One located piece of evidence; the path is repository-relative."""

    path: str = Field(min_length=1)
    line: int | None = Field(default=None, ge=1)
    observed: str | None = None
    expected: str | None = None
    detail: str = ""

    @field_validator("path")
    @classmethod
    def _relative(cls, value: str) -> str:
        if value.startswith("/") or ".." in value.split("/") or "\\" in value or re.match(r"^[A-Za-z]:", value):
            raise ValueError(f"evidence path is not repository-relative: {value!r}")
        return value

    @field_validator("observed", "expected", "detail")
    @classmethod
    def _redacted(cls, value: str | None) -> str | None:
        return None if value is None else redact(value)


class RuleRecord(_Model):
    rule: str = Field(min_length=1)
    outcome: Outcome
    reason: str = Field(min_length=1)
    required: bool = True
    verbosity: Literal["summary", "detail"] = "detail"
    evidence: tuple[Evidence, ...] = ()

    @model_validator(mode="after")
    def _failure_is_located(self) -> RuleRecord:
        if self.outcome == "fail" and not self.evidence:
            raise ValueError(f"failed rule {self.rule!r} must carry located evidence")
        return self


class CheckRecord(_Model):
    """One executed analyzer or test run for one category."""

    category: str = Field(min_length=1)
    identity: str = Field(min_length=1)
    status: Literal["complete", "cannot-run"] = "complete"
    status_reason: str | None = None
    command: tuple[str, ...] = ()
    duration_ms: int = Field(default=0, ge=0)
    source_digest: str = ""
    policy_digest: str = ""
    scope: tuple[str, ...] = ()
    required: bool = True
    rules: tuple[RuleRecord, ...] = ()

    @model_validator(mode="after")
    def _consistent(self) -> CheckRecord:
        if self.status == "cannot-run" and not self.status_reason:
            raise ValueError(f"cannot-run check {self.identity!r} needs a reason")
        names = [rule.rule for rule in self.rules]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate rule identity in {self.category}/{self.identity}")
        return self


class SkillResult(_Model):
    """One graded skill bound to the snapshot, the skill digest and the policy."""

    skill_path: str = Field(min_length=1)
    snapshot: str = Field(min_length=1)
    skill_digest: str = Field(min_length=1)
    policy_digest: str = Field(min_length=1)
    status: Literal["pass", "fail", "skip"]
    grade: int | None = Field(default=None, ge=0, le=100)
    minimum_grade: int | None = Field(default=None, ge=0, le=100)
    criteria: dict[str, int] = Field(default_factory=dict)
    lineage: tuple[str, ...] = ()
    findings: tuple[Evidence, ...] = ()
    skip_reason: str | None = None

    @model_validator(mode="after")
    def _skip_has_reason(self) -> SkillResult:
        if self.status == "skip" and not self.skip_reason:
            raise ValueError(f"skipped skill {self.skill_path!r} needs a reason")
        return self


class SkillInventory(_Model):
    roots: tuple[str, ...] = ()
    applicable: bool = True
    reason: str | None = None
    results: tuple[SkillResult, ...] = ()

    @model_validator(mode="after")
    def _explicit_empty(self) -> SkillInventory:
        if not self.results and (self.applicable or not self.reason):
            raise ValueError("an empty skill inventory must report non-applicability with a reason")
        if self.results and not self.applicable:
            raise ValueError("an inventory with results is applicable")
        paths = [result.skill_path for result in self.results]
        if len(paths) != len(set(paths)):
            raise ValueError("duplicate skill result identity")
        return self


class Counts(_Model):
    passed: int = 0
    failed: int = 0
    skipped: int = 0


def _tally(report_checks: tuple[CheckRecord, ...], skills: SkillInventory | None) -> dict[str, Counts]:
    tallies: dict[str, Counter[str]] = {}
    for check in report_checks:
        bucket = tallies.setdefault(check.category, Counter())
        for rule in check.rules:
            bucket[rule.outcome] += 1
        if check.status == "cannot-run":
            bucket["skip"] += 1
    if skills is not None:
        bucket = tallies.setdefault("skill", Counter())
        for result in skills.results:
            bucket[result.status] += 1
    return {name: Counts(passed=c["pass"], failed=c["fail"], skipped=c["skip"]) for name, c in sorted(tallies.items())}


def _verdict(checks: tuple[CheckRecord, ...], skills: SkillInventory | None) -> Verdict:
    if any(c.status == "cannot-run" and c.required for c in checks):
        return "cannot-run"
    if any(rule.outcome == "skip" and rule.required for c in checks for rule in c.rules):
        return "cannot-run"
    if any(rule.outcome == "fail" for c in checks for rule in c.rules):
        return "fail"
    if skills is not None and any(result.status == "fail" for result in skills.results):
        return "fail"
    return "pass"


def _full_coverage(checks: tuple[CheckRecord, ...], skills: SkillInventory | None) -> bool:
    if any(c.status != "complete" or any(r.outcome == "skip" for r in c.rules) for c in checks):
        return False
    return skills is None or (skills.applicable and all(r.status != "skip" for r in skills.results))


class ValidationReport(_Model):
    schema_version: Literal["validation-report-v1"] = SCHEMA_VERSION
    repository: str = Field(min_length=1)
    snapshot: str = Field(min_length=1)
    checks: tuple[CheckRecord, ...] = ()
    skills: SkillInventory | None = None
    counts: dict[str, Counts] = Field(default_factory=dict)
    verdict: Verdict = "pass"
    full_coverage: bool = True

    @model_validator(mode="after")
    def _recomputed(self) -> ValidationReport:
        identities = [(c.category, c.identity) for c in self.checks]
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate check identity")
        if self.counts != _tally(self.checks, self.skills):
            raise ValueError("counts are inconsistent with the records")
        if self.verdict != _verdict(self.checks, self.skills):
            raise ValueError("verdict is inconsistent with the records")
        if self.full_coverage != _full_coverage(self.checks, self.skills):
            raise ValueError("full_coverage is inconsistent with the records")
        return self

    @classmethod
    def build(
        cls,
        *,
        repository: str,
        snapshot: str,
        checks: list[CheckRecord] | tuple[CheckRecord, ...] = (),
        skills: SkillInventory | None = None,
    ) -> ValidationReport:
        """Assemble a report in stable order with recomputed counts and verdict."""
        ordered = tuple(
            sorted(
                (c.model_copy(update={"rules": tuple(sorted(c.rules, key=lambda r: r.rule))}) for c in checks),
                key=lambda c: (c.category, c.identity),
            )
        )
        if skills is not None:
            skills = skills.model_copy(update={"results": tuple(sorted(skills.results, key=lambda r: r.skill_path))})
        try:
            return cls(
                repository=repository,
                snapshot=snapshot,
                checks=ordered,
                skills=skills,
                counts=_tally(ordered, skills),
                verdict=_verdict(ordered, skills),
                full_coverage=_full_coverage(ordered, skills),
            )
        except ValidationError as exc:
            raise CannotRun(f"validation-report: invalid record: {exc.errors()[0]['msg']}") from exc

    @property
    def exit_code(self) -> int:
        """0 pass, 1 failed rule, 2 cannot-run (which takes precedence over a failure)."""
        return {"pass": 0, "fail": 1, "cannot-run": 2}[self.verdict]

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> ValidationReport:
        """Parse a canonical document; an unknown schema, tampering or truncation is ``CannotRun``."""
        if len(text.encode("utf-8")) > MAX_REPORT_BYTES:
            raise CannotRun("validation-report: document exceeds the size bound")
        try:
            payload = json.loads(text)
        except ValueError as exc:
            raise CannotRun(f"validation-report: malformed or truncated JSON: {exc}") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
            raise CannotRun("validation-report: unsupported schema version")
        try:
            return cls.model_validate(payload)
        except ValidationError as exc:
            first = exc.errors()[0]
            raise CannotRun(
                f"validation-report: refused: {first['msg']} at {'.'.join(map(str, first['loc']))}"
            ) from exc

    def to_markdown(self) -> str:
        """Render the same object as inert Markdown; nothing here is evidence to parse back."""
        lines = [
            f"# {self.schema_version}",
            f"- repository: {_md(self.repository)}",
            f"- snapshot: {_md(self.snapshot)}",
            f"- verdict: {self.verdict}",
            f"- full coverage: {str(self.full_coverage).lower()}",
        ]
        for name, c in self.counts.items():
            lines.append(f"- {_md(name)}: {c.passed} pass, {c.failed} fail, {c.skipped} skip")
        for check in self.checks:
            command = " ".join(check.command)
            lines += [
                f"\n## {_md(check.category)}: {_md(check.identity)}",
                f"- invocation: {check.status}"
                + (f" ({_md(check.status_reason or '')})" if check.status_reason else ""),
                f"- command: {_md(command)}" if command else "- command: none",
                f"- duration: {check.duration_ms} ms",
            ]
            for rule in check.rules:
                lines.append(f"- {_md(rule.rule)}: {rule.outcome.upper()}: {_md(rule.reason)}")
                lines += [f"  - {_evidence_line(item)}" for item in rule.evidence]
        if self.skills is not None:
            lines.append("\n## skills")
            lines.append(f"- roots: {', '.join(_md(r) for r in self.skills.roots) or 'none'}")
            if not self.skills.applicable:
                lines.append(f"- not applicable: {_md(self.skills.reason or '')}")
            for result in self.skills.results:
                lines.append(f"- {_md(result.skill_path)}: {result.status.upper()} grade={result.grade}")
                lines += [f"  - lineage {_md(item)}" for item in result.lineage]
                lines += [f"  - {_evidence_line(item)}" for item in result.findings]
                if result.skip_reason:
                    lines.append(f"  - skip: {_md(result.skip_reason)}")
        return "\n".join(lines) + "\n"


def _md(value: str) -> str:
    """Escape Markdown and HTML metacharacters and flatten line breaks."""
    flat = " ".join(value.split())
    return re.sub(r"([\\`*_{}\[\]<>()#+!|~])", r"\\\1", flat)


def _evidence_line(item: Evidence) -> str:
    where = f"{item.path}:{item.line}" if item.line else item.path
    detail = f" {item.detail}" if item.detail else ""
    return _md(f"{where}{detail}")
