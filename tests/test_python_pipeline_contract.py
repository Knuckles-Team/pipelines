"""Focused contracts for the reusable Python release workflow."""

from __future__ import annotations

from pathlib import Path


WORKFLOW = Path(__file__).parents[1] / ".github/workflows/python_pipeline.yml"


def test_release_body_has_an_unambiguous_commit_identity() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "uv pip install -r requirements.txt twine" in text
    assert 'LATEST_COMMIT=$(git rev-parse --verify HEAD)' in text
    assert 'COMMIT_MESSAGE=$(git log -1 --format=%B "$LATEST_COMMIT"' in text
    assert 'echo "LATEST_COMMIT=$LATEST_COMMIT"' in text
    assert "Commit: ${{ env.LATEST_COMMIT }}" in text


def test_release_metadata_does_not_depend_on_an_undefined_tag_variable() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "if [[ $TAG" not in text
    assert "CURRENT_COMMIT" not in text
    assert "CURRENT_RELEASE" not in text
