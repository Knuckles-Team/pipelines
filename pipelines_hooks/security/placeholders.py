"""Documented placeholder credentials, shared by every credential-URI rule.

A credential-shaped URI whose SECRET is a documented placeholder word
(``postgresql://agent:agent@localhost`` in a docstring, ``changeme``,
``your-password``) or a mask (``****``) is an example, not a leak. The
tracked-privacy and secret-history gates apply this one rule, so a
documentation example is judged the same by both. A real-looking secret still
fires regardless of the host it targets.
"""

from __future__ import annotations

import re

PLACEHOLDER_TOKENS = frozenset(
    {"agent", "changeme", "change_me", "example", "fixme", "masked", "password", "placeholder",
     "redacted", "replace", "sample", "secret", "test", "todo", "xxxx", "your"}
)
URI_SECRET_RE = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s/@:'\"]+:(?P<secret>[^\s/@'\"]+)@")


def is_placeholder_secret(secret: str) -> bool:
    """Whether a URI password is empty, a mask, or contains a documented placeholder word."""
    rendered = secret.strip()
    if not rendered or re.fullmatch(r"(?:\*+|#+|x{4,})", rendered, flags=re.IGNORECASE):
        return True
    return bool(set(re.findall(r"[a-z0-9]+", rendered.lower())) & PLACEHOLDER_TOKENS)


def only_placeholder_uri_secrets(line: str) -> bool:
    """Whether every credential-bearing URI on the line carries a placeholder secret."""
    secrets = [match.group("secret") for match in URI_SECRET_RE.finditer(line)]
    return bool(secrets) and all(is_placeholder_secret(secret) for secret in secrets)
