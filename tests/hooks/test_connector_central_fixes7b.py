"""Fixes found by verifying batch 1: module aliases in version reads and connector-name constants (PIPE-GATES-R016.58, .100)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from pipelines_hooks.hygiene.connector_central import base, identity, wave1

PYPROJECT = (
    '[project]\nname = "demo-agent"\nversion = "1.0.0"\n\n'
    '[project.entry-points."agent_connector_sdk.connector"]\ndemo-mcp = "demo_agent:connector"\n'
)


def _repo(tmp_path: Path, files: dict[str, str]) -> base.Ctx:
    root = tmp_path / "demo-agent"
    (root / "demo_agent").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (root / "demo_agent" / "__init__.py").write_text("", encoding="utf-8")
    for rel, text in files.items():
        (root / rel).write_text(text, encoding="utf-8")
    ctx = base.make_ctx(root, {})
    assert ctx is not None
    return ctx


SERVER = '__version__ = "2.3.6"\n\n\ndef engine_health():\n    return {"version": __version__}\n'


@pytest.mark.spec("PIPE-GATES-R016.58")
@pytest.mark.parametrize(
    "binding",
    [
        'mcp_server = importlib.import_module("demo_agent.mcp_server")\n',
        "from demo_agent import mcp_server\n",
        "import demo_agent.mcp_server as mcp_server\n",
    ],
)
def test_k1_a_test_reading_the_version_through_an_alias_of_the_module_is_rewritten(
    tmp_path: Path, binding: str
) -> None:
    """audio-transcriber: `mcp_server = importlib.import_module(...)`; `assert health["version"] == mcp_server.__version__`."""
    test = (
        "import importlib\n\n"
        + binding
        + '\n\ndef test_health():\n    health = mcp_server.engine_health()\n    assert health["version"] == mcp_server.__version__\n'
    )
    ctx = _repo(tmp_path, {"demo_agent/mcp_server.py": SERVER, "tests/test_health.py": test})
    wave1.k1(ctx)
    after = (ctx.root / "tests/test_health.py").read_text(encoding="utf-8")
    ast.parse(after)
    assert '== importlib.metadata.version("demo-agent")' in after and "mcp_server.__version__" not in after
    assert "import importlib.metadata" in after
    server = (ctx.root / "demo_agent/mcp_server.py").read_text(encoding="utf-8")
    assert '__version__ = "2.3.6"' not in server and '_v("demo-agent")' in server
    assert not [i for i in ctx.review.items if i["blocking"]]


@pytest.mark.spec("PIPE-GATES-R016.58")
def test_k1_a_non_test_module_reading_the_version_through_an_alias_is_reviewed(tmp_path: Path) -> None:
    other = "from demo_agent import mcp_server\n\nprint(mcp_server.__version__)\n"
    ctx = _repo(tmp_path, {"demo_agent/mcp_server.py": SERVER, "demo_agent/banner.py": other})
    wave1.k1(ctx)
    assert any(i["blocking"] and "banner.py" in i["path"] for i in ctx.review.items)
    assert '__version__ = "2.3.6"' in (ctx.root / "demo_agent/mcp_server.py").read_text(encoding="utf-8")


KG = """from agent_connector_sdk.ingest import IngestBinding

_CONNECTOR = "demo-agent"
_STREAM = "demo"

