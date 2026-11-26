"""PIPE-GATES-R100: a repository's specs use its glossary and the ontology mapping."""

from __future__ import annotations

from tests.hooks.conftest import Repo

GLOSSARY = """# Glossary

| Term | Class | Synonyms |
|---|---|---|
| seam | Contract | boundary, interface |
| row | RequirementRow | line item |
"""
BAD_GLOSSARY = GLOSSARY + "| nothing | | |\n| thing | NoSuchClass | |\n| Seam | Contract | |\n"
ROWS = (
    "| ID | Requirement | Test |\n|---|---|---|\n"
    "| `DEMO-R001` | **A seam.** Depends: none. Refusal: exit 1 names the row. | Test: `tests/test_a.py::test_a`. |\n"
)
BAD_ROWS = (
    "| ID | Requirement | Test |\n|---|---|---|\n"
    "| `DEMO-R001` | **A boundary.** Uses the `interface` code. Depends: none. | Test: `tests/test_a.py::test_a`. |\n"
    "| `DEMO-R002` | **No fields.** | |\n"
    "| `DEMO-R003` | **Vague refusal.** Depends: none. Refusal: it fails. | Test: `tests/t.py::t`. |\n"
)


def _stage(repo: Repo, glossary: str, rows: str) -> None:
    repo.stage({"specs/glossary.md": glossary, "specs/demo/requirements.md": rows})


# spec: PIPE-GATES-R100
def test_unmapped_unknown_duplicate_and_synonym_terms_are_findings(repo: Repo, capsys) -> None:
    _stage(repo, BAD_GLOSSARY, BAD_ROWS)
    assert repo.run("spec-glossary", "--base", "HEAD") == 1
    out = capsys.readouterr().out
    assert "glossary.md:7: term 'nothing' has no class; expected one of" in out
    assert "glossary.md:8: term 'thing' maps to unknown class 'NoSuchClass'" in out
    assert "glossary.md:9: duplicate term 'Seam' (first at line 5)" in out
    assert "row DEMO-R001 uses 'boundary', a synonym of the defined term 'seam'" in out
    assert "DEMO-R002 lacks a typed 'Depends:' field" in out
    assert "DEMO-R002 lacks a typed 'Test:' field" in out
    assert "DEMO-R003 has a Refusal: clause with no exit status or code" in out


# spec: PIPE-GATES-R100
def test_a_mapped_glossary_passes(repo: Repo, capsys) -> None:
    _stage(repo, GLOSSARY, ROWS)
    assert repo.run("spec-glossary", "--base", "HEAD") == 0
    assert "spec-glossary: clean" in capsys.readouterr().out


# spec: PIPE-GATES-R100
def test_an_untouched_spec_and_a_custom_glossary_path(repo: Repo, capsys) -> None:
    repo.commit({"specs/vocab.md": GLOSSARY, "specs/demo/requirements.md": BAD_ROWS}, "old spec")
    assert repo.run("spec-glossary", "--glossary", "specs/vocab.md", "--base", "HEAD") == 0
    out = capsys.readouterr().out
    assert "ADV spec-glossary:" in out and "uses 'boundary'" in out
