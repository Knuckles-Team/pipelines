"""Published-boundary evidence for the R031, R035, and R039 quality gates."""

from __future__ import annotations

import json

import pytest
import yaml

from pipelines_hooks import prompt_format
from pipelines_hooks.cli import GATES, main
from tests.hooks.conftest import HOOK_REPOSITORY, Repo


def _published_hooks() -> dict[str, dict]:
    document = yaml.safe_load((HOOK_REPOSITORY / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))
    return {hook["id"]: hook for hook in document}


def _self_run_hooks() -> dict[str, dict]:
    document = yaml.safe_load((HOOK_REPOSITORY / ".config" / "pre-commit.yaml").read_text(encoding="utf-8"))
    return {
        hook["id"]: hook
        for repository in document["repos"]
        if repository["repo"] == "local"
        for hook in repository["hooks"]
    }


@pytest.mark.spec("PIPE-PAGES-R031.3")
def test_source_path_gate_has_published_and_self_run_boundaries(repo: Repo) -> None:
    published = _published_hooks()["source-path-portability"]
    local = _self_run_hooks()["source-path-portability"]
    assert GATES["source-path-portability"] == "pipelines_hooks.hygiene.path_portability"
    assert published["entry"] == "pipelines-hook source-path-portability"
    assert published["stages"] == ["pre-commit", "pre-push"]
    assert published["always_run"] is True
    assert local["entry"].endswith("pipelines-hook source-path-portability")
    assert local["stages"] == ["pre-commit", "pre-push"]
    assert local["always_run"] is True
    assert main(["source-path-portability", "--root", str(repo.root)]) == 0


@pytest.mark.spec("PIPE-PAGES-R031.6")
def test_source_path_published_cli_rejects_then_accepts_fixture(repo: Repo) -> None:
    long_rel = "pkg/" + ("u" * 120) + "/" + ("v" * 120) + "/module.py"
    repo.commit({"pkg/PRN.md": "reserved\n", long_rel: "long\n"}, "plant portability defects")
    assert main(["source-path-portability", "--root", str(repo.root)]) == 1

    repo.git("rm", "-q", "pkg/PRN.md", long_rel)
    repo.git("commit", "-q", "-m", "repair portability defects")
    assert main(["source-path-portability", "--root", str(repo.root)]) == 0


PROMPT = {
    "task": "pages-published-boundary",
    "type": "prompt",
    "schema_version": "1.0",
    "instructions": {"core_directive": "Preserve the prompt's semantic values."},
}


@pytest.mark.spec("PIPE-PAGES-R035.3")
def test_prompt_format_gate_has_published_and_self_run_boundaries() -> None:
    published = _published_hooks()["prompt-format"]
    local = _self_run_hooks()["prompt-format"]
    assert GATES["prompt-format"] == "pipelines_hooks.prompt_format"
    assert published["entry"] == "pipelines-hook prompt-format"
    assert published["stages"] == ["pre-commit", "pre-push"]
    assert published["always_run"] is True
    assert local["entry"].endswith("pipelines-hook prompt-format")
    assert local["stages"] == ["pre-commit", "pre-push"]
    assert local["always_run"] is True


@pytest.mark.spec("PIPE-PAGES-R035.6")
def test_prompt_format_published_cli_rejects_then_accepts_fixture(repo: Repo) -> None:
    prompt_path = repo.root / "prompts" / "demo.json"
    prompt_path.parent.mkdir(parents=True)
    canonical = prompt_format.serialize_prompt(PROMPT)
    prompt_path.write_bytes(canonical)
    assert main(["prompt-format", "--root", str(repo.root)]) == 0

    prompt_path.write_text(json.dumps(PROMPT, indent=4), encoding="utf-8")
    assert main(["prompt-format", "--root", str(repo.root)]) == 1

    prompt_path.write_bytes(canonical)
    assert main(["prompt-format", "--root", str(repo.root)]) == 0


def _layout_files(*, dependent: bool = False) -> dict[str, str]:
    unit = "def test_unit():\n    pass\n"
    integration = "def test_integration():\n    pass\n"
    if dependent:
        unit = "from pathlib import Path\n\n\ndef test_unit():\n    Path('leak').mkdir()\n    Path('leak/marker').write_text('ready', encoding='utf-8')\n"
        integration = (
            "from pathlib import Path\n\n\ndef test_integration():\n    assert Path('leak/marker').is_file()\n"
        )
    return {
        "pkg/unit.py": "VALUE = 'unit'\n",
        "pkg/integration.py": "VALUE = 'integration'\n",
        "tests/conftest.py": "# shared fixture declaration\n",
        "tests/unit/test_unit.py": unit,
        "tests/integration/test_integration.py": integration,
        "state/marker": "reset\n",
        ".config/test-layout.json": json.dumps(
            {
                "version": 1,
                "projects": [
                    {
                        "name": "fixture-project",
                        "unit_module_roots": ["tests/unit"],
                        "integration_module_roots": ["tests/integration"],
                        "shared_fixture_locations": ["tests/conftest.py"],
                        "required_category_modules": ["pkg/unit.py", "pkg/integration.py"],
                        "isolation_boundaries": ["state"],
                        "reset_contracts": ["state"],
                    }
                ],
                "shuffle_seeds": [11, 29],
                "timeout_seconds": 10,
            }
        ),
    }


@pytest.mark.spec("PIPE-PAGES-R039.3")
def test_test_layout_gate_has_published_and_self_run_boundaries() -> None:
    published = _published_hooks()["test-layout"]
    local = _self_run_hooks()["test-layout"]
    assert GATES["test-layout"] == "pipelines_hooks.ci_replica.test_layout"
    assert published["entry"] == "pipelines-hook test-layout"
    assert published["additional_dependencies"] == ["pytest==9.1.1"]
    assert published["stages"] == ["pre-push", "manual"]
    assert published["always_run"] is True
    assert local["entry"].endswith("pipelines-hook test-layout")
    assert local["stages"] == ["pre-push", "manual"]
    assert local["files"] == r"^\.config/test-layout\.(json|toml)$"


@pytest.mark.spec("PIPE-PAGES-R039.6")
def test_test_layout_published_cli_blocks_planted_order_dependency(repo: Repo) -> None:
    repo.commit(_layout_files(), "valid layout fixture")
    assert main(["test-layout", "--root", str(repo.root), "--inventory", ".config/test-layout.json"]) == 0

    repo.commit(_layout_files(dependent=True), "plant order dependency")
    assert main(["test-layout", "--root", str(repo.root), "--inventory", ".config/test-layout.json"]) == 1

    repo.commit(_layout_files(), "repair order dependency")
    assert main(["test-layout", "--root", str(repo.root), "--inventory", ".config/test-layout.json"]) == 0
