"""Catalog identities match exact or delimited words, including Unicode boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipelines_hooks.privacy.identity_scan import group_matches
from tests.hooks.conftest import Repo

IDENTITY = "velora"


@pytest.fixture
def catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("AGENT_UTILITIES_PRIVACY_IDENTIFIERS", "fixture-identity-token")
    path = tmp_path / "prohibited-identities.json"
    path.write_text(json.dumps({"version": "1", "identities": [IDENTITY]}), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("velora", True),
        ("MODEL-velora-v2", True),
        ("MODEL_velora_v2", True),
        ("π velora λ", True),
        ("Veloran", False),
        ("VeloraModel", False),
        ("myVeloraTool", False),
        ("Veloraé", False),
        ("Velora\u0301", False),
    ],
)
def test_catalog_identity_requires_unicode_word_boundaries(text: str, expected: bool) -> None:
    assert group_matches(text.encode("utf-8"), (IDENTITY.encode("ascii"),)) is expected


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("MODEL-velora-v2", 1),
        ("π velora λ", 1),
        ("Veloran title", 0),
        ("Veloraé title", 0),
        ("Velora\u0301 title", 0),
    ],
)
def test_privacy_keeps_unicode_title_matches_bounded(repo: Repo, catalog: Path, body: str, expected: int) -> None:
    repo.commit({"docs/title.md": f"{body}\n"})
    assert repo.run("tracked-privacy", "--identity-catalog", str(catalog)) == expected


@pytest.mark.spec("PIPE-GATES-R016.117")
def test_overlong_group_is_scanned_in_overlapping_windows(tmp_path: Path) -> None:
    from pipelines_hooks.privacy.identity_scan import (
        MAX_GROUP_BYTES,
        scan_prohibited_identities,
    )

    blob = tmp_path / "blob.json"
    edge = MAX_GROUP_BYTES - 3
    body = "A" * edge + "-velora-" + "B" * (3 * MAX_GROUP_BYTES)
    blob.write_text('{"data": "' + body + '"}\n', encoding="utf-8")
    clean = tmp_path / "clean.json"
    clean.write_text('{"data": "' + "C" * (3 * MAX_GROUP_BYTES) + '"}\n', encoding="utf-8")

    findings = scan_prohibited_identities(tmp_path, [blob, clean], (IDENTITY.encode("ascii"),))

    assert {finding.path for finding in findings} == {"blob.json"}
