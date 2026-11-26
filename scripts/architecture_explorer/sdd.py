"""Spec-driven delivery facts for Canopy (PIPE-PAGES-R051.*).

Reads the documents of each spec family (already fetched by ``sources``) and returns the compact facts the page needs
without holding any document text: one card per family (title, phase, task progress, present documents, constitution
warnings), the constitution version per repository, and the lazily loaded search extras (task lines and plan headings).
Rendering to HTML stays in ``details``; this module only parses markdown for counts and headings.
"""

from __future__ import annotations

import enum
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

# Document kinds a card links to. The page holds the same list; a card stores the present kinds as a bit set.
KINDS = ("spec", "plan", "tasks", "test-spec", "checklists", "research", "data-model", "quickstart", "contracts")
TASK_RE = re.compile(r"^[ \t]*[-*][ \t]+\[([ xX])\][ \t]+(\S.*)$", re.M)
PHASE_LINE_RE = re.compile(r"^Delivery phase:\s*P([1-5])\b", re.M)
VERSION_RE = re.compile(r"\*\*Version\*\*:\s*([0-9][^\s|]*)")
FAIL_RE = re.compile(r"(?:[:|—–-]|\*\*)\s*\**fail\b", re.I)
H2_RE = re.compile(r"^##[ \t]+(.+?)[ \t]*#*[ \t]*$", re.M)
TITLE_RE = re.compile(r"^#[ \t]+(.+?)[ \t]*$", re.M)
LEAD_RE = re.compile(r"^[A-Za-z][A-Za-z ]*[:—–-]\s+")
TASK_MAX = 120
WARN_MAX = 72
PLAN = "plan.md"
TASKS = "tasks.md"
SPEC = "spec.md"
CONSTITUTION_PATH = ".specify/memory/constitution.md"
CONSTITUTION_DOC = ("_constitution", "constitution.md")


def slug(text: str) -> str:
    """Return the anchor of a heading: lower-case words joined by hyphens."""
    return "-".join(re.findall(r"[a-z0-9]+", text.lower())) or "section"


def section(markdown: str, name: str) -> str:
    """Return the body of the ``## <name>`` section (case-insensitive prefix match), or an empty string."""
    heads = list(H2_RE.finditer(markdown))
    for i, head in enumerate(heads):
        if head.group(1).strip().lower().startswith(name.lower()):
            end = heads[i + 1].start() if i + 1 < len(heads) else len(markdown)
            return markdown[head.end() : end]
    return ""


def tasks_of(markdown: str) -> list[tuple[bool, str]]:
    """Return ``(done, text)`` for every checkbox task line, text cut at TASK_MAX characters."""
    return [(m.group(1) != " ", m.group(2).strip()[:TASK_MAX]) for m in TASK_RE.finditer(markdown)]


def constitution_version(text: str) -> str:
    """Return the version string a constitution states, or an empty string."""
    match = VERSION_RE.search(text)
    return match.group(1) if match else ""


def failing_principles(plan: str) -> list[str]:
    """Return the Constitution Check lines of a plan whose verdict is a failure, each cut at WARN_MAX characters."""
    out = []
    for line in section(plan, "Constitution Check").splitlines():
        if line.lstrip().startswith(("-", "*", "|")) and FAIL_RE.search(line):
            out.append(re.sub(r"[*`]", "", line).strip(" -*|")[:WARN_MAX])
    return out


def title_of(spec: str, plan: str, family: str) -> str:
    """Return the spec title: the first heading of spec.md, else of plan.md, else the family name."""
    for text in (spec, plan):
        match = TITLE_RE.search(text)
        if match:
            return LEAD_RE.sub("", match.group(1)).strip()[:96]
    return family


def kinds_bits(names) -> int:
    """Return the bit set of document kinds present among the given file names."""
    bits = 0
    for name in names:
        head = name.split("/")[0].removesuffix(".md")
        if head in KINDS:
            bits |= 1 << KINDS.index(head)
    return bits


def phase_of(plan: str, release_phases: list[str]) -> str:
    """Return ``P1`` to ``P5``: the plan's ``Delivery phase: P<n>`` line, else the most common release phase."""
    found = PHASE_LINE_RE.search(plan)
    if found:
        return "P" + found.group(1)
    return Counter(release_phases).most_common(1)[0][0] if release_phases else ""


# ------------------------------------------------------------ SDD phase of a family (PIPE-PAGES-R054)

RESEARCH = "research.md"
CLARIFY_MARK = "NEEDS CLARIFICATION"
OPEN_HEADING_RE = re.compile(r"open questions|unresolved", re.I)
ROW_ID_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-R\d+(?:\.\d+)*\b")
UNCHECKED_RE = re.compile(r"^[ \t]*[-*][ \t]+\[ \][ \t]+(\S.*)$")
HEADING_LINE_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")


