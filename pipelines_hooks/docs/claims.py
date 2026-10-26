"""Explicit documentation claims and their offline repository resolvers.

Claims are deliberately explicit.  Policy-scoped documentation files can
contain an HTML comment in one of these forms::

    <!-- claim:path docs/guide.md -->
    <!-- claim gate: public-surface -->

The comment is kept out of the rendered page while retaining a source file and
line for a useful finding.  The parser accepts the colon and whitespace forms
so existing Markdown authors do not need a special renderer or extension.
Resolvers only inspect the supplied tree; they never execute a claimed command
or contact a remote registry.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import tomllib
from collections.abc import Callable, Iterable, Mapping, MutableMapping
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
from typing import cast

from pipelines_hooks.core.errors import CannotRun

ClaimResolver = Callable[[Path, str], bool | None]

CLAIM_KINDS = frozenset({"path", "command", "gate", "count", "diagram-node"})
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_ABSOLUTE_PATH_RE = re.compile(r"(?<![A-Za-z0-9_:/])/(?:[^\s/]+/)+[^\s/]*")
_WINDOWS_PATH_RE = re.compile(r"\b[A-Za-z]:[\\/][^\s]+")
_SECRET_RE = re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*[^\s,;]+")


@dataclass(frozen=True)
class DocClaim:
    """A source-located assertion made by a repository document."""

    file: str
    line: int
    kind: str
    text: str

    def __post_init__(self) -> None:
        if self.kind not in CLAIM_KINDS:
            raise ValueError(f"unsupported documentation claim kind: {self.kind!r}")


@dataclass(frozen=True)
class LocatedFinding:
    """One measured, source-located result shared at report boundaries.

    The source path is repository-relative and the two digests bind the
    finding to the bytes that were scanned and to this deterministic record.
    ``observed`` and ``expected`` intentionally remain generic JSON values so
    documentation, code and future report producers can share this contract.
    """

    source_path: str
    line: int
    source_digest: str
    rule: str
    observed: object
    expected: object
    evidence_digest: str

    @property
    def path(self) -> str:
        """Alias for report consumers that call the source path ``path``."""

        return self.source_path

    @property
    def observed_value(self) -> object:
        """Alias preserving the prose name used by the contract."""

        return self.observed

    @property
    def expected_value(self) -> object:
        """Alias preserving the prose name used by the contract."""

        return self.expected

    def __post_init__(self) -> None:
        if not isinstance(self.source_path, str) or not self.source_path:
            raise ValueError("located-evidence source_path must be a non-empty string")
        if isinstance(self.line, bool) or not isinstance(self.line, int):
            raise ValueError("located-evidence line must be an integer")
        if not isinstance(self.source_digest, str) or not self.source_digest:
            raise ValueError("located-evidence source_digest must be a non-empty string")
        if not isinstance(self.rule, str) or not self.rule.strip():
            raise ValueError("located-evidence rule must be a non-empty string")
        if not isinstance(self.evidence_digest, str) or not self.evidence_digest:
            raise ValueError("located-evidence evidence_digest must be a non-empty string")

    def as_dict(self) -> dict[str, object]:
        """Return a deterministic, machine-safe report record."""

        return {
            "source_path": _safe_value(self.source_path),
            "line": self.line,
            "source_digest": self.source_digest,
            "rule": _safe_value(self.rule),
            "observed": _safe_value(self.observed),
            "expected": _safe_value(self.expected),
            "evidence_digest": self.evidence_digest,
        }


@dataclass(frozen=True)
class FindingRefusal:
    """A located finding rejected before it can become a verdict."""

    source_path: str
    line: int | None
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "source_path": _safe_value(self.source_path),
            "line": self.line,
            "reason": _safe_value(self.reason),
        }


def _safe_value(value: object) -> object:
    """Make report values deterministic and remove machine paths/secrets."""

    if isinstance(value, Mapping):
        return {str(key): _safe_value(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        if isinstance(value, str):
            redacted = _SECRET_RE.sub(lambda match: f"{match.group(1)}=<redacted>", value)
            redacted = _WINDOWS_PATH_RE.sub("<absolute-path>", redacted)
            return _ABSOLUTE_PATH_RE.sub("<absolute-path>", redacted)
        return value
    return _safe_value(str(value))


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(_safe_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise CannotRun(f"located-evidence value is not JSON-serializable: {exc}") from exc


def _sha256(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def source_digest(root: Path, source_path: str) -> str:
    """Digest one repository-relative regular file from the scanned tree."""

    relative = _relative_source_path(source_path)
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise CannotRun(f"located-evidence source path escapes repository: {source_path!r}")
    try:
        payload = path.read_bytes()
    except (OSError, UnicodeError) as exc:
        raise CannotRun(f"located-evidence source cannot be read: {relative}") from exc
    return _sha256(payload)


def evidence_digest_for(
    source_path: str,
    line: int,
    source_digest_value: str,
    rule: str,
    observed: object,
    expected: object,
) -> str:
    """Compute the evidence digest excluding its own field."""

    payload = {
        "source_path": source_path,
        "line": line,
        "source_digest": source_digest_value,
        "rule": rule,
        "observed": observed,
        "expected": expected,
    }
    return _sha256(_canonical_json(payload).encode("utf-8"))


def make_located_finding(
    root: Path,
    source_path: str,
    line: int,
    rule: str,
    observed: object,
    expected: object,
) -> LocatedFinding:
    """Build a digest-bound finding from the current scanned tree."""

    digest = source_digest(root, source_path)
    return LocatedFinding(
        source_path=source_path,
        line=line,
        source_digest=digest,
        rule=rule,
        observed=observed,
        expected=expected,
        evidence_digest=evidence_digest_for(source_path, line, digest, rule, observed, expected),
    )


def _relative_source_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("source path must be a non-empty NUL-free string")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or re.match(r"^[A-Za-z]:/", normalized) or ".." in path.parts:
        raise ValueError(f"source path is not repository-relative: {value!r}")
    canonical = path.as_posix()
    if canonical in {"", "."} or canonical != normalized:
        raise ValueError(f"source path is not canonical: {value!r}")
    return canonical


_MISSING = object()


def validate_located_evidence(
    root: Path,
    finding: LocatedFinding,
    *,
    measured: object = _MISSING,
) -> FindingRefusal | None:
    """Validate one finding against the exact current source bytes.

    ``None`` means the record is exportable.  A :class:`FindingRefusal` means
    the record is unsupported and must not be turned into a clean or failed
    product verdict.  Malformed record types/digests raise ``CannotRun``.
    """

    if not isinstance(finding, LocatedFinding):
        raise CannotRun("located-evidence finding has an unsupported schema")
    try:
        relative = _relative_source_path(finding.source_path)
    except ValueError:
        return FindingRefusal(finding.source_path, finding.line, "unsafe-path")
    if finding.line <= 0:
        return FindingRefusal(relative, finding.line, "invalid-line")
    if not _DIGEST_RE.fullmatch(finding.source_digest) or not _DIGEST_RE.fullmatch(finding.evidence_digest):
        raise CannotRun(f"located-evidence malformed digest for {relative}:{finding.line}")
    if finding.observed is None or finding.expected is None or measured is None:
        return FindingRefusal(relative, finding.line, "missing-measurement")
    path = (root / relative).resolve()
    if (
        not path.is_relative_to(root.resolve())
        or path.is_symlink()
        and not path.resolve().is_relative_to(root.resolve())
    ):
        return FindingRefusal(relative, finding.line, "unsafe-path")
    try:
        payload = path.read_bytes()
    except (OSError, UnicodeError):
        return FindingRefusal(relative, finding.line, "missing-measurement")
    if _sha256(payload) != finding.source_digest:
        return FindingRefusal(relative, finding.line, "source-digest-mismatch")
    line_count = len(payload.splitlines())
    if payload.endswith((b"\n", b"\r")):
        line_count += 1
    if not 1 <= finding.line <= line_count:
        return FindingRefusal(relative, finding.line, "invalid-line")
    if measured is not _MISSING and measured != finding.observed:
        return FindingRefusal(relative, finding.line, "observed-value-mismatch")
    expected_digest = evidence_digest_for(
        finding.source_path,
        finding.line,
        finding.source_digest,
        finding.rule,
        finding.observed,
        finding.expected,
    )
    if expected_digest != finding.evidence_digest:
        return FindingRefusal(relative, finding.line, "evidence-digest-mismatch")
    return None


def validate_finding(root: Path, finding: LocatedFinding, *, measured: object = _MISSING) -> FindingRefusal | None:
    """Shared report-boundary alias for future skill/test-quality producers."""

    return validate_located_evidence(root, finding, measured=measured)


def located_evidence_records(
    findings: Iterable[LocatedFinding], refusals: Iterable[FindingRefusal] = ()
) -> dict[str, object]:
    """Return sorted deterministic records for a report boundary."""

    ordered_findings = sorted(
        (finding.as_dict() for finding in findings),
        key=lambda item: (str(item["source_path"]), int(str(item["line"])), str(item["rule"])),
    )
    ordered_refusals = sorted(
        (refusal.as_dict() for refusal in refusals),
        key=lambda item: (str(item["source_path"]), int(str(item["line"] or 0)), str(item["reason"])),
    )
    return {"findings": ordered_findings, "refusals": ordered_refusals}


def export_located_evidence(findings: Iterable[LocatedFinding], refusals: Iterable[FindingRefusal] = ()) -> str:
    """Serialize deterministic evidence without absolute paths or secrets."""

    materialized = list(findings)
    for finding in materialized:
        try:
            relative = _relative_source_path(finding.source_path)
        except ValueError as exc:
            raise CannotRun(f"located-evidence malformed source path: {finding.source_path!r}") from exc
        if finding.line <= 0:
            raise CannotRun(f"located-evidence malformed line for {relative}:{finding.line}")
        if not _DIGEST_RE.fullmatch(finding.source_digest) or not _DIGEST_RE.fullmatch(finding.evidence_digest):
            raise CannotRun(f"located-evidence malformed digest for {relative}:{finding.line}")
    return _canonical_json(located_evidence_records(materialized, refusals))


def load_located_evidence(payload: object) -> tuple[list[LocatedFinding], list[FindingRefusal]]:
    """Decode the persisted report-boundary schema used by the CLI.

    The input is intentionally the same compact object emitted by
    :func:`export_located_evidence`; unknown fields and malformed records fail
    closed before any finding can affect a verdict.
    """

    if not isinstance(payload, Mapping):
        raise CannotRun("located-evidence input must be an object")
    allowed = {"findings", "refusals"}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise CannotRun(f"located-evidence input has unknown field(s): {', '.join(str(item) for item in unknown)}")
    raw_findings = payload.get("findings", [])
    raw_refusals = payload.get("refusals", [])
    if not isinstance(raw_findings, list) or not isinstance(raw_refusals, list):
        raise CannotRun("located-evidence input findings and refusals must be arrays")

    finding_fields = {
        "source_path",
        "line",
        "source_digest",
        "rule",
        "observed",
        "expected",
        "evidence_digest",
    }
    findings: list[LocatedFinding] = []
    for index, raw in enumerate(raw_findings):
        if not isinstance(raw, Mapping):
            raise CannotRun(f"located-evidence finding {index} is not an object")
        missing = sorted(finding_fields - set(raw))
        unknown = sorted(set(raw) - finding_fields)
        if missing or unknown:
            details = []
            if missing:
                details.append(f"missing {', '.join(str(item) for item in missing)}")
            if unknown:
                details.append(f"unknown {', '.join(str(item) for item in unknown)}")
            raise CannotRun(f"located-evidence finding {index} schema: {'; '.join(details)}")
        try:
            findings.append(
                LocatedFinding(
                    source_path=cast(str, raw["source_path"]),
                    line=cast(int, raw["line"]),
                    source_digest=cast(str, raw["source_digest"]),
                    rule=cast(str, raw["rule"]),
                    observed=raw["observed"],
                    expected=raw["expected"],
                    evidence_digest=cast(str, raw["evidence_digest"]),
                )
            )
        except (TypeError, ValueError) as exc:
            raise CannotRun(f"located-evidence finding {index} is malformed: {exc}") from exc

    refusal_fields = {"source_path", "line", "reason"}
    refusals: list[FindingRefusal] = []
    for index, raw in enumerate(raw_refusals):
        if not isinstance(raw, Mapping):
            raise CannotRun(f"located-evidence refusal {index} is not an object")
        missing = sorted(refusal_fields - set(raw))
        unknown = sorted(set(raw) - refusal_fields)
        if missing or unknown:
            details = []
            if missing:
                details.append(f"missing {', '.join(str(item) for item in missing)}")
            if unknown:
                details.append(f"unknown {', '.join(str(item) for item in unknown)}")
            raise CannotRun(f"located-evidence refusal {index} schema: {'; '.join(details)}")
        line = raw["line"]
        if line is not None and (isinstance(line, bool) or not isinstance(line, int)):
            raise CannotRun(f"located-evidence refusal {index} has an invalid line")
        source_path = raw["source_path"]
        reason = raw["reason"]
        if not isinstance(source_path, str) or not isinstance(reason, str) or not reason.strip():
            raise CannotRun(f"located-evidence refusal {index} has invalid fields")
        refusals.append(FindingRefusal(source_path, line, reason))
    return findings, refusals


# Keep the grammar intentionally small: claims are comments, not arbitrary
# prose or code literals.  ``pipelines-claim`` is accepted for documents that
# want to make the ownership of the directive explicit.
_CLAIM_START_RE = re.compile(r"<!--\s*(?:pipelines[-_]?)?claim\b", re.IGNORECASE)
_CLAIM_KIND_RE = re.compile(r"(?P<kind>[A-Za-z][A-Za-z0-9_-]*)(?:\s*:\s*|\s+)(?P<text>.*)", re.DOTALL)


def _claim_error(file: str, line: int, reason: str) -> CannotRun:
    return CannotRun(f"{file}:{line} claims-unchecked {reason}")


def parse_claims(text: str, *, file: str) -> list[DocClaim]:
    """Extract explicit HTML-comment claims from one Markdown document.

    Claim-looking comments are declarations, so an empty, unknown or
    unterminated declaration is a refusal rather than text that can silently
    disappear from the checked set.
    """

    claims: list[DocClaim] = []
    for match in _CLAIM_START_RE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        end = text.find("-->", match.end())
        if end < 0:
            raise _claim_error(file, line, "unterminated claim comment")
        body = text[match.end() : end].strip()
        if body.startswith(":"):
            body = body[1:].lstrip()
        if not body:
            raise _claim_error(file, line, "empty claim")
        parsed = _CLAIM_KIND_RE.fullmatch(body)
        if parsed is None:
            raise _claim_error(file, line, f"malformed claim {body!r}")
        kind = parsed.group("kind").lower()
        value = parsed.group("text").strip()
        if kind not in CLAIM_KINDS:
            raise _claim_error(file, line, f"unknown claim kind {kind!r}")
        if not value:
            raise _claim_error(file, line, f"empty {kind} claim")
        claims.append(
            DocClaim(
                file=file,
                line=line,
                kind=kind,
                text=value,
            )
        )
    return claims


# ``extract_claims`` is a descriptive alias for callers that do not care that
# the source format is Markdown.  Keep one implementation so line accounting
# cannot diverge between the hook and focused tests.
extract_claims = parse_claims


_MKDOCS_DOCS_DIR_RE = re.compile(r"^docs_dir\s*:\s*(?P<value>[^#\n]+?)\s*(?:#.*)?$", re.MULTILINE)
_DOCUMENT_SKIP_DIRS = frozenset({".git", ".venv", "venv", "node_modules", "build", "dist", "site"})


def _declared_docs_dir(root: Path) -> Path | None:
    """Read the simple top-level MkDocs content-root declaration, if present."""

    manifest = root / "mkdocs.yml"
    if not manifest.is_file():
        return None
    try:
        text = manifest.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CannotRun(f"mkdocs.yml cannot be read: {exc}") from exc
    match = _MKDOCS_DOCS_DIR_RE.search(text)
    if match is None:
        return None
    value = match.group("value").strip().strip("\"'")
    target = _safe_target(root, value)
    if target is None or not target.is_dir():
        raise CannotRun(f"mkdocs.yml docs_dir is not a repository directory: {value!r}")
    return target


def _document_paths(root: Path) -> list[Path]:
    """Return Markdown files in the declared content root and public guides."""

    candidates: list[Path] = [root / "README.md", root / "AGENTS.md"]
    declared = _declared_docs_dir(root)
    if declared is not None:
        candidates.append(declared)
    else:
        # Consumer repositories without MkDocs still commonly declare their
        # canonical content under ``docs``.  Do not walk arbitrary source or
        # generated trees when no documentation policy names a root.
        candidates.extend(path for path in (root / "docs", root / "pages") if path.is_dir())

    documents: set[Path] = set()
    for candidate in candidates:
        if candidate.is_file() and candidate.suffix.lower() == ".md" and not candidate.is_symlink():
            safe = _safe_target(root, str(candidate.relative_to(root)))
            if safe is not None:
                documents.add(safe)
        elif candidate.is_dir() and not candidate.is_symlink():
            try:
                for path in candidate.rglob("*.md"):
                    if path.is_symlink() or _DOCUMENT_SKIP_DIRS.intersection(path.relative_to(root).parts):
                        continue
                    safe = _safe_target(root, str(path.relative_to(root)))
                    if safe is not None:
                        documents.add(safe)
            except OSError as exc:
                raise CannotRun(f"documentation inventory cannot be read under {candidate}: {exc}") from exc
    return sorted(documents)


def document_sources(root: Path) -> list[tuple[Path, str]]:
    """Read the Markdown files selected by the repository documentation policy."""

    sources: list[tuple[Path, str]] = []
    for path in _document_paths(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            relative = path.relative_to(root).as_posix()
            raise CannotRun(f"{relative} cannot be read: {exc}") from exc
        sources.append((path, text))
    return sources


def collect_claims(
    root: Path, claims: Iterable[DocClaim], *, sources: Iterable[tuple[Path, str]] | None = None
) -> list[DocClaim]:
    """Combine caller claims with declarations in the policy-scoped documents."""

    result = list(claims)
    seen = {(claim.file, claim.line, claim.kind, claim.text) for claim in result}
    for path, text in sources if sources is not None else document_sources(root):
        relative = path.relative_to(root).as_posix()
        for claim in parse_claims(text, file=relative):
            key = (claim.file, claim.line, claim.kind, claim.text)
            if key not in seen:
                seen.add(key)
                result.append(claim)
    return result


def _safe_target(root: Path, value: str) -> Path | None:
    """Return a repository-contained target, or ``None`` for unsafe input."""

    candidate = value.strip()
    if not candidate:
        return None
    try:
        target = (root / candidate).resolve()
        if not target.is_relative_to(root.resolve()):
            return None
    except (OSError, RuntimeError, ValueError):
        return None
    return target


def resolve_path(root: Path, text: str) -> bool | None:
    """Resolve a repository-relative path claim."""

    target = _safe_target(root, text)
    if target is None:
        return None
    return target.exists()


def _script_names(root: Path) -> set[str] | None:
    """Read declared project entry points without importing project code."""

    manifest = root / "pyproject.toml"
    if not manifest.is_file():
        return set()
    try:
        document = tomllib.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return None
    project = document.get("project", {})
    if not isinstance(project, dict):
        return None
    scripts = project.get("scripts", {})
    if not isinstance(scripts, dict):
        return None
    return {name for name in scripts if isinstance(name, str)}


def _make_targets(root: Path) -> set[str] | None:
    """Read simple Make targets as command declarations."""

    makefile = root / "Makefile"
    if not makefile.is_file():
        return set()
    try:
        text = makefile.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    targets: set[str] = set()
    for line in text.splitlines():
        if line.startswith((" ", "\t")) or ":" not in line:
            continue
        name = line.split(":", 1)[0].strip()
        if name and not name.startswith("#"):
            targets.update(part.strip() for part in name.split())
    return targets


_PYTHON_MODULE_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")


def _module_exists(root: Path, module: str) -> bool | None:
    """Check a ``python -m`` module path without importing it."""

    if not _PYTHON_MODULE_RE.fullmatch(module):
        return None
    relative = Path(*module.split("."))
    module_file = _safe_target(root, str(relative.with_suffix(".py")))
    package_file = _safe_target(root, str(relative / "__main__.py"))
    if module_file is None or package_file is None:
        return None
    return module_file.is_file() or package_file.is_file()


def resolve_command(root: Path, text: str) -> bool | None:
    """Resolve a command against declared entry points and tracked scripts.

    The check is intentionally structural.  A command is valid when its first
    token is a declared Python entry point, a Make target, a repository script
    or a module named by ``python -m``.  No executable is run.
    """

    try:
        tokens = shlex.split(text)
    except ValueError:
        return None
    if not tokens:
        return None
    command = tokens[0]

    scripts = _script_names(root)
    if scripts is None:
        return None
    target = _safe_target(root, command)
    if target is None:
        return None
    make_targets = _make_targets(root)
    if make_targets is None:
        return None
    if command in scripts or command in make_targets:
        return True
    if target.is_file():
        return True

    if command in {"python", "python3", "python3.12", "python3.13", "python3.14"}:
        if len(tokens) < 3 or tokens[1] != "-m":
            return False
        return _module_exists(root, tokens[2])
    if command.endswith("python") and len(tokens) >= 3 and tokens[1] == "-m":
        return _module_exists(root, tokens[2])
    return False


def resolve_gate(root: Path, text: str) -> bool | None:
    """Resolve a gate name against the published CLI registry."""  # noqa: ARG001

    try:
        from pipelines_hooks.cli import GATES
    except (ImportError, AttributeError):
        return None
    try:
        name = shlex.split(text)[0]
    except (IndexError, ValueError):
        return None
    return name in GATES


def _tree_file_count(root: Path) -> int | None:
    try:
        return sum(
            1 for path in root.rglob("*") if not path.is_symlink() and ".git" not in path.parts and path.is_file()
        )
    except OSError:
        return None


def _count_measurement(root: Path, selector: str) -> int | None:
    selector = selector.strip()
    if selector in {"files", "file", "tree"}:
        return _tree_file_count(root)
    if selector in {"gates", "gate"}:
        try:
            from pipelines_hooks.cli import GATES
        except (ImportError, AttributeError):
            return None
        return len(GATES)
    if selector.startswith("path:"):
        target = _safe_target(root, selector.removeprefix("path:"))
        if target is None or not target.exists():
            return None
        if target.is_file():
            return 1
        try:
            return sum(
                1 for path in target.rglob("*") if not path.is_symlink() and ".git" not in path.parts and path.is_file()
            )
        except OSError:
            return None
    return None


def resolve_count(root: Path, text: str) -> bool | None:
    """Resolve ``count`` claims using ``files=3`` or ``gates: 42`` syntax."""

    value = text.strip()
    match = re.fullmatch(r"(?P<selector>[A-Za-z][A-Za-z0-9_.-]*(?::[^=:\s]+)?)\s*[:=]\s*(?P<expected>\d+)", value)
    if match is None:
        return None
    else:
        selector, expected_text = match.group("selector"), match.group("expected")
    measured = _count_measurement(root, selector)
    return None if measured is None else measured == int(expected_text)


def _registry_paths(root: Path) -> tuple[Path, ...]:
    return (
        root / "registry.json",
        root / ".config" / "registry.json",
        root / "scripts" / "registry.json",
        root / "scripts" / "skill_graph" / "registry.json",
        root / "scripts" / "architecture_explorer" / "registry.json",
    )


def _registry_names(value: object) -> set[str]:
    """Collect names from the small JSON registry shapes used by the fleet."""

    names: set[str] = set()
    if isinstance(value, str):
        names.add(value)
    elif isinstance(value, list):
        for item in value:
            names.update(_registry_names(item))
    elif isinstance(value, dict):
        for key in ("name", "id", "slug", "node"):
            item = value.get(key)
            if isinstance(item, str):
                names.add(item)
        for key in ("nodes", "registry", "entries", "components", "repositories", "pages_node", "projects"):
            item = value.get(key)
            if isinstance(item, (dict, list)):
                if key == "pages_node" and isinstance(item, dict):
                    names.update(name for name in item if isinstance(name, str))
                else:
                    names.update(_registry_names(item))
    return names


def resolve_diagram_node(root: Path, text: str) -> bool | None:
    """Resolve a diagram node against a repository-local JSON registry."""

    target = text.strip()
    for registry in _registry_paths(root):
        if not registry.is_file() and not registry.is_symlink():
            continue
        relative = registry.relative_to(root).as_posix()
        safe_registry = _safe_target(root, relative)
        if safe_registry is None or not safe_registry.is_file():
            return None
        try:
            document = json.loads(safe_registry.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        return target in _registry_names(document)
    return None


RESOLVERS: dict[str, ClaimResolver] = {
    "path": resolve_path,
    "command": resolve_command,
    "gate": resolve_gate,
    "count": resolve_count,
    "diagram-node": resolve_diagram_node,
}


def claim_findings(
    root: Path,
    claims: Iterable[DocClaim],
    *,
    stats: MutableMapping[str, int] | None = None,
    located_findings: list[LocatedFinding] | None = None,
    refusals: list[FindingRefusal] | None = None,
) -> list[str]:
    """Return one location-bearing finding for every failed or unchecked claim.

    A resolver returns ``None`` when it cannot establish a trustworthy answer;
    this is reported as ``claims-unchecked`` rather than being treated as a
    passing claim.  ``stats`` is optional so the public-surface gate can emit a
    deterministic summary without changing the simple list return contract.
    """

    findings: list[str] = []
    checked = 0
    for claim in claims:
        checked += 1
        resolver = RESOLVERS.get(claim.kind)
        result: bool | None
        if resolver is None:
            result = None
        else:
            try:
                result = resolver(root, claim.text)
            except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError, IndexError, RuntimeError):
                result = None
        if result is True:
            continue
        if result is None:
            if located_findings is not None:
                refusal = FindingRefusal(claim.file, claim.line, "missing-measurement")
                if refusals is not None:
                    refusals.append(refusal)
                findings.append(f"unsupported-finding {claim.file}:{claim.line} {claim.kind} {claim.text}")
                continue
            findings.append(f"{claim.file}:{claim.line} claims-unchecked {claim.kind} {claim.text}")
        else:
            if located_findings is not None:
                try:
                    located = make_located_finding(
                        root,
                        claim.file,
                        claim.line,
                        f"claim:{claim.kind}",
                        result,
                        True,
                    )
                    located_refusal = validate_located_evidence(root, located, measured=result)
                except (OSError, UnicodeError, ValueError, CannotRun) as exc:
                    raise CannotRun(f"located-evidence cannot measure {claim.file}:{claim.line}: {exc}") from exc
                if located_refusal is not None:
                    if refusals is not None:
                        refusals.append(located_refusal)
                    findings.append(f"unsupported-finding {claim.file}:{claim.line} {located_refusal.reason}")
                    continue
                located_findings.append(located)
            findings.append(f"{claim.file}:{claim.line} {claim.kind} {claim.text}")
    if stats is not None:
        stats["checked"] = checked
        stats["unresolved"] = len(findings)
    return findings
