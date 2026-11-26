"""Canopy releases view: part progress, manifests and the delivery phase line (PIPE-PAGES-R056)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from scripts.architecture_explorer import releases, sdd  # noqa: E402
from canopy_browser import ADGUARD, NEEDS_BROWSER, PREFIX, build_site, drive, manifest, node_of, payload, serve  # noqa: E402


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


R030 = f"{PREFIX}-R030"
MANIFESTS = [manifest("P1", "P1", [R030, f"{PREFIX}-R050"]), manifest("P2", "P2", [f"{ADGUARD}-R002"])]
WAIT = "const wait=(ms)=>new Promise(r=>setTimeout(r,ms));\n"


def _site(monkeypatch, tmp_path: Path) -> Path:
    return build_site(monkeypatch, tmp_path, manifests=MANIFESTS)


@pytest.mark.spec("PIPE-PAGES-R056.2")
@NEEDS_BROWSER
def test_selecting_a_release_dims_other_nodes_and_shows_part_progress(monkeypatch, tmp_path: Path) -> None:
    site = _site(monkeypatch, tmp_path)
    mine, other = node_of(site, R030), node_of(site, f"{ADGUARD}-R002")
    with serve(site) as url:
        out = drive(
            tmp_path,
            url,
            WAIT
            + """
document.getElementById("vrel").click(); await wait(200);
const btn=Array.from(document.querySelectorAll("#panel .bundle button")).find(b=>/P1/.test(b.textContent)); btn.click(); await wait(400);
return {dim:window.__arch.relDim(), mine:window.__arch.relProg(%r), other:window.__arch.relProg(%r), hash:location.hash};
"""
            % (mine, other),
        )
    assert mine not in out["dim"] and other in out["dim"]
    assert out["mine"] == {"node": mine, "rows": 1, "verified": 0} and out["other"] is None
    assert "release=P1" in out["hash"]


@pytest.mark.spec("PIPE-PAGES-R056.5")
@NEEDS_BROWSER
def test_release_card_links_manifest_and_unscheduled_count_matches_rows(monkeypatch, tmp_path: Path) -> None:
    site = _site(monkeypatch, tmp_path)
    data = payload(site)["tree"]
    specs = [s for n in _flat(data) for s in n["specs"]]
    assert data["releases"]["unscheduled"] == sum(1 for s in specs if s["release"] == "unscheduled")
    with serve(site) as url:
        out = drive(
            tmp_path,
            url,
            WAIT
            + """
document.getElementById("vrel").click(); await wait(300);
return {links:Array.from(document.querySelectorAll("#panel .bundle a.src")).map(a=>a.href), eyebrow:document.querySelector("#panel .eyebrow").textContent,
  steps:Array.from(document.querySelectorAll("#panel .bundle .step")).map(s=>s.textContent)};
""",
        )
    assert [link.rsplit("/", 1)[-1] for link in out["links"]] == ["P1.yml", "P2.yml"]
    assert f"{data['releases']['unscheduled']} unscheduled" in out["eyebrow"].replace(",", "")
    assert any("of 1 verified" in s for s in out["steps"])


def _flat(tree: dict):
    yield tree
    for child in tree["children"]:
        yield from _flat(child)


@pytest.mark.spec("PIPE-PAGES-R056.6")
@NEEDS_BROWSER
def test_release_hash_filters_the_map_in_a_browser(monkeypatch, tmp_path: Path) -> None:
    site = _site(monkeypatch, tmp_path)
    mine, other = node_of(site, R030), node_of(site, f"{ADGUARD}-R002")
    with serve(site) as url:
        out = drive(
            tmp_path,
            url + "#release=P1",
            WAIT
            + """
const listed=Array.from(document.querySelectorAll("#specsec li[data-spec]")).map(li=>li.dataset.spec);
return {dim:window.__arch.relDim(), listed, prog:window.__arch.relProg(%r)};
"""
            % mine,
        )
    assert other in out["dim"] and mine not in out["dim"]
    assert sorted(out["listed"]) == sorted([R030, f"{PREFIX}-R050"]) and out["prog"] == {
        "node": mine,
        "rows": 1,
        "verified": 0,
    }
