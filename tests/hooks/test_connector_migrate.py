"""connector-ontology-map migrate: each transform on a fixture connector (PIPE-GATES-R016.10 to R016.15)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipelines_hooks.hygiene import connector_migrate as cm

PYPROJECT = """[project]
name = "demo-agent"
version = "1.0.4"
dependencies = [ "agent-connector-sdk[mcp]>=0.3.18,<1.0.0", "requests",]

[project.entry-points."agent_connector_sdk.connector"]
demo-mcp = "demo_agent"

[tool.setuptools.package-data]
demo_agent = [ "connector_manifest.yml", "prompts/**", "ontology/**", "connectors/**",]
"""
BUMP = """[bumpversion]
current_version = 1.0.4
commit = True

[bumpversion:file:pyproject.toml]
search = version = "{current_version}"
replace = version = "{new_version}"

[bumpversion:file(docker-img):docker/Dockerfile]
search = =={current_version}"
replace = =={new_version}"
"""
MANIFEST = {
    "connector": "demo-mcp",
    "resources": [{"name": "Thing", "label": "Thing", "id_prefix": "thing", "relations": []}],
    "schema_mappings": {"Thing": {"ontology_class": "Item", "fields": {"a": "xsd:string"}}},
    "sync": [{"preset": "demo-things", "raw": {"server": "demo-mcp", "tool": "demo_get_things"}}],
}
PRESETS = {
    "_comment": "x",
    "demo-things": {
        "server": "demo-mcp",
        "tool": "demo_get_things",
        "records_path": "data",
        "id_field": "id",
        "title_field": "name",
        "updated_field": "updated_at",
        "pagination": "page",
        "page_param": "page",
        "page_kind": "number",
        "doc_type": "thing",
        "params_style": "args",
    },
}
INGEST = {
    "connector": "demo-mcp",
    "sources": [
        {
            "source_id": "things",
            "record_type": "Thing",
            "tools": ["demo_get_things"],
            "id_field": "id",
            "incremental": True,
            "cursor_field": "updated_at",
            "arguments": {"per_page": 50},
        }
    ],
}
PROMPT = """{
  "task": "t",
  "extends": "agent-connector-sdk:base",
  "compose": "append",
  "skills": ["a", "b"]
}
"""
TEST = '''"""sources"""

from pathlib import Path

import pytest
import yaml
from agent_connector_sdk.ingest.sources import load_ingest_sources

import demo_agent


@pytest.mark.spec("CONN-DEMO-R001")
def test_sources() -> None:
    declaration = load_ingest_sources(Path(demo_agent.__file__).parent)
    manifest = yaml.safe_load(
        (Path(demo_agent.__file__).parent / "connector_manifest.yml").read_text("utf-8")
    )
    assert declaration.source("things").record_type in manifest["schema_mappings"]
'''


def make(tmp_path: Path) -> Path:
    root = tmp_path / "demo-agent"
    pkg = root / "demo_agent"
    for d in (pkg / "ontology", pkg / "connectors", pkg / "prompts", root / "tests", root / "docker"):
        d.mkdir(parents=True)
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (root / ".bumpversion.cfg").write_text(BUMP, encoding="utf-8")
    (root / "docker" / "Dockerfile").write_text('RUN pip install "demo-agent==1.0.4"\n', encoding="utf-8")
    (root / "MANIFEST.in").write_text("include README.md\ninclude connector_manifest.yml\n", encoding="utf-8")
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    import yaml

    (pkg / "connector_manifest.yml").write_text(yaml.safe_dump(MANIFEST), encoding="utf-8")
    (pkg / "connectors" / "mcp_source_presets.json").write_text(json.dumps(PRESETS), encoding="utf-8")
    (pkg / "connectors" / "tool_schema_fingerprints.json").write_text("{}", encoding="utf-8")
    (pkg / "ontology" / "ingest_sources.json").write_text(json.dumps(INGEST), encoding="utf-8")
    (pkg / "prompts" / "p.json").write_text(PROMPT, encoding="utf-8")
    (root / "tests" / "test_ingest_sources.py").write_text(TEST, encoding="utf-8")
    (root / "tests" / "test_connector_manifest.py").write_text(
        "def test_m():\n    assert 'connector_manifest.yml'\n", encoding="utf-8"
    )
    return root


def run(root: Path) -> dict:
    return cm.migrate(root, None, lock=False)


@pytest.mark.spec("PIPE-GATES-R016.10")
def test_declarations_are_generated_sorted_and_loadable(tmp_path: Path) -> None:
    root = make(tmp_path)
    report = run(root)
    text = (root / "demo_agent" / "connector_sources.py").read_text(encoding="utf-8")
    ns: dict = {}
    # The module imports the SDK; check the literal shape without it.
    # One source per tool: the ingest id wins and the preset id is dropped.
    assert text.count('tool="demo_get_things"') == 1 and 'source_id="things"' in text
    assert "demo-things" not in text
    assert '"per_page": 50' in text and 'id_field="id"' in text and 'title_field="name"' in text
    assert '"page_kind": "number"' in text and 'cursor_field="updated_at"' in text
    assert 'record_type="Thing"' in text and '"ontology_class": "Item"' in text
    assert not [i for i in report["review"] if i["blocking"]]
    del ns


@pytest.mark.spec("PIPE-GATES-R016.10")
def test_record_type_rule_prefers_tool_noun_then_doc_type() -> None:
    assert cm._record_type("gitlab_get_projects", "repository", ["Issue", "Project"]) == "Project"
    assert cm._record_type("x_do", "issue", ["Issue"]) == "Issue"
    assert cm._record_type("x_do", "zzz", ["Issue"]) is None


@pytest.mark.spec("PIPE-GATES-R016.10")
def test_unresolvable_preset_is_a_blocking_review_item(tmp_path: Path) -> None:
    root = make(tmp_path)
    p = root / "demo_agent" / "connectors" / "mcp_source_presets.json"
    p.write_text(json.dumps({"bad": {"tool": "t"}}), encoding="utf-8")
    report = run(root)
    assert any(i["blocking"] and i["step"] == "declarations" for i in report["review"])
    assert not (root / "demo_agent" / "connector_sources.py").exists()
    assert (root / "demo_agent" / "connector_manifest.yml").exists()


@pytest.mark.spec("PIPE-GATES-R016.11")
def test_cut_files_and_packaging_entries_are_removed(tmp_path: Path) -> None:
    root = make(tmp_path)
    report = run(root)
    names = {p.name for p in root.rglob("*") if p.is_file()}
    assert not names & set(cm.CUT_NAMES)
    assert "connector_manifest.yml" not in (root / "pyproject.toml").read_text(encoding="utf-8")
    assert "connector_manifest" not in (root / "MANIFEST.in").read_text(encoding="utf-8")
    assert "README.md" in (root / "MANIFEST.in").read_text(encoding="utf-8")
    assert "demo_agent/connector_manifest.yml" in report["deleted"]


@pytest.mark.spec("PIPE-GATES-R016.12")
def test_prompt_extends_and_compose_are_stripped_keeping_format() -> None:
    new = cm.strip_prompt(PROMPT)
    assert new == '{\n  "task": "t",\n  "skills": ["a", "b"]\n}\n'
    last = '{\n  "task": "t",\n  "extends": "x",\n  "compose": "append"\n}\n'
    assert json.loads(cm.strip_prompt(last) or "") == {"task": "t"}
    assert cm.strip_prompt("{not json") is None


@pytest.mark.spec("PIPE-GATES-R016.13")
def test_sdk_floor_and_patch_bump_follow_the_repo_bump_config(tmp_path: Path) -> None:
    root = make(tmp_path)
    run(root)
    py = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert "agent-connector-sdk[mcp]>=0.4.1,<1.0.0" in py and 'version = "1.0.5"' in py
    assert "current_version = 1.0.5" in (root / ".bumpversion.cfg").read_text(encoding="utf-8")
    assert "==1.0.5" in (root / "docker" / "Dockerfile").read_text(encoding="utf-8")


@pytest.mark.spec("PIPE-GATES-R016.13")
def test_floor_already_at_or_above_leaves_version_alone(tmp_path: Path) -> None:
    root = make(tmp_path)
    py = root / "pyproject.toml"
    py.write_text(py.read_text(encoding="utf-8").replace(">=0.3.18", ">=0.4.2"), encoding="utf-8")
    run(root)
    assert 'version = "1.0.4"' in py.read_text(encoding="utf-8")


@pytest.mark.spec("PIPE-GATES-R016.14")
def test_tests_are_redirected_or_deleted_by_fixed_rules(tmp_path: Path) -> None:
    root = make(tmp_path)
    report = run(root)
    text = (root / "tests" / "test_ingest_sources.py").read_text(encoding="utf-8")
    assert "from demo_agent.connector_sources import declaration as declared_sources" in text
    assert "declared_sources().schema_mappings" in text and "import yaml" not in text
    assert "from pathlib import Path" not in text and "import demo_agent\n" not in text
    assert not (root / "tests" / "test_connector_manifest.py").exists()
    assert "tests/test_connector_manifest.py" in report["deleted"]


@pytest.mark.spec("PIPE-GATES-R016.14")
def test_unmatched_test_goes_to_review_unedited(tmp_path: Path) -> None:
    root = make(tmp_path)
    odd = root / "tests" / "test_odd.py"
    odd.write_text("import json\nx = json.load(open('tool_schema_fingerprints.json'))\n", encoding="utf-8")
    before = odd.read_text(encoding="utf-8")
    report = run(root)
    assert odd.read_text(encoding="utf-8") == before
    assert any(i["path"] == "tests/test_odd.py" and i["blocking"] for i in report["review"])


@pytest.mark.spec("PIPE-GATES-R016.15")
def test_second_run_is_a_no_op_and_output_is_deterministic(tmp_path: Path) -> None:
    a, b = make(tmp_path / "a"), make(tmp_path / "b")
    run(a)
    run(b)
    sa = (a / "demo_agent" / "connector_sources.py").read_text(encoding="utf-8")
    assert sa == (b / "demo_agent" / "connector_sources.py").read_text(encoding="utf-8")
    snapshot = {p.relative_to(a): p.read_bytes() for p in a.rglob("*") if p.is_file()}
    again = run(a)
    assert snapshot == {p.relative_to(a): p.read_bytes() for p in a.rglob("*") if p.is_file()}
    assert again["changed"] == [] and again["deleted"] == []


@pytest.mark.spec("PIPE-GATES-R016.15")
def test_leftover_reference_to_a_cut_file_is_blocking(tmp_path: Path) -> None:
    root = make(tmp_path)
    (root / "scripts").mkdir()
    (root / "scripts" / "gen.py").write_text("OUT = 'connector_manifest.yml'\n", encoding="utf-8")
    report = run(root)
    assert any(i["step"] == "leftover" and i["blocking"] and i["path"] == "scripts/gen.py" for i in report["review"])


@pytest.mark.spec("PIPE-GATES-R016.15")
def test_cli_writes_the_report_and_exit_code_follows_blocking_items(tmp_path: Path) -> None:
    from pipelines_hooks.hygiene import ontology_orphan_map as omap

    root = make(tmp_path)
    out = tmp_path / "r.json"
    assert omap.main(["migrate", "--root", str(root), "--no-lock", "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["changed"]
    (root / "tests" / "test_odd.py").write_text("x = 'mcp_source_presets'\n", encoding="utf-8")
    assert omap.main(["migrate", "--root", str(root), "--no-lock"]) == 2


@pytest.mark.spec("PIPE-GATES-R016.14")
def test_manifest_schema_mapping_reads_are_redirected_and_certification_digests_dropped(tmp_path: Path) -> None:
    root = make(tmp_path)
    (root / "tests" / "test_cq.py").write_text(
        "import yaml\nfrom pathlib import Path\nP = Path('x')\n\n\ndef test_a() -> None:\n"
        "    manifest = yaml.safe_load(\n        (P / 'connector_manifest.yml').read_text('utf-8')\n    )\n"
        "    assert manifest['schema_mappings']\n".replace("['schema_mappings']", '["schema_mappings"]'),
        encoding="utf-8",
    )
    cert = root / "demo_agent" / "ontology" / "certification.json"
    cert.write_text(
        json.dumps(
            {"artifacts": {"connector_manifest.yml": "a", "demo_agent/ontology/x.ttl": "b"}}, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )
    report = run(root)
    text = (root / "tests" / "test_cq.py").read_text(encoding="utf-8")
    assert "declared_sources().schema_mappings" in text and "yaml" not in text
    assert json.loads(cert.read_text(encoding="utf-8"))["artifacts"] == {"demo_agent/ontology/x.ttl": "b"}
    assert not [i for i in report["review"] if i["blocking"]]


@pytest.mark.spec("PIPE-GATES-R016.14")
def test_mapping_item_access_follows_the_declaration_model() -> None:
    text = (
        "import yaml\n\n\ndef test_a() -> None:\n"
        "    manifest = yaml.safe_load(open('x/connector_manifest.yml'))\n"
        '    bad = [n for n, mapping in manifest["schema_mappings"].items() if not mapping["ontology_class"]]\n'
    )
    new, action = cm.rewrite_test(text, "test_x.py", "demo_agent")
    assert action == "rewrite" and new is not None
    assert "if not mapping.ontology_class" in new and "declared_sources().schema_mappings" in new


@pytest.mark.spec("PIPE-GATES-R016.14")
def test_connector_name_read_from_the_manifest_uses_the_entry_point_identity() -> None:
    text = (
        'import json\nimport re\nimport tomllib\nfrom pathlib import Path\n\nPACKAGE = Path("p")\nFLEET = "demo-mcp"\n\n\n'
        "def test_name() -> None:\n"
        '    manifest = (PACKAGE / "connector_manifest.yml").read_text(encoding="utf-8")\n'
        "    match = re.search(r'^connector: (.+)', manifest, re.MULTILINE)\n"
        "    assert match is not None and match.group(1) == FLEET\n"
        '    fingerprints = PACKAGE / "connectors" / "tool_schema_fingerprints.json"\n'
        "    if fingerprints.is_file():\n"
        "        assert (\n"
        '            json.loads(fingerprints.read_text(encoding="utf-8"))["connector"] == FLEET\n'
        "        )\n"
    )
    new, action = cm.rewrite_test(text, "test_fleet_name.py", "demo_agent")
    assert action == "rewrite" and new is not None
    assert 'assert connector_name("demo_agent") == FLEET' in new
    assert "from agent_connector_sdk.connector_identity import connector_name" in new
    assert "connector_manifest" not in new and "fingerprints" not in new
    assert "import re\n" not in new and "import json\n" not in new
    # A manifest reader of anything else is still a review item.
    other = "def test_x():\n    t = open('connector_manifest.yml').read()\n    assert 'actions' in t\n"
    assert cm.rewrite_test(other, "test_other.py", "demo_agent")[1] == "review"


def _driver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verify: str = '{"ok": true}'):
    import argparse
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "connector_migrate_batch", Path(__file__).resolve().parents[2] / "scripts" / "connector_migrate_batch.py"
    )
    assert spec and spec.loader
    drv = importlib.util.module_from_spec(spec)
    sys.modules["connector_migrate_batch"] = drv
    spec.loader.exec_module(drv)
    worktrees = tmp_path / "wt"
    root = make(worktrees / "demo-agent" / "x")
    (worktrees / "demo-agent" / "manifest-cut").symlink_to(root)
    calls: list[list[str]] = []

    def fake(step, cmd, cwd=None, env=None, ok=(0,)):
        calls.append(cmd)
        if "migrate" in cmd:
            report = cm.migrate(Path(cmd[cmd.index("--root") + 1]), None, lock=False)
            Path(cmd[cmd.index("--out") + 1]).write_text(json.dumps(report), encoding="utf-8")
            return ""
        if cmd[:3] == ["git", "diff", "--cached"]:
            return " 5 files changed, 10 insertions(+)\n"
        if any(str(c).endswith("connector_verify.py") for c in cmd):
            return "banner\n" + verify + "\n"
        if "graph-check" in cmd:
            return "ORPHAN_CLASS: 1\n"
        if "pr-test-scope" in cmd:
            return "NONE\n"
        return ""

    monkeypatch.setattr(drv, "sh", fake)
    args = argparse.Namespace(
        fleet=tmp_path / "fleet",
        worktrees=worktrees,
        tmpdir=str(tmp_path / "tmp"),
        eg_repo=tmp_path,
        pipelines_venv=tmp_path,
        sdk_path=None,
        dry_run=True,
        patches=tmp_path / "patches",
        rebump=False,
    )
    return drv, args, drv.Ledger(tmp_path / "ledger.json"), calls


@pytest.mark.spec("PIPE-GATES-R016.16")
def test_driver_dry_run_migrates_commits_verifies_and_records_the_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    drv, args, led, calls = _driver(tmp_path, monkeypatch)
    drv.migrate_repo("demo-agent", args, led)
    row = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))["demo-agent"]
    assert row["status"] == "dry-run-verified" and row["verify"] == {"ok": True}
    assert row["diffstat"].startswith("5 files changed") and row["test_scope"] == "NONE"
    commit = next(c for c in calls if c[:2] == ["git", "commit"])
    assert commit[3] == drv.FIXED_MESSAGE and "--no-verify" not in commit
    assert not any(c[:2] == ["git", "push"] for c in calls)
    assert led.done("demo-agent")


@pytest.mark.spec("PIPE-GATES-R016.16")
def test_driver_failure_stops_that_repo_and_lands_in_the_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    drv, args, led, _ = _driver(tmp_path, monkeypatch)
    (tmp_path / "wt" / "demo-agent" / "manifest-cut" / "tests" / "test_odd.py").write_text(
        "x = 'mcp_source_presets'\n", encoding="utf-8"
    )
    drv.migrate_repo("demo-agent", args, led)
    row = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))["demo-agent"]
    assert row["status"] == "failed" and row["failed_step"] == "migrate" and "test_odd.py" in row["output_tail"]
    assert not led.done("demo-agent")


@pytest.mark.spec("PIPE-GATES-R016.16")
def test_gates_checks_are_read_from_plain_gh_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    drv, _, _, _ = _driver(tmp_path, monkeypatch)
    text = "gates / pre-commit\tpass\t1m\thttps://x\nother\tfail\t1s\thttps://y\ngates / tests\tpending\t0\thttps://z\n"
    assert drv.parse_checks(text) == {"gates / pre-commit": "pass", "gates / tests": "pending"}


@pytest.mark.spec("PIPE-GATES-R016.16")
def test_driver_applies_a_reviewed_per_repo_patch_after_migrate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    drv, args, led, calls = _driver(tmp_path, monkeypatch)
    (tmp_path / "patches").mkdir()
    (tmp_path / "patches" / "demo-agent.patch").write_text("--- a/tests/x.py\n+++ b/tests/x.py\n", encoding="utf-8")
    drv.migrate_repo("demo-agent", args, led)
    row = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))["demo-agent"]
    assert row["repo_patch_files"] == ["tests/x.py"]
    assert any(c[:2] == ["git", "apply"] for c in calls)


@pytest.mark.spec("PIPE-GATES-R016.14")
def test_scaffolded_parent_import_assertion_is_dropped_because_r1_removes_the_import() -> None:
    text = (
        "def test_x(path):\n    triples = []\n"
        '    imports = {o for s, p, o in triples if p == OWL + "imports"}\n'
        '    assert any(i == PARENT_IRI or i.startswith(PARENT_IRI + "/") for i in imports)\n'
        "    assert _orphans(triples) == set()\n"
    )
    new = cm.drop_parent_import_assertion(text)
    assert "imports" not in new and "_orphans(triples) == set()" in new
    assert cm.drop_parent_import_assertion(new) == new


@pytest.mark.spec("PIPE-GATES-R016.16")
def test_driver_runs_tests_without_pytest_plugin_flags_and_merges_by_repo_slug() -> None:
    text = (Path(__file__).resolve().parents[2] / "scripts" / "connector_migrate_batch.py").read_text(encoding="utf-8")
    assert '"-p", "no:cacheprovider"' not in text
    assert '"-R", slug, "--squash"' in text


DOC = """# Demo

