"""plan-conformance: a ``specs/<feature>/plan.md`` follows the vendored plan template exactly.

Checks one or more plans and prints ``path:line: message`` lines. A plan fails when its level-2
headings differ from the template, when a template placeholder is left in, when it names a spec
row that no ``requirements.md`` of this repository defines, cites a foreign-prefix ID that its owner
repository does not define (resolved against the ``--id-index`` file; the gate fails closed without one), or when a relative link does not
resolve. The headings are read from ``.specify/templates/plan-template.md`` at run time.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.core.settings import setting
from pipelines_hooks.docs.public_surface_links import local_link_findings
from pipelines_hooks.specs import narrative
from pipelines_hooks.specs.artifacts import unfenced
from pipelines_hooks.specs.ids import ROW_RE, TOKEN_RE
from pipelines_hooks.specs.templates_sync import TEMPLATES, vended_source

TEMPLATE_NAME = "plan-template.md"
MARKERS = ("[NEEDS CLARIFICATION", "[FEATURE]", "[###-feature-name]", "ACTION REQUIRED", "NEEDS CLARIFICATION")
TITLE_RE = re.compile(r"^# ([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*) — Implementation plan$")
SPEC_TITLE_RE = re.compile(r"^# ([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*) — ")
FIELD_RE = re.compile(r"^\s*[-*]\s+\*\*[^*]+\*\*:\s*(.*)$")
TOKEN_SPAN_RE = re.compile(r"\[[^\]\n]{4,}\](?![(\[:])")
PREFIX_RE = re.compile(r"-R\d+(?:\.\d+)*$")


def template_text(root: Path) -> str:
    """The plan template: the repository copy, else the vended one."""
    local = root / TEMPLATES / TEMPLATE_NAME
    path = local if local.is_file() else vended_source() / TEMPLATE_NAME
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CannotRun(f"cannot read {path}: {exc}") from exc


def _headings(text: str) -> list[tuple[int, str]]:
    return [(n, line.rstrip()) for n, line in narrative.prose(text) if line.startswith("## ")]


def required_headings(template: str) -> list[str]:
    """The level-2 headings of the template, in order."""
    return [h for _, h in _headings(template)]


def placeholder_tokens(template: str) -> set[str]:
    """Bracketed spans the template itself uses as fill-in text."""
    return {m.group(0) for _, line in narrative.prose(template) for m in TOKEN_SPAN_RE.finditer(line)}


def known_ids(root: Path) -> set[str]:
    """Every row ID that a ``requirements.md`` of this repository defines."""
    found: set[str] = set()
    for path in sorted((root / "specs").glob("*/requirements.md")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = ROW_RE.match(line)
            if match:
                found.add(match.group(1))
    return found


def _spec_id(plan: Path) -> str | None:
    req = plan.parent / "requirements.md"
    first = req.read_text(encoding="utf-8", errors="replace").splitlines()[:1] if req.is_file() else []
    match = SPEC_TITLE_RE.match(first[0]) if first else None
    return match.group(1) if match else None


def _heading_findings(text: str, required: list[str], spec_id: str | None) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    lines = text.splitlines()
    match = TITLE_RE.match(lines[0] if lines else "")
    if not match:
        out.append((1, "first line must read '# <SPEC-ID> — Implementation plan' with the real spec ID"))
    elif spec_id and match.group(1) != spec_id:
        out.append((1, f"title ID {match.group(1)} must equal the spec ID {spec_id} of requirements.md"))
    found = _headings(text)
    names = [h for _, h in found]
    for heading in required:
        if heading not in names:
            out.append((1, f"missing heading '{heading}'; add it exactly as written, in template order"))
        elif names.count(heading) > 1:
            out.append(([n for n, h in found if h == heading][1], f"duplicate heading '{heading}'; keep exactly one"))
    for n, heading in found:
        if heading not in required:
            out.append((n, f"unexpected heading '{heading}'; rename it to a template heading or demote it to '###'"))
    present = [h for h in names if h in required]
    wanted = [h for h in required if h in present]
    if len(set(present)) == len(present) and present != wanted:
        for n, heading in found:
            if heading in required and present.index(heading) != wanted.index(heading):
                out.append((n, f"heading '{heading}' is out of order; template order is: {' > '.join(required)}"))
                break
    return out


def _empty_sections(text: str) -> list[tuple[int, str]]:
    heads, lines = _headings(text), text.splitlines()
    out: list[tuple[int, str]] = []
    for i, (n, heading) in enumerate(heads):
        end = heads[i + 1][0] - 1 if i + 1 < len(heads) else len(lines)
        if not any(line.strip() for line in lines[n:end]):
            out.append((n, f"section '{heading}' is empty; write its content, or 'none' where the template allows"))
    return out


def _placeholder_findings(text: str, tokens: set[str]) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for n, line in unfenced(text):
        marker = next((m for m in MARKERS if m in line), None)
        stripped, field = line.strip(), FIELD_RE.match(line)
        whole = stripped.startswith("[") and stripped.endswith("]") and not stripped.startswith("[ ]")
        hit = next((t for t in tokens if t in line), None)
        if marker:
            out.append((n, f"unresolved placeholder '{marker}'; resolve it and delete the marker"))
        elif whole and not re.match(r"^\[[^\]]*\]\(", stripped):
            out.append((n, "template placeholder left as a bracketed line; replace it with real content"))
        elif field and field.group(1).startswith("["):
            out.append((n, "template field value left in brackets; replace it with the real value or N/A"))
        elif hit:
            out.append((n, f"template text {hit[:40]!r} left in the plan; replace it with real content"))
    return out


def foreign_ids(text: str, known: set[str]) -> set[str]:
    """IDs the plan cites whose prefix no row of this repository uses."""
    prefixes = {PREFIX_RE.sub("", i) for i in known}
    cited = {m.group(1) for _, line in unfenced(text) for m in TOKEN_RE.finditer(line)}
    return {i for i in cited if i not in known and PREFIX_RE.sub("", i) not in prefixes}


def load_index(path: Path | None) -> dict[str, set[str]]:
    """The cross-repo ID index (repository -> row IDs); fails closed when absent or unreadable."""
    if path is None:
        raise CannotRun(
            "no cross-repo ID index; pass --id-index <path> or set PIPELINES_SPEC_ID_INDEX (pipelines-hook spec-id-index writes one)"
        )
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return {repo: set(ids) for repo, ids in doc["repos"].items()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise CannotRun(f"no cross-repo ID index: cannot read {path}: {exc}") from exc


def _owner(ident: str, index: dict[str, set[str]]) -> str:
    prefix = PREFIX_RE.sub("", ident)
    return next((r for r, ids in sorted(index.items()) if any(PREFIX_RE.sub("", i) == prefix for i in ids)), "unknown")


def _id_findings(text: str, known: set[str], index: dict[str, set[str]] | None = None) -> list[tuple[int, str]]:
    prefixes = {PREFIX_RE.sub("", i) for i in known}
    resolved = set().union(*index.values()) if index else set()
    out: list[tuple[int, str]] = []
    for n, line in unfenced(text):
        for match in TOKEN_RE.finditer(line):
            ident = match.group(1)
            if ident in known:
                continue
            if PREFIX_RE.sub("", ident) in prefixes:
                out.append(
                    (n, f"spec ID {ident} is not defined by any specs/*/requirements.md; fix the ID or add the row")
                )
            elif ident not in resolved:
                out.append(
                    (
                        n,
                        f"unknown ID {ident} (owner {_owner(ident, index or {})}); fix the ID or cite a row its owner defines",
                    )
                )
    return out


def _link_findings(root: Path, plan: Path, text: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for n, line in unfenced(text):
        for finding in local_link_findings(root, line, name="link", base=plan.parent):
            out.append((n, f"{finding}; fix the relative path"))
    return out


def check_plan(
    root: Path, plan: Path, template: str, known: set[str], index: dict[str, set[str]] | None = None
) -> list[str]:
    """All ``path:line: message`` findings for one plan."""
    text = plan.read_text(encoding="utf-8", errors="replace")
    rel = plan.resolve().relative_to(root.resolve()).as_posix()
    found = _heading_findings(text, required_headings(template), _spec_id(plan))
    found += _empty_sections(text) + _placeholder_findings(text, placeholder_tokens(template))
    found += _id_findings(text, known, index) + _link_findings(root, plan, text)
    return [f"{rel}:{n}: {msg}" for n, msg in sorted(dict.fromkeys(found), key=lambda item: item[0])]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="plan-conformance", description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="plan.md files (default: the plans the change touches)")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--all", action="store_true", help="check every specs/*/plan.md")
    parser.add_argument(
        "--id-index", type=Path, default=None, help="cross-repo ID index (default: PIPELINES_SPEC_ID_INDEX)"
    )
    parser.add_argument("--base", default=None, help="revision the change is measured against")
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    if args.paths:
        plans = [p if p.is_absolute() else Path.cwd() / p for p in args.paths]
    elif args.all:
        plans = sorted((root / "specs").glob("*/plan.md"))
    else:
        touched = narrative.touched_paths(root, args.base)
        plans = [root / t for t in sorted(touched) if re.fullmatch(r"specs/[^/]+/plan\.md", t) and (root / t).is_file()]
    template, known = template_text(root), known_ids(root)
    index = None
    if any(foreign_ids(plan.read_text(encoding="utf-8", errors="replace"), known) for plan in plans):
        env = setting("PIPELINES_SPEC_ID_INDEX")
        index = load_index(args.id_index or (Path(env) if env else None))
    findings = [f for plan in plans for f in check_plan(root, plan, template, known, index)]
    for finding in findings:
        print(finding)
    if findings:
        print(f"plan-conformance: FAIL: {len(findings)} finding(s) in {len(plans)} plan(s)")
        return 1
    print(f"plan-conformance: clean ({len(plans)} plan(s) checked)")
    return 0
