"""GitHub Actions workflow rules (SC-GHA-*)."""

from __future__ import annotations

import re

from pipelines_hooks.supply_chain.finding import NETWORK_TO_SHELL_RE, Finding, Source, pinned_digest

ACTION_SHA_RE = re.compile(r"^[^/@\s]+/[^@\s]+@[0-9a-fA-F]{40}$")
EXTERNAL_USES_RE = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", re.MULTILINE)
_CHECKOUT_RE = re.compile(r"\buses:\s*actions/checkout@[0-9a-fA-F]{40}\b")
_PERSIST_FALSE_RE = re.compile(r"^\s*persist-credentials:\s*false\s*(?:#.*)?$")
_NESTED_WRITE_RE = re.compile(r"^\s{1,2}[a-z-]+:\s*write\s*(?:#.*)?$", re.IGNORECASE)
_REPO_WRITE = "repository-wide write permission must be scoped to the publishing job"
FORBIDDEN = (
    (r"^\s*pull_request_target:\s*", "SC-GHA-005", "pull_request_target requires an explicit security exception"),
    (r"\bsecrets:\s*inherit\b", "SC-GHA-006", "blanket reusable-workflow secret inheritance is forbidden"),
    (r"\bpermissions:\s*write-all\b", "SC-GHA-003", "write-all token permissions are forbidden"),
    (r"\bpersist-credentials:\s*true\b", "SC-GHA-007", "checkout credentials must not be persisted explicitly"),
    (r"ACTIONS_ALLOW_UNSECURE_COMMANDS", "SC-GHA-008", "insecure Actions command compatibility is forbidden"),
)


def _pinned(reference: str) -> bool:
    if reference.startswith("./"):
        return True
    if reference.startswith("docker://"):
        return pinned_digest(reference.removeprefix("docker://"))
    return bool(ACTION_SHA_RE.fullmatch(reference))


def _uses_findings(source: Source) -> list[Finding]:
    return [
        source.at_offset(m.start(), rule="SC-GHA-001", message="external action or reusable workflow is not pinned to a full commit SHA")
        for m in EXTERNAL_USES_RE.finditer(source.text)
        if not _pinned(m.group(1))
    ]


def _step_block(lines: list[str], index: int) -> list[str]:
    indentation = len(lines[index]) - len(lines[index].lstrip())
    block = []
    for candidate in lines[index + 1 :]:
        depth = len(candidate) - len(candidate.lstrip())
        if candidate.strip() and (depth < indentation or (depth == indentation and candidate.lstrip().startswith("-"))):
            break
        block.append(candidate)
    return block


def _checkout_findings(source: Source) -> list[Finding]:
    lines = source.text.splitlines()
    return [
        source.at_line(index + 1, rule="SC-GHA-007", message="checkout must explicitly disable persisted credentials")
        for index, line in enumerate(lines)
        if _CHECKOUT_RE.search(line) and not any(_PERSIST_FALSE_RE.match(c) for c in _step_block(lines, index))
    ]


def _nested_write_findings(source: Source, start: int) -> list[Finding]:
    findings = []
    for number, line in enumerate(source.text[start:].splitlines(), source.line_of(start) + 1):
        if line and not line[0].isspace() and not line.lstrip().startswith("#"):
            break
        if _NESTED_WRITE_RE.match(line):
            findings.append(source.at_line(number, rule="SC-GHA-004", message=_REPO_WRITE))
    return findings


def _permission_findings(source: Source) -> list[Finding]:
    permissions = re.search(r"^permissions:\s*(.*)$", source.text, re.MULTILINE)
    if permissions is None:
        return [source.at_line(1, rule="SC-GHA-002", message="top-level token permissions are not declared")]
    inline = permissions.group(1).strip().casefold()
    findings = []
    if "write-all" in inline:
        findings.append(source.at_offset(permissions.start(), rule="SC-GHA-003", message="top-level write-all token permissions are forbidden"))
    elif re.search(r"\bwrite\b", inline):
        findings.append(source.at_offset(permissions.start(), rule="SC-GHA-004", message=_REPO_WRITE))
    return findings + _nested_write_findings(source, permissions.end())


def workflow_findings(source: Source) -> list[Finding]:
    findings = _uses_findings(source) + _checkout_findings(source) + _permission_findings(source)
    for pattern, rule, message in FORBIDDEN:
        findings.extend(source.each_match(re.compile(pattern, re.IGNORECASE | re.MULTILINE), rule=rule, message=message))
    findings.extend(source.each_match(NETWORK_TO_SHELL_RE, rule="SC-GHA-009", message="network response is executed by a shell"))
    return findings
