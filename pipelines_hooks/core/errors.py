"""The one exception type that turns into exit status 2."""

from __future__ import annotations


class CannotRun(RuntimeError):
    """The gate could not produce a trustworthy verdict.

    An unavailable tool, a malformed report, an unreadable configuration or a
    failing git call is an environment fact. It is reported as exit status 2
    and never as a clean pass: a gate that could not run has not found nothing.
    """
