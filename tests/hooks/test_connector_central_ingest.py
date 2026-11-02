"""Ingest rules i1-i9 of the central connector migration (PIPE-GATES-R016.82-.90)."""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from pipelines_hooks.hygiene.connector_central import ingest
from pipelines_hooks.hygiene.connector_central.base import RULES, Ctx, make_ctx
from pipelines_hooks.hygiene.connector_central.fleet import WORKSPACE_ROOT


def _sdk_checkout() -> Path:
    """Find the real SDK checkout used by a central migration dry run.

    The migration driver accepts an explicit checkout path.  Tests may provide
    the same path through ``PIPELINES_SDK_PATH``; locally, prefer the current
    Scion rename worktree and then the workspace checkout.  The test remains
    skipped when neither checkout is available, rather than comparing against
    a fabricated helper implementation.
    """
    state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    worktrees = state / "repository-worktrees" / "agent-connector-sdk"
    configured = os.environ.get("PIPELINES_SDK_PATH")
    candidates = tuple(
        path
        for path in (
            *((Path(configured),) if configured else ()),
            *sorted(worktrees.glob("codex/pypi-rename-scion-sdk-*"), reverse=True),
            WORKSPACE_ROOT / "agent-packages" / "agent-connector-sdk",
            worktrees / "wave2-dryrun",
        )
    )
    for candidate in candidates:
        if (candidate / "scion_sdk/ingest/mapping.py").is_file():
            return candidate
    return candidates[0]


SDK = _sdk_checkout()

PYPROJECT = """[project]
name = "demo-mcp"
version = "1.0.0"
[project.entry-points."scion_sdk.connector"]
demo-mcp = "{value}"
"""

KG_HEAD = '''"""Demo ingest."""

from __future__ import annotations

from typing import Any

from scion_sdk.ingest import (
    ChangeSet,
    Document,
    Entity,
    IngestBinding,
    IngestError,
    KnowledgeIngest,
    Relationship,
    current_ingest,
)

_SOURCE = "{connector}"
_BINDING = IngestBinding(connector=_SOURCE, stream="demo")

_ENTITY_RESERVED_KEYS = frozenset({{"id", "node_type"}})
_RELATIONSHIP_RESERVED_KEYS = frozenset({{"source", "target", "relationship"}})


def _to_entity(record: dict[str, Any]) -> Entity:
    return Entity(
        id=record.get("id"),
        node_type=record.get("node_type"),
        properties={{key: value for key, value in record.items() if key not in _ENTITY_RESERVED_KEYS}},
    )


def _to_relationship(record: dict[str, Any]) -> Relationship:
    props = {{k: v for k, v in record.items() if k not in ("source", "target", "relationship")}}
    return Relationship(
        source=record["source"],
        target=record["target"],
        relationship=record["relationship"],
        properties=props or None,
    )


async def ingest_entities(
    entities: list[dict[str, Any]],
    relationships: list[dict[str, Any]] | None = None,
    *,
    ingest: KnowledgeIngest | None = None,
) -> dict[str, int]:
    """Write nodes."""
    if not entities:
        raise IngestError("ingest_entities needs at least one entity")
    change_set = ChangeSet(
        entities=tuple(_to_entity(e) for e in entities),
        relationships=tuple(_to_relationship(r) for r in relationships or ()),
    )
    service = ingest or current_ingest()
    receipt = await service.submit(_BINDING, change_set)
    return {{"nodes": receipt.affected_count, "edges": receipt.relationship_count}}


async def ingest_documents(
    documents: list[dict[str, Any]],
    *,
    ingest: KnowledgeIngest | None = None,
) -> dict[str, int]:
    if not documents:
        raise IngestError("ingest_documents needs at least one document")
    change_set = ChangeSet(
        documents=tuple(
            Document(id=d["id"], text=d["text"], title=d.get("title"), source_uri=d.get("source_uri"))
            for d in documents
        )
    )
    service = ingest or current_ingest()
    receipt = await service.submit(_BINDING, change_set)
    return {{"nodes": receipt.affected_count, "edges": receipt.relationship_count}}
'''

