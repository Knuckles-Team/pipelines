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

import json
import re
import shlex
import tomllib
from collections.abc import Callable, Iterable, MutableMapping
from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun

ClaimResolver = Callable[[Path, str], bool | None]

CLAIM_KINDS = frozenset({"path", "command", "gate", "count", "diagram-node"})


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
    root: Path, claims: Iterable[DocClaim], *, stats: MutableMapping[str, int] | None = None
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
            findings.append(f"{claim.file}:{claim.line} claims-unchecked {claim.kind} {claim.text}")
        else:
            findings.append(f"{claim.file}:{claim.line} {claim.kind} {claim.text}")
    if stats is not None:
        stats["checked"] = checked
        stats["unresolved"] = len(findings)
    return findings
