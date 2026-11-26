"""Planted-violation tests for the hooks whose other tests do not run the hook itself (PIPE-GATES-R066).

Each hook runs on a planted violation and on a clean tree, through the registry that
``pipelines-hook`` serves.
"""

from __future__ import annotations

import json

from pipelines_hooks.cli import main
from pipelines_hooks.specs.templates_sync import TEMPLATES
from tests.hooks.conftest import Repo


def test_spec_templates_hook_refuses_a_drifted_copy_and_passes_a_vended_one(repo: Repo) -> None:
    repo.stage({f"{TEMPLATES}/spec-template.md": "drifted\n"})
    assert repo.run("spec-templates", "--strict") == 1
    assert repo.run("spec-templates", "--write") == 0
    assert repo.run("spec-templates", "--strict") == 0


def test_spec_standard_hook_passes_a_tree_without_specs_and_refuses_a_malformed_spec(repo: Repo) -> None:
    repo.stage({"README.md": "# fixture\n"})
    assert repo.run("spec-standard") == 0
    repo.stage({"specs/Bad_Name/spec.md": "no title\n"})
    assert repo.run("spec-standard") == 1


def test_packaging_roles_hook_refuses_a_missing_contract(tmp_path) -> None:
    args = ["--wheel", str(tmp_path / "none.whl"), "--wheel-sha256", "0" * 64, "--receipt", str(tmp_path / "r.json")]
    assert main(["packaging-roles", "--contract", str(tmp_path / "missing.json"), *args]) == 2
    assert not (tmp_path / "r.json").exists()


def test_spec_bind_suggest_hook_refuses_a_foreign_root_and_reports_nothing_for_a_clean_tree(
    repo: Repo, tmp_path, capsys
) -> None:
    assert repo.run("spec-bind-suggest", "--root", str(tmp_path / "not-a-repository")) == 2
    repo.commit({"README.md": "# fixture\n"}, "initial")
    capsys.readouterr()
    assert repo.run("spec-bind-suggest") == 0
    assert json.loads(capsys.readouterr().out)["candidates"] == []


def test_spec_prefix_rename_hook_refuses_a_bad_pair_and_renames_with_a_good_one(repo: Repo, capsys) -> None:
    repo.commit({"specs/demo/requirements.md": "| `OLD-R001` | **Row.** |\n"}, "initial")
    assert repo.run("spec-prefix-rename", "--map", "OLD=NEW", "--dry-run") == 2
    assert repo.run("spec-prefix-rename", "--map", "OLD-=NEW-", "--dry-run") == 0
    assert "(dry run)" in capsys.readouterr().out


def test_readme_deploy_block_hook_refuses_a_missing_block_and_passes_a_well_formed_one(repo: Repo) -> None:
    begin = "<!-- BEGIN GENERATED: additional-deployment-options -->"
    end = "<!-- END GENERATED: additional-deployment-options -->"
    repo.stage({"README.md": "# fixture\n"})
    assert repo.run("readme-deploy-block") == 1
    repo.stage({"README.md": f"# fixture\n{begin}\nimage: registry/app:1.2.3\n{end}\n"})
    assert repo.run("readme-deploy-block") == 0


def test_harness_bundles_untracked_hook_refuses_a_tracked_bundle_and_passes_a_clean_tree(repo: Repo) -> None:
    pyproject = (
        '[project]\nname = "x"\nversion = "1"\n\n[tool.pipelines.harness_bundles]\n'
        'command = "x"\noutput = "out"\ncatalog = ".codex-plugin/catalog.json"\n'
    )
    repo.stage({"pyproject.toml": pyproject, ".claude-plugin/plugin.json": "{}"})
    assert repo.run("harness-bundles-untracked") == 1
    repo.git("rm", "-q", "-f", "--", ".claude-plugin/plugin.json")
    assert repo.run("harness-bundles-untracked") == 0


def test_ingest_worker_policy_hook_refuses_a_duplicated_value_and_passes_a_citing_row(repo: Repo) -> None:
    cited = (
        "| `X-R1` | The floor is 0.36 of memory, 3 GiB, the reserved floor. Owner: MEDULLA-DURABLE-KERNEL-R075. | t |\n"
    )
    bare = "| `X-R2` | The worker keeps a reserved floor of 3 GiB and admits 0.36 of cores. | t |\n"
    repo.stage({"specs/ingest-worker/requirements.md": cited + bare})
    assert repo.run("ingest-worker-policy") == 1
    repo.stage({"specs/ingest-worker/requirements.md": cited})
    assert repo.run("ingest-worker-policy") == 0
