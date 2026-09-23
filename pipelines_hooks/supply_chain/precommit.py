"""Pre-commit configuration rules (SC-HOOK-*): immutable hook revisions and pinned dependencies."""

from __future__ import annotations

import re

from pipelines_hooks.supply_chain.finding import Finding, Source

_REPO_RE = re.compile(r"^\s*-\s*repo:\s*([^\s#]+)")
_REV_RE = re.compile(r"^\s*rev:\s*([^\s#]+)")
_SHA_RE = re.compile(r"[0-9a-fA-F]{40}")
# Knuckles-Team/pipelines is the sanctioned exception to "immutable revision":
# every repository pins its hook repo entry to `rev: main`, never a commit SHA
# or tag (operator ruling, plans/refactor/DECISIONS.md).
_PIPELINES_HOOK_RE = re.compile(r"^https://github\.com/Knuckles-Team/pipelines(?:\.git)?/?$", re.IGNORECASE)
_PYTHON_PIN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[A-Za-z0-9_,.-]+\])?==[^\s]+")
_NPM_PIN_RE = re.compile(r"@[^/\s]+/[^@\s]+@[0-9][0-9A-Za-z.+_-]*")
_VCS_PIN_RE = re.compile(r"@[0-9a-fA-F]{40}(?:#|$)")


def _repository_blocks(lines: list[str]) -> list[tuple[int, str, list[tuple[int, str]]]]:
    """``(line, repository, following lines)`` for each ``- repo:`` entry."""
    blocks: list[tuple[int, str, list[tuple[int, str]]]] = []
    for number, line in enumerate(lines, 1):
        match = _REPO_RE.match(line)
        if match:
            blocks.append((number, match.group(1).strip("\"'"), []))
        elif blocks:
            blocks[-1][2].append((number, line))
    return blocks


def _revision_findings(source: Source) -> list[Finding]:
    findings = []
    for number, repository, body in _repository_blocks(source.text.splitlines()):
        if repository in {"local", "meta"}:
            continue
        revision = next(((n, m.group(1).strip("\"'")) for n, line in body if (m := _REV_RE.match(line))), None)
        if _PIPELINES_HOOK_RE.match(repository):
            if revision is None or revision[1] != "main":
                line = revision[0] if revision else number
                findings.append(
                    source.at_line(
                        line,
                        rule="SC-HOOK-003",
                        message="Knuckles-Team/pipelines pre-commit hook must be pinned to rev: main; a commit SHA or tag is rejected",
                    )
                )
            continue
        if revision is None:
            findings.append(source.at_line(number, rule="SC-HOOK-001", message="external pre-commit hook repository has no immutable revision"))
        elif not _SHA_RE.fullmatch(revision[1]):
            findings.append(source.at_line(revision[0], rule="SC-HOOK-001", message="external pre-commit hook is not pinned to a full commit SHA"))
    return findings


def _pinned_dependency(dependency: str) -> bool:
    return bool(_PYTHON_PIN_RE.fullmatch(dependency) or _NPM_PIN_RE.fullmatch(dependency) or _VCS_PIN_RE.search(dependency))


def precommit_findings(source: Source) -> list[Finding]:
    findings = _revision_findings(source)
    for match in re.finditer(r"additional_dependencies:\s*\[([^\]]*)\]", source.text, re.DOTALL):
        dependencies = [raw.strip().strip("\"'") for raw in match.group(1).split(",")]
        findings.extend(
            source.at_offset(match.start(), rule="SC-HOOK-002", message="pre-commit additional dependency is not pinned exactly")
            for dependency in dependencies
            if dependency and not _pinned_dependency(dependency)
        )
    return findings
