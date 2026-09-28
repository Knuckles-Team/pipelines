"""The one exception type that turns into exit status 2."""

from __future__ import annotations


class CannotRun(RuntimeError):
    """The gate could not produce a trustworthy verdict.

    An unavailable tool, a malformed report, an unreadable configuration or a
    failing git call is an environment fact. It is reported as exit status 2
    and never as a clean pass: a gate that could not run has not found nothing.
    """


class Unavailable(CannotRun):
    """A prerequisite is absent from this environment: a native tool or a sibling checkout.

    Unlike other :class:`CannotRun` causes this is not a defect of the input, so
    the command line reports it by environment: in CI (``$CI`` set) it is exit
    status 2, fail closed; locally it prints ``SKIPPED (<gate>): <reason>`` with
    the ``remedy`` command and exits 0, so a fresh clone can commit before the
    optional scanners are installed.
    """

    def __init__(self, reason: str, *, remedy: str = "scripts/bootstrap.sh") -> None:
        super().__init__(reason)
        self.remedy = remedy


#: The remedy for a missing native scanner.
SCANNERS_REMEDY = "scripts/bootstrap.sh --scanners"
