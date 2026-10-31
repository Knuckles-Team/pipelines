"""Line classifiers for public text artifacts and for runtime/deployment source."""

from __future__ import annotations

import re
from pathlib import Path

from pipelines_hooks.privacy import patterns
from pipelines_hooks.privacy.hosts import internal_endpoint_in_line

_NEUTRAL_AUTHOR_NAME = "repository maintainers"
_NEUTRAL_AUTHOR_EMAIL_SUFFIX = "@example.invalid"
# A role address names no person; PyPI rejects the reserved .invalid domain.
_NEUTRAL_ROLE_ADDRESS = "maintainers@knuckles.team"
_DEPLOYMENT_MARKERS = ("deploy", "runbook", "configuration", "workspace-config", "mcp_auth", "secrets-auth")


def is_deployment_doc(path: Path) -> bool:
    value = path.as_posix().casefold()
    return value.startswith("docs/recipes/") or any(marker in value for marker in _DEPLOYMENT_MARKERS)


def _persisted_machine_path(line: str) -> bool:
    persisted = patterns.PERSISTED_FIELD_RE.search(line)
    if not persisted or patterns.NEUTRAL_URI_RE.search(persisted.group("value")):
        return False
    value = persisted.group("value").strip(" \t,;)}]\"'").casefold()
    # Only an absolute or home-relative value names this machine's filesystem; a repository-relative path
    # (`pkg/skills/x/SKILL.md`) or a ${...} template is the same on every checkout (PIPE-GATES-R016.118).
    return bool(re.match(r"^(?:[a-z]:|[/\\]|~)", value, re.IGNORECASE))


def _has_identifier(line: str, identifiers: frozenset[str]) -> bool:
    folded = line.casefold()
    return any(re.search(rf"(?<![\w-]){re.escape(value)}(?![\w-])", folded) for value in identifiers)


def _attributed_name(line: str, names: frozenset[str]) -> bool:
    """Recognize explicit attribution, account fields, and name-role labels."""
    line = line.casefold()
    role = r"(?:author|owner|maintainer|committer|contributor|creator|operator|username|user(?:\.name)?|account)"
    prefix = rf"(?:\b{role}(?:[ _-]name)?[\"']?\s*[:=]\s*|\b(?:authored|written|created|generated|maintained|owned|committed|signed)[ -]by\s+)"
    prefix += r"|\bgit\s+config\s+(?:(?:--global|--local|--system)\s+)?user\.name\s+"
    prefix = "(?:" + prefix + ")"
    for name in names:
        token = rf"(?<![\w-]){re.escape(name)}(?![\w-])"
        if re.search(prefix + r"[\"']?" + token, line, re.IGNORECASE):
            return True
        if re.search(token + rf"\s*\({role}\)", line, re.IGNORECASE):
            return True
        if re.search(token + r"@[\w.-]", line):  # `account@host`
            return True
    return False


def _has_local_identity(line: str, identifiers: frozenset[str], display_names: frozenset[str]) -> bool:
    """Strict evidence wins; contextual attribution adds display-name evidence."""
    return _has_identifier(line, identifiers) or _attributed_name(line, display_names)


def classify_line(
    line: str, *, identifiers: frozenset[str], deployment_doc: bool, display_names: frozenset[str] = frozenset()
) -> frozenset[str]:
    """Categories for one line of a public text artifact."""
    persisted = _persisted_machine_path(line)
    checks = [
        (persisted, "persisted machine path"),
        (not persisted and patterns.has_real_home_path(line), "machine-specific home path"),
        (_has_local_identity(line, identifiers, display_names), "local account or host identifier"),
        (patterns.machine_host_id_in_line(line), "machine-specific host identifier"),
    ]
    if deployment_doc:
        checks += [
            (bool(patterns.INTERNAL_ENDPOINT_RE.search(line)), "hard-coded internal endpoint"),
            (patterns.credential_uri_leak(line), "credential-bearing URI"),
            (bool(patterns.HOST_IDENTITY_RE.search(line)), "hard-coded remote account"),
        ]
    return frozenset(category for hit, category in checks if hit)


def classify_runtime_source_line(
    line: str, *, identifiers: frozenset[str], display_names: frozenset[str] = frozenset()
) -> frozenset[str]:
    """Categories for one line of runtime or deployment source.

    Source legitimately manipulates path-shaped values, so the generic
    ``source_path = ...`` rule is not applied; concrete account paths,
    internal endpoints, credential URIs, identities and key material are.
    """
    checks = (
        (patterns.has_real_home_path(line), "machine-specific home path in runtime source"),
        (_has_local_identity(line, identifiers, display_names), "local account or host identifier in runtime source"),
        (internal_endpoint_in_line(line), "hard-coded internal endpoint in runtime source"),
        (patterns.credential_uri_leak(line), "credential-bearing URI in runtime source"),
        (bool(patterns.PRIVATE_KEY_LINE_RE.fullmatch(line)), "private key material in runtime source"),
    )
    return frozenset(category for hit, category in checks if hit)


def _neutral_email(folded: str) -> bool:
    return _NEUTRAL_AUTHOR_EMAIL_SUFFIX in folded or _NEUTRAL_ROLE_ADDRESS in folded


def _non_neutral_author(folded: str, *, in_authors: bool) -> bool:
    if re.match(r"authors\s*=", folded):
        return _NEUTRAL_AUTHOR_NAME not in folded or not _neutral_email(folded)
    if in_authors and re.match(r"name\s*=", folded):
        return _NEUTRAL_AUTHOR_NAME not in folded
    return in_authors and bool(re.match(r"email\s*=", folded)) and not _neutral_email(folded)


def author_metadata_lines(path: Path, lines: list[str]) -> list[int]:
    """Non-neutral package-author lines of a TOML file (values never returned)."""
    if path.suffix.casefold() != ".toml":
        return []
    found, in_authors = [], False
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped == "[[project.authors]]":
            in_authors = True
            continue
        in_authors = in_authors and not stripped.startswith("[")
        if _non_neutral_author(stripped.casefold(), in_authors=in_authors):
            found.append(number)
    return found
