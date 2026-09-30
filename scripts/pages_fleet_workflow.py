"""Bind each consumer's Pages call to the declared immutable pipeline source."""

from __future__ import annotations

import yaml

from scripts.pages_fleet_declaration import ParityError, object_git
from scripts.pages_fleet_trees import ExactTree
from scripts.readiness.filesystem import _safe_existing_path
from scripts.readiness.mkdocs import validate_content_source


def mapping_entries(node: yaml.Node):
    """Validate the mapping authority before interpreting its entries."""
    if not isinstance(node, yaml.MappingNode) or node.tag != "tag:yaml.org,2002:map":
        raise ParityError("workflow-mapping-required")
    return node.value


def mapping(node: yaml.Node) -> dict:
    result = {}
    for key, value in mapping_entries(node):
        if scalar(key) in (None, "<<") or key.value in result:
            raise ParityError("workflow-ambiguous-mapping")
        result[key.value] = value
    return result


def scalar(node: yaml.Node | None, *, boolean: bool = False) -> str | None:
    """Authority strings must have standard tags; boolean input also permits bool."""
    return scalar_value(node, boolean) if isinstance(node, yaml.ScalarNode) else None


def scalar_value(node: yaml.ScalarNode, boolean: bool) -> str:
    """Reject explicit tags outside the authority's supported YAML types."""
    allowed = ("tag:yaml.org,2002:str", "tag:yaml.org,2002:bool") if boolean else ("tag:yaml.org,2002:str",)
    if node.tag not in allowed:
        raise ParityError("workflow-scalar-tag-invalid")
    return node.value


def pages_calls(tree: ExactTree, repository: str) -> list[dict]:
    paths = object_git(tree.root, ["ls-tree", "-r", "-z", "--name-only", tree.commit, "--", ".github/workflows"])
    calls = []
    for path in paths.split("\0"):
        if not path.endswith((".yaml", ".yml")):
            continue
        try:
            # BaseLoader keeps GitHub's `on` and plain scalars as strings,
            # while preserving explicit tags for authority validation. Compose
            # never constructs tagged objects or resolves root merge mappings.
            document = yaml.compose(tree.read(path), Loader=yaml.BaseLoader)
        except yaml.YAMLError as exc:
            raise ParityError("workflow-yaml-invalid") from exc
        jobs = mapping(mapping(document).get("jobs"))
        for node in jobs.values():
            job = mapping(node)
            uses = scalar(job.get("uses")) or ""
            if is_pages_call(uses, repository):
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
    if scalar(inputs.get("shared_theme_enabled"), boolean=True) != "true":
        raise ParityError("workflow-shared-theme-disabled")
    content = scalar(inputs["content_source"]) if "content_source" in inputs else "pages"
    if content != consumer["content_source"]:
        raise ParityError("workflow-content-source-mismatch")
    _safe_existing_path(tree.root, "mkdocs.yml", "mkdocs")
    validate_content_source(tree.root, content)


def is_pages_call(uses: str, repository: str) -> bool:
    """GitHub repository identity ignores case; the Git workflow path does not."""
    parts = uses.split("/", 2)
    return (len(parts) == 3 and "/".join(parts[:2]).lower() == repository.lower()
            and parts[2].startswith(".github/workflows/pages_pipeline.yml@"))
