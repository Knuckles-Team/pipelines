"""Canonical full definitions remain useful when generated titles are generic."""

import json

import pytest

from scripts.spec_dashboard_records import inventory_panel
from scripts.spec_dashboard_sources import read_records


def snapshot(root, rows):
    directory = root / "specs" / "pages"
    directory.mkdir(parents=True)
    (directory / "spec.md").write_text("# PIPE-PAGES — Shared Pages\n")
    (directory / "requirements.md").write_text("# Requirements\n" + rows)
    (directory / "status.json").write_text(
        json.dumps(
            {
                "spec_id": "PIPE-PAGES",
                "delivery_state": "SPECIFIED",
                "requirements": [
                    {
                        "id": "PIPE-PAGES-R020.37",
                        "title": "Model",
                        "delivery_state": "SPECIFIED",
                        "landed_in": ["a" * 12],
                        "verified_by": ["tests/test_example.py::test_model"],
                    }
                ],
            }
        )
    )
    return {
        "repository": "Knuckles-Team/pipelines",
        "revision": "b" * 40,
        "records": read_records(root, {"sources": [{"glob": "specs/*/status.json"}]}),
    }


def test_generic_title_has_full_definition_parent_context_and_exact_link(tmp_path):
    data = snapshot(
        tmp_path,
        "| `PIPE-PAGES-R020.37` | **Model.** The tool mapping contains method parameters. | Verify the complete schema. |\n",
    )
    row = data["records"][1]
    assert row["title"] == "Model" and row["delivery_state"] == "SPECIFIED"
    assert row["landed_in"] == ["a" * 12] and row["verified_by"] == ["tests/test_example.py::test_model"]
    page = inventory_panel(data)
    assert "method parameters" in page and "Verify the complete schema." in page
    assert "PIPE-PAGES — Shared Pages" in page
    assert "/specs/pages/requirements.md#L2" in page
    assert "<details open><summary>All documented records" in page
    assert 'id="req-PIPE-PAGES-R020.37"' in page


def test_definition_html_is_escaped_and_missing_text_is_explicit(tmp_path):
    data = snapshot(tmp_path, "| `PIPE-PAGES-R020.37` | <script>alert(1)</script> | <img src=x> |\n")
    page = inventory_panel(data)
    assert "<script>" not in page and "<img src=x>" not in page
    assert "&lt;script&gt;" in page and "&lt;img src=x&gt;" in page
    (tmp_path / "specs/pages/requirements.md").unlink()
    records = read_records(tmp_path, {"sources": [{"glob": "specs/*/status.json"}]})
    assert "definition unavailable" in inventory_panel(data | {"records": records})


def test_duplicate_definition_refuses_ambiguous_source(tmp_path):
    row = "| `PIPE-PAGES-R020.37` | First | Test |\n"
    with pytest.raises(ValueError, match="Duplicate requirement definition"):
        snapshot(tmp_path, row + row)