KG_MAPPER = '''

async def ingest_items(items: list[dict[str, Any]], *, ingest: KnowledgeIngest | None = None) -> dict[str, int]:
    """Map items."""
    entities = [{"id": f"demo:item:{i['id']}", "node_type": "Item"} for i in items]
    await ingest_documents([{"id": "d", "text": "t"}], ingest=ingest)
    return await ingest_entities(entities, ingest=ingest)
'''

MCP_SERVER = '''"""Demo server."""


async def sync(records):
    from demo_mcp import kg_ingest

    return await kg_ingest.ingest_entities(records)
'''

TESTS = '''"""Demo ingest tests mention ``ingest_entities`` in the docstring."""

import pytest

from demo_mcp.kg_ingest import _to_entity, ingest_entities, ingest_items


def test_to_entity():
    assert _to_entity({"id": "a", "node_type": "T"}).id == "a"


@pytest.mark.asyncio
async def test_entities(service):
    assert await ingest_entities([{"id": "a", "node_type": "T"}], ingest=service)


@pytest.mark.asyncio
async def test_items(service):
    assert await ingest_items([{"id": 1}], ingest=service)
'''


def _connector(
    tmp_path: Path,
    *,
    value: str = "demo_mcp:connector",
    connector: str = "demo-mcp",
    kg: str | None = None,
    tests: str = TESTS,
    extra: str = KG_MAPPER,
) -> Path:
    root = tmp_path / "repo"
    pkg = root / "demo_mcp"
    pkg.mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "pyproject.toml").write_text(PYPROJECT.format(value=value), encoding="utf-8")
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    if kg is None:
        kg = KG_HEAD.format(connector=connector) + extra
    if kg:
        (pkg / "kg_ingest.py").write_text(kg, encoding="utf-8")
    (pkg / "mcp_server.py").write_text(MCP_SERVER, encoding="utf-8")
    (root / "tests" / "test_kg_ingest.py").write_text(tests, encoding="utf-8")
    return root


def _ctx(root: Path) -> Ctx:
    ctx = make_ctx(root, {"sdk_path": str(SDK)})
    assert ctx is not None
    return ctx


def _run(ctx: Ctx, *ids: str) -> Ctx:
    for rid in ids:
        RULES[rid](ctx)
    return ctx


def _snapshot(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in root.rglob("*") if p.is_file()}


def _steps(ctx: Ctx) -> list[str]:
    return [i["step"] for i in ctx.review.items]


# ---------------------------------------------------------------- i1


# spec: PIPE-GATES-R016.82 — reviewed existing assertion binding
@pytest.mark.spec("PIPE-GATES-R016.82")
def test_i1_deletes_standard_plumbing_only(tmp_path: Path) -> None:
    root = _connector(tmp_path)
    before = _snapshot(root)
    ctx = _run(_ctx(root), "ingest.i1")
    kg = (root / "demo_mcp/kg_ingest.py").read_text(encoding="utf-8")
    for gone in ("def _to_entity", "def _to_relationship", "async def ingest_entities", "_ENTITY_RESERVED_KEYS"):
        assert gone not in kg
    assert "async def ingest_items" in kg
    assert "_BINDING = IngestBinding" in kg  # i2 replaces it
    assert ctx.applied == ["ingest.i1"]
    assert not ctx.review.items
    after = _snapshot(root)
    assert {k for k in before if before[k] != after[k]} == {"demo_mcp/kg_ingest.py"}
    ast.parse(kg)


