"""The AU copy's acceptance survives deletion and shared-gate adoption."""

import pytest

from pipelines_hooks.hygiene.gitignore import REQUIRED

AU_REQUIRED = {
    "dist/",
    "dist-*/",
    "sdist/",
    "build/",
    "target/",
    "target-*/",
    ".venv/",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".hypothesis/",
    ".pytest_tmp/",
    "node_modules/",
    ".kissconfig",
    "reports/",
    "scratch/",
}


@pytest.mark.spec("PIPE-VALIDATION-R001.6")
@pytest.mark.parametrize(
    "path",
    [
        "dist/x",
        "dist-proof/x",
        "build/x",
        "build-proof/x",
        "target/x",
        "target-proof/x",
    ],
)
def test_au_ignore_acceptance_is_retained(repo, path):
    assert AU_REQUIRED <= REQUIRED
    repo.write(".gitignore", "\n".join(sorted(REQUIRED)) + "\n")
    repo.stage({"build_backend.py": "# source\n", "build.rs": "// source\n"})
    assert repo.run("gitignore-convergence") == 0
    repo.write(path, "tracked output\n")
    repo.git("add", "-f", "--", path)
    assert repo.run("gitignore-convergence") == 1


@pytest.mark.spec("PIPE-VALIDATION-R001.6")
@pytest.mark.parametrize("missing", sorted(AU_REQUIRED))
def test_each_au_ignore_pattern_remains_required(repo, missing):
    repo.write(".gitignore", "\n".join(sorted(REQUIRED - {missing})) + "\n")
    assert repo.run("gitignore-convergence") == 1
