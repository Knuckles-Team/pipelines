"""The only module that reads the process environment.

Gates never call ``os.environ`` directly (the env-sprawl gate enforces this for
the package); every process-level override is read here, by name, so the full
set of variables the hooks honour is visible in one place.
"""

from __future__ import annotations

import os

#: Every environment variable a gate reads, with what it controls.
KNOWN_SETTINGS = {
    "CCCC_BIN": "path of the pinned cccc binary",
    "KISS_BIN": "path of the pinned kiss binary",
    "DUPEHOUND_BIN": "path of the pinned dupehound binary",
    "JSCPD_BIN": "path of the pinned jscpd binary",
    "CX_DUP_BASE_REF": "base revision of the clone gates in CI",
    "PRE_COMMIT_FROM_REF": "remote revision of the range pre-commit is pushing",
    "PRE_COMMIT_HOME": "pre-commit cache directory (patch-safety)",
    "XDG_CACHE_HOME": "cache root used when PRE_COMMIT_HOME is unset",
    "SECURITY_AUDIT_OFFLINE_POLICY": "'warn' downgrades an unreachable OSV locally",
    "SSL_CERT_FILE": "PEM bundle for the OSV client",
    "REQUESTS_CA_BUNDLE": "PEM bundle for the OSV client",
    "SSL_CERT_DIR": "hashed CA directory for the OSV client",
    "AGENT_UTILITIES_PRIVACY_IDENTIFIERS": "declared identities for tracked-privacy",
    "USER": "ambient account name (tracked-privacy)",
    "LOGNAME": "ambient account name (tracked-privacy)",
    "USERNAME": "ambient account name (tracked-privacy)",
    "CI_GATE_TMPDIR": "temporary directory of the local CI replica",
    "CI_GATE_STEP_TIMEOUT_SECS": "per-step timeout of the local CI replica",
}


def setting(name: str, default: str = "") -> str:
    """The stripped value of one known variable, or ``default``."""
    if name not in KNOWN_SETTINGS:
        raise KeyError(f"undeclared setting {name!r}")
    return (os.environ.get(name) or default).strip()


def process_environment() -> dict[str, str]:
    """A copy of the environment, for handing to a child process."""
    return dict(os.environ)
