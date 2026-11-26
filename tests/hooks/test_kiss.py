"""kiss-staged attributes only what a diff caused; kiss-census enforces every finding."""

from __future__ import annotations

import pytest

from pipelines_hooks.kiss.report import attributable
from pipelines_hooks.kiss.runner import unknown_keys
from pipelines_hooks.kiss.spans import python_spans, rust_spans
from tests.hooks.conftest import Repo, branchy


def test_attribution_counts_only_new_or_modified_functions_and_grown_aggregates() -> None:
    head = "def untouched():\n    return 1\n\n\ndef changed():\n    return 1\n"
    staged = (
        head.replace("return 1\n", "return 2\n", 2).replace("return 2\n", "return 1\n", 1)
        + "\n\ndef added():\n    return 3\n"
    )
    report = "\n".join(
        [
            "VIOLATION:returns_per_function:m.py:1:untouched: too many returns",
            "VIOLATION:returns_per_function:m.py:5:changed: too many returns",
            "VIOLATION:returns_per_function:m.py:9:added: too many returns",
            "VIOLATION:functions_per_file:m.py:1:m.py: File has 3 functions",
        ]
    )
    head_report = "VIOLATION:functions_per_file:m.py:1:m.py: File has 2 functions"
    names = [v["name"] for v in attributable((staged, report), (head, head_report), python_spans)]
    assert names == ["changed", "added", "m.py"]
    assert len(attributable((staged, report), None, python_spans)) == 4


def test_rust_spans_ignore_a_function_named_in_a_comment_or_string() -> None:
    source = '// fn target() {\nconst S: &str = "fn target() {";\nfn target() {\n    1\n}\n'
    assert [span[:2] for span in rust_spans(source, "target")] == [(3, 5)]


@pytest.mark.scanner("kiss")
def test_staged_gate_fires_on_a_new_function_with_too_many_returns(repo: Repo) -> None:
    repo.stage({"pkg/returns.py": branchy("returns", 6)})
    assert repo.run("kiss-staged") == 1


@pytest.mark.scanner("kiss")
def test_staged_gate_does_not_count_untouched_debt_in_a_changed_file(repo: Repo) -> None:
    repo.commit({"pkg/debt.py": branchy("debt", 6)})
    repo.stage({"pkg/debt.py": branchy("debt", 6) + "\n\ndef fresh():\n    return 1\n"})
    assert repo.run("kiss-staged") == 0


@pytest.mark.scanner("kiss")
def test_census_fires_on_findings_and_passes_when_clean(repo: Repo) -> None:
    repo.commit({"pkg/returns.py": branchy("returns", 6)})
    assert repo.run("kiss-census") == 1
    repo.commit({"pkg/returns.py": "VALUE = 1\n"})
    assert repo.run("kiss-census") == 0


def test_unknown_keys_names_every_key_kiss_would_drop_its_table_for() -> None:
    document = {
        "global": {"docs_allowed": [], "orphan_module_enabled": True},
        "test": {"bogus": 1},
        "gate": {},
    }
    assert unknown_keys(document) == [
        "global.orphan_module_enabled",
        "test.bogus",
        "[gate] (renamed to [global]/[test] in kiss 0.4.11)",
    ]
    assert unknown_keys({"global": {"docs_allowed": []}, "test": {"orphan_detection": True}}) == []


@pytest.mark.parametrize("gate", ["kiss-census", "kiss-staged"])
def test_gates_refuse_a_config_key_kiss_would_silently_drop(repo: Repo, gate: str, capsys) -> None:
    config = (repo.root / ".config/kiss.toml").read_text(encoding="utf-8")
    bad = config.replace("[global]\n", "[global]\norphan_module_enabled = true\n", 1)
    repo.commit({".config/kiss.toml": bad, "pkg/returns.py": "VALUE = 1\n"})
    repo.stage({"pkg/returns.py": "VALUE = 2\n"})
    assert repo.run(gate) == 2
    assert "global.orphan_module_enabled" in capsys.readouterr().err


# spec: PIPE-GATES-R082
def test_a_test_mod_declaration_resolves_to_its_child_file(tmp_path) -> None:
    from pipelines_hooks.core.errors import CannotRun
    from pipelines_hooks.kiss.modules import is_test_target_root, resolve_children

    tests = tmp_path / "pkg" / "tests"
    (tests / "support").mkdir(parents=True)
    (tmp_path / "pkg" / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
    (tests / "it.rs").write_text("// mod ignored;\nmod support;\nmod flat;\n", encoding="utf-8")
    (tests / "support" / "mod.rs").write_text("pub mod helpers;\n", encoding="utf-8")
    (tests / "support" / "helpers.rs").write_text("pub fn help() {}\n", encoding="utf-8")
    (tests / "flat.rs").write_text("mod inner;\n", encoding="utf-8")
    (tests / "flat").mkdir()
    (tests / "flat" / "inner.rs").write_text("", encoding="utf-8")
    (tests / "shared").mkdir()
    (tests / "shared" / "extra.rs").write_text("", encoding="utf-8")
    (tests / "it.rs").write_text(
        (tests / "it.rs").read_text(encoding="utf-8") + '#[path = "shared/extra.rs"]\nmod renamed;\n', encoding="utf-8"
    )
    assert is_test_target_root(tmp_path, "pkg/tests/it.rs")
    assert not is_test_target_root(tmp_path, "pkg/src/tests/it.rs")
    assert sorted(resolve_children(tmp_path, "pkg/tests/it.rs")) == [
        "pkg/tests/flat.rs",
        "pkg/tests/flat/inner.rs",
        "pkg/tests/shared/extra.rs",
        "pkg/tests/support/helpers.rs",
        "pkg/tests/support/mod.rs",
    ]
    (tests / "flat" / "inner.rs").unlink()
    with pytest.raises(CannotRun, match="mod inner;"):
        resolve_children(tmp_path, "pkg/tests/it.rs")


# spec: PIPE-GATES-R082
@pytest.mark.scanner("kiss")
def test_staged_hook_resolves_a_test_mod_declaration(repo: Repo) -> None:
    config = repo.root / ".config" / "kiss.toml"
    repo.stage({".config/kiss.toml": config.read_text(encoding="utf-8") + "\n[rust]\nreturns_per_function = 8\n"})
    repo.stage({"pkg/Cargo.toml": '[package]\nname = "pkg"\n'})
    repo.stage({"pkg/tests/it.rs": "mod support;\n\n#[test]\nfn works() {\n    support::run();\n}\n"})
    assert repo.run("kiss-staged") == 2  # the declared child is not in the staged tree
    repo.stage({"pkg/tests/support.rs": "pub fn run() {}\n"})
    assert repo.run("kiss-staged") == 0
