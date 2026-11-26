"""Core repositories call the shared Pages workflow with the spec dashboard enabled.

The fixture holds each core repository's Pages caller exactly as it stands on
its main branch, with the commit that last touched it. The predicate is
replayed over those bytes without network access, so a missing, stale or
tampered record fails closed.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
import yaml

FIXTURE = Path(__file__).parent / "fixtures/connector_spec_delivery/core_reference_callers.json"
CORE = {"medulla", "meristem", "arbora", "scion-sdk", "overstory"}
WORKFLOW = "Knuckles-Team/pipelines/.github/workflows/pages_pipeline.yml"
SHA = re.compile(r"^[0-9a-f]{40}$")
REF = re.compile(r"^(main|[0-9a-f]{40})$")


def _evidence() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def calls_with_dashboard(text: str) -> bool:
    """True when some job uses the shared Pages workflow at main (or a full commit) and enables the dashboard."""
    jobs = (yaml.safe_load(text) or {}).get("jobs") or {}
    for job in jobs.values():
        uses = str((job or {}).get("uses") or "")
        name, _, ref = uses.partition("@")
        if (
            name == WORKFLOW
            and REF.match(ref)
            and str(((job or {}).get("with") or {}).get("spec_dashboard_enabled")).lower() == "true"
        ):
            return True
    return False


def test_fixture_is_content_addressed_and_main_bound() -> None:
    repos = _evidence()["repos"]
    assert set(repos) == CORE
    for name, row in repos.items():
        assert SHA.match(row["main_sha"]) and SHA.match(row["last_commit"]), name
        assert row["path"] == ".github/workflows/pages.yml"
        assert row["bytes"] == len(row["content"].encode())
        assert row["sha256"] == hashlib.sha256(row["content"].encode()).hexdigest()


@pytest.mark.spec("PIPE-CONNSPEC-R004")
def test_core_callers_enable_spec_dashboard() -> None:
    repos = _evidence()["repos"]
    assert set(repos) == CORE
    for name, row in repos.items():
        assert calls_with_dashboard(row["content"]), name


@pytest.mark.parametrize(
    "mutate",
    [
        lambda t: t.replace("spec_dashboard_enabled: true", "spec_dashboard_enabled: false"),
        lambda t: t.replace("pages_pipeline.yml@", "other_pipeline.yml@"),
        lambda t: re.sub(r"pages_pipeline\.yml@\S+", "pages_pipeline.yml@feature", t),
    ],
)
def test_a_caller_that_drifts_is_refused(mutate) -> None:
    for row in _evidence()["repos"].values():
        assert not calls_with_dashboard(mutate(row["content"]))