Config lives in code.

- `connector_manifest.yml`
- demo_agent/connectors/mcp_source_presets.json
- keep: see `connector_manifest.yml` for the old layout

| File | Purpose |
|---|---|
| `tool_schema_fingerprints.json` | pins |
| `pyproject.toml` | build |

```
demo_agent/
\u251c\u2500\u2500 connector_manifest.yml   # retired
\u2514\u2500\u2500 prompts/
```
"""


@pytest.mark.spec("PIPE-GATES-R016.17")
def test_docs_lines_that_only_name_a_cut_file_are_removed_and_ambiguous_ones_stay() -> None:
    new = cm.strip_doc_mentions(DOC)
    assert "- `connector_manifest.yml`\n" not in new and "mcp_source_presets.json\n" not in new.replace("keep", "")
    assert "tool_schema_fingerprints" not in new and "# retired" not in new
    assert "| `pyproject.toml` | build |" in new and "prompts/" in new
    assert "keep: see `connector_manifest.yml` for the old layout" in new
    assert cm.strip_doc_mentions(new) == new


@pytest.mark.spec("PIPE-GATES-R016.17")
def test_migrate_edits_docs_and_leaves_ambiguous_mentions_as_non_blocking_review(tmp_path: Path) -> None:
    root = make(tmp_path)
    (root / "README.md").write_text(DOC, encoding="utf-8")
    report = run(root)
    assert "README.md" in report["changed"]
    left = [i for i in report["review"] if i["step"] == "leftover" and i["path"] == "README.md"]
    assert left and not left[0]["blocking"]


@pytest.mark.spec("PIPE-GATES-R016.18")
def test_rebump_raises_the_floor_bumps_the_patch_and_touches_nothing_else(tmp_path: Path) -> None:
    root = make(tmp_path)
    py = root / "pyproject.toml"
    py.write_text(py.read_text(encoding="utf-8").replace(">=0.3.18", ">=0.4.0"), encoding="utf-8")
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    report = cm.rebump(root, lock=False)
    assert report["deleted"] == [] and set(report["changed"]) <= {
        "pyproject.toml",
        ".bumpversion.cfg",
        "docker/Dockerfile",
    }
    assert ">=0.4.1" in py.read_text(encoding="utf-8") and 'version = "1.0.5"' in py.read_text(encoding="utf-8")
    after = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert {k for k in after if after[k] != before.get(k)} == {Path(c) for c in report["changed"]}
    assert cm.rebump(root, lock=False)["changed"] == []


FLEET_NAME_TEST = '''"""CONN-X-R002: the connector is filed under its fleet name."""

from __future__ import annotations

import ast
import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "demo_agent"
FLEET = "demo-mcp"


def test_connector_name_is_the_fleet_name() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["entry-points"]["agent_connector_sdk.connector"] == {FLEET: "demo_agent"}
    manifest_path = PACKAGE / "connector_manifest.yml"
    if not manifest_path.is_file():
        manifest_path = ROOT / "connector_manifest.yml"
    manifest = manifest_path.read_text(encoding="utf-8")
    match = re.search(r'^\\s*"?connector"?\\s*:\\s*"?([^"\\s,]+)', manifest, re.MULTILINE)
    assert match is not None and match.group(1) == FLEET
    fingerprints = PACKAGE / "connectors" / "tool_schema_fingerprints.json"
    if fingerprints.is_file():
        assert (
            json.loads(fingerprints.read_text(encoding="utf-8"))["connector"] == FLEET
        )
    assert ast and PACKAGE
'''


@pytest.mark.spec("PIPE-GATES-R016.20")
def test_fleet_name_test_with_manifest_path_fallback_reads_connector_name_instead() -> None:
    new, action = cm.rewrite_test(FLEET_NAME_TEST, "test_fleet_name.py", "demo_agent")
    assert action == "rewrite" and new is not None
    assert 'assert connector_name("demo_agent") == FLEET' in new
    assert "connector_manifest" not in new and "tool_schema_fingerprints" not in new
    assert "import re\n" not in new and "import json\n" not in new and "import ast\n" in new
    assert new.index("from agent_connector_sdk.connector_identity import connector_name") < new.index("import ast")


REF_TEST = """
def test_refs(request, relation_refs) -> None:
    assert request.relationships[0].relation_reference.endswith(
        "resources/Job/relations/launchedFrom"
    )
    assert any(ref.endswith("relations/usesInventory") for ref in relation_refs)
    assert rel.relation_reference.endswith("/relations/onDevice")
    assert rel.relation_reference.endswith(f"/relations/{relationship}")
    assert record.mapping_reference.endswith("schema_mappings/Project")
    assert x == rel.relation_reference.rsplit("/relations/", 1)[-1]
    return f"manifest:{connector}#schema_mappings/{node_type}", f"manifest:{c}#resources/{t}/relations/{r}"
    assert "agent-connector-sdk[mcp]>=0.3.18,<1.0.0" in deps
