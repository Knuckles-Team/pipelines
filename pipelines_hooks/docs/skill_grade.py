"""Deterministic, offline quality grading for declared ``SKILL.md`` files.

The grader deliberately measures a small, versioned contract.  It does not
install a skill, infer quality from prose with a model, or contact an external
service.  A report is bound to the repository-relative source document, the
effective policy digest, and one immutable Git index/commit snapshot so a host
can consume the receipt without treating it as admission or deployment approval.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from urllib.parse import unquote, urlsplit

import yaml

from pipelines_hooks.connector.skill_checks.frontmatter import _split_frontmatter
from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import blob_bytes, git_text, repo_root, run_git
from pipelines_hooks.core.settings import setting
from pipelines_hooks.docs.public_surface_constants import HEADING_RE, WINDOWS_ABSOLUTE_RE
from pipelines_hooks.docs.public_surface_links import _destinations


SCHEMA_VERSION = "skill-grade-v1"
CRITERIA = ("frontmatter", "description", "structure", "links", "file_metadata")
DEFAULT_CRITERION_WEIGHTS = {criterion: 20 for criterion in CRITERIA}
DEFAULT_MINIMUM_GRADE = 80
_DESCRIPTION_USE_RE = re.compile(r"\b(?:use(?:\s+this)?\s+when|when\s+(?:you|the\s+agent|an\s+agent))\b", re.I)
_FENCED_RE = re.compile(r"(?ms)^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?^ {0,3}\1[ \t]*$")
_SKILL_DIR_PARTS = {".git", ".venv", "venv", "__pycache__", "build", "dist"}
_GIT_MODES = {"100644": "regular", "100755": "regular", "120000": "symlink"}
SnapshotMode = Literal["index", "commit", "filesystem"]


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _safe_relative(raw: str) -> str:
    """Validate and normalize a repository-relative Git pathname."""
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or "" in path.parts:
        raise CannotRun(f"skill-grade: Git inventory contains unsafe path {raw!r}")
    return path.as_posix()


def _parse_index_entries(raw: str) -> tuple[dict[str, str], dict[str, str]]:
    modes: dict[str, str] = {}
    object_ids: dict[str, str] = {}
    for item in raw.split("\x00"):
        if not item:
            continue
        header, separator, pathname = item.partition("\t")
        fields = header.split()
        if separator != "\t" or len(fields) != 3:
            raise CannotRun("skill-grade: malformed Git index inventory")
        mode, object_id, stage = fields
        if stage != "0":
            raise CannotRun("skill-grade: Git index contains an unmerged skill inventory")
        relative = _safe_relative(pathname)
        modes[relative] = _GIT_MODES.get(mode, "special")
        object_ids[relative] = object_id
    return modes, object_ids


def _parse_tree_entries(raw: str) -> tuple[dict[str, str], dict[str, str]]:
    modes: dict[str, str] = {}
    object_ids: dict[str, str] = {}
    for item in raw.split("\x00"):
        if not item:
            continue
        header, separator, pathname = item.partition("\t")
        fields = header.split()
        if separator != "\t" or len(fields) != 3:
            raise CannotRun("skill-grade: malformed Git tree inventory")
        mode, _kind, object_id = fields
        relative = _safe_relative(pathname)
        modes[relative] = _GIT_MODES.get(mode, "special")
        object_ids[relative] = object_id
    return modes, object_ids


@dataclass(frozen=True)
class SkillGradeSnapshot:
    """Immutable input identity and byte reader for one grading run.

    Local hooks read the alternate index (the staged snapshot); CI/read-only
    runs read ``HEAD``.  The working tree is never consulted for a Git-backed
    run, so an unstaged edit cannot change a receipt after its inventory was
    selected.
    """

    root: Path
    mode: SnapshotMode
    commit: str | None
    tree: str | None
    paths: tuple[str, ...]
    modes: Mapping[str, str]
    object_ids: Mapping[str, str]
    identity: str

    @property
    def is_git(self) -> bool:
        return self.mode in {"index", "commit"}

    def as_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity,
            "mode": self.mode,
            "commit": self.commit,
            "tree": self.tree,
            "inventory_digest": _sha256(
                _canonical_json(
                    {"paths": self.paths, "modes": dict(self.modes), "objects": dict(self.object_ids)}
                ).encode("utf-8")
            ),
        }

    def kind(self, relative: str) -> str | None:
        if relative in self.modes:
            return self.modes[relative]
        if self.mode == "filesystem":
            path = self.root / relative
            if path.is_symlink():
                return "symlink"
            if path.is_file():
                return "regular"
        return None

    def read_bytes(self, relative: str) -> bytes | None:
        if self.mode == "filesystem":
            try:
                return (self.root / relative).read_bytes()
            except (OSError, UnicodeError):
                return None
        spec = f":{relative}" if self.mode == "index" else f"{self.commit}:{relative}"
        return blob_bytes(self.root, spec)

    def has_path(self, relative: str) -> bool:
        if relative in self.modes:
            return True
        prefix = relative.rstrip("/") + "/"
        return any(path.startswith(prefix) for path in self.paths)


def _identity(
    mode: SnapshotMode,
    commit: str | None,
    tree: str | None,
    paths: tuple[str, ...],
    modes: Mapping[str, str],
    object_ids: Mapping[str, str],
) -> str:
    payload = {
        "mode": mode,
        "commit": commit,
        "tree": tree,
        "paths": paths,
        "modes": dict(modes),
        "objects": dict(object_ids),
    }
    return _sha256(_canonical_json(payload).encode("utf-8"))


def _head(root: Path) -> str | None:
    result = run_git(root, ("rev-parse", "--verify", "-q", "HEAD"))
    value = (result.stdout or "").strip()
    return value if result.returncode == 0 and value else None


def _git_snapshot(root: Path) -> SkillGradeSnapshot | None:
    if not (root / ".git").exists():
        return None
    try:
        repository = repo_root(root).resolve()
    except CannotRun:
        raise
    if repository != root.resolve():
        raise CannotRun("skill-grade: --root must be the Git repository root for an immutable snapshot")
    use_commit = bool(setting("GITHUB_EVENT_NAME") or setting("PRE_COMMIT_FROM_REF"))
    if use_commit:
        commit = _head(root)
        if commit is None:
            raise CannotRun("skill-grade: commit snapshot requires HEAD")
        tree = git_text(root, ("rev-parse", f"{commit}^{{tree}}")).strip()
        raw = git_text(root, ("ls-tree", "-r", "-z", "--full-tree", commit))
        modes, object_ids = _parse_tree_entries(raw)
        mode: SnapshotMode = "commit"
    else:
        tree = git_text(root, ("write-tree",), preserve_index=True).strip()
        raw = git_text(root, ("ls-files", "-s", "-z"), preserve_index=True)
        modes, object_ids = _parse_index_entries(raw)
        commit = _head(root)
        mode = "index"
    paths = tuple(sorted(modes))
    return SkillGradeSnapshot(
        root,
        mode,
        commit,
        tree,
        paths,
        dict(modes),
        dict(object_ids),
        _identity(mode, commit, tree, paths, modes, object_ids),
    )


def _filesystem_snapshot(root: Path) -> SkillGradeSnapshot:
    paths = tuple(
        sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("SKILL.md")
            if not any(part in _SKILL_DIR_PARTS for part in path.parts) and (path.is_file() or path.is_symlink())
        )
    )
    modes = {relative: "symlink" if (root / relative).is_symlink() else "regular" for relative in paths}
    object_ids: dict[str, str] = {}
    for relative in paths:
        try:
            object_ids[relative] = _sha256((root / relative).read_bytes())
        except OSError:
            object_ids[relative] = "unreadable"
    return SkillGradeSnapshot(
        root,
        "filesystem",
        None,
        None,
        paths,
        modes,
        object_ids,
        _identity("filesystem", None, None, paths, modes, object_ids),
    )


def _snapshot(root: Path) -> SkillGradeSnapshot:
    return _git_snapshot(root) or _filesystem_snapshot(root)


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
    disposition: str | None = None
    blocking: bool = True

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
        if self.disposition is not None:
            result["disposition"] = self.disposition
        result["blocking"] = self.blocking
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
    snapshot: Mapping[str, object] = field(default_factory=dict)
    policy_source_digest: str = ""

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
            "policy_source_digest": self.policy_source_digest,
            "snapshot": dict(self.snapshot),
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


def _policy_from_bytes(raw: bytes, label: str) -> SkillGradePolicy:
    try:
        value = yaml.safe_load(raw.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise CannotRun(f"skill-grade: malformed policy {label}: {exc}") from exc
    return policy_from_mapping(value)


def load_policy(path: Path, *, snapshot: SkillGradeSnapshot | None = None) -> SkillGradePolicy:
    """Load a UTF-8 JSON/YAML policy with a strict schema from one snapshot."""
    if snapshot is not None:
        candidate = path if path.is_absolute() else snapshot.root / path
        lexical = candidate.absolute()
        if not lexical.is_relative_to(snapshot.root):
            raise CannotRun(f"skill-grade: policy escapes repository: {path}")
        relative = lexical.relative_to(snapshot.root).as_posix()
        if snapshot.kind(relative) != "regular":
            raise CannotRun(f"skill-grade: policy is absent or not regular in snapshot: {relative}")
        raw = snapshot.read_bytes(relative)
        if raw is None:
            raise CannotRun(f"skill-grade: cannot read policy from snapshot: {relative}")
        return _policy_from_bytes(raw, relative)
    try:
        raw = path.read_bytes()
    except (OSError, UnicodeError) as exc:
        raise CannotRun(f"skill-grade: cannot read policy {path}: {exc}") from exc
    return _policy_from_bytes(raw, str(path))


def _finding(
    criterion: str,
    code: str,
    message: str,
    skill_path: str,
    *,
    line: int | None = None,
    target: str | None = None,
    refusal: str | None = None,
    disposition: str | None = None,
    blocking: bool = True,
) -> SkillGradeFinding:
    return SkillGradeFinding(criterion, code, message, skill_path, line, target, refusal, disposition, blocking)


def _line_for(text: str, needle: str) -> int | None:
    index = text.find(needle)
    return None if index < 0 else text.count("\n", 0, index) + 1


def _heading_names(text: str) -> set[str]:
    prose = _FENCED_RE.sub("", text)
    return {match.group(2).strip().casefold() for match in HEADING_RE.finditer(prose)}


def _declared_root_relative(root: Path, raw: Path) -> str:
    candidate = raw if raw.is_absolute() else root / raw
    lexical = candidate.absolute()
    if not lexical.is_relative_to(root):
        raise CannotRun(f"skill-grade: declared skills root escapes repository: {raw}")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise CannotRun(f"skill-grade: declared skills root escapes repository: {raw}")
    return resolved.relative_to(root).as_posix() or "."


def _canonical_root_relatives(snapshot: SkillGradeSnapshot, declared: tuple[Path, ...] | None) -> tuple[str, ...]:
    if declared:
        ordered_roots: list[str] = []
        seen_declared: set[str] = set()
        for raw in declared:
            relative = _declared_root_relative(snapshot.root, raw)
            if snapshot.mode == "filesystem":
                candidate = snapshot.root / relative
                if not candidate.is_dir():
                    raise CannotRun(f"skill-grade: declared skills root is not a directory: {raw}")
            elif relative != "." and not snapshot.has_path(relative):
                raise CannotRun(f"skill-grade: declared skills root is absent from snapshot: {relative}")
            if relative not in seen_declared:
                ordered_roots.append(relative)
                seen_declared.add(relative)
        return tuple(ordered_roots)

    roots: list[str] = []
    seen: set[str] = set()
    if snapshot.has_path("SKILL.md"):
        roots.append(".")
        seen.add(".")
    for path in snapshot.paths:
        parts = PurePosixPath(path).parts
        for depth in (1, 2):
            if (
                len(parts) > depth
                and parts[depth - 1] == "skills"
                and not any(part in _SKILL_DIR_PARTS for part in parts[:depth])
            ):
                relative = PurePosixPath(*parts[:depth]).as_posix()
                if relative not in seen:
                    roots.append(relative)
                    seen.add(relative)
    return tuple(sorted(roots))


def discover_skill_inventory(
    root: Path,
    declared_roots: tuple[Path, ...] | None = None,
    *,
    snapshot: SkillGradeSnapshot | None = None,
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    """Return ordered canonical roots and deduplicated skill documents."""
    root = root.resolve()
    if not root.is_dir():
        raise CannotRun(f"skill-grade: repository root is not a directory: {root}")
    selected = snapshot or _snapshot(root)
    relatives = _canonical_root_relatives(selected, declared_roots)
    documents: list[Path] = []
    seen: set[str] = set()
    for relative_root in relatives:
        prefix = "" if relative_root == "." else relative_root + "/"
        for path in selected.paths:
            if not path.startswith(prefix) or PurePosixPath(path).name != "SKILL.md":
                continue
            if any(part in _SKILL_DIR_PARTS for part in PurePosixPath(path).parts):
                continue
            if path not in seen:
                documents.append(root / path)
                seen.add(path)
    return tuple(root / relative for relative in relatives), tuple(documents)


def _skill_roots(root: Path, declared: tuple[Path, ...] | None) -> list[Path]:
    """Compatibility wrapper returning the canonical ordered root paths."""
    roots, _documents = discover_skill_inventory(root, declared)
    return list(roots)


def discover_skill_documents(root: Path, declared_roots: tuple[Path, ...] | None = None) -> tuple[Path, ...]:
    """Discover all deterministic ``SKILL.md`` inputs under the declared scope."""
    _roots, documents = discover_skill_inventory(root, declared_roots)
    return documents


def _logical_snapshot_target(snapshot: SkillGradeSnapshot, base: str, path_part: str) -> tuple[str | None, str | None]:
    """Resolve one local target against the immutable Git inventory."""
    target = posixpath.normpath(posixpath.join(base, path_part))
    if target == ".":
        return None, None
    if target == ".." or target.startswith("../"):
        return None, "unsafe-path"
    visited: set[str] = set()
    for _ in range(16):
        if target in visited:
            return None, "unsafe-path"
        visited.add(target)
        if snapshot.kind(target) != "symlink":
            return target, None
        payload = snapshot.read_bytes(target)
        if payload is None:
            return target, "missing-target"
        try:
            link_target = payload.decode("utf-8").replace("\\", "/")
        except UnicodeDecodeError:
            return None, "unsafe-path"
        if link_target.startswith("/") or WINDOWS_ABSOLUTE_RE.match(link_target):
            return None, "unsafe-path"
        target = posixpath.normpath(posixpath.join(posixpath.dirname(target), link_target))
        if target == ".." or target.startswith("../"):
            return None, "unsafe-path"
    return None, "unsafe-path"


def _link_findings(
    root: Path,
    document: Path,
    text: str,
    skill_path: str,
    *,
    snapshot: SkillGradeSnapshot,
) -> tuple[list[SkillGradeFinding], bool]:
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
        # Web, mail and telephone links are intentionally offline.  Emit an
        # explicit non-blocking receipt so consumers cannot mistake omission
        # for a reachability check.
        if parsed.scheme.lower() in {"http", "https", "mailto", "tel"}:
            findings.append(
                _finding(
                    "links",
                    "external-unchecked",
                    f"external URL was not checked for reachability: {destination!r}",
                    skill_path,
                    line=_line_for(text, destination),
                    target=destination,
                    disposition="unchecked",
                    blocking=False,
                )
            )
            continue
        if parsed.netloc and not parsed.scheme:
            findings.append(
                _finding(
                    "links",
                    "external-unchecked",
                    f"external URL was not checked for reachability: {destination!r}",
                    skill_path,
                    line=_line_for(text, destination),
                    target=destination,
                    disposition="unchecked",
                    blocking=False,
                )
            )
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
        if snapshot.is_git:
            base_relative = PurePosixPath(skill_path).parent.as_posix()
            relative_target, refusal = _logical_snapshot_target(snapshot, base_relative, path_part)
            if refusal == "unsafe-path":
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
            if relative_target is None:
                continue
            exists = snapshot.has_path(relative_target)
        else:
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
            exists = target.exists()
        if not exists:
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
    return findings, any(finding.blocking for finding in findings)


def grade_document(
    root: Path,
    document: Path,
    policy: SkillGradePolicy = DEFAULT_POLICY,
    *,
    snapshot: SkillGradeSnapshot | None = None,
    policy_source_digest: str | None = None,
) -> SkillGradeReport:
    """Grade one skill document against one immutable source snapshot."""
    root = root.resolve()
    document = document if document.is_absolute() else root / document
    lexical = document.absolute()
    if not lexical.is_relative_to(root):
        raise CannotRun(f"skill-grade: skill document escapes repository: {document}")
    skill_path = lexical.relative_to(root).as_posix()
    selected = snapshot or _snapshot(root)
    findings: list[SkillGradeFinding] = []
    metadata_hard = False
    source_digest = "refused:unsafe-path"
    text: str | None = None
    payload: bytes | None = None

    if selected.is_git:
        kind = selected.kind(skill_path)
        if kind != "regular":
            code = "symlink-escape" if kind == "symlink" else "not-regular-file"
            message = (
                "skill document is a symlink in the immutable snapshot"
                if kind == "symlink"
                else "skill document is not a regular file in the immutable snapshot"
            )
            findings.append(_finding("file_metadata", code, message, skill_path, refusal="unsafe-path"))
            metadata_hard = True
        else:
            payload = selected.read_bytes(skill_path)
            if payload is None:
                raise CannotRun(f"skill-grade: skill document is unreadable in snapshot: {skill_path}")
    else:
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

    if payload is not None:
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
        link_findings, link_hard = _link_findings(root, document, text, skill_path, snapshot=selected)
        findings.extend(link_findings)

    frontmatter_hard = not frontmatter_ok
    if text is None:
        frontmatter_hard = True
    scores = {
        "frontmatter": policy.criterion_weights["frontmatter"] if frontmatter_ok else 0,
        "description": policy.criterion_weights["description"] if description_ok else 0,
        "structure": policy.criterion_weights["structure"] if structure_ok else 0,
        "links": policy.criterion_weights["links"] if not link_hard else 0,
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
        snapshot=selected.as_dict(),
        policy_source_digest=policy_source_digest or policy.digest,
    )


def grade(
    root: Path,
    policy: SkillGradePolicy = DEFAULT_POLICY,
    *,
    declared_roots: tuple[Path, ...] | None = None,
    snapshot: SkillGradeSnapshot | None = None,
    policy_source_digest: str | None = None,
) -> tuple[SkillGradeReport, ...]:
    """Grade every discovered skill in one immutable declared scope."""
    root = root.resolve()
    selected = snapshot or _snapshot(root)
    _roots, documents = discover_skill_inventory(root, declared_roots, snapshot=selected)
    return tuple(
        grade_document(
            root,
            document,
            policy,
            snapshot=selected,
            policy_source_digest=policy_source_digest,
        )
        for document in documents
    )


def _text_report(
    root: Path,
    policy: SkillGradePolicy,
    reports: tuple[SkillGradeReport, ...],
    *,
    snapshot: SkillGradeSnapshot,
    roots: tuple[Path, ...],
    policy_source_digest: str,
) -> str:
    lines = [
        f"# {policy.schema_version}",
        f"- root: `{root}`",
        f"- snapshot: `{snapshot.identity}` ({snapshot.mode})",
        f"- policy digest: `{policy.digest}`",
        f"- policy source digest: `{policy_source_digest}`",
        f"- skill roots: {len(roots)}",
        f"- skill documents: {len(reports)}",
    ]
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
    selected = _snapshot(root)
    policy_source_digest = DEFAULT_POLICY.digest
    if args.policy:
        policy = load_policy(args.policy, snapshot=selected)
        policy_path = args.policy if args.policy.is_absolute() else root / args.policy
        try:
            policy_payload = (
                policy_path.read_bytes()
                if selected.mode == "filesystem"
                else selected.read_bytes(policy_path.absolute().relative_to(root).as_posix())
            )
        except (OSError, ValueError) as exc:
            raise CannotRun(f"skill-grade: cannot read policy source: {exc}") from exc
        if policy_payload is None:
            raise CannotRun("skill-grade: policy source is absent from snapshot")
        policy_source_digest = _sha256(policy_payload)
    else:
        policy = DEFAULT_POLICY
    root_paths, documents = discover_skill_inventory(root, tuple(args.skills_root) or None, snapshot=selected)
    reports = tuple(
        grade_document(
            root,
            document,
            policy,
            snapshot=selected,
            policy_source_digest=policy_source_digest,
        )
        for document in documents
    )
    if args.json or args.format == "json":
        payload: dict[str, object] = {
            "schema_version": policy.schema_version,
            "policy": policy.as_dict(),
            "policy_digest": policy.digest,
            "policy_source_digest": policy_source_digest,
            "snapshot": selected.as_dict(),
            "inventory": {
                "roots": [path.relative_to(root).as_posix() or "." for path in root_paths],
                "documents": [report.skill_path for report in reports],
                "root_count": len(root_paths),
                "document_count": len(reports),
            },
            "root": str(root),
            "applicable": bool(reports),
            "reports": [report.as_dict() for report in reports],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            _text_report(
                root,
                policy,
                reports,
                snapshot=selected,
                roots=root_paths,
                policy_source_digest=policy_source_digest,
            )
        )
    return 0 if all(report.status == "pass" for report in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
