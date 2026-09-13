"""Dependency-manifest rules (SC-DEP-*) and installer rules (SC-INSTALL-*)."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.supply_chain.finding import NETWORK_TO_SHELL_RE, Finding, Source

VCS_REVISION_RE = re.compile(r"@[0-9a-fA-F]{40}(?:$|[#&])")
POWERSHELL_NETWORK_RE = re.compile(r"(?:irm|iwr|Invoke-RestMethod|Invoke-WebRequest)\b[^\n|]*\|\s*(?:iex|Invoke-Expression)\b", re.IGNORECASE)
DYNAMIC_EXPRESSION_RE = re.compile(r"(?:^|[;&|]\s*)(?:eval\b|Invoke-Expression\b|iex\b)", re.IGNORECASE)
_LOCKS = (
    ("pyproject.toml", {"Pipfile.lock", "poetry.lock", "uv.lock"}, "SC-DEP-001", "Python dependency manifest has no committed resolver lock"),
    ("package.json", {"package-lock.json", "pnpm-lock.yaml", "yarn.lock"}, "SC-DEP-002", "Node dependency manifest has no committed resolver lock"),
    ("Cargo.toml", {"Cargo.lock"}, "SC-DEP-003", "Rust application/workspace manifest has no committed Cargo.lock"),
)


def _strings(values: object) -> list[str]:
    return [item for item in values if isinstance(item, str)] if isinstance(values, list) else []


def declared_dependencies(document: dict[str, Any]) -> list[str]:
    """Runtime, optional and group dependency strings of a pyproject document."""
    project = document.get("project", {}) if isinstance(document.get("project"), dict) else {}
    tables = [project.get("optional-dependencies", {}), document.get("dependency-groups", {})]
    values = _strings(project.get("dependencies", []))
    for table in tables:
        values.extend(v for group in (table.values() if isinstance(table, dict) else []) for v in _strings(group))
    return values


def _unsafe(dependency: str) -> bool:
    folded = dependency.casefold()
    vcs = "git+" in folded and ("git+https://" not in folded or VCS_REVISION_RE.search(dependency) is None)
    archive = bool(re.search(r"\s@\s*https?://", dependency, re.IGNORECASE)) and (" @ https://" not in folded or "#sha256=" not in folded)
    return vcs or archive


def _pyproject_findings(label: str, pyproject: Path, reader: Callable[[Path], str]) -> list[Finding]:
    try:
        text = reader(pyproject)
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return [Finding(label, "pyproject.toml", 1, "SC-DEP-004", "Python dependency manifest is invalid")]
    except CannotRun as error:
        return [Finding(label, "pyproject.toml", 0, "SC-SRC-001", str(error))]
    source = Source(label, "pyproject.toml", text)
    message = "direct network dependency must use HTTPS and an immutable revision or SHA-256 digest"
    return [
        source.at_offset(max(text.find(d), 0), rule="SC-DEP-004", message=message)
        for d in declared_dependencies(document)
        if _unsafe(d)
    ]


def dependency_findings(label: str, repository: Path, sources: tuple[Path, ...], *, reader: Callable[[Path], str]) -> list[Finding]:
    names = {path.name for path in sources if path.parent == repository}
    findings = [
        Finding(label, manifest, 1, rule, message)
        for manifest, locks, rule, message in _LOCKS
        if manifest in names and not names & locks
    ]
    if "pyproject.toml" in names:
        findings += _pyproject_findings(label, repository / "pyproject.toml", reader)
    return findings


def installer_findings(source: Source) -> list[Finding]:
    """Bootstrap code must not execute network responses or evaluate expressions."""
    findings = []
    for number, line in enumerate(source.text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if NETWORK_TO_SHELL_RE.search(line) or POWERSHELL_NETWORK_RE.search(line):
            findings.append(source.at_line(number, rule="SC-INSTALL-001", message="installer executes an unverified network response"))
        if DYNAMIC_EXPRESSION_RE.search(line):
            findings.append(source.at_line(number, rule="SC-INSTALL-002", message="installer uses dynamic expression evaluation"))
    return findings
