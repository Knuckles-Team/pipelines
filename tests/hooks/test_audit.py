"""dependency-audit: lock parsing, the acceptance ledger, and the verdict (OSV stubbed out)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from pipelines_hooks.audit import gate
from pipelines_hooks.audit.acceptances import parse_line
from pipelines_hooks.audit.lock import AuditError, parse_lock

LOCK = (
    'version = 1\n\n[[package]]\nname = "Demo_Pkg"\nversion = "1.0.0"\n'
    'source = { registry = "https://pypi.org/simple" }\n'
    'sdist = { url = "https://files.example.invalid/demo-1.0.0.tar.gz", hash = "sha256:' + "a" * 64 + '" }\n'
)


@pytest.fixture
def lock(tmp_path: Path) -> Path:
    path = tmp_path / "uv.lock"
    path.write_text(LOCK, encoding="utf-8")
    return path


def test_parse_lock_normalises_registry_packages_and_rejects_unverified_artifacts(lock: Path) -> None:
    assert parse_lock(lock) == (("demo-pkg", "1.0.0"),)
    lock.write_text(LOCK.replace("https://files", "http://files"), encoding="utf-8")
    with pytest.raises(AuditError):
        parse_lock(lock)


def test_acceptance_lines_must_be_exact_justified_and_short_lived() -> None:
    today = dt.date(2026, 9, 13)
    accepted = parse_line(1, "GHSA-aaaa-bbbb demo-pkg expires=2026-10-01 # no fixed release exists yet", today)
    assert accepted is not None and accepted.package == "demo-pkg"
    for bad in ("GHSA-aaaa-bbbb demo-pkg expires=2026-10-01", "GHSA-aaaa-bbbb demo-pkg expires=2027-01-01 # far too long a horizon"):
        with pytest.raises(AuditError):
            parse_line(2, bad, today)


def test_gate_fires_on_an_unaccepted_finding_and_on_a_stale_acceptance(lock: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate, "audit", lambda packages: [("demo-pkg", "1.0.0", "GHSA-aaaa-bbbb", ("1.0.1",))])
    assert gate.main([str(lock)]) == 1
    expiry = (dt.date.today() + dt.timedelta(days=30)).isoformat()
    (lock.parent / ".config").mkdir()
    (lock.parent / ".config" / "security-audit-allow.txt").write_text(f"GHSA-aaaa-bbbb demo-pkg expires={expiry} # upstream fix pending review\n", encoding="utf-8")
    assert gate.main([str(lock)]) == 0
    monkeypatch.setattr(gate, "audit", lambda packages: [])
    assert gate.main([str(lock)]) == 1
