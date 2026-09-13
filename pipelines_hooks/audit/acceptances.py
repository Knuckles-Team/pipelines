"""The risk-acceptance ledger ``.security-audit-allow.txt``.

One line per accepted advisory: ``ADVISORY-ID package expires=YYYY-MM-DD #
justification`` (at least 12 characters). Package-only suppressions are
rejected, the horizon is at most 90 days, an expired line fails, a duplicate
fails, and an acceptance that matches no live finding fails as stale.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

from pipelines_hooks.audit.lock import PACKAGE_RE, AuditError, normalise_package

LEDGER = ".security-audit-allow.txt"
MAX_ACCEPTANCE_DAYS = 90
ADVISORY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]{2,127}$")
_EXPIRY_RE = re.compile(r"^expires=(\d{4}-\d{2}-\d{2})$")


@dataclass(frozen=True)
class RiskAcceptance:
    advisory_id: str
    package: str
    expires: dt.date
    justification: str


def _expiry(number: int, field: str, today: dt.date) -> dt.date:
    match = _EXPIRY_RE.fullmatch(field)
    try:
        expires = dt.date.fromisoformat(match.group(1)) if match else None
    except ValueError:
        expires = None
    if expires is None:
        raise AuditError(f"security acceptance line {number} is invalid")
    if expires < today:
        raise AuditError(f"security acceptance line {number} has expired")
    if expires > today + dt.timedelta(days=MAX_ACCEPTANCE_DAYS):
        raise AuditError(f"security acceptance line {number} exceeds the review horizon")
    return expires


def parse_line(number: int, raw: str, today: dt.date) -> RiskAcceptance | None:
    """One ledger line, or ``None`` for a blank or comment line."""
    stripped = raw.strip()
    if not stripped or stripped.startswith("#"):
        return None
    declaration, separator, justification = stripped.partition("#")
    fields = declaration.split()
    if not separator or len(fields) != 3 or len(justification.strip()) < 12:
        raise AuditError(f"security acceptance line {number} is not justified")
    advisory, package = fields[0], normalise_package(fields[1])
    if not ADVISORY_RE.fullmatch(advisory) or not PACKAGE_RE.fullmatch(package):
        raise AuditError(f"security acceptance line {number} is invalid")
    return RiskAcceptance(advisory, package, _expiry(number, fields[2], today), justification.strip())


def load_acceptances(root: Path) -> dict[tuple[str, str], RiskAcceptance]:
    path = root / LEDGER
    if not path.exists():
        return {}
    if path.is_symlink() or path.stat().st_size > 1024 * 1024:
        raise AuditError("security acceptance ledger is unavailable or too large")
    accepted: dict[tuple[str, str], RiskAcceptance] = {}
    today = dt.date.today()
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        acceptance = parse_line(number, raw, today)
        key = None if acceptance is None else (acceptance.advisory_id.casefold(), acceptance.package)
        if key is not None and key in accepted:
            raise AuditError(f"security acceptance line {number} is duplicated")
        if key is not None:
            accepted[key] = acceptance
    return accepted
