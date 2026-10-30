"""Architecture explorer: renamed spec prefixes never unmap rows, failures name their cause, and the model stays current."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from scripts.architecture_explorer.canonical import (  # noqa: E402
    canonical_model,
    failure_message,
    merged_aliases,
    tag_family_keys,
)
from scripts.architecture_explorer.place import Placer, Tree, unmapped_violations  # noqa: E402
from scripts.architecture_explorer.sources import Snapshot  # noqa: E402

PKG = ROOT / "scripts/architecture_explorer"
RETIRED = json.loads((ROOT / "tests/fixtures/architecture_retired_prefixes.json").read_text())


def _model(fam: str) -> dict:
    return {
        "id": "root",
        "label": "Root",
        "desc": "Root.",
        "children": [{"id": "sdk", "label": "SDK", "desc": "SDK.", "repo": "scion-sdk", "fam": [fam]}],
    }


def _snap(family: str) -> Snapshot:
    row = {"id": "SCION-X-R001", "title": "t", "status": "SPECIFIED", "repo": "scion-sdk", "family": family}
    return Snapshot(
        repo="scion-sdk", slug="scion-sdk", rows=[{**row, "text": "", "req": ""}], aliases={"SDK-": "SCION-"}
    )


@pytest.mark.spec("PIPE-PAGES-R042")
@pytest.mark.parametrize("model_key", ["SDK-X", "SCION-X"])
@pytest.mark.parametrize("row_family", ["SDK-X", "SCION-X"])
def test_a_family_renamed_through_an_alias_still_maps(model_key: str, row_family: str) -> None:
    snap = _snap(row_family)
    model = _model(model_key)
    canonical_model(model, merged_aliases([snap]))
    tag_family_keys([snap])
    tree = Tree(model)
    direct = Placer(tree).run(snap.rows)
    assert unmapped_violations(tree, direct, []) == []
    assert [r["id"] for r in direct["sdk"]] == ["SCION-X-R001"]


@pytest.mark.spec("PIPE-PAGES-R042")
def test_an_exact_row_alias_never_renames_a_spec_directory() -> None:
    snap = _snap("US-PAGES-001")
    snap.aliases = {"US-PAGES-001": "US-PAGES-R002"}
    tag_family_keys([snap])
    assert snap.rows[0]["family_key"] == "US-PAGES-001"


@pytest.mark.spec("PIPE-PAGES-R042")
def test_the_failure_message_names_the_cause() -> None:
    violations = [f"scion-sdk:SCION-A-R{n:03d}" for n in range(1, 4)] + [f"axil:AXIL-B-R00{n}" for n in range(1, 3)]
    violations += [f"r{n}:FAM{n}-R001" for n in range(30)]
    text = failure_message({"medulla": "URLError: boom"}, violations)
    assert "medulla: URLError: boom" in text
    assert "scion-sdk:SCION-A (e.g. scion-sdk:SCION-A-R001): 3" in text
    assert "axil:AXIL-B (e.g. axil:AXIL-B-R001): 2" in text
    assert "more" in text
    assert text.endswith("fix: map the family in scripts/architecture_explorer/model.json or add it to unmapped_allow")
    assert len(text.splitlines()) <= 30


def _keys(node: dict) -> list[str]:
    out = [*node.get("fam", []), *node.get("ids", [])]
    for child in node.get("children", []):
        out += _keys(child)
    return out


@pytest.mark.spec("PIPE-PAGES-R042")
def test_model_keys_use_no_retired_prefix() -> None:
    """Retired prefixes come from the checked-in alias maps (tests/fixtures/architecture_retired_prefixes.json)."""
    model = json.loads((PKG / "model.json").read_text())
    retired = {old: new for prefixes in RETIRED.values() for old, new in prefixes.items()}
    stale = sorted(
        {f"{key} (use {new})" for key in _keys(model) for old, new in retired.items() if key.startswith(old)}
    )
    assert not stale, "model.json keys use retired spec prefixes; rename them: " + ", ".join(stale)
