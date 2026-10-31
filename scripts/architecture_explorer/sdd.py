"""Spec-driven delivery facts for Canopy (PIPE-PAGES-R051.*).

Reads the documents of each spec family (already fetched by ``sources``) and returns the compact facts the page needs
without holding any document text: one card per family (title, phase, task progress, present documents, constitution
warnings), the constitution version per repository, and the lazily loaded search extras (task lines and plan headings).
Rendering to HTML stays in ``details``; this module only parses markdown for counts and headings.
"""

from __future__ import annotations

import re
from collections import Counter

# Document kinds a card links to. The page holds the same list; a card stores the present kinds as a bit set.
KINDS = ("spec", "plan", "tasks", "test-spec", "checklists", "research", "data-model", "quickstart", "contracts")
TASK_RE = re.compile(r"^[ \t]*[-*][ \t]+\[([ xX])\][ \t]+(\S.*)$", re.M)
PHASE_RE = re.compile(r"\bP([1-5])\b")
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
    """Return ``P1`` to ``P5``: the phase the plan's Delivery phase section names, else the most common release phase."""
    found = PHASE_RE.findall(section(plan, "Delivery phase"))
    if found:
        return "P" + Counter(found).most_common(1)[0][0]
    return Counter(release_phases).most_common(1)[0][0] if release_phases else ""


def family_card(docs: dict[str, str], files: set[str], family: str, release_phases: list[str]) -> dict:
    """Return the compact card of one spec family: title, phase, ``[done, open]`` tasks, document bits and warnings."""
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
    warn = failing_principles(plan)
    if warn:
        card["w"] = warn
    return card


def build_cards(snaps: list, release_of: dict[str, str], release_phase: dict[str, str]) -> dict[str, dict[str, dict]]:
    """Return ``{repo: {family: card}}`` for every family that has spec rows."""
    cards: dict[str, dict[str, dict]] = {}
    for snap in snaps:
        by_family: dict[str, list[str]] = {}
        for row in snap.rows:
            phase = release_phase.get(release_of.get(row["id"], ""), "")
            by_family.setdefault(row["family"], []).append(phase)
        for family, phases in by_family.items():
            docs = snap.docs.get(family, {})
            cards.setdefault(snap.repo, {})[family] = family_card(docs, snap.files, family, [p for p in phases if p])
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
