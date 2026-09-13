"""kiss-staged attributes only what a diff caused; kiss-census enforces findings and orphans."""

from __future__ import annotations

from pipelines_hooks.kiss.report import attributable
from pipelines_hooks.kiss.spans import python_spans, rust_spans
from tests.hooks.conftest import Repo, branchy


def test_attribution_counts_only_new_or_modified_functions_and_grown_aggregates() -> None:
    head = "def untouched():\n    return 1\n\n\ndef changed():\n    return 1\n"
    staged = head.replace("return 1\n", "return 2\n", 2).replace("return 2\n", "return 1\n", 1) + "\n\ndef added():\n    return 3\n"
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


def test_staged_gate_fires_on_a_new_function_with_too_many_returns(repo: Repo) -> None:
    repo.stage({"pkg/returns.py": branchy("returns", 6)})
    assert repo.run("kiss-staged") == 1


def test_staged_gate_does_not_count_untouched_debt_in_a_changed_file(repo: Repo) -> None:
    repo.commit({"pkg/debt.py": branchy("debt", 6)})
    repo.stage({"pkg/debt.py": branchy("debt", 6) + "\n\ndef fresh():\n    return 1\n"})
    assert repo.run("kiss-staged") == 0


def test_census_fires_on_findings_and_orphans_and_passes_when_wired(repo: Repo, capsys) -> None:
    repo.commit({"pkg/__init__.py": "from pkg import used\n", "pkg/used.py": "VALUE = 1\n", "pkg/lonely.py": "UNUSED = 1\n"})
    assert repo.run("kiss-census") == 1
    assert "orphan_module" in capsys.readouterr().out
    repo.commit({"pkg/__init__.py": "from pkg import lonely, used\n"})
    assert repo.run("kiss-census") == 0
