"""The public README/AGENTS contract accepts polished docs and rejects drift."""

from __future__ import annotations

from pipelines_hooks.docs.public_surface_constants import GITHUB_BADGES, PYPI_BADGES
from tests.hooks.conftest import Repo


def _config(*, distribution: str | None = "fixture", mcp_server: bool = False) -> str:
    optional = f'\ndistribution = "{distribution}"' if distribution else ""
    return (
        '[project]\nname = "fixture"\nversion = "0"\n\n'
        '[tool.pipelines_hooks]\npackages = ["pkg"]\n\n'
        "[tool.pipelines_hooks.public_surface]\n"
        'repository = "Knuckles-Team/fixture"\n'
        f"{optional}\n"
        'pages_url = "https://knuckles-team.github.io/fixture/"\n'
        f"mcp_server = {str(mcp_server).lower()}\n"
    )


def _readme(*, distribution: str | None = "fixture", mcp_server: bool = False, extra: str = "") -> str:
    badges = [
        f"![{alt}]({url.format(repository='Knuckles-Team/fixture', distribution=distribution or '')})"
        for alt, url in GITHUB_BADGES
    ]
    if distribution:
        badges.extend(
            f"![{alt}]({url.format(repository='Knuckles-Team/fixture', distribution=distribution)})"
            for alt, url in PYPI_BADGES
        )
    if mcp_server:
        badges.append("![MCP Server](https://badge.mcpx.dev?type=server 'MCP Server')")
    paragraphs = " ".join(
        [
            "Pipelines supplies reproducible quality gates and reusable GitHub Actions for the agent ecosystem.",
            "The package keeps policy in each consuming repository while one implementation provides deterministic checks.",
            "Every result is local and reviewable, so contributors can repair a finding before opening a change.",
        ]
        * 4
    )
    return (
        "# fixture\n\n"
        + "\n".join(badges)
        + "\n\n"
        + "## Overview\n\n"
        + paragraphs
        + "\n\n## Key capabilities\n\nReusable hooks, release workflows, and Pages delivery templates keep repository conventions aligned.\n\n"
        + "## Documentation\n\nRead the [local guide](docs/guide.md) or visit the [Pages site](https://knuckles-team.github.io/fixture/).\n\n"
        + "## Architecture\n\nThe hook entry point reads repository-local TOML settings and returns stable exit classes.\n\n"
        + "## Quick start\n\nInstall the package, then run its public-surface check:\n\n```bash\npython -m pip install fixture\nfixture --help\n```\n\n"
        + "## Contributing\n\nRun the test suite with `pytest -q` and keep changes covered by focused fixtures.\n\n"
        + "## License\n\nThis project is released under the repository license.\n"
        + extra
    )


def _agents(*, extra: str = "") -> str:
    return (
        "# fixture engineering contract\n\n"
        "This file describes the current repository contract for contributors and automation.\n\n"
        "## What this repository owns\n\nThe package owns validation, reporting, and the repository-local policy contract.\n\n"
        "## Architecture and module map\n\nThe package exposes one command-line entry point; Python implementation lives under `pkg`, with tests and documentation in their named directories.\n\n"
        "## Commands\n\nUse `pytest -q` for tests and `pre-commit run --all-files` for the complete local check.\n\n"
        "## Quality gates\n\nRun `pytest -q` and `pre-commit run --all-files`; a failed gate is fixed at its source.\n\n"
        "## Development rules\n\nUse a clean branch, make focused changes, and add positive and adversarial fixtures for each invariant.\n\n"
        "## Documentation\n\nThe README is the concise entry point; deeper references belong in the Pages site.\n\n"
        "## Branching & isolation\n\nKeep changes in an explicit branch or worktree and never mix unrelated edits or shared credentials.\n\n"
        "## Release\n\nRelease automation builds from a reviewed commit and publishes only after the required checks succeed.\n"
        "\nThe contract is intentionally short enough to review as one current-state document. Detailed API and workflow references belong in the Pages site, while this file records ownership, commands, and the invariants that contributors must preserve. Changes are reviewed against these statements and the executable fixtures so the written contract stays aligned with the implementation.\n"
        + extra
    )


