"""Adversarial offline fleet declarations, overlays and inaccessible assets."""

import copy
import json

import pytest

from scripts.check_five_repo_parity import main
from scripts.pages_fleet_declaration import load, validate
from scripts.pages_fleet_parity import verify
from pages_fleet_fixtures import consumer_root, declaration_file, fleet_fixture, git, revise, workflow


@pytest.fixture
def fleet(tmp_path):
    return tmp_path, fleet_fixture(tmp_path)


@pytest.mark.parametrize("change", ["duplicate", "case-duplicate", "missing", "extra", "version", "traversal", "empty"])
def test_invalid_declaration(fleet, change):
    _, declaration = fleet
    item = declaration["consumers"][0]
    if change in {"duplicate", "case-duplicate"}:
        other = copy.deepcopy(item)
        other["repository"] = other["repository"].upper() if change == "case-duplicate" else other["repository"]
        declaration["consumers"].append(other)
    elif change == "missing":
        del item["revision"]
    elif change == "extra":
        item["overlay"] = "local"
    elif change == "version":
        declaration["schema_version"] = True
    elif change == "traversal":
        item["content_source"] = "../outside"
    else:
        declaration["consumers"] = []
    with pytest.raises(ValueError):
        validate(declaration)


@pytest.mark.parametrize("overlay", ["tracked", "staged", "untracked", "ignored", "assume-unchanged"])
def test_dirty_and_hidden_overlays_never_pass(fleet, overlay):
    root, declaration = fleet
    target = consumer_root(root, declaration)
    asset = target / "docs/stylesheets/extra.css"
    if overlay in {"tracked", "staged", "assume-unchanged"}:
        asset.write_text("modified")
        if overlay == "staged":
            git(target, "add", str(asset))
        if overlay == "assume-unchanged":
            git(target, "update-index", "--assume-unchanged", str(asset))
    else:
        (target / "overlay.css").write_text("overlay")
        if overlay == "ignored":
            (target / ".git/info/exclude").write_text("overlay.css\n")
    result = verify(declaration, root)
    assert result["status"] == "unverified"
    assert result["consumers"][0]["reason"] in {"tree-overlay", "index-flags-unsupported"}
    assert result["consumers"][1]["status"] == "pass"


@pytest.mark.parametrize("failure", ["missing-asset", "symlink-file", "symlink-content", "missing-content", "mkdocs-mismatch"])
def test_unsafe_or_missing_assets_fail_closed(fleet, failure):
    root, declaration = fleet

    def mutate(target):
        asset = target / "docs/stylesheets/extra.css"
        if failure == "missing-asset":
            asset.unlink()
        elif failure == "symlink-file":
            asset.unlink()
            asset.symlink_to("../../../../outside.css")
        elif failure == "symlink-content":
            (target / "docs").rename(target / "saved-docs")
            (target / "docs").symlink_to("../outside")
        elif failure == "missing-content":
            (target / "docs").rename(target / "saved-docs")
        else:
            (target / "mkdocs.yml").write_text("docs_dir: other\n")

    changed = revise(root, declaration, mutate)
    result = verify(changed, root)
    assert result["status"] == "unverified"
    first = result["consumers"][0]
    assert first["reason"] or first["assets"][0]["reason"]


@pytest.mark.parametrize("failure", ["missing-ref", "wrong-head", "missing-pipeline", "tree-id"])
def test_unavailable_exact_ref_has_no_fallback(fleet, failure):
    root, declaration = fleet
    if failure == "missing-pipeline":
        declaration["pipeline"]["revision"] = "0" * 40
    elif failure == "missing-ref":
        declaration["consumers"][0]["revision"] = "0" * 40
    else:
        target = consumer_root(root, declaration)
        if failure == "wrong-head":
            git(target, "checkout", "--orphan", "different")
        else:
            tree = git(target, "rev-parse", "HEAD^{tree}")
            target.rename(target.parent / tree)
            declaration["consumers"][0]["revision"] = tree
    result = verify(declaration, root)
    assert result["status"] == "unverified"


@pytest.mark.parametrize("failure", ["mutable", "wrong-sha", "missing-workflow", "wrong-content", "duplicate-call", "disabled"])
def test_pages_workflow_must_bind_declared_pipeline(fleet, failure):
    root, declaration = fleet

    def mutate(target):
        pipeline = dict(declaration["pipeline"])
        if failure in {"mutable", "wrong-sha"}:
            pipeline["revision"] = "main" if failure == "mutable" else "f" * 40
        workflow(target, pipeline, "pages" if failure == "wrong-content" else "docs")
        path = target / ".github/workflows/pages.yml"
        if failure == "missing-workflow":
            path.unlink()
        elif failure == "duplicate-call":
            path.with_name("duplicate.yml").write_bytes(path.read_bytes())
        elif failure == "disabled":
            path.write_text(path.read_text().replace("enabled: true", "enabled: false"))

    changed = revise(root, declaration, mutate)
    result = verify(changed, root)
    assert result["status"] == "unverified"
    assert result["consumers"][0]["reason"]


def test_duplicate_json_and_untracked_declaration_rejected(tmp_path, capsys):
    path = declaration_file(tmp_path / "declaration", {})
    path.write_text('{"schema_version":1,"schema_version":1}')
    git(path.parent, "add", ".")
    git(path.parent, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "-qm", "duplicate")
    with pytest.raises(ValueError, match="duplicate-json-key"):
        load(path)
    untracked = path.with_name("untracked.json")
    untracked.write_text("{}")
    assert main(["--declaration", str(untracked), "--fixtures", str(tmp_path)]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "unverified"
    assert str(tmp_path) not in json.dumps(output)
