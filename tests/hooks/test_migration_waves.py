"""Receipt-backed migration wave gates (PIPE-GATES-R006.1-.7)."""

from __future__ import annotations

import pytest
from pipelines_hooks.migration_waves import evaluate_wave


_WAVE_ONE_SPECS = [
    "MEDULLA-SCM-R001",
    "MEDULLA-SCM-R002",
    "MEDULLA-SCM-R003",
    "MEDULLA-SCM-R004",
    "MEDULLA-SCM-R010",
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
def test_wave_1_entry_and_exit() -> None:
    result = evaluate_wave("1", _ledger())
    assert result.passed, result.findings


def test_wave_one_refuses_a_mirror_hash_mismatch_and_wrong_land_operation() -> None:
    ledger = _ledger()
    changesets = ledger["waves"]["1"]["changesets"]  # type: ignore[index]
    changesets[0]["mirror_tree_hash"] = "f" * 40
    changesets[1]["landed_via"] = "git.push"

    result = evaluate_wave("1", ledger)

    assert not result.passed
    assert any("mirror tree hash differs" in finding for finding in result.findings)
    assert any("landed_via" in finding for finding in result.findings)


@pytest.mark.spec("PIPE-GATES-R006.2")
def test_wave_2_entry_and_exit() -> None:
    ledger = _ledger()
    ledger["verified_specs"] = [*ledger["verified_specs"], "MEDULLA-SCM-R007"]  # type: ignore[index]
    _with_connector(ledger, 2, 100, source_lines=9_999)

    result = evaluate_wave("2", ledger)

    assert result.passed, result.findings


def test_wave_two_refuses_the_ten_thousand_line_boundary() -> None:
    ledger = _ledger()
    ledger["verified_specs"] = [*ledger["verified_specs"], "MEDULLA-SCM-R007"]  # type: ignore[index]
    _with_connector(ledger, 2, 200, source_lines=10_000)

    result = evaluate_wave("2", ledger)

    assert not result.passed
    assert any("below 10000" in finding for finding in result.findings)


@pytest.mark.spec("PIPE-GATES-R006.3")
def test_wave_3_entry_and_exit() -> None:
    ledger = _ledger()
    ledger["verified_specs"] = [*ledger["verified_specs"], "MEDULLA-SCM-R007", "MEDULLA-SCM-R011"]  # type: ignore[index]
    _with_connector(ledger, 2, 300, source_lines=4_000)
    wave_three = _scope(400)
    wave_three.update({"name": "remaining", "wave": 3, "release_tree_hash": wave_three["mirror_tree_hash"]})
    ledger.setdefault("connectors", []).append(wave_three)  # type: ignore[union-attr]

    result = evaluate_wave("3", ledger)

    assert result.passed, result.findings


def test_wave_three_refuses_a_release_that_changes_the_mirror_tree() -> None:
    ledger = _ledger()
    ledger["verified_specs"] = [*ledger["verified_specs"], "MEDULLA-SCM-R007", "MEDULLA-SCM-R011"]  # type: ignore[index]
    _with_connector(ledger, 2, 500, source_lines=4_000)
    wave_three = _scope(600)
    wave_three.update({"name": "remaining", "wave": 3, "release_tree_hash": "e" * 40})
    ledger.setdefault("connectors", []).append(wave_three)  # type: ignore[union-attr]

    result = evaluate_wave("3", ledger)

    assert not result.passed
    assert any("release tree differs" in finding for finding in result.findings)


@pytest.mark.spec("PIPE-GATES-R006.4")
def test_wave_4_entry_and_exit() -> None:
    ledger = _ledger()
    ledger["verified_specs"] = [*ledger["verified_specs"], "MEDULLA-SCM-R007", "MEDULLA-SCM-R011", "PIPE-GATES-R003"]  # type: ignore[index]
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


def test_wave_four_refuses_a_missing_named_repository() -> None:
    ledger = _ledger()
    ledger["verified_specs"] = [*ledger["verified_specs"], "MEDULLA-SCM-R007", "MEDULLA-SCM-R011", "PIPE-GATES-R003"]  # type: ignore[index]
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


def test_wave_four_does_not_accept_a_similar_repository_name() -> None:
    ledger = _ledger()
    ledger["verified_specs"] = [*ledger["verified_specs"], "MEDULLA-SCM-R007", "MEDULLA-SCM-R011", "PIPE-GATES-R003"]  # type: ignore[index]
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


def _through_wave_four() -> dict[str, object]:
    ledger = _ledger()
    ledger["verified_specs"] = [
        *ledger["verified_specs"],  # type: ignore[misc]
        "MEDULLA-SCM-R007",
        "MEDULLA-SCM-R011",
        "PIPE-GATES-R003",
    ]
    _with_connector(ledger, 2, 700, source_lines=4_000)
    wave_three = _scope(800)
    wave_three.update({"name": "remaining", "wave": 3, "release_tree_hash": wave_three["mirror_tree_hash"]})
    ledger.setdefault("connectors", []).append(wave_three)  # type: ignore[union-attr]
    ledger["repositories"] = [
        {**_scope(900 + index), "name": name, "wave": 4}
        for index, name in enumerate(("universal-skills", "pipelines", "Overstory", "Tuig", "Axil"))
    ]
    return ledger


def _add_repository(ledger: dict[str, object], name: str, wave: int, seed: int, **extra: object) -> dict[str, object]:
    repository = {**_scope(seed), "name": name, "wave": wave, **extra}
    ledger["repositories"].append(repository)  # type: ignore[union-attr]
    return repository


def _through_wave_five() -> dict[str, object]:
    ledger = _through_wave_four()
    ledger["verified_specs"] = [*ledger["verified_specs"], "SCION-SCM-R002", "MERISTEM-SCM-R001"]  # type: ignore[misc]
    _add_repository(ledger, "scion-sdk", 5, 1000)
    _add_repository(ledger, "meristem", 5, 1100)
    return ledger


def _through_wave_six() -> dict[str, object]:
    ledger = _through_wave_five()
    ledger["verified_specs"] = [*ledger["verified_specs"], "ARBORA-OPS-R850", "ARBORA-OPS-R851"]  # type: ignore[misc]
    arbora = _add_repository(ledger, "arbora", 6, 1200)
    arbora["release_deploy"] = {"source": "changeset_tree", "tree_hash": f"{1200 + 19:040x}"}
    return ledger


def _through_wave_seven(restores: int = 2) -> dict[str, object]:
    ledger = _through_wave_six()
    ledger["verified_specs"] = [*ledger["verified_specs"], "MEDULLA-SCM-R009"]  # type: ignore[misc]
    _add_repository(ledger, "medulla", 7, 1300)
    ledger["restores"] = [{"source": "git_mirror", "result": "passed"}] * restores
    return ledger


@pytest.mark.spec("PIPE-GATES-R006.5")
def test_wave_5_entry_and_exit() -> None:
    assert evaluate_wave("5", _through_wave_five()).passed
    ledger = _through_wave_five()
    ledger["verified_specs"] = [s for s in ledger["verified_specs"] if s != "MERISTEM-SCM-R001"]  # type: ignore[attr-defined]
    missing = evaluate_wave("5", ledger)
    assert any("MERISTEM-SCM-R001" in finding for finding in missing.findings)
    ledger = _through_wave_five()
    ledger["repositories"] = [r for r in ledger["repositories"] if r["name"] != "meristem"]  # type: ignore[index,attr-defined]
    assert any("'meristem'" in finding for finding in evaluate_wave("5", ledger).findings)


@pytest.mark.spec("PIPE-GATES-R006.6")
def test_wave_6_entry_and_exit() -> None:
    assert evaluate_wave("6", _through_wave_six()).passed
    ledger = _through_wave_six()
    ledger["repositories"][-1]["release_deploy"] = {"source": "changeset_tree", "tree_hash": "a" * 40}  # type: ignore[index]
    assert any("not the tree hash of any receipted changeset" in f for f in evaluate_wave("6", ledger).findings)
    ledger = _through_wave_six()
    del ledger["repositories"][-1]["release_deploy"]  # type: ignore[index]
    assert any("release_deploy" in f for f in evaluate_wave("6", ledger).findings)
    ledger = _through_wave_six()
    ledger["verified_specs"] = [s for s in ledger["verified_specs"] if s != "ARBORA-OPS-R851"]  # type: ignore[attr-defined]
    assert any("ARBORA-OPS-R851" in f for f in evaluate_wave("6", ledger).findings)


@pytest.mark.spec("PIPE-GATES-R006.7")
def test_wave_7_entry_and_exit() -> None:
    assert evaluate_wave("7", _through_wave_seven()).passed
    one_restore = evaluate_wave("7", _through_wave_seven(restores=1))
    assert any("wave 7 exit: expected 2 passed restore(s)" in finding for finding in one_restore.findings)
    none = evaluate_wave("7", _through_wave_seven(restores=0))
    assert any("wave 7 entry: expected 1 passed restore(s)" in finding for finding in none.findings)
    ledger = _through_wave_seven()
    ledger["restores"] = [{"source": "git_mirror", "result": "failed"}, {"source": "git_mirror", "result": "passed"}]
    assert not evaluate_wave("7", ledger).passed
    with pytest.raises(Exception, match="unsupported wave"):
        evaluate_wave("8", _through_wave_seven())
