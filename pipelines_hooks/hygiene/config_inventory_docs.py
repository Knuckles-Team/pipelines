"""Documentation roles of the project configuration inventory.

Extends ``config-inventory`` (never a second project list): when the declaration carries a
``[documentation]`` table every declared project must also carry five documentation roles, each
a managed section bounded by ``<!-- pipelines:managed role=... -->`` markers (comment form in
YAML): ``readme``, ``agent-guide``, ``content-index``, ``changelog`` and ``doc-config``.  The
navigation graph README -> content index -> overview/components/reference pages is checked edge
by edge.  Content outside managed sections (custom prose, historical changelog entries) is
preserved and never compared.  Retired documentation roots are refused.
"""

from __future__ import annotations

import hashlib
import posixpath
import re
import string
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import blob_bytes
from pipelines_hooks.core.tracked import tracked_paths

DOC_TEMPLATE_VERSION = "1"
NAV_PAGES = ("overview", "components", "reference")
ROLES = ("readme", "agent-guide", "content-index", "changelog", "doc-config")
_FILES = {
    "readme": "README.md",
    "agent-guide": "AGENTS.md",
    "content-index": "$content/index.md",
    "changelog": "CHANGELOG.md",
    "doc-config": "mkdocs.yml",
}
_OPEN = {"doc-config": "# pipelines:managed role={role} template={template}\n"}
_CLOSE = {"doc-config": "# pipelines:end role={role}\n"}
_MD_OPEN, _MD_CLOSE = (
    "<!-- pipelines:managed role={role} template={template} -->\n",
    "<!-- pipelines:end role={role} -->\n",
)
_BODIES = {
    "readme": "# $name\n\n## Documentation\n\n- [Documentation index]($content/index.md)\n",
    "agent-guide": "# $name agent guide\n\nStart at the [README](README.md).\n",
    "content-index": "# $name\n\n- [Overview](overview.md)\n- [Components](components.md)\n- [Reference](reference.md)\n",
    "changelog": "# Changelog\n\nEntries follow `## [x.y.z] - YYYY-MM-DD`, newest first.\n",
    "doc-config": "site_name: $name\ndocs_dir: $content\n",
}
_PAGE = "# $title\n\nWrite the $title page of $name here.\n"
_ENTRY = re.compile(r"^## \[(\d+\.\d+\.\d+|Unreleased)\]( - \d{4}-\d{2}-\d{2})?\s*$")
_LINK = re.compile(r"\[[^\]]*\]\((?P<target>[^)#\s]+)")


@dataclass(frozen=True)
class DocPolicy:
    """The declared ``[documentation]`` table: template version, content directory and retired roots."""

    template: str
    content: str | None
    retired: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.template != DOC_TEMPLATE_VERSION:
            raise CannotRun(f"config-inventory: unknown documentation template version {self.template!r}")
        for path in (self.content or "x", *self.retired):
            pure = PurePosixPath(path)
            if pure.is_absolute() or ".." in pure.parts or "\\" in path:
                raise CannotRun(f"config-inventory: unsafe documentation path {path!r}")


def parse_policy(table: object) -> DocPolicy:
    if not isinstance(table, dict) or set(table) - {"template", "content", "retired"}:
        raise CannotRun("config-inventory: unknown fields in [documentation]")
    return DocPolicy(str(table.get("template", "")), table.get("content"), tuple(table.get("retired", ())))


def _join(project: str, rel: str) -> str:
    return rel if project == "." else f"{project}/{rel}"


def content_dir(root: Path, project: str, policy: DocPolicy) -> str:
    """The canonical content directory: declared, or discovered; two candidates are ambiguous."""
    if policy.content:
        return policy.content
    found = [c for c in ("pages", "docs") if blob_bytes(root, f":{_join(project, c + '/index.md')}") is not None]
    if len(found) > 1:
        raise CannotRun(f"config-inventory: ambiguous canonical documentation root for {project!r}: {found}")
    return found[0] if found else "pages"


def doc_file(project: str, role: str, content: str) -> str:
    return _join(project, string.Template(_FILES[role]).substitute(content=content))


def _wrap(role: str, body: str) -> str:
    return (
        _OPEN.get(role, _MD_OPEN).format(role=role, template=DOC_TEMPLATE_VERSION)
        + body
        + _CLOSE.get(role, _MD_CLOSE).format(role=role)
    )


def render_role(role: str, params: dict[str, str], content: str) -> str:
    body = string.Template(_BODIES[role]).substitute(name=params["name"], content=content)
    return _wrap(role, body)


