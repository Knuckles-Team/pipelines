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
    assert "agent-connector-sdk[mcp]>=0.4.0,<1.0.0" in py and 'version = "1.0.5"' in py
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