class SddPhase(enum.IntEnum):
    """The spec-driven phases of a family, lowest first."""

    SPECIFIED = 1
    RESEARCH_DONE = 2
    PLAN_ACCEPTED = 3
    TASKS_READY = 4
    IMPLEMENTING = 5
    VERIFIED = 6

    @property
    def label(self) -> str:
        return self.name.lower().replace("_", "-")


@dataclass(frozen=True)
class PhaseFacts:
    """What the phase predicates read: family documents, the family's rows, and the plan findings."""

    docs: dict[str, str]
    rows: tuple[dict, ...]
    plan_findings: tuple[str, ...] | None  # None when the plan was not checked


def active_rows(rows) -> list[dict]:
    """Rows that count toward phases: not retired and not a rollup."""
    return [r for r in rows if r.get("status") != "RETIRED" and not r.get("rollup")]


def _has_spec(f: PhaseFacts) -> bool:
    return bool(f.docs.get(SPEC, "").strip())


def _research_done(f: PhaseFacts) -> bool:
    if any(CLARIFY_MARK in text for text in f.docs.values()):
        return False
    return not any(q["kind"] == "open" for q in open_questions(f.docs))


def _plan_accepted(f: PhaseFacts) -> bool:
    return bool(f.docs.get(PLAN, "").strip()) and f.plan_findings == ()


def _tasks_ready(f: PhaseFacts) -> bool:
    full = f.docs.get(TASKS, "")
    tasks = " ".join(m.group(2) for m in TASK_RE.finditer(full))
    rows = active_rows(f.rows)
    return bool(rows) and all(r["id"] in tasks for r in rows)


def _implementing(f: PhaseFacts) -> bool:
    return any(r.get("status") in ("LANDED", "VERIFIED") for r in f.rows) or any(
        d for d, _ in tasks_of(f.docs.get(TASKS, ""))
    )


def _verified(f: PhaseFacts) -> bool:
    rows = [r for r in f.rows if r.get("status") != "RETIRED"]
    return bool(rows) and all(r.get("status") == "VERIFIED" for r in rows)


PHASE_PREDICATES: dict[SddPhase, Callable[[PhaseFacts], bool]] = {
    SddPhase.SPECIFIED: _has_spec,
    SddPhase.RESEARCH_DONE: _research_done,
    SddPhase.PLAN_ACCEPTED: _plan_accepted,
    SddPhase.TASKS_READY: _tasks_ready,
    SddPhase.IMPLEMENTING: _implementing,
    SddPhase.VERIFIED: _verified,
}


def sdd_phase(docs: dict[str, str], rows, plan_findings: list[str] | None = None) -> SddPhase | None:
    """Return the highest phase whose predicate holds when every lower predicate holds, or ``None``."""
    facts = PhaseFacts(docs, tuple(rows), None if plan_findings is None else tuple(plan_findings))
    reached = None
    for phase in SddPhase:
        if not PHASE_PREDICATES[phase](facts):
            break
        reached = phase
    return reached


def open_questions(docs: dict[str, str], files: set[str] | None = None, family: str = "") -> list[dict]:
    """Return ``{kind, text, doc, line, row}`` for each open question of a family (PIPE-PAGES-R058.1).

    ``marker`` is a ``NEEDS CLARIFICATION`` marker in any document; ``open`` is an unchecked item under a heading of
    ``research.md`` that names open questions; ``unreadable`` marks a research file that could not be decoded.
    """
    found = []
    if files and f"specs/{family}/{RESEARCH}" in files and not docs.get(RESEARCH, "").strip():
        found.append({"kind": "unreadable", "text": "research unreadable", "doc": RESEARCH, "line": 0, "row": ""})
    for name in sorted(docs):
        text = docs[name]
        lines = text.splitlines()
        under_open = False
        for number, line in enumerate(lines, 1):
            head = HEADING_LINE_RE.match(line)
            if head:
                under_open = bool(OPEN_HEADING_RE.search(head.group(2)))
            ids = ROW_ID_RE.search(line)
            row = ids.group(0) if ids else ""
            if CLARIFY_MARK in line:
                found.append(
                    {"kind": "marker", "text": line.strip()[:TASK_MAX], "doc": name, "line": number, "row": row}
                )
            elif name == RESEARCH and under_open and UNCHECKED_RE.match(line):
                item = UNCHECKED_RE.match(line).group(1).strip()
                found.append({"kind": "open", "text": item[:TASK_MAX], "doc": name, "line": number, "row": row})
    return found


