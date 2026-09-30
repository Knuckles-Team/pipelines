"""Tagged authority nodes cannot turn an invalid workflow into a passing receipt."""

import pytest

from pages_fleet_fixtures import fleet_fixture, revise
from pages_fleet_assertions import assert_unverified_receipt, replace_workflow
from scripts.pages_fleet_parity import verify


@pytest.mark.parametrize("old,new", [
    ("uses: ", "uses: !custom "),
    ("uses: ", "uses: !<str> "),
    ("shared_theme_enabled: true", "shared_theme_enabled: !custom true"),
    ("content_source: docs", "content_source: !custom docs"),
    ("jobs:\n", "jobs: !custom\n"),
    ("with:\n", "with: !custom\n"),
    ("pages:\n", "pages: !custom\n"),
    ("jobs:", "!custom jobs:"),
    ("jobs:\n", "!custom\njobs:\n"),
])
def test_tagged_workflow_authority_fails_receipt(tmp_path, capsys, old, new):
    declaration = fleet_fixture(tmp_path)

    changed = replace_workflow(tmp_path, declaration, old, new)
    assert verify(changed, tmp_path)["status"] == "unverified"
    assert_unverified_receipt(tmp_path, changed, capsys)


@pytest.mark.parametrize("enabled", ["true", '"true"', "!!bool true", "!!str true"])
def test_standard_workflow_tags_and_event_key_remain_valid(tmp_path, enabled):
    declaration = fleet_fixture(tmp_path)

    def mutate(target):
        path = target / ".github/workflows/pages.yml"
        text = path.read_text().replace("uses: ", "uses: !!str ")
        text = text.replace("jobs:\n", "jobs: !!map\n").replace("with:\n", "with: !!map\n")
        text = text.replace("shared_theme_enabled: true", f"shared_theme_enabled: {enabled}")
        path.write_text("on: push\n" + text)

    changed = revise(tmp_path, declaration, mutate)
    assert verify(changed, tmp_path)["status"] == "pass"
