"""Explicit documentation claims and their offline repository resolvers.

Claims are deliberately opt-in.  A documentation file can contain an HTML
comment in one of these forms::

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
_CLAIM_RE = re.compile(
    r"<!--\s*(?:pipelines[-_]?)?claim\s*(?::\s*|\s+)"
    r"(?P<kind>path|command|gate|count|diagram-node)\s*(?::\s*|\s+)"
    r"(?P<text>.*?)\s*-->",
    re.IGNORECASE,
)


def parse_claims(text: str, *, file: str) -> list[DocClaim]:
    """Extract explicit HTML-comment claims from one Markdown document."""

    claims: list[DocClaim] = []
    for match in _CLAIM_RE.finditer(text):
        value = match.group("text").strip()
        if not value:
            # An empty assertion cannot be resolved and is better treated as
            # malformed documentation than as an implicit wildcard.
            continue
        claims.append(
            DocClaim(
                file=file,
                line=text.count("\n", 0, match.start()) + 1,
                kind=match.group("kind").lower(),
                text=value,
            )
        )
    return claims


# ``extract_claims`` is a descriptive alias for callers that do not care that
# the source format is Markdown.  Keep one implementation so line accounting
# cannot diverge between the hook and focused tests.
extract_claims = parse_claims


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


def resolve_path(root: Path, text: str) -> bool:
    """Resolve a repository-relative path claim."""

    target = _safe_target(root, text)
    return target is not None and target.exists()


def _script_names(root: Path) -> set[str] | None:
    """Read declared project entry points without importing project code."""

    manifest = root / "pyproject.toml"
    if not manifest.is_file():
        return set()
    try:
        document = tomllib.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return None
    scripts = document.get("project", {}).get("scripts", {})
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


def _module_exists(root: Path, module: str) -> bool:
    """Check a ``python -m`` module path without importing it."""

    if not module or any(part in {".", ".."} for part in module.split(".")):
        return False
    relative = Path(*module.split("."))
    return (root / relative).with_suffix(".py").is_file() or (root / relative / "__main__.py").is_file()


def resolve_command(root: Path, text: str) -> bool:
    """Resolve a command against declared entry points and tracked scripts.

    The check is intentionally structural.  A command is valid when its first
    token is a declared Python entry point, a Make target, a repository script
    or a module named by ``python -m``.  No executable is run.
    """

    try:
        tokens = shlex.split(text)
    except ValueError:
        return False
    if not tokens:
        return False
    command = tokens[0]

    if command in (_script_names(root) or set()):
        return True
    if command in (_make_targets(root) or set()):
        return True

    target = _safe_target(root, command)
    if target is not None and target.is_file():
        return True

    if command in {"python", "python3", "python3.12", "python3.13", "python3.14"}:
        return len(tokens) >= 3 and tokens[1] == "-m" and _module_exists(root, tokens[2])
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
        return False
    return name in GATES


def _tree_file_count(root: Path) -> int | None:
    try:
        return sum(1 for path in root.rglob("*") if ".git" not in path.parts and path.is_file())
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
            return 0 if target is not None else None
        if target.is_file():
            return 1
        try:
            return sum(1 for path in target.rglob("*") if ".git" not in path.parts and path.is_file())
        except OSError:
            return None
    return None


def resolve_count(root: Path, text: str) -> bool | None:
    """Resolve ``count`` claims using ``files=3`` or ``gates: 42`` syntax."""

    value = text.strip()
    match = re.fullmatch(r"(?P<selector>[A-Za-z][A-Za-z0-9_.-]*(?::[^=:\s]+)?)\s*[:=]\s*(?P<expected>\d+)", value)
    if match is None and re.fullmatch(r"\d+", value):
        selector, expected_text = "files", value
    elif match is None:
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
        if not registry.is_file():
            continue
        try:
            document = json.loads(registry.read_text(encoding="utf-8"))
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
            except (OSError, UnicodeError, ValueError, TypeError, KeyError):
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