def family_card(
    docs: dict[str, str],
    files: set[str],
    family: str,
    release_phases: list[str],
    rows=(),
    plan_check: Callable[[str], list[str]] | None = None,
) -> dict:
    """Return the compact card of one family: title, phase, tasks, document bits, SDD phase and open questions.

    ``s`` is the SDD phase number (0 when the family has no ``spec.md``); ``q`` is the count of open questions that
    name no row, and appears only when above zero. ``plan_check`` returns the plan-conformance findings of a plan text.
    """
    plan = docs.get(PLAN, "")
    tasks = tasks_of(docs.get(TASKS, ""))
    done = sum(1 for d, _ in tasks if d)
    base = f"specs/{family}/"
    present = [f[len(base) :] for f in files if f.startswith(base)]
    card = {
        "t": title_of(docs.get(SPEC, ""), plan, family),
        "p": phase_of(plan, release_phases),
        "k": [done, len(tasks) - done],
        "d": kinds_bits(present),
    }
    findings = plan_check(plan) if plan_check and plan.strip() else None
    phase = sdd_phase(docs, rows, findings)
    card["s"] = int(phase) if phase else 0
    asked = [q for q in open_questions(docs, files, family) if q["kind"] != "unreadable"]
    if asked:
        card["q"] = len(asked)
    if any(q["kind"] == "unreadable" for q in open_questions(docs, files, family)):
        card["u"] = "research unreadable"
    warn = failing_principles(plan)
    if warn:
        card["w"] = warn
    return card


def next_step(row: dict, phase: int, frontier: bool) -> str:
    """Return the Next-step chip of a row: ``verify``, ``ready``, ``plan``, ``research`` or empty (PIPE-PAGES-R055).

    Rules apply in that order. ``verify``: the row is LANDED. ``ready``: the row is in Next up and the family phase is
    tasks-ready or implementing. ``plan``: the phase is research-done. ``research``: the phase is specified.
    """
    if row.get("status") == "LANDED":
        return "verify"
    if frontier and phase in (SddPhase.TASKS_READY, SddPhase.IMPLEMENTING):
        return "ready"
    if phase == SddPhase.RESEARCH_DONE:
        return "plan"
    if phase == SddPhase.SPECIFIED:
        return "research"
    return ""


def build_cards(
    snaps: list,
    release_of: dict[str, str],
    release_phase: dict[str, str],
    plan_check: Callable[[str], list[str]] | None = None,
) -> dict[str, dict[str, dict]]:
    """Return ``{repo: {family: card}}`` for every family that has spec rows."""
    cards: dict[str, dict[str, dict]] = {}
    for snap in snaps:
        by_family: dict[str, list[dict]] = {}
        for row in snap.rows:
            by_family.setdefault(row["family"], []).append(row)
        for family, rows in by_family.items():
            phases = [release_phase.get(release_of.get(r["id"], ""), "") for r in rows]
            docs = snap.docs.get(family, {})
            cards.setdefault(snap.repo, {})[family] = family_card(
                docs, snap.files, family, [p for p in phases if p], rows, plan_check
            )
    return cards


def constitutions(snaps: list) -> dict[str, str]:
    """Map each repository that holds a constitution to its version (``"?"`` when the file states none)."""
    return {s.repo: constitution_version(s.constitution) or "?" for s in snaps if s.constitution}


def family_nodes(data_nodes: list[dict]) -> dict[tuple[str, str], str]:
    """Map ``(repo, family)`` to the node that owns most of its rows, from the placed tree's nodes."""
    best: dict[tuple[str, str], tuple[int, str]] = {}
    for node in data_nodes:
        count = Counter((s["repo"], s["family"]) for s in node["specs"])
        for key, n in count.items():
            if key not in best or n > best[key][0]:
                best[key] = (n, node["id"])
    return {k: v[1] for k, v in best.items()}


def search_extra(snaps: list, owner: dict[tuple[str, str], str]) -> dict:
    """Return the lazy search extras: one entry per task line and plan heading.

    An entry is ``[kind, text, node, repo, family, doc, anchor]``: kind ``t`` for an open task, ``x`` for a
    checked task and ``h`` for a plan heading; ``doc`` is the file name and ``anchor`` the heading slug.
    """
    items = []
    for snap in snaps:
        for family, docs in sorted(snap.docs.items()):
            node = owner.get((snap.repo, family))
            if not node:
                continue
            for done, text in tasks_of(docs.get(TASKS, "")):
                items.append(["x" if done else "t", text, node, snap.repo, family, TASKS, ""])
            for head in H2_RE.finditer(docs.get(PLAN, "")):
                text = head.group(1).strip()
                items.append(["h", text, node, snap.repo, family, PLAN, slug(text)])
    return {"v": 1, "items": items}
