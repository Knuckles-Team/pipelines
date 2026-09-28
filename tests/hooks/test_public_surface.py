"""public-surface fails only on reader-visible breakage: dead links and no way to start."""

from __future__ import annotations

import pytest

from tests.hooks.conftest import Repo

README = (
    "# fixture\n\n"
    "![Logo](docs/logo.svg) ![PyPI](https://img.shields.io/pypi/v/fixture)\n\n"
    "Read the [guide](docs/guide.md#usage) or the [site](https://example.org/fixture/).\n\n"
    "## Installation\n\n```bash\npython -m pip install fixture\n```\n"
)


def _plant(repo: Repo, readme: str = README, **extra: str) -> None:
    repo.commit({"README.md": readme, "docs/guide.md": "# Guide\n", "docs/logo.svg": "<svg/>\n", **extra}, "docs")


def test_accepts_a_readme_with_live_links_and_an_install_section(repo: Repo) -> None:
    _plant(repo)
    assert repo.run("public-surface") == 0


@pytest.mark.parametrize(
    "prose",
    [
        "This used to be the legacy path; previously it was formerly superseded.",
        "Reference paragraph.\n" * 400,
        "## Random heading\n\n## Another\n\n# Second H1\n",
    ],
)
def test_wording_length_and_layout_are_not_gated(repo: Repo, prose: str) -> None:
    _plant(repo, README + "\n" + prose + "\n")
    assert repo.run("public-surface") == 0


def test_agents_md_is_optional_and_needs_no_fixed_headings(repo: Repo) -> None:
    _plant(repo, **{"AGENTS.md": "# Agents\n\nSee [README](README.md).\n"})
    assert repo.run("public-surface") == 0


@pytest.mark.parametrize(
    "heading",
    ["## Quick start", "## Quickstart", "### Getting started", "## Install", "## Usage", "## Setup"],
)
def test_any_quick_start_style_heading_is_enough(repo: Repo, heading: str) -> None:
    _plant(repo, f"# fixture\n\n{heading}\n\nSee the guide.\n")
    assert repo.run("public-surface") == 0


def test_a_fenced_install_command_without_a_heading_is_enough(repo: Repo) -> None:
    _plant(repo, "# fixture\n\n```bash\nuv tool install fixture\n```\n")
    assert repo.run("public-surface") == 0


def test_fires_when_the_readme_never_says_how_to_start(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    _plant(repo, "# fixture\n\n## Overview\n\nA library.\n\n```text\n## Install\n```\n")
    assert repo.run("public-surface") == 1
    assert "no quick start" in capsys.readouterr().out


def test_fires_when_the_readme_is_missing(repo: Repo) -> None:
    assert repo.run("public-surface") == 1


@pytest.mark.parametrize(
    ("link", "finding"),
    [
        ("[gone](docs/missing.md)", "does not exist"),
        ("![gone](docs/missing.png)", "does not exist"),
        ("[escape](../../etc/passwd)", "escapes the repository"),
        ("[abs](/etc/passwd)", "is absolute"),
        ("[file](file:///etc/passwd)", "forbidden URL scheme"),
    ],
)
def test_fires_on_a_broken_or_non_portable_link(
    repo: Repo, capsys: pytest.CaptureFixture[str], link: str, finding: str
) -> None:
    _plant(repo, README + f"\n{link}\n")
    assert repo.run("public-surface") == 1
    assert finding in capsys.readouterr().out


def test_fires_on_a_broken_link_in_agents_md(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    _plant(repo, **{"AGENTS.md": "# Agents\n\nSee [spec](specs/absent.md).\n"})
    assert repo.run("public-surface") == 1
    assert "AGENTS.md local link does not exist" in capsys.readouterr().out


def test_links_inside_code_are_examples_not_references(repo: Repo) -> None:
    _plant(repo, README + "\n`[x](nope.md)`\n\n```md\n[y](also-nope.md)\n```\n")
    assert repo.run("public-surface") == 0
