"""Every `needs:` entry of every shared workflow names a job defined in that workflow.

A dangling `needs:` makes GitHub reject the whole workflow file at startup, so no job runs and no check reports.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

WORKFLOWS = sorted((Path(__file__).parents[1] / ".github/workflows").glob("*.yml"))


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_every_needs_entry_names_a_defined_job(path: Path) -> None:
    jobs = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("jobs") or {}
    for name, job in jobs.items():
        needs = job.get("needs") or []
        for target in [needs] if isinstance(needs, str) else needs:
            assert target in jobs, f"{path.name}: job {name} needs undefined job {target}"