def _plant(repo: Repo, *, distribution: str | None = "fixture", mcp_server: bool = False) -> None:
    repo.commit(
        {
            "pyproject.toml": _config(distribution=distribution, mcp_server=mcp_server),
            "README.md": _readme(distribution=distribution, mcp_server=mcp_server),
            "AGENTS.md": _agents(),
            "docs/guide.md": "# Guide\n\nLocal usage details.\n",
        },
        "docs",
    )


def test_public_surface_accepts_package_docs(repo: Repo) -> None:
    _plant(repo)
    assert repo.run("public-surface") == 0


def test_public_surface_accepts_non_package_docs_without_pypi_badges(repo: Repo) -> None:
    _plant(repo, distribution=None)
    assert repo.run("public-surface") == 0


def test_public_surface_rejects_a_separate_installation_heading(repo: Repo) -> None:
    _plant(repo)
    readme = _readme().replace(
        "## Quick start", "## Installation\n\nInstall the package.\n\n## Quick start"
    )
    repo.commit({"README.md": readme}, "duplicate installation heading")
    assert repo.run("public-surface") == 1


def test_public_surface_accepts_an_mcp_server_only_when_configured(repo: Repo) -> None:
    _plant(repo, mcp_server=True)
    assert repo.run("public-surface") == 0


def test_public_surface_rejects_missing_heading_and_wrong_badge(repo: Repo) -> None:
    _plant(repo)
    repo.commit(
        {
            "README.md": _readme().replace("## Key capabilities", "## Features").replace(
                "https://img.shields.io/github/stars/Knuckles-Team/fixture",
                "https://example.invalid/stars",
            )
        },
        "bad docs",
    )
    assert repo.run("public-surface") == 1


def test_public_surface_rejects_reordered_root_sections(repo: Repo) -> None:
    _plant(repo)
    readme = _readme().replace("## Documentation", "## TEMP", 1)
    readme = readme.replace("## Architecture", "## Documentation", 1)
    readme = readme.replace("## TEMP", "## Architecture", 1)
    repo.commit({"README.md": readme}, "reordered root sections")
    assert repo.run("public-surface") == 1


def test_public_surface_requires_fenced_install_and_run_commands(repo: Repo) -> None:
    _plant(repo)
    no_install = _readme().replace(
        "python -m pip install fixture", "echo python -m pip install fixture"
    )
    repo.commit({"README.md": no_install}, "missing install command")
    assert repo.run("public-surface") == 1
    no_run = _readme().replace("fixture --help", "echo run omitted").replace(
        "pre-commit run --all-files", "echo alternate run omitted"
    )
    repo.commit({"README.md": no_run}, "missing run command")
    assert repo.run("public-surface") == 1


def test_public_surface_rejects_verbose_root_readme_dump(repo: Repo) -> None:
    _plant(repo)
    large = _readme(extra="\n" + ("Detailed reference paragraph.\n" * 220))
    repo.commit({"README.md": large}, "verbose root README")
    assert repo.run("public-surface") == 1


def test_public_surface_rejects_mcp_mismatch_and_escaping_link(repo: Repo) -> None:
    _plant(repo)
    repo.commit(
        {
            "README.md": _readme(
                extra="\n[escape](../../etc/passwd)\n![MCP Server](https://badge.mcpx.dev?type=server)"
            )
        },
        "bad links",
    )
    assert repo.run("public-surface") == 1


def test_public_surface_rejects_public_history_and_incomplete_agents(repo: Repo) -> None:
    _plant(repo)
    repo.commit(
        {
            "README.md": _readme(extra="\nThis is the historical refactor program path: /home/user/repo.\n"),
            "AGENTS.md": _agents(extra="\n## Historical notes\n\nPreviously this used a legacy path.\n"),
        },
        "bad history",
    )
    assert repo.run("public-surface") == 1


def test_public_surface_configuration_fails_closed(repo: Repo) -> None:
    _plant(repo)
    repo.commit(
        {"pyproject.toml": _config().replace("mcp_server = false", 'mcp_server = "false"')},
        "bad config",
    )
    assert repo.run("public-surface") == 2
