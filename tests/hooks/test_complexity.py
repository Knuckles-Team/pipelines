"""complexity-staged and complexity-census fire on planted over-cap functions."""

from __future__ import annotations

from tests.hooks.conftest import Repo, branchy


def test_staged_gate_fires_on_a_new_function_over_the_cyclomatic_cap(repo: Repo) -> None:
    repo.stage({"pkg/heavy.py": branchy("heavy", 11)})
    assert repo.run("complexity-staged") == 1


def test_staged_gate_passes_a_new_function_under_both_caps(repo: Repo) -> None:
    repo.stage({"pkg/light.py": branchy("light", 5)})
    assert repo.run("complexity-staged") == 0


def test_staged_gate_fires_when_an_existing_function_gets_worse(repo: Repo) -> None:
    repo.commit({"pkg/debt.py": branchy("debt", 11)})
    repo.stage({"pkg/debt.py": branchy("debt", 12)})
    assert repo.run("complexity-staged") == 1


def test_staged_gate_ignores_untouched_pre_existing_debt(repo: Repo, capsys) -> None:
    repo.commit({"pkg/debt.py": branchy("debt", 11)})
    repo.stage({"pkg/debt.py": branchy("debt", 11) + "\n\n" + branchy("fresh", 3)})
    assert repo.run("complexity-staged") == 0
    assert "1 already over 10/15" in capsys.readouterr().out


def test_census_fires_on_any_over_cap_function_and_passes_when_clean(repo: Repo) -> None:
    repo.commit({"pkg/heavy.py": branchy("heavy", 11)})
    assert repo.run("complexity-census") == 1
    repo.commit({"pkg/heavy.py": branchy("heavy", 4)})
    assert repo.run("complexity-census") == 0


def test_census_accepts_an_exhaustive_rust_dispatcher_by_rule(repo: Repo, capsys) -> None:
    arms = "".join(f"        Kind::V{index} => {index},\n" for index in range(12))
    dispatcher = f"pub fn dispatch(kind: Kind) -> u8 {{\n    match kind {{\n{arms}    }}\n}}\n"
    repo.commit({"pkg/dispatch.rs": dispatcher})
    assert repo.run("complexity-census") == 0
    assert "ACCEPTED BY RULE              1" in capsys.readouterr().out
