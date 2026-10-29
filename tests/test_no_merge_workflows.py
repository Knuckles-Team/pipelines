"""Auto-merge is GitHub's native setting, enabled per PR by its author; no workflow merges (PIPE-GATES-R016.116)."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
WORKFLOWS = [*(ROOT / ".github/workflows").glob("*.y*ml"), *(ROOT / "templates/workflows").glob("*.y*ml")]


@pytest.mark.spec("PIPE-GATES-R016.116")
def test_no_auto_merge_workflow_or_merge_token() -> None:
    names = {path.name for path in WORKFLOWS}
    assert not {name for name in names if name.startswith("auto_merge")}
    for path in WORKFLOWS:
        text = path.read_text(encoding="utf-8")
        assert "GIT_TOKEN" not in text, path
        assert "pull_request_target" not in text.split("#")[0], path


@pytest.mark.spec("PIPE-GATES-R016.116")
def test_ci_template_has_the_single_required_check() -> None:
    text = (ROOT / "templates/workflows/ci.yml").read_text(encoding="utf-8")
    assert "name: CI required" in text
