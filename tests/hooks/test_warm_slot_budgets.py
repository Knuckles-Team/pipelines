"""Warm slot timing budgets (PIPE-GATES-R075)."""

from __future__ import annotations

import pytest
from pipelines_hooks.ci.warm_slots.budgets import (
    COLD_PRIME,
    PR_WALL,
    WARM_CHECK,
    Budgets,
    Timing,
    check_budgets,
    record_timing,
)
from pipelines_hooks.ci.warm_slots.cli import main

from tests.hooks.warm_slot_fixtures import CONFIG_TEXT

BUDGETS = Budgets(warm_check_seconds=60, cold_prime_seconds=900, pr_wall_seconds=1200)


@pytest.mark.spec("PIPE-GATES-R075")
def test_a_warm_one_file_check_over_60_seconds_fails() -> None:
    assert check_budgets([Timing(WARM_CHECK, 60)], BUDGETS) == []
    assert check_budgets([Timing(WARM_CHECK, 61, "pr-12")], BUDGETS) == [
        "warm_one_file_check (pr-12): a warm one-file-change check took 61s, over the 60s limit"
    ]


@pytest.mark.spec("PIPE-GATES-R075")
def test_a_cold_prime_over_15_minutes_fails() -> None:
    assert check_budgets([Timing(COLD_PRIME, 900, "alpha-1")], BUDGETS) == []
    assert check_budgets([Timing(COLD_PRIME, 901, "alpha-1")], BUDGETS) == [
        "cold_prime (alpha-1): a cold prime took 901s, over the 900s limit"
    ]
    # A four-job slot gets the limit scaled to its size; an unrelated measurement is ignored.
    assert check_budgets([Timing(COLD_PRIME, 1700, "small", jobs=4)], BUDGETS) == []
    assert check_budgets([Timing("other", 99999)], BUDGETS) == []


@pytest.mark.spec("PIPE-GATES-R075")
def test_pr_wall_time_over_20_minutes_fails(tmp_path, capsys) -> None:
    assert check_budgets([Timing(PR_WALL, 1201)], BUDGETS) == [
        "pr_wall_time: pull request CI wall time took 1201s, over the 1200s limit"
    ]
    timings = tmp_path / "timings.json"
    config = tmp_path / "slots.toml"
    # timings_file is a top-level key, so it goes before the first table.
    config.write_text(f'timings_file = "{timings}"\n' + CONFIG_TEXT, encoding="utf-8")
    record_timing(timings, Timing(PR_WALL, 900))
    assert main(["budgets", "--config", str(config)]) == 0
    record_timing(timings, Timing(PR_WALL, 1500))
    assert main(["budgets", "--config", str(config)]) == 1
    assert "pr_wall_time" in capsys.readouterr().out
