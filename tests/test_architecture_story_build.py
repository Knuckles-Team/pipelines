"""Same-build source capture is pinned, bounded, and cannot degrade to stale charts."""

from copy import deepcopy
import base64
import hashlib
import json
from pathlib import Path
import sys
import urllib.error

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from scripts.architecture_explorer import story_build as build
from scripts.architecture_explorer.story_contract import ContractError

pytestmark = pytest.mark.spec("PIPE-PAGES-R042")
SHA, TREE = "a" * 40, "b" * 40
ENTRY = {"name": "pipelines", "slug": "pipelines", "sha": SHA, "kind": "core"}
A, B = "PIPE-DEMO-R001", "PIPE-DEMO-R002"


DEMO_STATUS = {
    "schema_version": 2,
    "owner_repo": "pipelines",
    "delivery_state": "SPECIFIED",
    "requirement_ids": [A, B],
    "spec_id": "PIPE-DEMO",
    "requirements": [
        {"id": r, "title": title, "delivery_state": "SPECIFIED", "landed_in": [], "verified_by": []}
        for r, title in [(A, "First"), (B, "Second")]
    ],
}


@pytest.fixture(autouse=True)
def computed_status(monkeypatch):
    """Status is computed from a clone at the frozen commit; the fake API has no clone to compute from."""
    monkeypatch.setattr(build, "STATUS_SOURCE", lambda url, commit: {"specs/demo/status.json": deepcopy(DEMO_STATUS)})


def fake_api():
    docs = {
        "specs/demo/requirements.md": f"| `{A}` | **First**. | tests |\n| `{B}` | **Second**. Depends-on: `{A}`. | tests |\n",
        "specs/demo/plan.md": "# Exact frozen plan",
    }
    base = build.API + "pipelines"
    entries, responses = (
        [],
        {
            base: {"full_name": "Knuckles-Team/pipelines", "node_id": "R_1"},
            base + "/git/commits/" + SHA: {"sha": SHA, "tree": {"sha": TREE}},
        },
    )
    for path, text in docs.items():
        raw = text.encode()
        oid = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": oid})
        responses[base + "/git/blobs/" + oid] = {
            "sha": oid,
            "encoding": "base64",
            "size": len(raw),
            "content": base64.b64encode(raw).decode(),
        }
    responses[base + "/git/trees/" + TREE + "?recursive=1"] = {"sha": TREE, "truncated": False, "tree": entries}
    calls = []

    def request(url):
        calls.append(url)
        return deepcopy(responses[url])

    return responses, calls, request


