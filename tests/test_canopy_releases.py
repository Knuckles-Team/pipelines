"""Canopy releases view: part progress, manifests and the delivery phase line (PIPE-PAGES-R056)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from scripts.architecture_explorer import releases, sdd  # noqa: E402


def _manifest(rel_id: str, phase: str, roots: list[str]) -> dict:
    return {
        "id": rel_id,
        "name": rel_id,
        "phase": phase,
        "scenario": "S-1",
        "scope": [{"repo": "r", "spec": "FAM", "roots": roots}],
    }


def _rows() -> list[dict]:
    return [
        {"id": "FAM-R001", "status": "VERIFIED", "repo": "r", "family": "fam", "spec_id": "FAM"},
        {"id": "FAM-R002", "status": "SPECIFIED", "repo": "r", "family": "fam", "spec_id": "FAM"},
        {"id": "FAM-R003", "status": "SPECIFIED", "repo": "r", "family": "fam", "spec_id": "FAM"},
    ]


@pytest.mark.spec("PIPE-PAGES-R056.1")
def test_phase_line_in_plan_wins_over_release_phase_and_part_progress_counts() -> None:
    assert sdd.phase_of("# Plan\n\nDelivery phase: P3\n", ["P1"]) == "P3"
    assert sdd.phase_of("# Plan\n\nDelivery phase: P3\n", []) == "P3"
    # The old heading form no longer declares a phase; the release phase is the fallback.
    assert sdd.phase_of("# Plan\n\n## Delivery phase\n\nRows serve P3.\n", ["P2", "P2"]) == "P2"
    assert sdd.phase_of("# Plan\n\nDelivery phase: P9\n", []) == ""
    assert sdd.phase_of("# Plan\n\nno phase\n", []) == ""
    manifests = [_manifest("P1", "P1", ["FAM-R001", "FAM-R002"])]
    node_of = {"FAM-R001": "core.a", "FAM-R002": "core.b", "FAM-R003": "core.b"}
    assert releases.part_progress(manifests, _rows(), node_of) == {
        "P1": [{"node": "core.a", "rows": 1, "verified": 1}, {"node": "core.b", "rows": 1, "verified": 0}]
    }
    view = releases.release_view(manifests, _rows(), None, node_of)
    assert view["releases"][0]["progress"][0]["node"] == "core.a"
    assert view["releases"][0]["manifest"] == "releases/P1.yml"


@pytest.mark.spec("PIPE-PAGES-R056.3")
def test_github_mode_refuses_a_missing_releases_directory(tmp_path: Path) -> None:
    assert releases.load_manifests(tmp_path / "absent") == []  # a local build tolerates it
    with pytest.raises(releases.ReleaseManifestInvalid, match="missing"):
        releases.load_manifests(tmp_path / "absent", required=True)
    shipped = releases.load_manifests(ROOT / "releases", required=True)
    assert [m["id"] for m in shipped] == ["P1", "P2", "P3", "P4", "P5"]


@pytest.mark.spec("PIPE-PAGES-R056.4")
def test_empty_state_explains_manifests_and_bad_phase_fails_the_build(tmp_path: Path) -> None:
    (tmp_path / "bad.yml").write_text(json.dumps({"id": "X", "name": "X", "phase": "P9", "scenario": "S", "scope": []}))
    with pytest.raises(releases.ReleaseManifestInvalid) as err:
        releases.load_manifests(tmp_path)
    assert err.value.code == "release-manifest-invalid"
    (tmp_path / "bad.yml").write_text("{not json")
    with pytest.raises(releases.ReleaseManifestInvalid):
        releases.load_manifests(tmp_path)
    template = (ROOT / "scripts/architecture_explorer/template.html").read_text()
    assert "No release manifests were published." not in template
    assert "releases/<id>.yml" in template and "releases/README.md" in template
