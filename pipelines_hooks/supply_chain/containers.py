"""Dockerfile and compose rules (SC-CTR-*)."""

from __future__ import annotations

import re

from pipelines_hooks.supply_chain.finding import NETWORK_TO_SHELL_RE, Finding, Source, pinned_digest

DOCKER_FROM_RE = re.compile(r"^\s*FROM(?:\s+--platform=\S+)?\s+(\S+)(?:\s+AS\s+(\S+))?", re.IGNORECASE | re.MULTILINE)
DOCKER_COPY_FROM_RE = re.compile(r"\bCOPY\s+--from=([^\s]+)", re.IGNORECASE)
DOCKER_ARG_RE = re.compile(r"^\s*ARG\s+([A-Za-z_][A-Za-z0-9_]*)(?:=(\S+))?", re.MULTILINE)
SECRET_NAME_RE = re.compile(
    r"(?:^|_)(?:ACCESS_KEY|ACCESS_TOKEN|API_KEY|AUTH_TOKEN|CLIENT_SECRET|PASSWORD|PASSWD|PRIVATE_KEY|SECRET|TOKEN)$", re.IGNORECASE
)
COMPOSE_IMAGE_RE = re.compile(r"^\s*image:\s*(.+?)\s*(?:#.*)?$", re.MULTILINE)
REQUIRED_IMAGE_DIGEST_VARIABLE_RE = re.compile(r"^\$\{[A-Z][A-Z0-9_]*_IMAGE_DIGEST:\?[^}\r\n]{1,128}\}$")
_DANGEROUS_COMPOSE = (
    (r"^\s*privileged:\s*true\s*$", "privileged containers require a reviewed exception"),
    (r"^\s*(?:network_mode|pid|ipc):\s*host\s*$", "host namespace sharing requires a reviewed exception"),
    (r"^\s*security_opt:.*unconfined", "unconfined container security profiles are forbidden"),
    (r"/var/run/docker\.sock", "mounting the Docker control socket is forbidden"),
)


def _from_valid(image: str, stages: set[str], arguments: dict[str, str | None]) -> bool:
    names = re.findall(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", image)
    if len(names) == 1 and names[0] in arguments:
        default = arguments[names[0]]
        if default is None:
            return image in {f"${names[0]}", f"${{{names[0]}}}"}
        return pinned_digest(image.replace(f"${{{names[0]}}}", default).replace(f"${names[0]}", default))
    return image.casefold() == "scratch" or image.casefold() in stages or (len(names) != 1 and pinned_digest(image))


def _from_findings(source: Source) -> tuple[list[Finding], set[str]]:
    arguments = {m.group(1): m.group(2) for m in DOCKER_ARG_RE.finditer(source.text)}
    stages: set[str] = set()
    findings = []
    for match in DOCKER_FROM_RE.finditer(source.text):
        if match.group(2):
            stages.add(match.group(2).casefold())
        if not _from_valid(match.group(1), stages, arguments):
            findings.append(source.at_offset(match.start(), rule="SC-CTR-001", message="external base image is not pinned to sha256"))
    return findings, stages


def docker_findings(source: Source) -> list[Finding]:
    findings, stages = _from_findings(source)
    for match in DOCKER_COPY_FROM_RE.finditer(source.text):
        origin = match.group(1)
        if not (origin.isdigit() or origin.casefold() in stages or origin.startswith("$") or pinned_digest(origin)):
            findings.append(source.at_offset(match.start(), rule="SC-CTR-002", message="external COPY --from image is not pinned to sha256"))
    findings += source.each_match(NETWORK_TO_SHELL_RE, rule="SC-CTR-003", message="network response is executed by a shell during the build")
    findings += source.each_match(
        re.compile(r"^\s*ADD\s+https?://", re.IGNORECASE | re.MULTILINE), rule="SC-CTR-004", message="remote ADD bypasses explicit digest verification"
    )
    findings += [
        source.at_offset(m.start(), rule="SC-CTR-005", message="secret-shaped build ARG/ENV can persist in image metadata; use a secret mount")
        for m in re.finditer(r"^\s*(?:ARG|ENV)\s+([A-Za-z_][A-Za-z0-9_]*)", source.text, re.MULTILINE)
        if SECRET_NAME_RE.search(m.group(1))
    ]
    return findings


def _compose_image_valid(image: str) -> bool:
    if image.endswith((":local", ":dev-local")):
        return True
    if not image.startswith("${"):
        return pinned_digest(image)
    return (
        (":?" in image and "@sha256" in image)
        or bool(REQUIRED_IMAGE_DIGEST_VARIABLE_RE.fullmatch(image))
        or pinned_digest(image)
        or bool(re.search(r":-[^}]+:(?:dev-)?local}", image))
    )


def compose_findings(source: Source) -> list[Finding]:
    findings = [
        source.at_offset(m.start(), rule="SC-CTR-006", message="runtime image must be a digest or a required immutable image variable")
        for m in COMPOSE_IMAGE_RE.finditer(source.text)
        if not _compose_image_valid(m.group(1).strip().strip("\"'"))
    ]
    for pattern, message in _DANGEROUS_COMPOSE:
        findings += source.each_match(re.compile(pattern, re.IGNORECASE | re.MULTILINE), rule="SC-CTR-007", message=message)
    return findings
