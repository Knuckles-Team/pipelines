"""Credential-shaped patterns for patch and plain-text scans (hard failures).

Written so that no line of this module matches any of its own patterns: the
scanner audits its own history like any other file, with no self-exclusion.
"""

from __future__ import annotations

import re

CREDENTIAL_PATTERNS: dict[str, re.Pattern[str]] = {
    "aws_access_key_id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "aws_secret_key_assignment": re.compile(r"(?i)aws_secret_access_key\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{40}['\"]?"),
    "github_pat_classic": re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
    "github_pat_fine_grained": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"),
    "github_oauth": re.compile(r"\bgho_[A-Za-z0-9]{36}\b"),
    "gitlab_pat": re.compile(r"\bglpat-[A-Za-z0-9_-]{20}\b"),
    "slack_token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "stripe_key": re.compile(r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9]{20,}(?:T3BlbkFJ[A-Za-z0-9]{20,})?\b"),
    "openai_project_key": re.compile(r"\bsk-proj-[A-Za-z0-9_-]{20,}\b"),
    "anthropic_key": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    "google_api_key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "npm_token": re.compile(r"\bnpm_[A-Za-z0-9]{36}\b"),
    "pypi_token": re.compile(r"\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_-]{20,}\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    "private_key_block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    "client_secret_assignment": re.compile(r"(?i)client_secret\s*[:=]\s*['\"][A-Za-z0-9~_.\-+/=]{8,}['\"]"),
    "generic_secret_assignment": re.compile(
        r"(?i)\b(?:password|passwd|pwd|secret|api[_-]?key|token)\s*[:=]\s*['\"][^'\"\s]{6,}['\"]"
    ),
    # A signer-key credential is named signer_key(s)[_json] and usually carries
    # a JSON object value, so the quote never follows the '=' directly. No
    # leading \b: the real names are underscore-joined compounds. The lazy
    # window allows quotes so it reaches past a short inner JSON key.
    "engine_signer_credential_assignment": re.compile(
        r"(?i)signer_keys?(?:_json)?\b.{0,120}?['\"][A-Za-z0-9+/_.=-]{16,}['\"]"
    ),
    "db_url_with_password": re.compile(r"(?i)\b(?:postgres|postgresql|mysql|mongodb|redis)://[^\s'\"/@]+:[^\s'\"/@]+@"),
    "basic_auth_url": re.compile(r"(?i)https?://[^\s'\"/@]+:[^\s'\"/@]+@[^\s'\"]+"),
}
