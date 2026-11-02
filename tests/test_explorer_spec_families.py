"""Every spec directory of this repository has an architecture model node (PIPE-GATES-R061)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.architecture_explorer import spec_families

ROOT = Path(__file__).parents[1]


@pytest.mark.spec("PIPE-GATES-R061")
def test_every_spec_directory_of_this_repository_has_a_node() -> None:
    model = json.loads(spec_families.MODEL.read_text(encoding="utf-8"))
    assert spec_families.unmapped(ROOT / "specs", model) == []


@pytest.mark.spec("PIPE-GATES-R061")
def test_a_new_spec_directory_without_a_node_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "brand-new-family").mkdir()
    (tmp_path / "_template").mkdir()
    model = json.loads(spec_families.MODEL.read_text(encoding="utf-8"))
    assert spec_families.unmapped(tmp_path, model) == ["brand-new-family"]
    assert spec_families.main([str(tmp_path)]) == 1
    assert "brand-new-family" in capsys.readouterr().out
