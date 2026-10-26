"""End-to-end public-surface claim proof for PIPE-PAGES-R020.6."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from pipelines_hooks.core.gitenv import sanitized_env
from tests.hooks.conftest import Repo


# spec: PIPE-PAGES-R020.6
def test_public_surface_hook_fails_on_stale_claim(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.commit(
        {
            "README.md": (
                "# fixture\n\n<!-- claim:path docs/missing.md -->\n\n## Installation\n\n```bash\nuv sync\n```\n"
            )
        },
        "docs",
    )
    assert repo.run("public-surface") == 1
    output = capsys.readouterr().out
    assert "README.md:3 path docs/missing.md" in output
    assert "claims: checked 1, unresolved 1" in output


# spec: PIPE-PAGES-R020.3
def test_installed_cli_checks_an_ordinary_document_claim(repo: Repo) -> None:
    repo.commit(
        {
            "README.md": "# fixture\n\n## Installation\n\n```bash\nuv sync\n```\n",
            "mkdocs.yml": "site_name: fixture\ndocs_dir: docs\n",
            "docs/guide.md": (
                "# Guide\n\n<!-- claim:path docs/asset.md -->\n<!-- claim:command scripts/bootstrap.sh -->\n"
            ),
            "docs/asset.md": "# Asset\n",
            "scripts/bootstrap.sh": "#!/bin/sh\n",
        },
        "docs",
    )
    executable = shutil.which("pipelines-hook")
    assert executable is not None
    result = subprocess.run(
        [executable, "public-surface", "--root", str(repo.root)],
        cwd=repo.root,
        env=sanitized_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "claims: checked 2, unresolved 0" in result.stdout


# spec: PIPE-PAGES-R020.4
@pytest.mark.parametrize(
    "comment",
    [
        "<!-- claim:path -->",
        "<!-- claim:unknown docs/guide.md -->",
        "<!-- claim:path docs/guide.md",
    ],
)
def test_installed_cli_refuses_malformed_claims(repo: Repo, comment: str) -> None:
    repo.write(
        "README.md",
        f"# fixture\n\n{comment}\n\n## Installation\n\n```bash\nuv sync\n```\n",
    )
    executable = shutil.which("pipelines-hook")
    assert executable is not None
    result = subprocess.run(
        [executable, "public-surface", "--root", str(repo.root)],
        cwd=repo.root,
        env=sanitized_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "README.md:3 claims-unchecked" in result.stderr
