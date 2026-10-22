"""agent-contract warns by default and fails under --strict when setup or the AGENTS.md section is missing."""

from __future__ import annotations

import pytest

from pipelines_hooks.hygiene.agent_contract import ORG_AGENTS, START, END
from tests.hooks import conftest
from tests.hooks.conftest import Repo

# Re-registered here: another test module imports the conftest first, so pytest may not register its fixture.
repo = conftest.repo

SECTION = (
    f"{START}\n## Agent contract\n- **Owner boundary:** x\n- **Setup:** y\n- **Gates:** z\n- **Commits:** w\n"
    f"- [org]({ORG_AGENTS})\n{END}\n"
)


@pytest.mark.spec("PIPE-CONNSPEC-R175")
def test_missing_bootstrap_and_section_warn_without_failing(repo: Repo, capsys) -> None:
    repo.commit({"README.md": "x\n"})
    assert repo.run("agent-contract") == 0
    assert "scripts/bootstrap.sh is not tracked" in capsys.readouterr().out
    assert repo.run("agent-contract", "--strict") == 1
    repo.commit({"AGENTS.md": "# a\n", "scripts/bootstrap.sh": "#!/bin/sh\n"})
    assert repo.run("agent-contract", "--strict") == 1
    assert "lacks the" in capsys.readouterr().out


@pytest.mark.spec("PIPE-CONNSPEC-R175")
def test_a_conformant_repository_passes_strict(repo: Repo) -> None:
    repo.commit({"AGENTS.md": "# a\n\n" + SECTION, "scripts/bootstrap.sh": "#!/bin/sh\n"})
    assert repo.run("agent-contract", "--strict") == 0
    repo.commit({"AGENTS.md": "# a\n\n" + SECTION.replace("**Gates:**", "gates")})
    assert repo.run("agent-contract", "--strict") == 1


@pytest.mark.spec("PIPE-CONNSPEC-R175")
def test_bootstrap_that_pipes_a_network_response_into_a_shell_is_flagged(repo: Repo, capsys) -> None:
    piped = "#!/bin/sh\npip install uv || curl -LsSf https://astral.sh/uv/install.sh | sh\n"
    repo.commit({"AGENTS.md": "# a\n\n" + SECTION, "scripts/bootstrap.sh": piped})
    assert repo.run("agent-contract", "--strict") == 1
    assert "scripts/bootstrap.sh:2: SC-INSTALL-001" in capsys.readouterr().out
    clean = "#!/bin/sh\n# curl x | sh is only a comment\npython3 -m pip install --user uv\n"
    repo.commit({"scripts/bootstrap.sh": clean})
    assert repo.run("agent-contract", "--strict") == 0
