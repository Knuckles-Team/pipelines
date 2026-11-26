"""The bundle plan document and its publication to arbora (PIPE-RELEASE-R025.4, R025.5)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from scripts import release_plan as rp  # noqa: E402
from scripts import release_scope as rs  # noqa: E402


def two_project_rows() -> dict[str, dict]:
    def row(rid: str, repo: str, deps: list[str], status: str) -> dict:
        return {
            "id": rid,
            "repo": repo,
            "spec_id": rid.rsplit("-R", 1)[0],
            "family": "f",
            "depends_on": deps,
            "status": status,
        }

    return {
        "P-A-R001": row("P-A-R001", "engine", [], "VERIFIED"),
        "P-A-R002": row("P-A-R002", "engine", ["P-A-R001"], "VERIFIED"),
        "Q-B-R001": row("Q-B-R001", "door", ["P-A-R002"], "LANDED"),
    }


# spec: PIPE-RELEASE-R025.4
def test_plan_is_deterministic_and_lists_rows_order_scenario_and_open_tasks(tmp_path: Path, capsys) -> None:
    rows = two_project_rows()
    doc = rs.manifest("P1", ["Q-B-R001"], rows)
    plan = rp.render_plan(doc, rows)
    assert plan == {
        "release": "P1",
        "scenario": "ARBORA-ACCEPTANCE-R006.1",
        "rows_by_repo": {"door": ["Q-B-R001"], "engine": ["P-A-R001", "P-A-R002"]},
        "closure": ["P-A-R001", "P-A-R002", "Q-B-R001"],
        "train_order": ["engine", "door"],
        "open_tasks": ["Q-B-R001"],
    }
    shuffled = dict(reversed(list(rows.items())))
    assert rp.plan_bytes(rp.render_plan(doc, shuffled)) == rp.plan_bytes(plan)
    releases = tmp_path / "releases"
    releases.mkdir()
    (releases / "P1.yml").write_text(json.dumps(doc))
    before = sorted(p.name for p in tmp_path.rglob("*"))
    from unittest import mock

    with mock.patch.object(rs, "all_rows", return_value=rows):
        assert rp.main(["--workspace", str(tmp_path), "--release", "P1", "--releases", str(releases)]) == 0
    assert capsys.readouterr().out.encode() == rp.plan_bytes(plan)
    assert sorted(p.name for p in tmp_path.rglob("*")) == before  # no committed or written file


# spec: PIPE-RELEASE-R025.5
def test_publish_posts_bundle_facts_and_plan_and_skips_without_endpoint() -> None:
    rows = two_project_rows()
    plan = rp.render_plan(rs.manifest("P1", ["Q-B-R001"], rows), rows)
    facts = rp.facts_of(plan, rows)
    assert facts["ReleaseBundle"] == [{"id": "P1", "scenario": "ARBORA-ACCEPTANCE-R006.1"}]
    assert {"row": "Q-B-R001", "bundle": "P1"} in facts["inBundle"]
    assert facts["dependsOn"] == [{"row": "P-A-R002", "on": "P-A-R001"}, {"row": "Q-B-R001", "on": "P-A-R002"}]
    posted: list[tuple[str, dict]] = []
    message = rp.publish_plan(
        facts, plan, "http://127.0.0.1:1/ops", lambda url, body: posted.append((url, body)) or 200
    )
    assert message == "published P1 (HTTP 200)"
    url, body = posted[0]
    assert body["op"].startswith("source.") and body["params"] == {"facts": facts, "plan": plan}
    assert rp.publish_plan(facts, plan, "", lambda *_: 1 / 0) == "publish skipped: no endpoint set"