@pytest.mark.spec("PIPE-GATES-R016.82")
def test_i1_name_insensitive_match(tmp_path: Path) -> None:
    kg = KG_HEAD.format(connector="demo-mcp").replace("async def ingest_entities(", "async def _ingest(")
    kg += KG_MAPPER.replace("ingest_entities(entities", "_ingest(entities")
    root = _connector(tmp_path, kg=kg, tests='"""No tests."""\n')
    (root / "demo_mcp/mcp_server.py").write_text('"""None."""\n', encoding="utf-8")
    _run(_ctx(root), *ingest.ORDER)
    text = (root / "demo_mcp/kg_ingest.py").read_text(encoding="utf-8")
    assert "def _ingest(" not in text and "await STREAM.entities(entities, ingest=ingest)" in text


@pytest.mark.spec("PIPE-GATES-R016.82")
def test_i1_connector_mismatch_derives_from_the_sdk_identity(tmp_path: Path) -> None:
    root = _connector(tmp_path, connector="demo-agent")
    ctx = _run(_ctx(root), *ingest.ORDER)
    text = (root / "demo_mcp/kg_ingest.py").read_text(encoding="utf-8")
    assert "STREAM = SourceStream" in text and "demo-agent" not in text
    assert any("derives from the SDK identity" in i["detail"] and not i["blocking"] for i in ctx.review.items)


@pytest.mark.spec("PIPE-GATES-R016.82")
def test_i1_nonstandard_body_goes_to_review(tmp_path: Path) -> None:
    kg = KG_HEAD.format(connector="demo-mcp").replace(
        "    service = ingest or current_ingest()\n    receipt = await service.submit(_BINDING, change_set)\n",
        "    service = ingest or current_ingest()\n    print(1)\n    receipt = await service.submit(_BINDING, change_set)\n",
        1,
    )
    root = _connector(tmp_path, kg=kg + KG_MAPPER)
    before = _snapshot(root)
    ctx = _run(_ctx(root), *ingest.ORDER)
    assert _snapshot(root) == before
    assert any(i["step"] == "ingest.i1" for i in ctx.review.items)


# ---------------------------------------------------------------- i2


# spec: PIPE-GATES-R016.83 — reviewed existing assertion binding
@pytest.mark.spec("PIPE-GATES-R016.83")
def test_i2_for_package_stream_and_imports(tmp_path: Path) -> None:
    root = _connector(tmp_path)
    _run(_ctx(root), "ingest.i1", "ingest.i2", "ingest.i3")
    kg = (root / "demo_mcp/kg_ingest.py").read_text(encoding="utf-8")
    assert 'STREAM = SourceStream.for_package(__package__.split(".")[0], "demo")\n' in kg
    assert "_BINDING" not in kg and "_SOURCE" not in kg
    imp = next(n for n in ast.parse(kg).body if isinstance(n, ast.ImportFrom) and n.module == ingest.SDK_MOD)
    assert [a.name for a in imp.names] == ["KnowledgeIngest", "SourceStream"]


@pytest.mark.spec("PIPE-GATES-R016.83")
def test_i2_explicit_binding_before_wave1_entry_point(tmp_path: Path) -> None:
    root = _connector(tmp_path, value="demo_mcp")
    _run(_ctx(root), *ingest.ORDER)
    kg = (root / "demo_mcp/kg_ingest.py").read_text(encoding="utf-8")
    assert 'STREAM = SourceStream(IngestBinding(connector="demo-mcp", stream="demo"))\n' in kg
    imp = next(n for n in ast.parse(kg).body if isinstance(n, ast.ImportFrom) and n.module == ingest.SDK_MOD)
    assert [a.name for a in imp.names] == ["IngestBinding", "KnowledgeIngest", "SourceStream"]


@pytest.mark.spec("PIPE-GATES-R016.83")
def test_i2_without_i1_plan_does_nothing(tmp_path: Path) -> None:
    kg = KG_HEAD.format(connector="demo-mcp").replace(
        "    service = ingest or current_ingest()\n",
        "    service = ingest or current_ingest()\n    print(1)\n",
        1,
    )
    root = _connector(tmp_path, kg=kg)
    before = _snapshot(root)
    ctx = _run(_ctx(root), "ingest.i2")
    assert _snapshot(root) == before
    assert not ctx.applied


