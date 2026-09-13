"""Which literal calls block an event loop, and how each is labelled.

The label is built purely from the AST (the call category plus its dotted
receiver path), so it is formatting-insensitive and serves as the content key.
"""

from __future__ import annotations

import ast

#: Passing a blocking callable by bare reference to one of these is the hop.
HOP_CALL_NAMES = frozenset({"run_blocking_ordered", "run_blocking", "invoke_client_method", "to_thread", "run_in_executor"})
BLOCKING_ATTR_SUFFIXES = {
    "add_node": "engine write: add_node", "add_edge": "engine write: add_edge",
    "link_nodes": "engine write: link_nodes", "delete_node": "engine write: delete_node",
    "upsert_node": "engine write: upsert_node", "_upsert_node": "engine write: _upsert_node",
    "query_cypher": "engine read: query_cypher", "query_cypher_write": "engine write: query_cypher_write",
    "execute_cypher": "engine: execute_cypher", "run_cypher": "engine: run_cypher",
    "discover_agents": "registry: discover_agents", "get_discovery_registry": "registry: get_discovery_registry",
    "read_text": "blocking file read: Path.read_text", "write_text": "blocking file write: Path.write_text",
    "read_bytes": "blocking file read: Path.read_bytes", "write_bytes": "blocking file write: Path.write_bytes",
    "submit_task": "engine write: submit_task (durable WorkItem enqueue)",
    "get_blast_radius": "engine read: get_blast_radius", "search_hybrid": "engine read: search_hybrid",
    "get_shortest_path": "engine read: get_shortest_path",
    "execute_federated_query": "engine read: execute_federated_query",
    "get_text_embedding": "blocking remote-embedder call: get_text_embedding",
    "get_text_embedding_batch": "blocking remote-embedder call: get_text_embedding_batch",
}
_MODULE_FUNCTIONS = {
    "subprocess": frozenset({"run", "call", "check_call", "check_output", "Popen"}),
    "requests": frozenset({"get", "post", "put", "delete", "patch", "head"}),
}
_SHAPE_PREFIXES = (
    ("time.sleep", "time_sleep"), ("subprocess.", "subprocess"), ("requests.", "http_request"),
    ("open()", "open_file"), ("engine write", "engine_write"), ("engine read", "engine_read"),
    ("engine:", "engine_other"), ("registry:", "registry_call"), ("blocking remote-embedder", "embedder_call"),
)


def dotted_name(node: ast.AST) -> str | None:
    """Dotted path of a call target, e.g. ``engine.query_cypher``."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    return ".".join([node.id, *reversed(parts)])


def call_label(call: ast.Call) -> str | None:
    """The blocking-call label for one call, or ``None``."""
    if isinstance(call.func, ast.Name) and call.func.id == "open":
        return "open() (blocking file I/O)"
    dotted = dotted_name(call.func)
    if dotted is None:
        return None
    base, tail = dotted.split(".")[0], dotted.split(".")[-1]
    if base == "time" and tail == "sleep":
        return "time.sleep (blocks the loop)"
    if tail in _MODULE_FUNCTIONS.get(base, frozenset()):
        return f"{base}.{tail}"
    human = BLOCKING_ATTR_SUFFIXES.get(tail)
    return f"{human} ({dotted})" if human else None


def label_shape(label: str) -> str:
    for prefix, shape in _SHAPE_PREFIXES:
        if label.startswith(prefix):
            return shape
    return "path_file_io" if "blocking file" in label else "other"


def _is_hop(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    callee = node.func
    return (callee.attr if isinstance(callee, ast.Attribute) else getattr(callee, "id", None)) in HOP_CALL_NAMES


def hopped_names(function: ast.AsyncFunctionDef) -> set[str]:
    """Nested functions passed by bare reference to a hop call (they run off-loop)."""
    return {arg.id for node in ast.walk(function) if _is_hop(node) for arg in node.args if isinstance(arg, ast.Name)}
