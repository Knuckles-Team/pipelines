"""Bring one repository to the spec-driven standard: constitution, templates, contribution and agent pointers.

The standard has four parts. Each step writes only when its part is absent, so a second run changes nothing.

* ``.specify/memory/constitution.md``: rendered from the vended constitution template when missing. An existing
  constitution is never rewritten.
* ``.specify/templates/``: the vended templates (``templates_sync.write``).
* ``CONTRIBUTING.md``: the "Spec-driven contributions" pointer section, appended or written with a title.
* ``AGENTS.md``: the "Spec-driven development" section, inserted above the first second-level heading. A repository
  without ``AGENTS.md`` gets none.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.specs import templates_sync

CONSTITUTION = Path(".specify") / "memory" / "constitution.md"
ORG = "https://github.com/Knuckles-Team/pipelines/blob/main"
CONTRIBUTING_HEADING = "## Spec-driven contributions"
AGENTS_HEADING = "## Spec-driven development"

CONTRIBUTING_SECTION = f"""{CONTRIBUTING_HEADING}

Every change follows one process: constitution, route, specify, clarify, plan, tasks, analyze, implement, land, release.
Each step names its skill and the files it writes, in the
[organization contribution guide](https://github.com/Knuckles-Team/.github/blob/main/CONTRIBUTING.md).
Read the [constitution](.specify/memory/constitution.md),
the [spec standard]({ORG}/reference/spec-standard.md) and the
[spec templates](.specify/templates), and pick an open row in
[Canopy](https://knuckles-team.github.io/.github/architecture/). Commit with a `Spec: <ROW-ID>` trailer and a bound test.
"""

AGENTS_SECTION = f"""{AGENTS_HEADING}

Every feature starts with a spec, in this order. Read `.specify/memory/constitution.md` first; it inherits the [organization constitution]({ORG}/.specify/memory/constitution.md). Route the feature with the [ecosystem boundaries]({ORG}/reference/ecosystem-boundaries.md) and file each part in its owner's `specs/`. Run the flow with the skills in the table (universal-skills). Rules: [spec standard]({ORG}/reference/spec-standard.md); templates: `.specify/templates/`, vended by pipelines.

| Step | Skill | Writes | Checked by |
|---|---|---|---|
| Constitution | `speckit-constitution` | `.specify/memory/constitution.md` | spec-standard constitution check |
| Specify | `speckit-specify` | `specs/<id>/spec.md`, `requirements.md` | spec-standard |
| Clarify | `speckit-clarify` | resolves each `[NEEDS CLARIFICATION: ...]` marker | spec-standard clarification check |
| Plan | `speckit-plan` | `plan.md` (upstream sections, Build contract, Production caller chain, Cross-repo seams) | spec-standard plan check |
| Tasks | `speckit-tasks` | `tasks.md`: `- [ ] T001 [P] [US1] <ROW-ID> ...` | spec-standard task-line check |
| Analyze | `speckit-analyze`, `speckit-checklist` | `checklists/requirements.md`, gap fixes | spec-standard analysis and checklist |
| Implement | `speckit-implement` | code and bound tests (`mark.spec("ID")` or `// spec: ID`) | `pipelines-hook spec-trailers` |
| Land | repository development skill | commit with `Spec: <IDs>` directly above `Co-Authored-By` | `spec-status` computes SPECIFIED, LANDED, VERIFIED, RETIRED |
| Release | repository development skill | pipelines `releases/*.yml` bundles (the PIPE-RELEASE bundle rows) | `release-standard` |
"""

_ARTICLES = re.compile(r"## Repository articles\n.*?(?=\nAmend this file)", re.DOTALL)
_COPY_HINT = re.compile(r" Copy this file to `[^`]+` and keep it to one page\.")
_HEADING2 = re.compile(r"^## ", re.MULTILINE)


def render_constitution(template: str, name: str, today: date) -> str:
    """The repository constitution: the template with the name and dates set and no placeholder left."""
    if "## Repository articles" not in template:
        raise CannotRun("the vended constitution template has no 'Repository articles' section")
    text = template.replace("[Repository]", name, 1).replace("[date]", today.isoformat())
    text = _COPY_HINT.sub(" This file adds only the rules and limits of this repository.", text, count=1)
    body = (
        "## Repository articles\n\nThis repository adds no article of its own. Every organization article applies.\n\n"
        "## Repository limits\n\nThis repository sets no numeric limit of its own. "
        "It follows the organization limits table.\n"
    )
    return _ARTICLES.sub(lambda _: body, text, count=1)


def contributing(existing: str | None) -> str | None:
    """``CONTRIBUTING.md`` with the pointer section, or None when it already holds it."""
    if existing is None:
        return f"# Contributing\n\n{CONTRIBUTING_SECTION}"
    if CONTRIBUTING_HEADING in existing:
        return None
    return f"{existing.rstrip()}\n\n{CONTRIBUTING_SECTION}"


def agents(existing: str | None) -> str | None:
    """``AGENTS.md`` with the spec-driven section above the first ``##`` heading, or None when no change is due."""
    if existing is None or AGENTS_HEADING.casefold() in existing.casefold():
        return None
    match = _HEADING2.search(existing)
    if match is None:
        return f"{existing.rstrip()}\n\n{AGENTS_SECTION}"
    return f"{existing[: match.start()]}{AGENTS_SECTION}\n{existing[match.start() :]}"


#: The stack profiles that pipelines owns: language or backend to hooks, CI inputs and change-scope classes.
STACK_PROFILES = Path("reference") / "stack-profiles.yml"


def stack_profile(pipelines_root: Path, repository: Path) -> dict | None:
    """The stack profile of ``repository``, or None while pipelines publishes no profiles.

    This is the one lookup the generator uses for per-stack hooks. It reads no hook set of its own.
    """
    path = pipelines_root / STACK_PROFILES
    if not path.is_file():
        return None
    import yaml

    profiles = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    stack = "rust" if (repository / "Cargo.toml").is_file() else "python"
    found = profiles.get("profiles", profiles).get(stack) if isinstance(profiles, dict) else None
    return found if isinstance(found, dict) else None


def _read(path: Path) -> str | None:
    return path.read_text(encoding="utf-8") if path.is_file() else None


def standardize(root: Path, name: str, source: Path, today: date) -> list[str]:
    """Apply every missing part to ``root``; the repository-relative paths written, in order."""
    written: list[str] = []
    constitution = root / CONSTITUTION
    if not constitution.is_file():
        template = (source / "constitution-template.md").read_text(encoding="utf-8")
        constitution.parent.mkdir(parents=True, exist_ok=True)
        constitution.write_text(render_constitution(template, name, today), encoding="utf-8")
        written.append(CONSTITUTION.as_posix())
    destination = root / templates_sync.TEMPLATES
    if templates_sync.mismatches(source, destination):
        templates_sync.write(source, destination)
        written.append(templates_sync.TEMPLATES.as_posix())
    for filename, update in (("CONTRIBUTING.md", contributing), ("AGENTS.md", agents)):
        text = update(_read(root / filename))
        if text is not None:
            (root / filename).write_text(text, encoding="utf-8")
            written.append(filename)
    return written
