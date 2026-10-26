"""PIPE-PAGES-R035: stable prompt JSON, Pydantic, and semantic diff proof."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from pipelines_hooks import prompt_format


def _prompt(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "task": "pages-test",
        "type": "prompt",
        "schema_version": "1.0",
        "source": "pipelines:test",
        "metadata": {"topic": "delivery", "extension": {"stable": True}},
        "instructions": {
            "core_directive": "Preserve the prompt's semantic values.",
            "workflow": ["load", "validate", "serialize"],
        },
        "custom": {"unicode": "café", "decimal": 1.2300, "a/b": [None, "x"]},
    }
    value.update(updates)
    return value


@pytest.mark.spec("PIPE-PAGES-R035")
@pytest.mark.spec("PIPE-PAGES-R035.1")
def test_au121_prompt_model() -> None:
    document = prompt_format.validate_prompt(_prompt())
    assert isinstance(document, prompt_format.PromptDiskDocument)
    canonical = prompt_format.serialize_prompt(document)
    assert canonical.endswith(b"\n")
    assert canonical.index(b'"instructions"') < canonical.index(b'"task"')
    assert b'"decimal": 1.23' in canonical
    assert b"caf\xc3\xa9" in canonical


@pytest.mark.spec("PIPE-PAGES-R035.2")
def test_au121_roundtrip_behavior() -> None:
    # Reordering keys, indentation, and decimal spelling is formatting noise;
    # the oracle compares the validated JSON value rather than source bytes.
    source = json.dumps(_prompt(), ensure_ascii=False, indent=4).encode("utf-8")
    canonical = prompt_format.canonicalize_prompt(source)
    assert prompt_format.difference_oracle(source, canonical) == []

    changed = _prompt(
        instructions={
            "core_directive": "Preserve the prompt's semantic values.",
            "workflow": ["load", "serialize"],
        }
    )
    differences = prompt_format.difference_oracle(_prompt(), changed)
    assert [(row.path, row.kind, row.before, row.after) for row in differences] == [
        ("/instructions/workflow/1", "changed", "validate", "serialize"),
        ("/instructions/workflow/2", "removed", "serialize", None),
    ]


@pytest.mark.spec("PIPE-PAGES-R035.3")
def test_au121_serializer_wiring() -> None:
    exported = _prompt(
        identity={"component_id": "prompt:pages-test", "revision": "r17"},
        schema_pin={"component_id": "prompt:pages-test", "entry_revision": "r17", "definition_digest": "sha256:x"},
        base_revision="r16",
        payload={"task": "pages-test", "custom": {"kept": [1, 2, 3]}},
        provenance={"producer": "epistemic-graph", "source_revision": "r17"},
        disk_format="0.9",
    )
    for disk_format in ("0.9", "1.0", "1.1"):
        exported["disk_format"] = disk_format
        snapshot = prompt_format.snapshot_prompt(prompt_format.serialize_prompt(exported))
        assert snapshot.producer_requirements == prompt_format.R094_WIRING_REQUIREMENTS
        assert snapshot.document.model_extra["schema_pin"]["definition_digest"] == "sha256:x"
        assert snapshot.document.model_extra["base_revision"] == "r16"
        assert snapshot.document.model_extra["payload"]["custom"]["kept"] == [1, 2, 3]
        assert snapshot.document.model_extra["disk_format"] == disk_format
        assert prompt_format.difference_oracle(snapshot.document, snapshot.canonical_bytes) == []


@pytest.mark.spec("PIPE-PAGES-R035.4")
def test_au121_coverage_refusal() -> None:
    # Retired flat bodies cannot sneak around the canonical instructions body,
    # and missing instructions never becomes a successful no-op round trip.
    with pytest.raises(prompt_format.PromptFormatError, match="retired"):
        prompt_format.validate_prompt(_prompt(content="legacy body"))
    with pytest.raises(prompt_format.PromptFormatError, match="instructions"):
        prompt_format.validate_prompt({"task": "pages-test", "type": "prompt", "schema_version": "1.0"})
    with pytest.raises(prompt_format.PromptFormatError, match="type"):
        prompt_format.validate_prompt(_prompt(type="not-a-prompt"))
    with pytest.raises(prompt_format.PromptFormatError, match="duplicate"):
        prompt_format.load_prompt(
            b'{"task":"pages-test","type":"prompt","schema_version":"1.0",'
            b'"instructions":{"core_directive":"x"},"task":"again"}'
        )
    with pytest.raises(prompt_format.PromptFormatError, match="non-finite"):
        prompt_format.load_prompt(
            b'{"task":"pages-test","type":"prompt","schema_version":"1.0",'
            b'"instructions":{"core_directive":"x"},"score":NaN}'
        )


@pytest.mark.spec("PIPE-PAGES-R035.5")
def test_au121_oracle_evidence() -> None:
    canonical = prompt_format.serialize_prompt(_prompt())
    snapshot = prompt_format.snapshot_prompt(canonical)
    assert snapshot.sha256 == hashlib.sha256(canonical).hexdigest()
    changed = prompt_format.serialize_prompt(_prompt(custom={"unicode": "café", "decimal": 2, "a/b": [None, "x"]}))
    rows = prompt_format.difference_oracle(snapshot.canonical_bytes, changed)
    assert [(row.path, row.kind, row.before, row.after) for row in rows] == [
        ("/custom/decimal", "changed", Decimal("1.23"), 2),
    ]
    assert rows[0].as_dict()["before"] == "1.23"


@pytest.mark.spec("PIPE-PAGES-R035.6")
def test_au121_roundtrip_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    prompt_path = tmp_path / "prompts" / "demo.json"
    prompt_path.parent.mkdir()
    canonical = prompt_format.serialize_prompt(_prompt())
    prompt_path.write_bytes(canonical)
    assert prompt_format.main(["--root", str(tmp_path)]) == 0
    assert "sha256=" in capsys.readouterr().out

    prompt_path.write_text(json.dumps(_prompt(), indent=4), encoding="utf-8")
    assert prompt_format.main(["--root", str(tmp_path)]) == 1
    assert "not canonical" in capsys.readouterr().out

    prompt_path.write_bytes(b'{"task":"pages-test","type":"prompt","schema_version":"1.0",')
    assert prompt_format.main(["--root", str(tmp_path)]) == 1
    assert "malformed" in capsys.readouterr().err

    assert prompt_format.main(["--root", str(tmp_path), "prompts/missing.json"]) == 2
    assert "does not exist" in capsys.readouterr().err


@pytest.mark.spec("PIPE-PAGES-R035.4")
def test_au121_bounded_json_numbers_refuse_before_conversion_or_expansion() -> None:
    prefix = (
        b'{"task":"pages-test","type":"prompt","schema_version":"1.0","instructions":{"core_directive":"x"},"value":'
    )
    with pytest.raises(prompt_format.PromptFormatError, match="integer"):
        prompt_format.load_prompt(prefix + (b"1" * 4_301) + b"}")
    with pytest.raises(prompt_format.PromptFormatError, match="exponent"):
        prompt_format.load_prompt(prefix + b"1e100000000}")
    with pytest.raises(prompt_format.PromptFormatError, match="expansion"):
        prompt_format.serialize_prompt(_prompt(custom={"value": Decimal("1e4096")}))
    padded_exponent = prompt_format.serialize_prompt(prompt_format.load_prompt(prefix + b"1e0002}"))
    assert b'"value": 100' in padded_exponent

    exact = _prompt(
        custom={
            "integer": int("9" * 100),
            "decimal": Decimal("1.2300"),
            "long_decimal": Decimal("9" * 100),
        }
    )
    canonical = prompt_format.serialize_prompt(exact)
    assert b'"integer": ' + (b"9" * 100) in canonical
    assert b'"decimal": 1.23' in canonical
    assert b'"long_decimal": ' + (b"9" * 100) in canonical
    assert prompt_format.difference_oracle(exact, prompt_format.load_prompt(canonical)) == []


@pytest.mark.spec("PIPE-PAGES-R035.6")
def test_au121_cli_rejects_absolute_outside_and_traversal_before_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_bytes(prompt_format.serialize_prompt(_prompt()))

    original_read_bytes = Path.read_bytes

    def fail_if_opened(path: Path) -> bytes:
        if path in {outside, root / "prompts" / ".." / "outside.json"}:
            raise AssertionError(f"untrusted path was opened: {path}")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fail_if_opened)
    assert prompt_format.main(["--root", str(root), str(outside)]) == 2
    assert "escapes repository root" in capsys.readouterr().err

    traversal = root / "prompts" / ".." / "outside.json"
    assert prompt_format.main(["--root", str(root), str(traversal)]) == 2
    assert "traversal" in capsys.readouterr().err


@pytest.mark.spec("PIPE-PAGES-R035.6")
def test_au121_cli_rejects_symlink_ancestor_and_accepts_contained_absolute(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "repo"
    prompt_path = root / "prompts" / "demo.json"
    prompt_path.parent.mkdir(parents=True)
    prompt_path.write_bytes(prompt_format.serialize_prompt(_prompt()))
    assert prompt_format.main(["--root", str(root), str(prompt_path)]) == 0
    assert "sha256=" in capsys.readouterr().out

    outside = tmp_path / "outside.json"
    outside.write_bytes(prompt_path.read_bytes())
    link = root / "prompts" / "outside.json"
    link.symlink_to(outside)
    assert prompt_format.main(["--root", str(root), str(link)]) == 2
    assert "symlink ancestor" in capsys.readouterr().err