# ---------------------------------------------------------------- i3


# spec: PIPE-GATES-R016.84 — reviewed existing assertion binding
@pytest.mark.spec("PIPE-GATES-R016.84")
def test_i3_rewrites_call_sites_and_deletes_helper_tests(tmp_path: Path) -> None:
    root = _connector(tmp_path)
    ctx = _run(_ctx(root), *ingest.ORDER)
    server = (root / "demo_mcp/mcp_server.py").read_text(encoding="utf-8")
    assert "await kg_ingest.STREAM.entities(records)" in server
    tests = (root / "tests/test_kg_ingest.py").read_text(encoding="utf-8")
    assert "from demo_mcp.kg_ingest import STREAM, ingest_items\n" in tests
    assert "def test_to_entity" not in tests and "_to_entity" not in tests
    assert "await STREAM.entities([" in tests
    kg = (root / "demo_mcp/kg_ingest.py").read_text(encoding="utf-8")
    assert "await STREAM.documents([" in kg
    for text in (server, tests, kg):
        ast.parse(text)
    assert set(ctx.applied) == {"ingest.i1", "ingest.i2", "ingest.i3"}
    assert not [i for i in ctx.review.items if i["step"] in ("ingest.i1", "ingest.i2", "ingest.i3")]


@pytest.mark.spec("PIPE-GATES-R016.84")
def test_i3_function_local_relative_import(tmp_path: Path) -> None:
    root = _connector(tmp_path)
    (root / "demo_mcp/prep.py").write_text(
        "import asyncio\n\n\ndef commit(e):\n    from .kg_ingest import ingest_entities\n\n"
        "    return asyncio.run(ingest_entities(e))\n",
        encoding="utf-8",
    )
    _run(_ctx(root), *ingest.ORDER)
    prep = (root / "demo_mcp/prep.py").read_text(encoding="utf-8")
    assert "    from .kg_ingest import STREAM\n" in prep and "asyncio.run(STREAM.entities(e))" in prep


@pytest.mark.spec("PIPE-GATES-R016.84")
def test_i3_aliased_import_or_monkeypatch_goes_to_review_untouched(tmp_path: Path) -> None:
    for i, tests in enumerate(
        (
            "from demo_mcp.kg_ingest import ingest_entities as ie\n",
            'def test_x(monkeypatch):\n    monkeypatch.setattr("demo_mcp.kg_ingest.ingest_entities", None)\n',
        )
    ):
        root = _connector(tmp_path / str(i), tests=tests)
        before = _snapshot(root)
        ctx = _run(_ctx(root), *ingest.ORDER)
        assert _snapshot(root) == before
        assert "ingest.i1" in _steps(ctx)


# ---------------------------------------------------------------- i4 i5


@pytest.mark.spec("PIPE-GATES-R016.85")
def test_i4_dispatch_table_is_noted(tmp_path: Path) -> None:
    extra = KG_MAPPER + '\n\n_MAPPERS = {"Item": ingest_items}\n'
    root = _connector(tmp_path, extra=extra)
    ctx = _run(_ctx(root), "ingest.i4")
    assert _steps(ctx) == ["ingest.i4"] and not ctx.review.items[0]["blocking"]
    plain = _run(_ctx(_connector(tmp_path / "b")), "ingest.i4")
    assert not plain.review.items


@pytest.mark.spec("PIPE-GATES-R016.85")
def test_i4_annotated_dispatch_table_is_noted(tmp_path: Path) -> None:
    extra = KG_MAPPER + '\n\n_MAPPERS: dict[str, object] = {"Item": ingest_items}\n'
    ctx = _run(_ctx(_connector(tmp_path, extra=extra)), "ingest.i4")
    assert _steps(ctx) == ["ingest.i4"] and "dispatch" in ctx.review.items[0]["detail"]


