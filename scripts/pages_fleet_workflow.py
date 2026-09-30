"""Bind each consumer's Pages call to the declared immutable pipeline source."""

from __future__ import annotations

import yaml

from scripts.pages_fleet_declaration import ParityError, object_git
from scripts.pages_fleet_trees import ExactTree
from scripts.readiness.filesystem import _safe_existing_path
from scripts.readiness.mkdocs import validate_content_source


def mapping(node: yaml.Node) -> dict:
    if not isinstance(node, yaml.MappingNode):
        raise ParityError("workflow-mapping-required")
    result = {}
    for key, value in node.value:
        if not isinstance(key, yaml.ScalarNode) or key.value in result:
            raise ParityError("workflow-ambiguous-mapping")
        result[key.value] = value
    return result


def scalar(node: yaml.Node | None) -> str | None:
    return node.value if isinstance(node, yaml.ScalarNode) else None


def pages_calls(tree: ExactTree, repository: str) -> list[dict]:
    paths = object_git(tree.root, ["ls-tree", "-r", "-z", "--name-only", tree.commit, "--", ".github/workflows"])
    prefix = f"{repository}/.github/workflows/pages_pipeline.yml@".lower()
    calls = []
    for path in paths.split("\0"):
        if not path.endswith((".yaml", ".yml")):
            continue
        try:
            document = yaml.compose(tree.read(path), Loader=yaml.SafeLoader)
        except yaml.YAMLError as exc:
            raise ParityError("workflow-yaml-invalid") from exc
        jobs = mapping(mapping(document).get("jobs"))
        for node in jobs.values():
            job = mapping(node)
            uses = scalar(job.get("uses")) or ""
            if uses.lower().startswith(prefix):
                calls.append(job)
    return calls


def validate_workflow(tree: ExactTree, consumer: dict, pipeline: dict) -> None:
    """Require an unambiguous literal Pages call, with no expression fallback."""
    calls = pages_calls(tree, pipeline["repository"])
    if len(calls) != 1:
        raise ParityError("pages-call-ambiguous-or-missing")
    call = calls[0]
    revision = scalar(call["uses"]).rsplit("@", 1)[1]
    if revision != pipeline["revision"]:
        raise ParityError("workflow-revision-mismatch")
    inputs = mapping(call.get("with"))
    if scalar(inputs.get("shared_theme_enabled")) != "true":
        raise ParityError("workflow-shared-theme-disabled")
    content = scalar(inputs["content_source"]) if "content_source" in inputs else "pages"
    if content != consumer["content_source"]:
        raise ParityError("workflow-content-source-mismatch")
    _safe_existing_path(tree.root, "mkdocs.yml", "mkdocs")
    validate_content_source(tree.root, content)
