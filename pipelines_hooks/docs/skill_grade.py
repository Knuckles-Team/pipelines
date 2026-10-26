"""Deterministic, offline quality grading for declared ``SKILL.md`` files.

The grader deliberately measures a small, versioned contract.  It does not
install a skill, infer quality from prose with a model, or contact an external
service.  A report is bound to the repository-relative source document and to
the effective policy digest so a host can consume the receipt without treating
it as admission or deployment approval.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import unquote, urlsplit

import yaml

from pipelines_hooks.connector.skill_checks.frontmatter import _split_frontmatter
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.docs.public_surface_constants import HEADING_RE, WINDOWS_ABSOLUTE_RE
from pipelines_hooks.docs.public_surface_links import _destinations


SCHEMA_VERSION = "skill-grade-v1"
CRITERIA = ("frontmatter", "description", "structure", "links", "file_metadata")
DEFAULT_CRITERION_WEIGHTS = {criterion: 20 for criterion in CRITERIA}
DEFAULT_MINIMUM_GRADE = 80
_DESCRIPTION_USE_RE = re.compile(r"\b(?:use(?:\s+this)?\s+when|when\s+(?:you|the\s+agent|an\s+agent))\b", re.I)
_FENCED_RE = re.compile(r"(?ms)^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?^ {0,3}\1[ \t]*$")
_SKILL_DIR_PARTS = {".git", ".venv", "venv", "__pycache__", "build", "dist"}


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _policy_values(schema_version: str, weights: Mapping[str, object], minimum_grade: object) -> dict[str, object]:
    if schema_version != SCHEMA_VERSION:
        raise CannotRun(f"skill-grade: unsupported policy schema {schema_version!r}")
    if any(not isinstance(key, str) for key in weights):
        raise CannotRun("skill-grade: criterion_weights keys must be strings")
    if set(weights) != set(CRITERIA):
        missing = sorted(set(CRITERIA) - set(weights))
        extra = sorted(set(weights) - set(CRITERIA))
        detail = []
        if missing:
            detail.append(f"missing {', '.join(missing)}")
        if extra:
            detail.append(f"unknown {', '.join(extra)}")
        raise CannotRun(f"skill-grade: criterion_weights must name exactly {', '.join(CRITERIA)} ({'; '.join(detail)})")
    checked: dict[str, int] = {}
    for criterion in CRITERIA:
        value = weights[criterion]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise CannotRun(f"skill-grade: weight for {criterion} must be a non-negative integer")
        checked[criterion] = value
    if sum(checked.values()) != 100:
        raise CannotRun("skill-grade: criterion weights must total 100")
    if isinstance(minimum_grade, bool) or not isinstance(minimum_grade, int) or not 0 <= minimum_grade <= 100:
        raise CannotRun("skill-grade: minimum_grade must be an integer from 0 through 100")
    return {"schema_version": schema_version, "criterion_weights": checked, "minimum_grade": minimum_grade}


@dataclass(frozen=True)
class SkillGradePolicy:
    """The reviewed versioned policy used by one skill-grade run."""

    schema_version: str = SCHEMA_VERSION
    criterion_weights: Mapping[str, int] = field(default_factory=lambda: dict(DEFAULT_CRITERION_WEIGHTS))
    minimum_grade: int = DEFAULT_MINIMUM_GRADE

    def __post_init__(self) -> None:
        _policy_values(self.schema_version, self.criterion_weights, self.minimum_grade)
        object.__setattr__(self, "criterion_weights", dict(self.criterion_weights))

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "criterion_weights": dict(self.criterion_weights),
            "minimum_grade": self.minimum_grade,
        }

    @property
    def digest(self) -> str:
        return _sha256(_canonical_json(self.as_dict()).encode("utf-8"))


@dataclass(frozen=True)
class SkillGradeFinding:
    """One located deterministic finding in a skill-grade report."""

    criterion: str
    code: str
    message: str
    source_document: str
    line: int | None = None
    target: str | None = None
    refusal: str | None = None

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "criterion": self.criterion,
            "code": self.code,
            "message": self.message,
            "source_document": self.source_document,
        }
        if self.line is not None:
            result["line"] = self.line
        if self.target is not None:
            result["target"] = self.target
        if self.refusal is not None:
            result["refusal"] = self.refusal
        return result


@dataclass(frozen=True)
class SkillGradeReport:
    """Evidence and verdict for one repository-relative ``SKILL.md``."""

    schema_version: str
    skill_path: str
    source_digest: str
    policy_digest: str
    scores: Mapping[str, int]
    criterion_weights: Mapping[str, int]
    findings: tuple[SkillGradeFinding, ...]
    total_grade: int
    minimum_grade: int
    status: str
    hard_failure: bool = False
    applicable: bool = True

    @property
    def document_path(self) -> str:
        """Alias used by consumers that call the field a document path."""
        return self.skill_path

    @property
    def document(self) -> str:
        """Short alias for the repository-relative skill document path."""
        return self.skill_path

    @property
    def criterion_scores(self) -> Mapping[str, int]:
        return self.scores

    @property
    def grade(self) -> int:
        return self.total_grade

    def as_dict(self) -> dict[str, object]:
        criteria = {
            criterion: {
                "score": self.scores[criterion],
                "weight": self.criterion_weights[criterion],
                "passed": self.scores[criterion] == self.criterion_weights[criterion],
            }
            for criterion in CRITERIA
        }
        return {
            "schema_version": self.schema_version,
            "skill_path": self.skill_path,
            "source_digest": self.source_digest,
            "policy_digest": self.policy_digest,
            "criteria": criteria,
            "scores": dict(self.scores),
            "findings": [finding.as_dict() for finding in self.findings],
            "total_grade": self.total_grade,
            "minimum_grade": self.minimum_grade,
            "status": self.status,
            "hard_failure": self.hard_failure,
            "applicable": self.applicable,
        }


DEFAULT_POLICY = SkillGradePolicy()


def policy_from_mapping(value: object) -> SkillGradePolicy:
    """Validate a strict policy mapping, failing closed on unknown fields."""
    if not isinstance(value, Mapping):
        raise CannotRun("skill-grade: policy must be a mapping")
    expected = {"schema_version", "criterion_weights", "minimum_grade"}
    if any(not isinstance(key, str) for key in value):
        raise CannotRun("skill-grade: policy keys must be strings")
    unknown = sorted(set(value) - expected)
    missing = sorted(expected - set(value))
    if unknown or missing:
        detail = []
        if unknown:
            detail.append(f"unknown field(s): {', '.join(unknown)}")
        if missing:
            detail.append(f"missing field(s): {', '.join(missing)}")
        raise CannotRun(f"skill-grade: malformed policy ({'; '.join(detail)})")
    schema_version = value["schema_version"]
    weights = value["criterion_weights"]
    minimum_grade = value["minimum_grade"]
    if not isinstance(schema_version, str) or not isinstance(weights, Mapping):
        raise CannotRun("skill-grade: malformed policy field types")
    _policy_values(schema_version, weights, minimum_grade)
    return SkillGradePolicy(schema_version, {str(key): int(item) for key, item in weights.items()}, int(minimum_grade))


def load_policy(path: Path) -> SkillGradePolicy:
    """Load a UTF-8 JSON/YAML policy with a strict schema."""
    try:
        raw = path.read_bytes()
    except (OSError, UnicodeError) as exc:
        raise CannotRun(f"skill-grade: cannot read policy {path}: {exc}") from exc
    try:
        value = yaml.safe_load(raw.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise CannotRun(f"skill-grade: malformed policy {path}: {exc}") from exc
    return policy_from_mapping(value)


def _finding(
    criterion: str,
    code: str,
    message: str,
    skill_path: str,
    *,
    line: int | None = None,
    target: str | None = None,
    refusal: str | None = None,
) -> SkillGradeFinding:
    return SkillGradeFinding(criterion, code, message, skill_path, line, target, refusal)


def _line_for(text: str, needle: str) -> int | None:
    index = text.find(needle)
    return None if index < 0 else text.count("\n", 0, index) + 1


def _heading_names(text: str) -> set[str]:
    prose = _FENCED_RE.sub("", text)
    return {match.group(2).strip().casefold() for match in HEADING_RE.finditer(prose)}


def _skill_roots(root: Path, declared: tuple[Path, ...] | None) -> list[Path]:
    if declared:
        roots: list[Path] = []
        for raw in declared:
            candidate = raw if raw.is_absolute() else root / raw
            candidate = candidate.resolve()
            if not candidate.is_dir():
                raise CannotRun(f"skill-grade: declared skills root is not a directory: {raw}")
            if not candidate.is_relative_to(root):
                raise CannotRun(f"skill-grade: declared skills root escapes repository: {raw}")
            roots.append(candidate)
        return sorted(set(roots))

    if (root / "SKILL.md").is_file():
        return [root]
    for depth in (1, 2):
        candidates = sorted(
            path for path in root.glob("/".join(["*"] * depth)) if path.is_dir() and path.name == "skills"
        )
        if candidates:
            candidate = candidates[0].resolve()
            if not candidate.is_relative_to(root):
                raise CannotRun("skill-grade: discovered skills root escapes repository")
            return [candidate]
    return []


def discover_skill_documents(root: Path, declared_roots: tuple[Path, ...] | None = None) -> tuple[Path, ...]:
    """Discover deterministic ``SKILL.md`` inputs under the declared scope."""
    root = root.resolve()
    if not root.is_dir():
        raise CannotRun(f"skill-grade: repository root is not a directory: {root}")
    documents: list[Path] = []
    for skill_root in _skill_roots(root, declared_roots):
        for path in sorted(skill_root.rglob("SKILL.md")):
            if any(part in _SKILL_DIR_PARTS for part in path.parts):
                continue
            if path.absolute().is_relative_to(root) or path.is_symlink():
                documents.append(path)
    return tuple(sorted(set(documents), key=lambda item: item.as_posix()))


def _link_findings(root: Path, document: Path, text: str, skill_path: str) -> tuple[list[SkillGradeFinding], bool]:
    findings: list[SkillGradeFinding] = []
    base = document.parent.resolve()
    root = root.resolve()
    if not base.is_relative_to(root):
        findings.append(
            _finding(
                "links",
                "unsafe-document-base",
                "document base resolves outside the repository",
                skill_path,
                refusal="unsafe-path",
            )
        )
        return findings, True

    for destination in _destinations(text):
        parsed = urlsplit(destination)
        # Web, mail and telephone links are intentionally offline: this gate
        # records no availability claim for them.
        if parsed.scheme.lower() in {"http", "https", "mailto", "tel"}:
            continue
        if parsed.netloc and not parsed.scheme:
            continue
        if parsed.scheme or parsed.netloc:
            findings.append(
                _finding(
                    "links",
                    "forbidden-url-scheme",
                    f"unsupported URL scheme in {destination!r}",
                    skill_path,
                    line=_line_for(text, destination),
                    refusal="unsupported-url-scheme",
                )
            )
            continue
        path_part = unquote(parsed.path).replace("\\", "/")
        if not path_part:
            continue
        line = _line_for(text, destination)
        if path_part.startswith("/") or WINDOWS_ABSOLUTE_RE.match(path_part):
            findings.append(
                _finding(
                    "links",
                    "unsafe-absolute-path",
                    f"local link is absolute: {destination!r}",
                    skill_path,
                    line=line,
                    refusal="unsafe-path",
                )
            )
            continue
        target = (base / path_part).resolve()
        if not target.is_relative_to(root):
            findings.append(
                _finding(
                    "links",
                    "unsafe-out-of-repository",
                    f"local link escapes the repository: {destination!r}",
                    skill_path,
                    line=line,
                    refusal="unsafe-path",
                )
            )
            continue
        relative_target = target.relative_to(root).as_posix()
        if not target.exists():
            findings.append(
                _finding(
                    "links",
                    "missing-target",
                    f"local link does not exist: {destination!r}",
                    skill_path,
                    line=line,
                    target=relative_target,
                    refusal="missing-target",
                )
            )
    # A link finding is a hard failure: a score cannot claim a resolved local
    # reference when the target is absent or the URL scheme is unsupported.
    # External web links produce no finding because this gate is explicitly
    # offline and makes no availability claim for them.
    return findings, bool(findings)


def grade_document(root: Path, document: Path, policy: SkillGradePolicy = DEFAULT_POLICY) -> SkillGradeReport:
    """Grade one skill document against ``root`` and a validated policy."""
    root = root.resolve()
    document = document if document.is_absolute() else root / document
    lexical = document.absolute()
    if not lexical.is_relative_to(root):
        raise CannotRun(f"skill-grade: skill document escapes repository: {document}")
    skill_path = lexical.relative_to(root).as_posix()
    findings: list[SkillGradeFinding] = []
    metadata_hard = False
    source_digest = "refused:unsafe-path"
    text: str | None = None
    payload: bytes | None = None

    if not document.exists() and not document.is_symlink():
        raise CannotRun(f"skill-grade: skill document is unreadable or missing: {skill_path}")
    if not document.is_file():
        findings.append(
            _finding("file_metadata", "not-regular-file", "skill document is not a regular file", skill_path)
        )
        metadata_hard = True
    else:
        resolved = document.resolve()
        if not resolved.is_relative_to(root):
            findings.append(
                _finding(
                    "file_metadata",
                    "symlink-escape",
                    "skill document resolves outside the repository",
                    skill_path,
                    refusal="unsafe-path",
                )
            )
            metadata_hard = True
        else:
            try:
                payload = document.read_bytes()
            except (OSError, UnicodeError) as exc:
                raise CannotRun(f"skill-grade: cannot read {skill_path}: {exc}") from exc
            source_digest = _sha256(payload)
            try:
                text = payload.decode("utf-8")
            except UnicodeDecodeError:
                findings.append(
                    _finding(
                        "file_metadata",
                        "invalid-utf8",
                        "skill document is not valid UTF-8",
                        skill_path,
                        refusal="invalid-utf8",
                    )
                )
                metadata_hard = True

    frontmatter_ok = False
    frontmatter: Mapping[str, Any] = {}
    body = text or ""
    if text is not None:
        fm_text, body = _split_frontmatter(text)
        if not fm_text.strip():
            findings.append(
                _finding(
                    "frontmatter", "missing-frontmatter", "skill document has no frontmatter block", skill_path, line=1
                )
            )
        else:
            try:
                parsed = yaml.safe_load(fm_text)
            except yaml.YAMLError as exc:
                findings.append(
                    _finding(
                        "frontmatter",
                        "malformed-frontmatter",
                        f"frontmatter is not valid YAML: {exc}",
                        skill_path,
                        line=1,
                    )
                )
            else:
                if not isinstance(parsed, Mapping):
                    findings.append(
                        _finding(
                            "frontmatter",
                            "frontmatter-not-mapping",
                            "frontmatter must be a mapping",
                            skill_path,
                            line=1,
                        )
                    )
                else:
                    frontmatter = parsed
                    missing = [
                        key
                        for key in ("name", "description")
                        if not isinstance(parsed.get(key), str) or not parsed[key].strip()
                    ]
                    if missing:
                        findings.append(
                            _finding(
                                "frontmatter",
                                "missing-required-key",
                                f"frontmatter is missing non-empty key(s): {', '.join(missing)}",
                                skill_path,
                                line=1,
                            )
                        )
                    else:
                        frontmatter_ok = True

    description_ok = False
    description = frontmatter.get("description")
    if not isinstance(description, str) or not description.strip():
        findings.append(
            _finding("description", "missing-description", "description must be a non-empty string", skill_path, line=1)
        )
    elif not _DESCRIPTION_USE_RE.search(description):
        findings.append(
            _finding(
                "description",
                "missing-use-condition",
                "description must name when the skill is used",
                skill_path,
                line=1,
            )
        )
    else:
        description_ok = True

    structure_ok = True
    headings = _heading_names(body)
    missing_sections = [section for section in ("usage", "examples") if section not in headings]
    if missing_sections:
        structure_ok = False
        findings.append(
            _finding(
                "structure",
                "missing-section",
                f"skill body is missing required section(s): {', '.join(missing_sections)}",
                skill_path,
            )
        )

    link_findings: list[SkillGradeFinding] = []
    link_hard = False
    if text is not None:
        link_findings, link_hard = _link_findings(root, document, text, skill_path)
        findings.extend(link_findings)

    frontmatter_hard = not frontmatter_ok
    if text is None:
        frontmatter_hard = True
    scores = {
        "frontmatter": policy.criterion_weights["frontmatter"] if frontmatter_ok else 0,
        "description": policy.criterion_weights["description"] if description_ok else 0,
        "structure": policy.criterion_weights["structure"] if structure_ok else 0,
        "links": policy.criterion_weights["links"] if not link_findings else 0,
        "file_metadata": policy.criterion_weights["file_metadata"] if not metadata_hard else 0,
    }
    total = sum(scores.values())
    hard_failure = frontmatter_hard or metadata_hard or link_hard
    status = "pass" if not hard_failure and total >= policy.minimum_grade else "fail"
    return SkillGradeReport(
        schema_version=policy.schema_version,
        skill_path=skill_path,
        source_digest=source_digest,
        policy_digest=policy.digest,
        scores=scores,
        criterion_weights=dict(policy.criterion_weights),
        findings=tuple(findings),
        total_grade=total,
        minimum_grade=policy.minimum_grade,
        status=status,
        hard_failure=hard_failure,
    )


def grade(
    root: Path,
    policy: SkillGradePolicy = DEFAULT_POLICY,
    *,
    declared_roots: tuple[Path, ...] | None = None,
) -> tuple[SkillGradeReport, ...]:
    """Grade every discovered skill in one declared repository scope."""
    root = root.resolve()
    documents = discover_skill_documents(root, declared_roots)
    return tuple(grade_document(root, document, policy) for document in documents)


def _text_report(root: Path, policy: SkillGradePolicy, reports: tuple[SkillGradeReport, ...]) -> str:
    lines = [f"# {policy.schema_version}", f"- root: `{root}`", f"- policy digest: `{policy.digest}`"]
    if not reports:
        lines.append("- status: NOT APPLICABLE (no declared skill documents)")
        return "\n".join(lines)
    for report in reports:
        lines.extend(
            [
                f"\n## `{report.skill_path}`",
                f"- status: {report.status.upper()}",
                f"- source digest: `{report.source_digest}`",
                f"- grade: {report.total_grade}/100 (minimum {report.minimum_grade})",
            ]
        )
        for criterion in CRITERIA:
            lines.append(f"- {criterion}: {report.scores[criterion]}/{report.criterion_weights[criterion]}")
        for finding in report.findings:
            location = f":{finding.line}" if finding.line is not None else ""
            target = f" -> `{finding.target}`" if finding.target else ""
            refusal = f" [{finding.refusal}]" if finding.refusal else ""
            lines.append(f"  - {finding.source_document}{location}: {finding.code}: {finding.message}{target}{refusal}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    """Run the standalone grader; registry dispatch maps ``CannotRun`` to 2."""
    parser = argparse.ArgumentParser(prog="pipelines-hook skill-grade", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--skills-root", type=Path, action="append", default=[])
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--json", action="store_true", help="emit a structured JSON receipt")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    policy = load_policy(args.policy) if args.policy else DEFAULT_POLICY
    reports = grade(root, policy, declared_roots=tuple(args.skills_root) or None)
    if args.json or args.format == "json":
        payload: dict[str, object] = {
            "schema_version": policy.schema_version,
            "policy": policy.as_dict(),
            "policy_digest": policy.digest,
            "root": str(root),
            "applicable": bool(reports),
            "reports": [report.as_dict() for report in reports],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_text_report(root, policy, reports))
    return 0 if all(report.status == "pass" for report in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
