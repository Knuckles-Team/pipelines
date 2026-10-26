"""Receipt-backed migration wave gates (PIPE-GATES-R006.1-.4)."""

from __future__ import annotations

import pytest
from pipelines_hooks.migration_waves import evaluate_wave


_WAVE_ONE_SPECS = [
    "EG-SCM-R001",
    "EG-SCM-R002",
    "EG-SCM-R003",
    "EG-SCM-R004",
    "EG-SCM-R010",
    "RM-SCM-R001",
    "RM-SCM-R002",
    "ARBORA-OPS-R848.2",
    "ARBORA-OPS-R849",
]


def _scope(seed: int) -> dict[str, object]:
    changesets = []
    for index in range(20):
        tree_hash = f"{seed + index:040x}"
        changesets.append(
            {
                "id": f"cs-{seed}-{index}",
                "landed_via": "source.land",
                "tree_hash": tree_hash,
                "mirror_tree_hash": tree_hash,
            }
        )
    return {
        "changesets": changesets,
        "auto_revert_rehearsal": {"gate_id": "PIPE-GATES-R002", "result": "passed"},
        "mirror_no_divergence_days": 7,
        "mirror_tree_hash": changesets[-1]["mirror_tree_hash"],
    }


def _ledger() -> dict[str, object]:
    return {"verified_specs": list(_WAVE_ONE_SPECS), "waves": {"1": _scope(1)}}


def _with_connector(ledger: dict[str, object], wave: int, seed: int, **extra: object) -> None:
    connectors = ledger.setdefault("connectors", [])
    assert isinstance(connectors, list)
    row = _scope(seed)
    row.update({"name": f"connector-{wave}-{seed}", "wave": wave, **extra})
    connectors.append(row)


@pytest.mark.spec("PIPE-GATES-R006.1")
def test_wave_one_requires_every_receipt_and_accepts_a_complete_scope() -> None:
    # spec: PIPE-GATES-R006.1
    result = evaluate_wave("1", _ledger())
    assert result.passed, result.findings


@pytest.mark.spec("PIPE-GATES-R006.1")
def test_wave_one_refuses_a_mirror_hash_mismatch_and_wrong_land_operation() -> None:
    # spec: PIPE-GATES-R006.1
    ledger = _ledger()
    changesets = ledger["waves"]["1"]["changesets"]  # type: ignore[index]
    changesets[0]["mirror_tree_hash"] = "f" * 40
    changesets[1]["landed_via"] = "git.push"

    result = evaluate_wave("1", ledger)

    assert not result.passed
    assert any("mirror tree hash differs" in finding for finding in result.findings)
    assert any("landed_via" in finding for finding in result.findings)


@pytest.mark.spec("PIPE-GATES-R006.2")
def test_wave_two_reuses_wave_one_exit_for_small_connectors() -> None:
    # spec: PIPE-GATES-R006.2
    ledger = _ledger()
    ledger["verified_specs"] = [*ledger["verified_specs"], "EG-SCM-R007"]  # type: ignore[index]
    _with_connector(ledger, 2, 100, source_lines=9_999)

    result = evaluate_wave("2", ledger)

    assert result.passed, result.findings


@pytest.mark.spec("PIPE-GATES-R006.2")
def test_wave_two_refuses_the_ten_thousand_line_boundary() -> None:
    # spec: PIPE-GATES-R006.2
    ledger = _ledger()
    ledger["verified_specs"] = [*ledger["verified_specs"], "EG-SCM-R007"]  # type: ignore[index]
    _with_connector(ledger, 2, 200, source_lines=10_000)

    result = evaluate_wave("2", ledger)

    assert not result.passed
    assert any("below 10000" in finding for finding in result.findings)


@pytest.mark.spec("PIPE-GATES-R006.3")
def test_wave_three_requires_an_unchanged_mirror_release_for_each_connector() -> None:
    # spec: PIPE-GATES-R006.3
    ledger = _ledger()
    ledger["verified_specs"] = [*ledger["verified_specs"], "EG-SCM-R007", "EG-SCM-R011"]  # type: ignore[index]
    _with_connector(ledger, 2, 300, source_lines=4_000)
    wave_three = _scope(400)
    wave_three.update({"name": "remaining", "wave": 3, "release_tree_hash": wave_three["mirror_tree_hash"]})
    ledger.setdefault("connectors", []).append(wave_three)  # type: ignore[union-attr]

    result = evaluate_wave("3", ledger)

    assert result.passed, result.findings


