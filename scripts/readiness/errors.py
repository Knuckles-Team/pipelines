"""Bounded errors shared by the Pages readiness contract modules."""

from __future__ import annotations

import re
from typing import NoReturn


class ReadinessTckError(ValueError):
    """A bounded, privacy-safe offline readiness failure."""


def _fail(code: str) -> NoReturn:
    """Raise a readiness error with a safe, stable machine-readable code."""

    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", code):
        code = "readiness-contract-invalid"
    raise ReadinessTckError(code)
