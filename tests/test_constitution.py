"""The organization constitution: traced articles, generated sections and repository inheritance."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from scripts import check_public_specs, constitution

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / ".specify" / "memory" / "constitution.md"
TEMPLATE = ROOT / "specs" / "_template" / "constitution.md"
VERSION = re.compile(
    r"\*\*Version\*\*: (\d+\.\d+\.\d+) \| \*\*Ratified\*\*: (\d{4}-\d{2}-\d{2}) \| \*\*Last amended\*\*: (\d{4}-\d{2}-\d{2})"
)
PRIVATE = re.compile(rf"{check_public_specs.PRIVATE.pattern}|\b[A-Z]{{1,2}}\d{{3,4}}\b|/srv/|/mnt/", re.IGNORECASE)
CITED = re.compile(
    r"`((?:tests|reference|scripts|pipelines_hooks|templates|specs|\.config|\.github)/[^`\s]+?)(?:::[^`]*)?`"
)


def _bodies() -> list[tuple[str, str]]:
    text = FILE.read_text(encoding="utf-8").split("## Core Principles", 1)[1].split("## Additional Constraints", 1)[0]
    chunks = re.split(r"^### ", text, flags=re.MULTILINE)[1:]
    return [(chunk.split("\n", 1)[0], chunk) for chunk in chunks]


def test_every_article_is_traced_and_has_a_plan_check() -> None:
    # spec: PIPE-GATES-R031
    bodies = _bodies()
    assert len(bodies) >= 20
    for title, body in bodies:
        assert "*Rationale*:" in body, title
        assert "**Enforced by:**" in body, title
        assert re.search(r"<!-- generated:begin constitution hooks: [\w, -]+ -->", body), title
        assert re.search(r"Standards and tests:\n\n- ", body), title
        checks = re.findall(r"^\*\*Plan check:\*\* (.+\?)$", body, flags=re.MULTILINE)
        assert len(checks) == 1, title
    text = FILE.read_text(encoding="utf-8")
    for heading in ("## Additional Constraints", "## Development Workflow", "## Governance"):
        assert heading in text
    assert VERSION.search(text)


def test_every_cited_path_exists() -> None:
    # spec: PIPE-GATES-R031
    cited = set(CITED.findall(FILE.read_text(encoding="utf-8")))
    assert cited
    missing = sorted(path for path in cited if not (ROOT / path).exists())
    assert missing == []


def test_constitution_names_nothing_private() -> None:
    # spec: PIPE-GATES-R031
    for path in (FILE, TEMPLATE):
        assert PRIVATE.findall(path.read_text(encoding="utf-8")) == [], path.name


def test_generated_sections_match_the_file() -> None:
    # spec: PIPE-GATES-R032
    text = FILE.read_text(encoding="utf-8")
    assert constitution.render(ROOT, text) == text


def test_check_fails_on_a_stale_file(tmp_path, capsys) -> None:
    # spec: PIPE-GATES-R032
    stale = tmp_path / "constitution.md"
    text = FILE.read_text(encoding="utf-8")
    stale.write_text(
        text.replace("| Cyclomatic complexity per function | 10 |", "| Cyclomatic complexity per function | 99 |")
    )
    before = stale.read_text(encoding="utf-8")
    assert before != text
    assert constitution.main(["--check", "--file", str(stale)]) == 1
    assert stale.read_text(encoding="utf-8") == before
    assert "out of date" in capsys.readouterr().err
    assert constitution.main(["--file", str(stale)]) == 0
    assert stale.read_text(encoding="utf-8") == text
    assert constitution.main(["--check", "--file", str(stale)]) == 0


def test_unknown_hook_id_fails_the_render() -> None:
    # spec: PIPE-GATES-R032
    text = "<!-- generated:begin constitution hooks: no-such-hook -->\n<!-- generated:end -->\n"
    with pytest.raises(SystemExit, match="no-such-hook"):
        constitution.render(ROOT, text)


def test_precommit_runs_the_check() -> None:
    # spec: PIPE-GATES-R032
    config = yaml.safe_load((ROOT / ".config" / "pre-commit.yaml").read_text(encoding="utf-8"))
    local = {hook["id"]: hook for repo in config["repos"] if repo["repo"] == "local" for hook in repo["hooks"]}
    assert local["constitution"]["entry"].endswith("scripts/constitution.py --check")


def test_repository_template_inherits_the_current_version() -> None:
    # spec: PIPE-GATES-R033
    version = VERSION.search(FILE.read_text(encoding="utf-8"))
    assert version is not None
    template = TEMPLATE.read_text(encoding="utf-8")
    assert f"**Inherits**: organization constitution v{version.group(1)}" in template
    assert "https://github.com/Knuckles-Team/pipelines/blob/main/.specify/memory/constitution.md" in template
    assert "## Repository articles" in template and "## Repository limits" in template