@pytest.mark.spec("PIPE-GATES-R016.86")
def test_i5_mapper_functions_are_noted(tmp_path: Path) -> None:
    extra = KG_MAPPER + "\n\ndef map_items(records):\n    return [], []\n"
    ctx = _run(_ctx(_connector(tmp_path, extra=extra)), "ingest.i5")
    assert _steps(ctx) == ["ingest.i5"] and "map_items" in ctx.review.items[0]["detail"]
    plain = _run(_ctx(_connector(tmp_path / "b")), "ingest.i5")
    assert not plain.review.items


@pytest.mark.spec("PIPE-GATES-R016.86")
def test_i5_async_mapper_functions_are_noted(tmp_path: Path) -> None:
    extra = KG_MAPPER + "\n\nasync def map_documents(records):\n    return records\n"
    ctx = _run(_ctx(_connector(tmp_path, extra=extra)), "ingest.i5")
    assert _steps(ctx) == ["ingest.i5"] and "map_documents" in ctx.review.items[0]["detail"]


# ---------------------------------------------------------------- i6

EXT_ID = '''

def _ext_id(record: dict[str, Any], *keys: str) -> str | None:
    """First non-empty key."""
    for k in keys:
        v = record.get(k)
        if v is not None and v != "":
            return str(v)
    return None


def node_id(rec):
    return f"demo:{_ext_id(rec, 'a', 'b')}"
'''


@pytest.mark.spec("PIPE-GATES-R016.87")
@pytest.mark.skipif(not (SDK / "scion_sdk/ingest/mapping.py").is_file(), reason="SDK checkout absent")
def test_i6_helper_equal_to_sdk_is_replaced(tmp_path: Path) -> None:
    root = _connector(tmp_path, extra=KG_MAPPER + EXT_ID)
    ctx = _run(_ctx(root), *ingest.ORDER)
    kg = (root / "demo_mcp/kg_ingest.py").read_text(encoding="utf-8")
    assert "def _ext_id" not in kg and "ext_id(rec, 'a', 'b')" in kg
    imp = next(n for n in ast.parse(kg).body if isinstance(n, ast.ImportFrom) and n.module == ingest.SDK_MOD)
    assert "ext_id" in [a.name for a in imp.names]
    assert "ingest.i6" in ctx.applied


@pytest.mark.spec("PIPE-GATES-R016.87")
def test_i6_helper_that_differs_is_kept(tmp_path: Path) -> None:
    root = _connector(tmp_path, extra=KG_MAPPER + EXT_ID.replace('v != ""', 'v != "" and v != 0'))
    ctx = _run(_ctx(root), "ingest.i6")
    assert "def _ext_id" in (root / "demo_mcp/kg_ingest.py").read_text(encoding="utf-8")
    assert _steps(ctx) == ["ingest.i6"] and not ctx.applied


# ---------------------------------------------------------------- i7 i8 i9

PAGING = """

async def ingest_all(get_page):
    page = 1
    while page:
        records, page = await get_page(page)
        await ingest_entities(records)
"""


# spec: PIPE-GATES-R016.88 — reviewed existing assertion binding
@pytest.mark.spec("PIPE-GATES-R016.88")
def test_i7_paging_is_review_and_stops_i1(tmp_path: Path) -> None:
    root = _connector(tmp_path, extra=KG_MAPPER + PAGING)
    before = _snapshot(root)
    ctx = _run(_ctx(root), *ingest.ORDER)
    assert _snapshot(root) == before
    assert "ingest.i7" in _steps(ctx) and "checkpointed paging" in ctx.review.items[0]["detail"]
    plain = _run(_ctx(_connector(tmp_path / "b")), "ingest.i7")
    assert not plain.review.items


BEST_EFFORT = """

async def try_ingest(entities):
    try:
        return await ingest_entities(entities)
    except IngestError:
        return None
"""


