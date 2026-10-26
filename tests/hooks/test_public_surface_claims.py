"""End-to-end public-surface claim proof for PIPE-PAGES-R020.6."""

from __future__ import annotations

import pytest

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