"""


@pytest.mark.spec("PIPE-GATES-R016.19")
def test_reference_strings_follow_the_live_layout_and_sdk_literals_follow_the_floor() -> None:
    new = cm.rewrite_references(REF_TEST)
    assert '"relations/Job/launchedFrom"' in new and 'endswith("/usesInventory")' in new
    assert 'endswith("/onDevice")' in new and 'endswith(f"/{relationship}")' in new
    assert 'endswith("mappings/Project")' in new and 'rsplit("/", 1)[-1]' in new
    assert 'f"connector:{connector}#mappings/{node_type}"' in new
    assert 'f"connector:{c}#relations/{t}/{r}"' in new
    assert "agent-connector-sdk[mcp]>=0.4.1,<1.0.0" in new
    assert cm.rewrite_references(new) == new


CUT_READS = """import json
from pathlib import Path

import pytest

ROOT = Path(".")


def test_names() -> None:
    assert [
        "LICENSE",
        "demo_agent/connector_manifest.yml",
    ]


@pytest.mark.spec("CONN-X-R003")
def test_presets() -> None:
    presets = json.loads((ROOT / "demo_agent/connectors/mcp_source_presets.json").read_text())
    assert presets


async def test_served() -> None:
    body = await client.read_resource("manifest://connector")
    assert body