@pytest.mark.spec("PIPE-GATES-R016.89")
def test_i8_best_effort_wrapper_is_review_and_stops_i1(tmp_path: Path) -> None:
    root = _connector(tmp_path, extra=KG_MAPPER + BEST_EFFORT)
    before = _snapshot(root)
    ctx = _run(_ctx(root), *ingest.ORDER)
    assert _snapshot(root) == before
    assert "ingest.i8" in _steps(ctx)
    plain = _run(_ctx(_connector(tmp_path / "b")), "ingest.i8")
    assert not plain.review.items


@pytest.mark.spec("PIPE-GATES-R016.89")
def test_i8_aliased_sdk_exception_wrapper_is_review_and_stops_i1(tmp_path: Path) -> None:
    extra = (
        KG_MAPPER + "\n\nfrom scion_sdk.ingest import IngestError as RetryableError\n"
        "\nasync def try_ingest(entities):\n"
        "    try:\n"
        "        return await ingest_entities(entities)\n"
        "    except RetryableError:\n"
        "        return None\n"
    )
    ctx = _run(_ctx(_connector(tmp_path, extra=extra)), *ingest.ORDER)
    assert any(item["step"] == "ingest.i8" and "RetryableError" in item["detail"] for item in ctx.review.items)
    assert not ctx.applied


MEDIA = """

async def ingest_blob(data: bytes) -> dict[str, int]:
    change_set = ChangeSet(media=(MediaAsset(data, "image/png"),))
    receipt = await current_ingest().submit(_BINDING, change_set)
    return {"nodes": receipt.affected_count}
"""


@pytest.mark.spec("PIPE-GATES-R016.90")
def test_i9_media_change_set_is_review_and_stops_i1(tmp_path: Path) -> None:
    root = _connector(tmp_path, extra=KG_MAPPER + MEDIA)
    before = _snapshot(root)
    ctx = _run(_ctx(root), *ingest.ORDER)
    assert _snapshot(root) == before
    assert "ingest.i9" in _steps(ctx)
    plain = _run(_ctx(_connector(tmp_path / "b")), "ingest.i9")
    assert not plain.review.items


@pytest.mark.parametrize(
    ("construction", "reason"),
    [("ChangeSet(payload)", "positional"), ("ChangeSet(**payload)", "dynamic")],
)
@pytest.mark.spec("PIPE-GATES-R016.90")
def test_i9_dynamic_change_set_is_review_and_stops_i1(tmp_path: Path, construction: str, reason: str) -> None:
    extra = KG_MAPPER + f"\n\nasync def ingest_blob(payload):\n    change_set = {construction}\n    return change_set\n"
    ctx = _run(_ctx(_connector(tmp_path, extra=extra)), *ingest.ORDER)
    assert any(item["step"] == "ingest.i9" and reason in item["detail"] for item in ctx.review.items)
    assert not ctx.applied


# ---------------------------------------------------------------- whole module


@pytest.mark.spec("PIPE-GATES-R016.82")
def test_no_kg_ingest_is_a_silent_no_op(tmp_path: Path) -> None:
    root = _connector(tmp_path, kg="")
    before = _snapshot(root)
    ctx = _run(_ctx(root), *ingest.ORDER)
    assert _snapshot(root) == before and not ctx.review.items and not ctx.applied


@pytest.mark.spec("PIPE-GATES-R016.84")
def test_all_rules_idempotent(tmp_path: Path) -> None:
    root = _connector(tmp_path, extra=KG_MAPPER + EXT_ID)
    first = _run(_ctx(root), *ingest.ORDER)
    assert "ingest.i3" in first.applied
    after = _snapshot(root)
    second = _run(_ctx(root), *ingest.ORDER)
    assert _snapshot(root) == after
    assert not second.applied and not second.changed
    assert not [i for i in second.review.items if i["step"] in ("ingest.i1", "ingest.i2", "ingest.i3")]


def test_order_lists_every_ingest_rule() -> None:
    assert sorted(ingest.ORDER) == sorted(r for r in RULES if r.startswith("ingest."))
