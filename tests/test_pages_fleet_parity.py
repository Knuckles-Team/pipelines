"""PIPE-EH-428 positive evidence and digest/revision negative fixtures."""

import copy
import json

import pytest

from scripts.check_five_repo_parity import main
from scripts.pages_fleet_declaration import canonical, digest, validate
from scripts.pages_fleet_parity import verify
from scripts.pages_fleet_receipt import receipt, render_receipt
from scripts.sync_mkdocs_theme import THEME_FILES
from pages_fleet_fixtures import consumer_root, declaration_file, fleet_fixture, git, revise


@pytest.fixture
def fleet(tmp_path):
    return tmp_path, fleet_fixture(tmp_path)


def test_six_exact_refs_stable_receipts_and_no_mutation(fleet):
    root, declaration = fleet
    before = {str(path): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    first = verify(declaration, root)
    second = verify(declaration, root)
    assert first == second
    assert first["status"] == "pass"
    assert first["public_source_verified"] is False
    assert first["fleet_sha256"] == digest(canonical(declaration).encode())
    assert len(first["consumers"]) == 6
    for index, row in enumerate(first["consumers"]):
        assert row["tree"] == git(consumer_root(root, declaration, index), "rev-parse", "HEAD^{tree}")
        assert row["commit"] == declaration["consumers"][index]["revision"]
        assert len(row["assets"]) == len(THEME_FILES)
        assert all(asset["expected_sha256"] == asset["actual_sha256"] for asset in row["assets"])
        assert row["assets"][0]["expected_sha256"] == digest(b"canonical extra.css\n")
    assert before == {str(path): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    frozen = receipt(first, generated_at="2026-01-01T00:00:00Z")
    assert canonical(frozen) == canonical(receipt(second, generated_at="2026-01-01T00:00:00Z"))
    assert "2026-01-01" in render_receipt(frozen)
    assert "https://github.com/example/consumer-5/commit/" in render_receipt(frozen)


def test_variable_fleet_without_code_change(fleet):
    root, declaration = fleet
    declaration["consumers"] = declaration["consumers"][:2]
    assert len(verify(declaration, root)["consumers"]) == 2


def test_changed_byte_nonzero_and_historical_receipt(fleet, tmp_path, capsys):
    root, declaration = fleet
    old = receipt(verify(declaration, root))
    unchanged_old = copy.deepcopy(old)
    changed = revise(root, declaration, lambda path: (path / "docs/stylesheets/extra.css").write_bytes(b"changed"))
    result = verify(changed, root)
    asset = result["consumers"][0]["assets"][0]
    assert result["status"] == "mismatch"
    assert asset["path"] == "docs/stylesheets/extra.css"
    assert asset["reason"] == "digest-mismatch"
    assert asset["actual_sha256"] == digest(b"changed")
    assert receipt(result, previous=old)["previous"]["status"] == "historical"
    assert old == unchanged_old
    path = declaration_file(tmp_path / "declaration", changed)
    assert main(["--declaration", str(path), "--fixtures", str(root)]) == 1
    assert json.loads(capsys.readouterr().out)["verification"]["status"] == "mismatch"


def test_same_input_previous_never_supplies_cached_pass(fleet):
    root, declaration = fleet
    old = receipt(verify(declaration, root))
    (consumer_root(root, declaration) / "overlay.txt").write_text("untracked")
    fresh = receipt(verify(declaration, root), previous=old)
    assert fresh["verification"]["status"] == "unverified"
    assert fresh["previous"]["status"] == "same-input"


def test_changed_commit_identical_assets_still_marks_history(fleet):
    root, declaration = fleet
    old = receipt(verify(declaration, root))
    changed = revise(root, declaration, lambda path: (path / "content.md").write_text("new content"))
    result = receipt(verify(changed, root), previous=old)
    assert result["verification"]["status"] == "pass"
    assert result["previous"]["status"] == "historical"


def test_cli_committed_declaration_json_and_markdown(fleet, tmp_path, capsys):
    root, declaration = fleet
    path = declaration_file(tmp_path / "declaration", declaration)
    args = ["--declaration", str(path), "--fixtures", str(root)]
    assert main(args) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["schema_version"] == 1
    assert output["verification_sha256"] == digest(canonical(output["verification"]).encode())
    assert main([*args, "--format", "markdown"]) == 0
    assert "Offline Pages fleet parity" in capsys.readouterr().out
    path.write_text("{}")
    assert main(args) == 2
    assert "declaration-overlay" in capsys.readouterr().out


@pytest.mark.parametrize("field,value", [("revision", "main"), ("revision", "a" * 7), ("revision", None),
                                         ("revision", "A" * 40), ("repository", "../escape")])
def test_invalid_identity_before_resolution(field, value):
    data = {"schema_version": 1, "pipeline": {"repository": "example/pipelines", "revision": "a" * 40},
            "consumers": [{"repository": "example/one", "revision": "b" * 40,
                           "content_source": "docs", "shared_theme_enabled": True}]}
    data["consumers"][0][field] = value
    with pytest.raises(ValueError):
        validate(data)