def render_pages(params: dict[str, str], content: str) -> dict[str, str]:
    return {
        f"{content}/{p}.md": string.Template(_PAGE).substitute(title=p.title(), name=params["name"]) for p in NAV_PAGES
    }


def _block(text: str, role: str) -> re.Match[str] | None:
    r = re.escape(role)
    if role in _OPEN:
        pattern = rf"# pipelines:managed role={r} template=(?P<template>\S+)\n(?P<body>.*?)# pipelines:end role={r}\n"
    else:
        pattern = rf"<!-- pipelines:managed role={r} template=(?P<template>\S+) -->\n(?P<body>.*?)<!-- pipelines:end role={r} -->\n"
    return re.search(pattern, text, re.S)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _links(text: str, base: str) -> set[str]:
    return {
        posixpath.normpath(posixpath.join(posixpath.dirname(base), m["target"]))
        for m in _LINK.finditer(text)
        if "://" not in m["target"]
    }


def check_docs(root: Path, projects: dict[str, dict[str, str]], policy: DocPolicy) -> tuple[list[str], list[str]]:
    """Findings (exit 1) and evidence lines for every declared project's documentation roles."""
    findings: list[str] = []
    lines: list[str] = []
    tree = hashlib.sha256()
    for project, params in projects.items():
        content = content_dir(root, project, policy)
        texts: dict[str, str] = {}
        for role in ROLES:
            path = doc_file(project, role, content)
            raw = blob_bytes(root, f":{path}")
            want = _block(render_role(role, params, content), role)
            assert want is not None
            if raw is None:
                findings.append(f"{path}: project {project!r} documentation role {role}: required file is missing")
                lines.append(
                    f"doc-role project={project} role={role} path={path} template={DOC_TEMPLATE_VERSION} expected={_digest(want['body'])} observed=absent"
                )
                continue
            text = raw.decode("utf-8", errors="replace")
            tree.update(path.encode() + raw)
            texts[role] = text
            found = _block(text, role)
            line = text[: found.start()].count("\n") + 1 if found else 1
            lines.append(
                f"doc-role project={project} role={role} path={path} template={found['template'] if found else 'absent'} "
                f"expected={_digest(want['body'])} observed={_digest(found['body']) if found else 'absent'}"
            )
            if found is None:
                findings.append(f"{path}:1: project {project!r} role {role}: managed section is missing")
            elif found["template"] != DOC_TEMPLATE_VERSION:
                findings.append(f"{path}:{line}: project {project!r} role {role}: template version drift")
            elif found["body"] != want["body"]:
                findings.append(f"{path}:{line}: project {project!r} role {role}: managed section drifted")
        if "doc-config" in texts:
            try:
                config = yaml.safe_load(texts["doc-config"])
            except yaml.YAMLError as exc:
                findings.append(
                    f"{doc_file(project, 'doc-config', content)}: invalid documentation configuration: {str(exc).splitlines()[0][:80]}"
                )
            else:
                if not isinstance(config, dict) or config.get("docs_dir") != content:
                    findings.append(f"{doc_file(project, 'doc-config', content)}: docs_dir must be {content!r}")
        if "changelog" in texts:
            path = doc_file(project, "changelog", content)
            found = _block(texts["changelog"], "changelog")
            outside = texts["changelog"].replace(found.group(0), "") if found else texts["changelog"]
            for number, text in enumerate(texts["changelog"].splitlines(), 1):
                if text.startswith("## ") and text in outside.splitlines() and not _ENTRY.match(text):
                    findings.append(f"{path}:{number}: changelog heading {text!r} breaks the entry grammar")
        index, readme = doc_file(project, "content-index", content), doc_file(project, "readme", content)
        edges = [(readme, index)] + [(index, _join(project, f"{content}/{page}.md")) for page in NAV_PAGES]
        for source, target in edges:
            role = "readme" if source == readme else "content-index"
            linked = _links(texts[role], source) if role in texts else set()
            ok = target in linked and blob_bytes(root, f":{target}") not in (None, b"")
            lines.append(f"doc-edge project={project} from={source} to={target} {'ok' if ok else 'broken'}")
            if not ok:
                findings.append(f"{source}: navigation edge to {target} is missing or its target is absent or empty")
    for retired in policy.retired:
        for path in tracked_paths(root, (f"{retired}/**", retired)):
            findings.append(f"{path}: content under the retired documentation root {retired}/")
    lines.append(f"doc-tree digest={tree.hexdigest()[:16]} template={DOC_TEMPLATE_VERSION}")
    return findings, lines