def test_other() -> None:
    assert 1
"""


@pytest.mark.spec("PIPE-GATES-R016.20")
def test_list_items_naming_cut_files_and_test_functions_reading_them_are_deleted() -> None:
    text = cm.drop_cut_list_items(CUT_READS)
    assert "demo_agent/connector_manifest.yml" not in text and '"LICENSE"' in text
    new, names, specs = cm.delete_cut_tests(text, cm._CUT_WORDS)
    assert names == ["test_presets", "test_served"] and specs == ["CONN-X-R003"]
    assert "def test_other" in new and "mcp_source_presets" not in new and "manifest://" not in new
    only, _, _ = cm.delete_cut_tests("def test_a():\n    open('connector_manifest.yml')\n", cm._CUT_WORDS)
    assert not cm.has_tests(only)


@pytest.mark.spec("PIPE-GATES-R016.20")
def test_migrate_deletes_cut_tests_and_files_left_without_tests(tmp_path: Path) -> None:
    root = make(tmp_path)
    (root / "tests" / "test_cut_reads.py").write_text(CUT_READS, encoding="utf-8")
    (root / "tests" / "test_only_cut.py").write_text("def test_a():\n    open('mcp_source_presets.json')\n")
    report = run(root)
    assert "tests/test_only_cut.py" in report["deleted"]
    assert "def test_other" in (root / "tests" / "test_cut_reads.py").read_text(encoding="utf-8")
    assert not [i for i in report["review"] if i["blocking"] and i["step"] in ("tests", "leftover")]


@pytest.mark.spec("PIPE-GATES-R016.21")
def test_prose_mentions_the_connectors_init_and_manifest_path_follow_the_generated_module() -> None:
    doc = '"""Presets.\n\n``mcp_source_presets.json`` is read here.\n"""\n\nX = 1  # see connector_manifest.yml\nY = "connector_manifest.yml"\n'
    new = cm.rewrite_py_prose(doc, "demo_agent")
    assert "``demo_agent.connector_sources`` is read" in new and "# see demo_agent.connector_sources" in new
    assert 'Y = "connector_manifest.yml"' in new
    init = '"""Governed presets.\n\n``mcp_source_presets.json`` and fingerprints.\n"""\n\nfrom __future__ import annotations\n'
    assert "``demo_agent.connector_sources``" in (cm.rewrite_connectors_init(init, "demo_agent") or "")
    assert cm.rewrite_connectors_init('"""x"""\nVALUE = 1\n', "demo_agent") is None
    kw = '        ConnectorContent(\n            package_root=r,\n            manifest_path=package_root / "connector_manifest.yml",\n        )\n'
    assert "manifest_path" not in cm.drop_manifest_path_kw(kw)
    ttl = "# resolved by `connectors/mcp_source_presets.json`\n<a> a <b> .\n"
    assert "demo_agent.connector_sources" in cm.rewrite_ttl_prose(ttl, "demo_agent")


@pytest.mark.spec("PIPE-GATES-R016.22")
def test_provider_entry_point_hook_alternatives_scripts_and_adapters_go(tmp_path: Path) -> None:
    pp = (
        '[project]\nname = "d"\n\n# presets (connectors/mcp_source_presets.json) are served by the hub\n'
        '[project.entry-points."agent_connector_sdk.source_connector_providers"]\nd = "d.connectors"\n\n'
        "[tool.x]\na = 1\n\n# generated by connector_manifest tooling\n# second line\n[tool.y]\nb = 2\n"
    )
    new = cm.strip_pyproject_cut_refs(pp)
    assert "source_connector_providers" not in new and "[tool.x]" in new and "[tool.y]" in new
    assert "connector_manifest" not in new and "mcp_source_presets" not in new
    hook = "    exclude: ^(connector_manifest\\.yml|d/connectors/.*\\.json|d/ontology/.*)$\n"
    assert cm.strip_regex_alternatives(hook) == "    exclude: ^(d/connectors/.*\\.json|d/ontology/.*)$\n"
    yml = (
        "- repo: local\n  hooks:\n  - id: keep\n    entry: python a.py\n"
        "  - id: schemas\n    entry: python scripts/generate_tool_schemas.py --check\n"
        "  - id: last\n    entry: pytest\n"
    )
    out = cm.drop_script_hooks(yml, ["generate_tool_schemas.py"])
    assert "schemas" not in out and "id: keep" in out and "id: last" in out
    root = make(tmp_path)
    (root / "scripts").mkdir()
    (root / "scripts" / "generate_tool_schemas.py").write_text("load_manifest('connector_manifest.yml')\n")
    (root / "scripts" / "verify_generated_schemas.py").write_text("run('scripts/generate_tool_schemas.py')\n")
    (root / "scripts" / "other.py").write_text("print(1)\n")
    (root / "demo_agent" / "connectors" / "adapters.py").write_text("import x\nread('mcp_source_presets.json')\n")
    (root / "tests" / "test_adapters.py").write_text(
        "from demo_agent.connectors.adapters import build\n\n\ndef test_a():\n    assert build\n"
    )
    report = run(root)
    assert {"scripts/generate_tool_schemas.py", "scripts/verify_generated_schemas.py"} <= set(report["deleted"])
    assert (root / "scripts" / "other.py").is_file() and "demo_agent/connectors/adapters.py" in report["deleted"]
    assert "tests/test_adapters.py" in report["deleted"]


@pytest.mark.spec("PIPE-GATES-R016.23")
def test_certification_is_canonicalized_then_stripped_and_missing_bump_targets_are_skipped(tmp_path: Path) -> None:
    root = make(tmp_path)
    cert = root / "demo_agent" / "ontology" / "certification.json"
    cert.write_text(
        '{"artifacts": {"demo_agent/connector_manifest.yml": "a", "demo_agent/ontology/x.ttl": "b"},\n"live": false}',
        encoding="utf-8",
    )
    (root / "docker" / "Dockerfile").write_text("nothing here\n", encoding="utf-8")
    report = run(root)
    data = json.loads(cert.read_text(encoding="utf-8"))
    assert list(data["artifacts"]) == ["demo_agent/ontology/x.ttl"]
    assert cert.read_text(encoding="utf-8") == json.dumps(data, indent=2, sort_keys=True) + "\n"
    skipped = [i for i in report["review"] if i["step"] == "version"]
    assert skipped and not skipped[0]["blocking"] and "skipped" in skipped[0]["detail"]


@pytest.mark.spec("PIPE-GATES-R016.24")
def test_an_action_preset_is_reported_and_lists_in_presets_stay_json_lists() -> None:
    review = cm.Review()
    presets = {
        "demo-rules": {
            "server": "demo-mcp",
            "tool": "dvr_operations",
            "action": "list_rules",
            "id_field": "id",
            "id_fallback_fields": ["id", "guid"],
        }
    }
    ingest = {"sources": [{"source_id": "rules", "record_type": "Rule", "tools": ["dvr_operations"], "id_field": "id"}]}
    out = cm.build_sources({"manifest": {"connector": "demo-mcp"}, "presets": presets, "ingest": ingest}, review)
    assert out is not None and [e["tool"] for e in out["entries"]] == ["dvr_operations"]
    assert [i for i in review.items if "action" in i["detail"] and not i["blocking"]]
    module = cm.render_module(out)
    assert '"id_fallback_fields": [' in module and '"id_fallback_fields": (' not in module


@pytest.mark.spec("PIPE-GATES-R016.18")
def test_rebump_also_points_reference_assertions_at_the_live_layout(tmp_path: Path) -> None:
    root = make(tmp_path)
    py = root / "pyproject.toml"
    py.write_text(py.read_text(encoding="utf-8").replace(">=0.3.18", ">=0.4.0"), encoding="utf-8")
    (root / "tests" / "test_refs.py").write_text(REF_TEST, encoding="utf-8")
    report = cm.rebump(root, lock=False)
    assert "tests/test_refs.py" in report["changed"]
    assert '"relations/Job/launchedFrom"' in (root / "tests" / "test_refs.py").read_text(encoding="utf-8")


@pytest.mark.spec("PIPE-GATES-R016.25")
def test_driver_sync_falls_back_to_the_pr_gate_extras_and_each_repo_gets_its_own_pre_commit_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import connector_migrate_batch as batch

    wt = tmp_path / "wt"
    (wt / ".github/workflows").mkdir(parents=True)
    (wt / ".github/workflows/connector-pr.yml").write_text(
        "with:\n  sync-args: --all-groups --extra mcp --extra test\n", encoding="utf-8"
    )
    assert batch.workflow_sync_args(wt) == ["--all-groups", "--extra", "mcp", "--extra", "test"]
    calls: list[list[str]] = []

    def fake_sh(step, cmd, cwd=None, env=None, ok=(0,)):  # noqa: ANN001
        calls.append(cmd)
        if "--all-extras" in cmd:
            raise batch.StepFailed(step, "flash-attn build failed")
        return ""

    monkeypatch.setattr(batch, "sh", fake_sh)
    led = batch.Ledger(tmp_path / "ledger.json")
    batch.sync("sync", wt, {}, led, "r")
    assert calls[-1][-5:] == ["--all-groups", "--extra", "mcp", "--extra", "test"][-5:]
    assert led.data["r"]["sync_args"].startswith("--all-groups")
    src = Path(batch.__file__).read_text(encoding="utf-8")
    assert '"PRE_COMMIT_HOME"' in src and 'worktree", "remove", "--force"' in src


@pytest.mark.spec("PIPE-GATES-R016.26")
def test_generated_module_is_fully_typed_and_test_rules_follow_the_live_layout() -> None:
    module = cm.render_module({"connector": "demo-mcp", "entries": [], "mappings": {}, "resources": []})
    for needle in (
        "SOURCES: tuple[Any, ...]",
        "SCHEMA_MAPPINGS: dict[str, Any]",
        "RESOURCES: tuple[",
        "specs: list[IngestSourceSpec] = []",
    ):
        assert needle in module
    compile(module, "connector_sources.py", "exec")
    assert "assert HUB_IRI in imports" not in cm.drop_parent_import_assertion(
        "    imports = set(g.objects(U, OWL.imports))\n    assert HUB_IRI in imports\n    assert LEGAL_IRI in imports\n"
    )
    assert 'assert ">=0.4.1" in sdk' in cm.rewrite_references('    assert ">=0.3.18" in sdk\n')
    assert ">=0.3.18" in cm.rewrite_references('    assert ">=0.3.18" in other\n')
    text = "def test_providers():\n    assert ep['agent_connector_sdk.source_connector_providers'] == {}\n\n\ndef test_ok():\n    assert 1\n"
    cut, names, _ = cm.delete_cut_tests(text, cm._CUT_WORDS)
    assert names == ["test_providers"] and "test_ok" in cut


@pytest.mark.spec("PIPE-GATES-R016.26")
def test_validation_evidence_is_not_a_leftover_and_verify_needs_shapes_only_with_shape_files(tmp_path: Path) -> None:
    root = make(tmp_path)
    (root / "validation").mkdir()
    (root / "validation" / "evidence.json").write_text('{"x": "manifest://connector"}', encoding="utf-8")
    review = cm.Review()
    cm.leftover_references(root, review)
    assert not [i for i in review.items if i["path"].startswith("validation/")]
    src = (Path(cm.__file__).parents[2] / "scripts" / "connector_verify.py").read_text(encoding="utf-8")
    assert 'has_shapes = any(root.glob("*/ontology/shapes/*.ttl"))' in src


@pytest.mark.spec("PIPE-GATES-R016.27")
def test_an_action_preset_resolves_to_the_one_served_split_tool_else_is_a_blocking_review_item() -> None:
    served = {"demo_dvr_list_rules", "demo_list_rules", "other_tool"}
    assert cm.action_tool_candidates("demo_dvr", "list_rules", "demo-mcp", served) == [
        "demo_dvr_list_rules",
        "demo_list_rules",
    ]
    assert cm.action_tool_candidates("vault_meta", "meta_snapshot", "vault-mcp", {"vault_meta_meta_snapshot"}) == [
        "vault_meta_meta_snapshot"
    ]
    assert cm.action_tool_candidates("objects", "list", "objectstore-mcp", {"objectstore_list_objects"}) == [
        "objectstore_list_objects"
    ]
    presets = {"p": {"server": "demo-mcp", "tool": "uptime_kuma_monitors", "action": "get_monitors", "id_field": "id"}}
    inputs = {"manifest": {"connector": "demo-mcp"}, "presets": presets, "ingest": {}}
    review = cm.Review()
    out = cm.build_sources(inputs, review, {"uptime_kuma_get_monitors"})
    assert out is not None and out["entries"][0]["tool"] == "uptime_kuma_get_monitors"
    assert "action" not in out["entries"][0]["preset"] and not [i for i in review.items if i["blocking"]]
    review = cm.Review()
    cm.build_sources(inputs, review, {"uptime_get_monitors", "uptime_kuma_get_monitors"})
    assert [i for i in review.items if i["blocking"] and "2 served tools" in i["detail"]]
    review = cm.Review()
    cm.build_sources(inputs, review, {"unrelated"})
    assert [i for i in review.items if i["blocking"] and "0 served tools" in i["detail"]]


@pytest.mark.spec("PIPE-GATES-R016.28")
def test_changelog_gets_one_fixed_entry_for_the_bumped_version(tmp_path: Path) -> None:
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\nintro\n\n## [1.0.4] - 2026-01-01\n\n- old\n", encoding="utf-8"
    )
    changed: list[str] = []
    cm.add_changelog(tmp_path, "1.0.5", changed, "2026-10-23")
    text = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    assert text.index("## [1.0.5] - 2026-10-23") < text.index("## [1.0.4]") and changed == ["CHANGELOG.md"]
    cm.add_changelog(tmp_path, "1.0.5", changed, "2026-10-24")
    assert (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8") == text
    (tmp_path / "CHANGELOG.md").write_text("no headings\n", encoding="utf-8")
    cm.add_changelog(tmp_path, "1.0.6", changed, "2026-10-23")
    assert (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8") == "no headings\n"


def _git(wt: Path, *args: str) -> str:
    import os
    import subprocess

    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}  # a hook run leaks GIT_DIR into tests
    return subprocess.run(["git", *args], cwd=wt, env=env, capture_output=True, text=True, check=True).stdout


@pytest.mark.spec("PIPE-GATES-R016.29")
def test_commit_restages_after_a_formatter_hook_stops_when_nothing_changes_and_reports_noop(tmp_path: Path) -> None:
    from scripts import connector_migrate_batch as batch

    wt = tmp_path / "wt"
    wt.mkdir()
    _git(wt, "init", "-q", "-b", "main")
    _git(wt, "config", "user.email", "t@example.com")
    _git(wt, "config", "user.name", "T")
    (wt / "a.txt").write_text("a\n", encoding="utf-8")
    _git(wt, "add", "--", "a.txt")
    _git(wt, "commit", "-q", "-m", "base")
    _git(wt, "update-ref", "refs/remotes/origin/main", "HEAD")
    hook = wt / ".git" / "hooks" / "pre-commit"
    hook.write_text(
        "#!/bin/sh\nif ! grep -q formatted a.txt; then echo formatted >> a.txt; exit 1; fi\nexit 0\n", encoding="utf-8"
    )
    hook.chmod(0o755)
    (wt / "a.txt").write_text("changed\n", encoding="utf-8")
    led = batch.Ledger(tmp_path / "ledger.json")
    batch.commit_all(wt, ["a.txt"], "commit", {}, led, "r", "msg")
    assert led.data["r"]["commit_attempts"] == 2
    assert "formatted" in _git(wt, "show", "HEAD:a.txt")
    batch.commit_all(wt, ["a.txt"], "commit", {}, led, "r", "msg")
    assert led.data["r"]["already_committed"] is True
    _git(wt, "update-ref", "refs/remotes/origin/main", "HEAD")
    with pytest.raises(batch.NoOp):
        batch.commit_all(wt, ["a.txt"], "commit", {}, led, "r", "msg")
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    (wt / "a.txt").write_text("again\n", encoding="utf-8")
    with pytest.raises(batch.StepFailed):
        batch.commit_all(wt, ["a.txt"], "commit", {}, led, "r", "msg")
    src = Path(batch.__file__).read_text(encoding="utf-8")
    assert 'env["PATH"] = f"{venv}/bin:' in src and "--served-tools" in src and ".pre.patch" in src
    assert '"--recount"' in src


@pytest.mark.spec("PIPE-GATES-R016.27")
def test_the_hook_dispatcher_forwards_the_served_tools_file(tmp_path: Path) -> None:
    from pipelines_hooks.hygiene import ontology_orphan_map as om

    root = make(tmp_path)
    served = tmp_path / "served.json"
    served.write_text("[]", encoding="utf-8")
    out = tmp_path / "report.json"
    om.main(["migrate", "--root", str(root), "--no-lock", "--served-tools", str(served), "--out", str(out)])
    assert out.is_file()


@pytest.mark.spec("PIPE-GATES-R016.30")
def test_mapping_subscripts_on_the_declaration_become_attribute_reads() -> None:
    text = (
        "import yaml\nfrom pathlib import Path\n\n\ndef test_x():\n"
        '    manifest = yaml.safe_load(Path("connector_manifest.yml").read_text())\n'
        '    assert manifest["schema_mappings"][name]["ontology_class"] == parent\n'
    )
    new, action = cm.rewrite_test(text, "test_x.py", "demo_agent")
    assert action == "rewrite" and new is not None
    assert "declared_sources().schema_mappings[name].ontology_class == parent" in new


@pytest.mark.spec("PIPE-GATES-R016.31")
def test_scripts_driving_a_deleted_script_go_to_a_fixed_point_and_tests_importing_them_are_deleted(
    tmp_path: Path,
) -> None:
    root = make(tmp_path)
    (root / "scripts").mkdir()
    (root / "scripts" / "generate_tool_schemas.py").write_text("load_manifest('connector_manifest.yml')\n")
    (root / "scripts" / "verify_generated_schemas.py").write_text("import generate_tool_schemas\n")
    # sorts before the script it imports: a single pass in file order would keep it
    (root / "scripts" / "a_clones.py").write_text("from verify_generated_schemas import MANIFEST\n")
    (root / "scripts" / "other.py").write_text("print(1)\n")
    (root / "tests" / "test_schema_policy.py").write_text(
        "from scripts import a_clones as clones\nfrom scripts import verify_generated_schemas as v\n\n\n"
        "def test_a():\n    assert clones and v\n"
    )
    report = run(root)
    assert {"scripts/generate_tool_schemas.py", "scripts/verify_generated_schemas.py", "scripts/a_clones.py"} <= set(
        report["deleted"]
    )
    assert (root / "scripts" / "other.py").is_file()
    assert "tests/test_schema_policy.py" in report["deleted"]
    assert not [i for i in report["review"] if i["blocking"]]


@pytest.mark.spec("PIPE-GATES-R016.32")
def test_assertions_on_the_stripped_prompt_keys_are_dropped() -> None:
    text = (
        'def test_p():\n    data = load()\n    assert data["type"] == "prompt"\n'
        '    assert data[\'extends\'] == "agent-connector-sdk:base"\n    assert data["compose"] == "append"\n'
        '    assert "extends" in data\n    assert data["identity"]["role"]\n'
    )
    new = cm.drop_prompt_key_assertions(text)
    assert "extends" not in new and "compose" not in new
    assert 'data["type"] == "prompt"' in new and 'data["identity"]["role"]' in new


@pytest.mark.spec("PIPE-GATES-R016.33")
def test_a_startup_test_reads_the_package_name_from_pyproject_not_the_checkout_directory(tmp_path: Path) -> None:
    src = (
        'def test_module_runnable():\n    pkg_name = (\n        __import__("pathlib")\n        .Path(__file__)\n'
        '        .resolve()\n        .parent.parent.name.replace("-", "_")\n    )\n    assert pkg_name\n'
    )
    new = cm.derive_package_from_pyproject(src)
    assert "pyproject.toml" in new and ".parent.parent.name" not in new
    project = tmp_path / "not-the-package-name"
    (project / "tests").mkdir(parents=True)
    (project / "pyproject.toml").write_text('[project]\nname = "demo-agent"\n', encoding="utf-8")
    test = project / "tests" / "test_startup.py"
    test.write_text(new, encoding="utf-8")
    scope: dict[str, object] = {"__file__": str(test)}
    exec(
        compile(
            new.replace("def test_module_runnable", "def probe").replace("assert pkg_name", "return pkg_name")
            + "\nresult = probe()\n",
            str(test),
            "exec",
        ),
        scope,
    )
    assert scope["result"] == "demo_agent"


@pytest.mark.spec("PIPE-GATES-R016.34")
def test_a_connector_without_sources_renders_an_import_free_empty_tuple_and_cut_tests_leave_no_trailing_blank_lines() -> (
    None
):
    text = cm.render_module({"connector": "demo-mcp", "entries": [], "mappings": {}, "resources": []})
    assert "SOURCES: tuple[Any, ...] = ()\n" in text and "source_meta" not in text
    compile(text, "connector_sources.py", "exec")
    with_sources = cm.render_module(
        {
            "connector": "demo-mcp",
            "entries": [{"tool": "t", "source_id": "s", "record_type": "R", "id_field": "id"}],
            "mappings": {},
            "resources": [],
        }
    )
    assert "import source_meta" in with_sources
    src = "def test_keep():\n    assert 1\n\n\ndef test_cut():\n    open('connector_manifest.yml')\n\n\n"
    new, names, _ = cm.delete_cut_tests(src, cm._CUT_WORDS)
    assert names == ["test_cut"] and new.endswith("assert 1\n") and not new.endswith("\n\n")


@pytest.mark.spec("PIPE-GATES-R016.36")
def test_entity_ids_read_with_get_become_validated_strings() -> None:
    src = (
        "from typing import Any\n\nfrom x import Entity\n\n\ndef _to_entity(record: dict[str, Any]) -> Entity:\n"
        "    # id/node_type are intentionally read with .get(): a missing one must reach\n"
        "    # the SDK's own builder.\n"
        '    return Entity(\n        id=record.get("id"),\n        node_type=record.get("node_type"),\n        properties={},\n    )\n'
    )
    new = cm.validate_entity_args(src)
    compile(new, "kg_ingest.py", "exec")
    assert 'id=_required_text(record, "id")' in new and "intentionally" not in new
    assert new.index("def _required_text") < new.index("def _to_entity")
    scope: dict[str, object] = {}
    exec(new.replace("from x import Entity", "Entity = dict"), scope)
    with pytest.raises(ValueError):
        scope["_to_entity"]({"id": None, "node_type": "T"})  # type: ignore[operator]
    assert cm.validate_entity_args(new) == new
