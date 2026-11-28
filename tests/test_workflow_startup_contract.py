"""A shared workflow must start in every caller: no dangling `needs`, no permission its callers withhold."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

WORKFLOW_DIR = Path(__file__).parents[1] / ".github/workflows"
WORKFLOWS = sorted(WORKFLOW_DIR.glob("*.yml"))
#: Jobs that publish or deploy and are reached only from callers that grant the write scope in the same file.
#: `npm` requests `id-token: write` for trusted publishing (PIPE-RELEASE-R033); its callers grant it beside the call.
PUBLISHING_JOBS = {
    "auto-tag", "deploy", "npm", "publish", "publish-pages", "publish-pypi", "publish-release", "services",
}  # fmt: skip
CALLER_GRANT = {"contents": "read"}


def _called(path: Path) -> dict:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    triggers = doc.get(True) or doc.get("on") or {}
    return doc if isinstance(triggers, dict) and "workflow_call" in triggers else {}


# spec: PIPE-GATES-R105
@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_every_needs_entry_names_a_defined_job(path: Path) -> None:
    jobs = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("jobs") or {}
    for name, job in jobs.items():
        needs = job.get("needs") or []
        for target in [needs] if isinstance(needs, str) else needs:
            assert target in jobs, f"{path.name}: job {name} needs undefined job {target}"


# spec: PIPE-GATES-R105
@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_a_nested_job_requests_no_permission_its_callers_withhold(path: Path) -> None:
    for name, job in (_called(path).get("jobs") or {}).items():
        permissions = job.get("permissions")
        if name in PUBLISHING_JOBS or not isinstance(permissions, dict):
            continue
        for scope, level in permissions.items():
            assert CALLER_GRANT.get(scope) == level, (
                f"{path.name}: job {name} requests {scope}: {level}, which a caller that grants "
                "only `contents: read` withholds, so GitHub would refuse to start the caller"
            )
