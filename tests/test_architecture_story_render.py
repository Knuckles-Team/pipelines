"""Synthetic same-build renderer contracts; no frozen study files or network."""

from copy import deepcopy
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from scripts.architecture_explorer.story_build import seal_chart  # noqa: E402
from scripts.architecture_explorer.story_render import prepare_models, render_story  # noqa: E402

pytestmark = pytest.mark.spec("PIPE-PAGES-R042")


def fixture():
    repo, commit, built = "R_TEST", "a" * 40, "2026-10-26T14:00:00Z"
    ids = ["PIPE-TEST-R001", "PIPE-TEST-R002"]
    keys = [repo + ":" + rid for rid in ids]
    rows = {}
    public = []
    for index, (rid, key) in enumerate(zip(ids, keys)):
        provenance = {
            "repository": "Knuckles-Team/pipelines",
            "commit": commit,
            "path": "specs/demo/requirements.md",
            "fragment": rid,
        }
        title = ["First requirement", "Second requirement"][index]
        rows[key] = {
            "key": key,
            "id": rid,
            "repositoryId": repo,
            "title": title,
            "family": "demo",
            "status": "SPECIFIED",
            "functional": True,
            "rollup": False,
            "provenance": provenance,
            "sourceEvidence": {"rollupOf": []},
            "dependencies": {"keys": [] if index == 0 else [keys[0]], "provenance": provenance},
            "priority": {
                "state": "scored",
                "value": 2 if index == 0 else 0,
                "formulaVersion": "goal-weighted/1",
                "inputs": {"openDependents": 1 if index == 0 else 0, "competencyQuestions": [], "functionalFactor": 1},
            },
            "readiness": "ready" if index == 0 else "blocked",
        }
        public.append({"id": rid, "repo": "pipelines", "family": "demo", "title": title, "status": "SPECIFIED"})
    chart = {
        "schema": "architecture-source-chart/1",
        "scope": {
            "kind": "selected-family-prerequisite-closure",
            "capturedRowCount": 2,
            "excludedDependencyGaps": [],
            "repositories": [
                {"repositoryId": repo, "fullName": "Knuckles-Team/pipelines", "commit": commit, "families": ["demo"]}
            ],
            "scoreRowCount": 2,
            "evidenceOnlyRowCount": 0,
            "selectedFamilyKeys": [repo + ":demo"],
            "selectedRowKeys": keys,
            "prerequisiteClosureRowKeys": keys,
            "fleetComplete": False,
        },
        "families": [
            {
                "key": repo + ":demo",
                "rowKeys": keys,
                "statusCounts": {"VERIFIED": 0, "LANDED": 0, "SPECIFIED": 2, "RETIRED": 0},
                "readyRowKeys": [keys[0]],
                "blockedRowKeys": [keys[1]],
            }
        ],
        "rows": rows,
        "evidenceRows": {},
        "dependencyCycles": [],
        "activity": {"state": "not_collected"},
        "modelMapping": {"state": "not_qualified"},
    }
    chart = seal_chart(
        chart,
        built_at=built,
        snapshots=[SimpleNamespace(repo="pipelines", slug="pipelines", head=commit[:10], error=None)],
    )
    tree = {
        "id": "root",
        "specs": [],
        "children": [{"id": "webui", "specs": public, "children": []}],
        "sourceChart": chart,
    }
    meta = {
        "built_at": built,
        "rows": 2,
        "nodes": 2,
        "heads": {"pipelines": commit[:10]},
        "slugs": {"pipelines": "pipelines"},
    }
    return {"tree": tree, "meta": meta}


def test_rebuild_models_and_source_scope_use_same_dynamic_receipt():
    payload = fixture()
    models = prepare_models(payload, require_source=True)
    assert models["evidence"]["root"]["total"] == 2
    assert models["evidence"]["webui"]["familyCount"] == 1
    view = models["sourceViews"]["webui"]
    assert view["scope"]["freeze"] == payload["meta"]["built_at"]
    assert view["scope"]["fleetComplete"] is False
    assert view["scope"]["modelMapping"] == "not_qualified"
    assert view["activity"] is None
    assert len(view["graph"]["edges"]) == 1
    script = render_story(payload["tree"], payload["meta"])
    assert payload["meta"]["built_at"] in script
    assert "Frozen 26 Oct 02:31" not in script
    subprocess.run(["node", "--check"], input=script, text=True, check=True, capture_output=True)


def test_evidence_only_default_does_not_fabricate_source_views():
    payload = fixture()
    del payload["tree"]["sourceChart"]
    assert prepare_models(payload)["sourceViews"] == {}
    with pytest.raises(ValueError, match="required rebuild source"):
        prepare_models(payload, require_source=True)


