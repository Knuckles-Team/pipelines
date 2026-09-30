"""Source authority, parser ambiguity and receipt boundary checks."""

import json

import pytest

from scripts.pages_fleet_declaration import validate
from scripts.pages_fleet_parity import verify
from pages_fleet_fixtures import consumer_root, fleet_fixture, git, pin, revise


@pytest.fixture
def fleet(tmp_path):
    return tmp_path, fleet_fixture(tmp_path)


@pytest.mark.parametrize("failure", ["dirty", "missing", "symlink"])
def test_pipeline_source_failure_is_explicit(fleet, failure):
    root, declaration = fleet
    pipeline = declaration["pipeline"]
    source = root / pipeline["repository"] / pipeline["revision"]
    path = source / "templates/mkdocs-theme/extra.css"
    if failure == "dirty":
        path.write_text("dirty source")
    elif failure == "missing":
        declaration["pipeline"]["revision"] = "f" * 40
    else:
        path.unlink()
        path.symlink_to("../../../outside")
        pin(source, pipeline)
    result = verify(declaration, root)
    assert result["status"] == "unverified"
    assert len(result["consumers"]) == 6
    assert str(root) not in json.dumps(result)


def test_git_replacement_cannot_change_declared_tree(fleet):
    root, declaration = fleet
    target = consumer_root(root, declaration)
    original = declaration["consumers"][0]["revision"]
    other = declaration["pipeline"]["revision"]
    source = root / declaration["pipeline"]["repository"] / other
    git(target, "fetch", str(source), other)
    git(target, "replace", original, other)
    result = verify(declaration, root)
    assert result["status"] == "pass"
    assert result["consumers"][0]["tree"] == git(target, "--no-replace-objects", "rev-parse", "HEAD^{tree}")


@pytest.mark.parametrize("payload", [
    "jobs: {pages: {}, pages: {}}",
    "jobs: !python/object:danger {}",
    "jobs: {pages: {uses: one, uses: two}}",
])
def test_ambiguous_yaml_never_passes(fleet, payload):
    root, declaration = fleet
    changed = revise(root, declaration, lambda target: (target / ".github/workflows/pages.yml").write_text(payload))
    assert verify(changed, root)["status"] == "unverified"


@pytest.mark.parametrize("field,value", [
    ("content_source", "docs/./nested"), ("content_source", "docs//nested"),
    ("content_source", "/docs"), ("site_url", "https://secret@example.com/"),
    ("site_url", 123), ("shared_theme_enabled", "true"),
])
def test_noncanonical_input_rejected(fleet, field, value):
    _, declaration = fleet
    declaration["consumers"][0][field] = value
    with pytest.raises(ValueError):
        validate(declaration)


def test_fixture_directory_symlink_is_not_a_checkout(fleet):
    root, declaration = fleet
    target = consumer_root(root, declaration)
    original = target.with_name("saved")
    target.rename(original)
    target.symlink_to(original, target_is_directory=True)
    assert verify(declaration, root)["status"] == "unverified"


@pytest.mark.parametrize("failure", ["empty-content", "control-filename"])
def test_workflow_paths_and_empty_inputs_fail_closed(fleet, failure):
    root, declaration = fleet

    def mutate(target):
        path = target / ".github/workflows/pages.yml"
        if failure == "empty-content":
            path.write_text(path.read_text().replace("content_source: pages", 'content_source: ""'))
        else:
            path.with_name("hidden\nworkflow.yml").write_bytes(path.read_bytes())

    changed = revise(root, declaration, mutate, index=1)
    assert verify(changed, root)["status"] == "unverified"