def test_same_capture_drives_details_public_rows_chart_and_receipt(monkeypatch):
    _, calls, request = fake_api()
    monkeypatch.setattr(build, "load_all", lambda entries, mode, workspace: [])
    snaps, chart = build.load_build_sources([ENTRY], "github", None, {"pipelines": ["demo"]}, token="", request=request)
    assert len(calls) == len(set(calls)) == 5  # status is computed, not fetched
    assert snaps[0].docs["demo"]["plan.md"] == "# Exact frozen plan"
    assert len(snaps[0].rows) == chart["scope"]["scoreRowCount"] == 2
    assert chart["scope"]["repositories"][0]["commit"] == SHA
    prior = json.dumps(chart, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    result = build.seal_chart(chart, built_at="2026-10-26T14:00:00Z", snapshots=snaps)
    assert result["buildReceipt"]["sourceChartSha256"] == hashlib.sha256(prior).hexdigest()
    assert result["buildReceipt"]["publicHeads"] == {"pipelines": SHA[:10]}
    assert result["activity"] == {"state": "not_collected"}
    with pytest.raises(ContractError, match="already sealed"):
        build.seal_chart(chart, built_at="2026-10-26T14:01:00Z", snapshots=snaps)


@pytest.mark.parametrize(
    "failure",
    ["identity", "commit", "tree", "truncated", "symlink", "blob_sha", "blob_bytes", "size", "duplicate_path"],
)
def test_untrusted_capture_refused(failure):
    responses, calls, request = fake_api()
    base = build.API + "pipelines"
    tree = responses[base + "/git/trees/" + TREE + "?recursive=1"]
    blob = responses[base + "/git/blobs/" + tree["tree"][0]["sha"]]
    if failure == "identity":
        responses[base]["full_name"] = "Other/pipelines"
    elif failure == "commit":
        responses[base + "/git/commits/" + SHA]["sha"] = "c" * 40
    elif failure == "tree":
        tree["sha"] = "c" * 40
    elif failure == "truncated":
        tree["truncated"] = True
    elif failure == "symlink":
        tree["tree"][0]["mode"] = "120000"
    elif failure == "blob_sha":
        blob["sha"] = "c" * 40
    elif failure == "blob_bytes":
        blob["content"] = base64.b64encode(b"x" * blob["size"]).decode()
    elif failure == "size":
        blob["size"] = True
    elif failure == "duplicate_path":
        tree["tree"].append(tree["tree"][0])
    with pytest.raises(ContractError):
        build.capture_repository(ENTRY, request)
    assert len(calls) <= 6


def test_config_outside_scan_fails_before_requests():
    _, calls, request = fake_api()
    with pytest.raises(ContractError, match="outside frozen scan"):
        build.load_build_sources([ENTRY], "github", None, {"other": ["demo"]}, token="", request=request)
    assert calls == []


def test_public_row_parity_failure_prevents_other_fleet_load(monkeypatch):
    _, _, request = fake_api()
    original = build.rows_for

    def changed(*args):
        rows = original(*args)
        rows[0]["status"] = "LANDED"
        return rows

    monkeypatch.setattr(build, "rows_for", changed)
    monkeypatch.setattr(build, "load_all", lambda *args: pytest.fail("should fail before remaining fleet load"))
    with pytest.raises(ContractError, match="parity"):
        build.load_build_sources([ENTRY], "github", None, {"pipelines": ["demo"]}, token="", request=request)


def test_transport_denial_no_fallback_or_retry(monkeypatch):
    class Opener:
        calls = 0

        def open(self, req, timeout):
            self.calls += 1
            assert req.get_header("Authorization") == "Bearer existing"
            raise urllib.error.HTTPError(req.full_url, 403, "private detail", {}, None)

    opener = Opener()
    monkeypatch.setattr(build.urllib.request, "build_opener", lambda *_: opener)
    request = build.source_transport("existing")
    with pytest.raises(ContractError, match="access denied") as exc:
        request(build.API + "pipelines")
    assert "private detail" not in str(exc.value) and "existing" not in str(exc.value)
    assert opener.calls == 1
    with pytest.raises(ContractError, match="unexpected source endpoint"):
        request("https://apiXgithubXcom/repos/Knuckles-Team/pipelines")
    assert opener.calls == 1


def test_transport_request_cap_and_existing_token(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, _):
            return b"{}"

    class Opener:
        calls = 0

        def open(self, *_args, **_kwargs):
            self.calls += 1
            return Response()

    opener = Opener()
    monkeypatch.setattr(build.urllib.request, "build_opener", lambda *_: opener)
    with pytest.raises(ContractError):
        build.source_transport("")
    request = build.source_transport("existing", max_requests=1)
    assert request(build.API + "pipelines") == {}
    with pytest.raises(ContractError, match="budget"):
        request(build.API + "pipelines")
    assert opener.calls == 1


def test_receipt_rejects_stale_public_snapshot(monkeypatch):
    _, _, request = fake_api()
    monkeypatch.setattr(build, "load_all", lambda *args: [])
    snaps, chart = build.load_build_sources([ENTRY], "github", None, {"pipelines": ["demo"]}, token="", request=request)
    snaps[0].head = "old-head"
    with pytest.raises(ContractError, match="commit receipt mismatch"):
        build.seal_chart(chart, built_at="2026-10-26T14:00:00Z", snapshots=snaps)
    assert "buildReceipt" not in chart


def setup_cli(monkeypatch, tmp_path):
    from scripts.architecture_explorer import build as explorer

    (tmp_path / "model.json").write_text(
        json.dumps(
            {
                "id": "root",
                "label": "Pipelines",
                "desc": "Fixture scope",
                "repo": "pipelines",
                "fam": ["*"],
                "children": [],
                "unmapped_allow": [],
            }
        )
    )
    (tmp_path / "registry.json").write_text(
        json.dumps({"repositories": [ENTRY], "owner": "Knuckles-Team", "pages_node": {"pipelines": "root"}})
    )
    config = tmp_path / "source-families.json"
    config.write_text(json.dumps({"pipelines": ["demo"]}))
    monkeypatch.setattr(explorer, "HERE", tmp_path)
    monkeypatch.setattr(explorer, "scan_set", lambda *_: [ENTRY])
    monkeypatch.setattr(explorer, "run_layout", lambda *_: {})
    monkeypatch.setattr(explorer, "render", lambda data, meta: json.dumps(data))
    monkeypatch.setattr(build, "load_all", lambda *_: [])
    _, _, request = fake_api()
    monkeypatch.setattr(build, "source_transport", lambda *_: request)
    return explorer, config


def test_actual_build_cli_receipt_and_same_capture_details(monkeypatch, tmp_path):
    explorer, config = setup_cli(monkeypatch, tmp_path)
    output = tmp_path / "site" / "index.html"
    tree = tmp_path / "tree.json"
    assert (
        explorer.main(
            ["--mode", "github", "--source-families", str(config), "--page", str(output), "--tree", str(tree)]
        )
        == 0
    )
    data = json.loads(tree.read_text())
    chart = data["tree"]["sourceChart"]
    assert chart["buildReceipt"]["builtAt"] == data["meta"]["built_at"]
    assert chart["buildReceipt"]["publicHeads"] == data["meta"]["heads"]
    assert len(data["tree"]["specs"]) == chart["scope"]["scoreRowCount"] == 2
    assert output.exists() and list((output.parent / "spec-details").rglob("*.json"))


def test_actual_build_failure_leaves_existing_bundle_untouched(monkeypatch, tmp_path):
    explorer, config = setup_cli(monkeypatch, tmp_path)
    output = tmp_path / "site" / "index.html"
    output.parent.mkdir()
    output.write_text("previous page")
    details = output.parent / "spec-details"
    details.mkdir()
    old = details / "old.json"
    old.write_text("previous details")
    tree = tmp_path / "tree.json"
    tree.write_text("previous tree")

    def denied(*_):
        raise ContractError("access denied; stopped")

    monkeypatch.setattr(build, "source_transport", lambda *_: denied)
    with pytest.raises(ContractError, match="access denied"):
        explorer.main(
            ["--mode", "github", "--source-families", str(config), "--page", str(output), "--tree", str(tree)]
        )
    assert output.read_text() == "previous page"
    assert old.read_text() == "previous details"
    assert tree.read_text() == "previous tree"


@pytest.mark.parametrize("text", ["null", "[]", "{}", '{"pipelines":["demo"],"pipelines":[]}'])
def test_explicit_bad_cli_config_cannot_downgrade_to_legacy(monkeypatch, tmp_path, text):
    explorer, config = setup_cli(monkeypatch, tmp_path)
    config.write_text(text)
    output = tmp_path / "index.html"
    output.write_text("previous")
    monkeypatch.setattr(explorer, "scan_set", lambda *_: pytest.fail("invalid config must fail before scan"))
    with pytest.raises(ContractError):
        explorer.main(["--mode", "github", "--source-families", str(config), "--page", str(output)])
    assert output.read_text() == "previous"


def test_redirect_cannot_silently_ignore_explicit_source_capture(monkeypatch, tmp_path):
    explorer, config = setup_cli(monkeypatch, tmp_path)
    output = tmp_path / "index.html"
    output.write_text("previous")
    with pytest.raises(SystemExit):
        explorer.main(["--redirect", "--source-families", str(config), "--page", str(output)])
    assert output.read_text() == "previous"


def test_digest_encoding_keeps_unicode_values_but_rejects_unicode_keys():
    assert (
        build.canonical_chart_bytes({"title": "Résumé 🌳", "a": [1, True]})
        == '{"a":[1,true],"title":"Résumé 🌳"}'.encode()
    )
    with pytest.raises(ContractError, match="non-ASCII chart key"):
        build.canonical_chart_bytes({"rows": {"é": {}}})


@pytest.mark.parametrize("mutation", [None, "digest", "time", "heads", "scope", "slugs", "absent"])
def test_python_receipt_verification_before_javascript(monkeypatch, mutation):
    _, _, request = fake_api()
    monkeypatch.setattr(build, "load_all", lambda *args: [])
    snaps, chart = build.load_build_sources([ENTRY], "github", None, {"pipelines": ["demo"]}, token="", request=request)
    now = "2026-10-26T14:00:00Z"
    build.seal_chart(chart, built_at=now, snapshots=snaps)
    heads, slugs = {"pipelines": SHA[:10]}, {"pipelines": "pipelines"}
    if mutation == "digest":
        chart["rows"]["R_1:" + A]["priority"]["value"] += 1
    elif mutation == "time":
        now = "2026-10-26T15:00:00Z"
    elif mutation == "heads":
        heads["pipelines"] = "c" * 10
    elif mutation == "scope":
        chart["buildReceipt"]["sourceScope"] = []
    elif mutation == "slugs":
        slugs["pipelines"] = "other"
    elif mutation == "absent":
        del chart["buildReceipt"]
    if mutation:
        with pytest.raises(ContractError):
            build.verify_chart_receipt(chart, built_at=now, public_heads=heads, public_slugs=slugs)
    else:
        assert build.verify_chart_receipt(chart, built_at=now, public_heads=heads, public_slugs=slugs) is chart


def test_candidate_config_is_explicit_selected_families_and_closure_only():
    config = Path(__file__).parents[1] / "scripts/architecture_explorer/source-families.json"
    assert build.read_family_config(config) == {
        "overstory": ["arbora-api-consumer", "arbora-app-surface"],
        "arbora": [],
    }


@pytest.mark.parametrize(
    ("path", "captured"),
    [
        ("specs/demo/requirements.md", True),
        ("specs/demo/checklists/requirements.md", True),
        ("specs/demo/contracts/api.yml", True),
        ("specs/demo/checklists/deep/requirements.md", False),
        ("specs/demo/notes/requirements.md", False),
        ("specs/demo/contracts/image.png", False),
    ],
)
def test_capture_covers_every_document_the_explorer_reads(path, captured):
    assert build.is_source_document(path) is captured