@pytest.mark.parametrize("field", ["timestamp", "digest", "heads", "scope", "public_title", "public_status", "host"])
def test_source_mismatch_fails_before_renderer_output(field):
    payload = deepcopy(fixture())
    chart = payload["tree"]["sourceChart"]
    if field == "timestamp":
        chart["buildReceipt"]["builtAt"] = "2026-01-01T00:00:00Z"
    elif field == "digest":
        chart["buildReceipt"]["sourceChartSha256"] = "0" * 64
    elif field == "heads":
        payload["meta"]["heads"]["pipelines"] = "0" * 10
    elif field == "scope":
        chart["buildReceipt"]["sourceScope"] = []
    elif field == "host":
        payload["tree"]["children"][0]["id"] = "different-host"
    else:
        row = payload["tree"]["children"][0]["specs"][0]
        row["title" if field == "public_title" else "status"] = "changed"
    with pytest.raises((ValueError, KeyError, subprocess.CalledProcessError)):
        render_story(payload["tree"], payload["meta"])


def test_six_positive_rows_keep_full_denominator_and_accessible_omissions():
    from scripts.architecture_explorer import story_render

    path = Path(story_render.__file__).with_name("story_canvas.js")
    js = r"""
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');const sandbox={module:{exports:{}},Intl};vm.createContext(sandbox);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),sandbox);const {richLayout}=sandbox.module.exports;
const refs={};for(let i=0;i<5;i++){const key='R:TEST-'+i;refs[key]={key,id:'TEST-'+i,title:'Source requirement '+i,rollupOf:[],readiness:i?'blocked':'ready',priority:{value:6-i},url:'https://github.com/Knuckles-Team/pipelines/blob/'+ 'a'.repeat(40)+'/specs/demo/requirements.md',provenance:{fragment:'TEST-'+i}};}
const view={scope:{freeze:'2026-01-02T03:04:05Z'},scopeLabel:'Synthetic scope',accessibility:'Selected scope only.',priorities:Object.values(refs),priorityScale:6,priorityCounts:{positiveOmitted:1,zeroScore:0},refs};
for(const width of [280,460]){const l=richLayout('priority',view,width,(t,s)=>Array.from(t).length*s*.52);assert(l);const shown=width<420?2:5;assert(l.ops.some(o=>o.text?.includes(shown+' of 6 positive rows')));assert(l.accessibility.includes((6-shown)+' omitted'));assert(l.ops.some(o=>o.text?.includes('2026-01-02 03:04')));for(const op of l.ops.filter(o=>o.type==='text'))assert(op.size>=11&&op.x>=0&&op.x+op.width<=width+.01);}
const huge=structuredClone(view);huge.priorityScale=Number.MAX_SAFE_INTEGER;huge.priorities[0].priority.value=Number.MAX_SAFE_INTEGER;assert.equal(richLayout('priority',huge,280,(t,s)=>Array.from(t).length*s*.52),null,'defer a complete oversized number rather than shift it across its bar');
"""
    subprocess.run(["node", "-e", js, str(path)], check=True, capture_output=True, text=True)


def test_actual_glyph_overhang_is_placed_inside_unchanged_module_bounds():
    from scripts.architecture_explorer import story_render

    path = Path(story_render.__file__).with_name("story_canvas.js")
    js = r"""
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const stack=[],ctx={font:'400 11px Inter',save(){stack.push(this.font)},restore(){this.font=stack.pop()},measureText(t){const w=Array.from(t).length*Number(this.font.match(/(\d+)px/)[1])*.52;return {width:w,actualBoundingBoxLeft:1,actualBoundingBoxRight:w+.104}}};
const c={module:{exports:{}},Intl,ctx,C:{body:'Inter'},fmt:n=>String(n),ST:['VERIFIED','LANDED','SPECIFIED','RETIRED']};vm.createContext(c);vm.runInContext(fs.readFileSync(process.argv[1],'utf8')+';this.familyLayout=storyLayout;',c);
const groups=[{key:'r:one',label:'Family one',total:735,counts:{VERIFIED:700,LANDED:30,SPECIFIED:5,RETIRED:0}},{key:'r:two',label:'Family two',total:8,counts:{VERIFIED:0,LANDED:0,SPECIFIED:8,RETIRED:0}}];
const l=c.familyLayout('comparison',{total:743,familyCount:2,takeaway:null},groups);assert(l);assert.equal(l.width,280);const count=l.ops.find(o=>o.text==='735 / 743');assert(count);for(const o of l.ops.filter(o=>o.type==='text'))assert(o.x>=1&&o.x+o.width+.104<=280.000001);assert(count.x+count.width+.104<=280.000001);
"""
    subprocess.run(["node", "-e", js, str(path)], check=True, capture_output=True, text=True)


def test_evidence_fills_share_native_progress_tokens_not_text_colors():
    from scripts.architecture_explorer import story_render

    path = Path(story_render.__file__).with_name("story_canvas.js")
    js = r"""
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const c={module:{exports:{}},Intl,C:{st:{VERIFIED:'text-color'},progress:{VERIFIED:'semantic-fill'}}};vm.createContext(c);vm.runInContext(fs.readFileSync(process.argv[1],'utf8')+';this.palette=storyBandColors;',c);
assert.equal(c.palette('comparison').VERIFIED,'semantic-fill');assert.equal(c.palette('concentration').VERIFIED,'semantic-fill');assert.equal(c.palette('priority').VERIFIED,'text-color');assert.equal(c.palette('frontier').VERIFIED,'text-color');
"""
    subprocess.run(["node", "-e", js, str(path)], check=True, capture_output=True, text=True)