_BINDING = IngestBinding(connector=_CONNECTOR, stream=_STREAM)
_PAGE_BINDING = IngestBinding(connector=_CONNECTOR, stream=_STREAM, document_type="Page")
"""
KG_TEST = (
    'from demo_agent import kg_ingest\n\n\ndef test_provenance(request):\n    assert request.connector == "demo-agent"\n'
    '    assert request.other == "demo-agent"\n'
)


@pytest.mark.spec("PIPE-GATES-R016.100")
def test_name_constant_that_a_binding_takes_as_connector_derives_from_the_identity(tmp_path: Path) -> None:
    """atlassian-agent: `_CONNECTOR = "atlassian-agent"` feeds `IngestBinding(connector=_CONNECTOR, ...)`; fleet name differs."""
    ctx = _repo(tmp_path, {"demo_agent/kg_ingest.py": KG, "tests/test_kg.py": KG_TEST})
    identity.connector_names(ctx)
    text = (ctx.pkg / "kg_ingest.py").read_text(encoding="utf-8")
    assert '_CONNECTOR = connector_name("demo_agent")' in text and "import connector_name" in text
    assert '_STREAM = "demo"' in text and "IngestBinding(connector=_CONNECTOR, stream=_STREAM)" in text
    test = (ctx.root / "tests/test_kg.py").read_text(encoding="utf-8")
    assert 'request.connector == "demo-mcp"' in test
    assert 'request.other == "demo-agent"' in test  # only `.connector` comparisons follow the rename
    once = (text, test)
    identity.connector_names(ctx)
    assert (ctx.pkg / "kg_ingest.py").read_text(encoding="utf-8") == once[0]
    assert (ctx.root / "tests/test_kg.py").read_text(encoding="utf-8") == once[1]


@pytest.mark.spec("PIPE-GATES-R016.100")
def test_two_constants_of_the_same_name_are_reviewed_not_guessed(tmp_path: Path) -> None:
    ctx = _repo(tmp_path, {"demo_agent/kg_ingest.py": KG + '_CONNECTOR = "other"\n'})
    identity.connector_names(ctx)
    assert any(i["blocking"] and i["step"] == "id.name" for i in ctx.review.items)


@pytest.mark.spec("PIPE-GATES-R016.67")
def test_l4_extras_of_a_dropped_one_element_extra_move_to_the_pin(tmp_path: Path) -> None:
    """audio-transcriber: `mcp = ["agent-connector-sdk[mcp,stream]>=0.4.1"]` carried `stream` (websockets) for the client."""
    pyproject = PYPROJECT.replace(
        'version = "1.0.0"\n',
        'version = "1.0.0"\ndependencies = ["agent-connector-sdk[mcp]>=0.4.1,<1.0.0", "faster-whisper>=1.2"]\n\n'
        '[project.optional-dependencies]\nmcp = ["agent-connector-sdk[mcp,stream]>=0.4.1,<1.0.0"]\ntest = ["pytest>=9"]\n',
    )
    ctx = _repo(tmp_path, {"pyproject.toml": pyproject})
    wave1.l4(ctx)
    import tomllib

    data = tomllib.loads((ctx.root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert data["dependencies"][0].startswith("agent-connector-sdk[mcp,stream]>=0.5.4")
    assert "mcp" not in data["optional-dependencies"]


DEAD_SETUP = """\
import importlib
import tomllib
from pathlib import Path

import demo_agent


def test_reported_version_matches_the_released_package():
    pyproject = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert demo_agent.__version__ == pyproject["project"]["version"]


def test_every_module_reports_the_same_version():
    for name in ("api_client", "mcp_server"):
        module = importlib.import_module(f"demo_agent.{name}")
        assert module.__version__ == demo_agent.__version__, name
"""


# spec: PIPE-GATES-R016.61 — reviewed existing assertion binding
@pytest.mark.spec("PIPE-GATES-R016.61")
def test_k4_version_tests_left_with_only_dead_setup_are_deleted_and_noted(tmp_path: Path) -> None:
    """caddy-mcp, camunda-mcp, erpnext-agent tests/test_version.py: no F841 local, no dead test, no leftover imports."""
    ctx = _repo(tmp_path, {"tests/test_version.py": DEAD_SETUP})
    wave1.k4(ctx)
    assert not (ctx.root / "tests/test_version.py").exists()
    assert any("dead setup" in n["detail"] and not n["blocking"] for n in ctx.review.items)


@pytest.mark.spec("PIPE-GATES-R016.61")
def test_k4_keeps_other_tests_and_drops_only_the_setup_that_fed_the_assertion(tmp_path: Path) -> None:
    src = (
        "import tomllib\nfrom pathlib import Path\n\nimport demo_agent\n\n\n"
        "def test_a():\n    pyproject = tomllib.loads(Path('p').read_text())\n    assert demo_agent.__version__ == pyproject['x']\n\n\n"
        "def test_b():\n    value = compute()\n    assert value == 1\n    assert demo_agent.__version__\n"
    )
    out = wave1._clean_version_asserts(src)
    assert "test_a" not in out and "tomllib" not in out and "Path" not in out
    assert "value = compute()" in out and "assert value == 1" in out
    assert wave1._clean_version_asserts(out) == out
    ast.parse(out)


@pytest.mark.spec("PIPE-GATES-R016.61")
def test_k4_keeps_assignments_with_side_effects_or_later_reads() -> None:
    src = (
        "import demo_agent\n\n\n"
        "def test_a():\n    started = launch()\n    assert demo_agent.__version__\n\n\n"
        "def test_b():\n    mod = demo_agent\n    assert mod.__version__\n    print(mod)\n"
    )
    out = wave1._clean_version_asserts(src)
    assert "started = launch()" in out
    assert "mod = demo_agent" in out and "print(mod)" in out
