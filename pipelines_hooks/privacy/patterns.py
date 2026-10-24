"""Home paths, credential URIs and placeholder rules for the privacy gate."""

from __future__ import annotations

import re

from pipelines_hooks.privacy.hosts import is_reserved_hostname
from pipelines_hooks.security.placeholders import is_placeholder_secret

# POSIX home directories are case-sensitive path segments (`/home/`, `/Users/`); a lowercase `/users/me/` is an API
# route, not a filesystem path. Windows drive paths stay case-insensitive.
HOME_PATH_RE = re.compile(
    r"(?:(?<![A-Za-z0-9_.-])(?-i:/home/)(?P<home_user>[A-Za-z0-9_.-]+)(?:/|\b)|"
    r"(?<![A-Za-z0-9_.-])(?-i:/Users/)(?P<users_user>[A-Za-z0-9_.-]+)(?:/|\b)|"
    r"(?<![A-Za-z0-9_.-])/mnt/[A-Za-z]/(?-i:Users/)(?P<mnt_user>[A-Za-z0-9_.-]+)(?:/|\b)|"
    r"(?<![A-Za-z0-9_.-])[A-Za-z]:[\\/]Users[\\/](?P<win_user>[^\\/\s]+)(?:[\\/]|\b))",
    re.IGNORECASE,
)
#: Documented "not a real account" stand-ins used by fixtures. The ambient
#: candidates the gate derives (the actual current account) are never here.
RESERVED_HOME_USERS = frozenset(
    {
        "a",
        "a-different-account",
        "account",
        "agent-user",
        "alice",
        "app",
        "bob",
        "example",
        "example-user",
        "exampleuser",
        "local",
        "local-account",
        "operator",
        "person",
        "sensitive-account",
        "some-account",
        "u",
        "user",
    }
)
PERSISTED_FIELD_RE = re.compile(
    r"[\"']?(?P<field>workspace_path|source_path|skill_path|local_path|source_file|eg_ledger_path)[\"']?\s*[:=]\s*(?P<value>.+)",
    re.IGNORECASE,
)
NEUTRAL_URI_RE = re.compile(r"^[\s\"']*(?:repo|skill|connector|design)://", re.IGNORECASE)
INTERNAL_ENDPOINT_RE = re.compile(
    r"(?i)\b(?:[A-Za-z0-9-]+\.)+(?:arpa|internal)\b|\b(?:[A-Za-z0-9-]+\.)*svc\.cluster\.local\b|"
    r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b"
)
PRIVATE_KEY_LINE_RE = re.compile(r"^\s*-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----\s*$")
CREDENTIAL_URI_RE = re.compile(
    r"(?i)\b[a-z][a-z0-9+.-]*://[^\s/@:]+:(?P<secret>[^\s/@]+)@(?P<cred_host>[^\s/@:\"'<>]+)"
)
HOST_IDENTITY_RE = re.compile(r"(?i)\bssh://(?!\$\{)[^\s/@]+@")
# D-EG-PRIVACY-R001-FALSEPOS (mirrored fix): the lookbehind excluded only
# alnum, so a hyphen-joined requirement ID (`GRAPHOS-FLEET-R016`) matched
# `R016` as a fleet host alias (an `r`/`rw` prefix plus 3+ digits is a real
# fleet node naming convention) -- the hyphen before `R016` was never
# itself alnum, so it never blocked the match. Excluding `-` too keeps a
# bare host token and a requirement ID embedded without a hyphen boundary
# caught, while a hyphen-prefixed requirement-ID citation is no longer
# misread as a host.
MACHINE_HOST_ID_RE = re.compile(r"(?i)(?<![a-z0-9-])(?:rw?|host)[0-9]{3,}(?![a-z0-9])")


#: A value that is a route (`endpoint = "/Users/Me"`) or the container user's home (`home = "/home/app"` in pyproject).
_API_ENDPOINT_BEFORE = re.compile(r"""(?:\bendpoint\w*|^\s*home)\s*[:=]\s*[rf]?["']$""")


def has_real_home_path(line: str) -> bool:
    """Whether any home-path match on the line is NOT a documented stand-in."""
    for match in HOME_PATH_RE.finditer(line):
        if _API_ENDPOINT_BEFORE.search(line[: match.start()]):
            continue  # `endpoint = "/Users/Me"`: an HTTP route a client calls, not a filesystem path
        user = next((value for value in match.groupdict().values() if value), None)
        if user is not None and user.strip("\\/").casefold() not in RESERVED_HOME_USERS:
            return True
    return False


#: A secret that is a variable reference (`${GITHUB_TOKEN}`, `$TOKEN`) resolved at run time holds no credential.
_INTERPOLATED = re.compile(r"^\$(?:\{[A-Za-z_][A-Za-z0-9_]*\}|\{\{[^}]*\}\}|[A-Za-z_][A-Za-z0-9_]*)$")


def credential_uri_leak(line: str) -> bool:
    """A credential-bearing URI whose secret is real and whose host is not reserved."""
    match = CREDENTIAL_URI_RE.search(line)
    if match is None or is_placeholder_secret(match.group("secret")) or _INTERPOLATED.match(match.group("secret")):
        return False
    host = match.group("cred_host")
    return not (host and is_reserved_hostname(host))