@pytest.mark.spec("PIPE-GATES-R006.3")
def test_wave_three_refuses_a_release_that_changes_the_mirror_tree() -> None:
    # spec: PIPE-GATES-R006.3
    ledger = _ledger()
    ledger["verified_specs"] = [*ledger["verified_specs"], "EG-SCM-R007", "EG-SCM-R011"]  # type: ignore[index]
    _with_connector(ledger, 2, 500, source_lines=4_000)
    wave_three = _scope(600)
    wave_three.update({"name": "remaining", "wave": 3, "release_tree_hash": "e" * 40})
    ledger.setdefault("connectors", []).append(wave_three)  # type: ignore[union-attr]

    result = evaluate_wave("3", ledger)

    assert not result.passed
    assert any("release tree differs" in finding for finding in result.findings)


@pytest.mark.spec("PIPE-GATES-R006.4")
def test_wave_four_requires_all_five_named_repositories() -> None:
    # spec: PIPE-GATES-R006.4
    ledger = _ledger()
    ledger["verified_specs"] = [*ledger["verified_specs"], "EG-SCM-R007", "EG-SCM-R011", "PIPE-GATES-R003"]  # type: ignore[index]
    _with_connector(ledger, 2, 700, source_lines=4_000)
    wave_three = _scope(800)
    wave_three.update({"name": "remaining", "wave": 3, "release_tree_hash": wave_three["mirror_tree_hash"]})
    ledger.setdefault("connectors", []).append(wave_three)  # type: ignore[union-attr]
    repositories = []
    for index, name in enumerate(("universal-skills", "pipelines", "Overstory", "Tuig", "Axil")):
        repository = _scope(900 + index)
        repository.update({"name": name, "wave": 4})
        repositories.append(repository)
    ledger["repositories"] = repositories

    result = evaluate_wave("4", ledger)

    assert result.passed, result.findings


@pytest.mark.spec("PIPE-GATES-R006.4")
def test_wave_four_refuses_a_missing_named_repository() -> None:
    # spec: PIPE-GATES-R006.4
    ledger = _ledger()
    ledger["verified_specs"] = [*ledger["verified_specs"], "EG-SCM-R007", "EG-SCM-R011", "PIPE-GATES-R003"]  # type: ignore[index]
    _with_connector(ledger, 2, 1_000, source_lines=4_000)
    wave_three = _scope(1_100)
    wave_three.update({"name": "remaining", "wave": 3, "release_tree_hash": wave_three["mirror_tree_hash"]})
    ledger.setdefault("connectors", []).append(wave_three)  # type: ignore[union-attr]
    repositories = []
    for index, name in enumerate(("universal-skills", "pipelines", "Overstory", "Tuig")):
        repository = _scope(1_200 + index)
        repository.update({"name": name, "wave": 4})
        repositories.append(repository)
    ledger["repositories"] = repositories

    result = evaluate_wave("4", ledger)

    assert not result.passed
    assert any("Axil" in finding for finding in result.findings)


@pytest.mark.spec("PIPE-GATES-R006.4")
def test_wave_four_does_not_accept_a_similar_repository_name() -> None:
    # spec: PIPE-GATES-R006.4
    ledger = _ledger()
    ledger["verified_specs"] = [*ledger["verified_specs"], "EG-SCM-R007", "EG-SCM-R011", "PIPE-GATES-R003"]  # type: ignore[index]
    _with_connector(ledger, 2, 1_300, source_lines=4_000)
    wave_three = _scope(1_400)
    wave_three.update({"name": "remaining", "wave": 3, "release_tree_hash": wave_three["mirror_tree_hash"]})
    ledger.setdefault("connectors", []).append(wave_three)  # type: ignore[union-attr]
    repositories = []
    for index, name in enumerate(("universal-skills", "pipelines", "Overstory", "Tuig", "axil")):
        repository = _scope(1_500 + index)
        repository.update({"name": name, "wave": 4})
        repositories.append(repository)
    ledger["repositories"] = repositories

    result = evaluate_wave("4", ledger)

    assert not result.passed
    assert any("Axil" in finding for finding in result.findings)
