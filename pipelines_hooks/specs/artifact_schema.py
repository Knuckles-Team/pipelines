"""spec-artifact-schema: validate generator-skill artifacts and render the standard spec files.

The adapter reads one UTF-8 JSON document (schema version 1) holding user stories,
acceptance criteria and tasks, validates ids, typed references and acyclic task
prerequisites, and only then renders ``spec.md``, ``requirements.md``, ``plan.md``,
``tasks.md``, ``test-spec.md`` and ``checklists/requirements.md`` into a new
directory inside the repository.  A rendered document proves schema compatibility
only: not implemented behaviour, graph ingestion or runtime acceptance.  Durable
graph facts stay engine-owned.  Checking never overwrites an existing spec source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root

SCHEMA_VERSION = 1
REQ_ID = r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-R\d+(?:\.\d+)*$"
MAX_INPUT_BYTES = 2 * 1024 * 1024
OUTPUT_FILES = ("spec.md", "requirements.md", "plan.md", "tasks.md", "test-spec.md", "checklists/requirements.md")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceRef(_Strict):
    path: str = Field(min_length=1)
    line: int | None = Field(default=None, ge=1)


class _Artifact(_Strict):
    id: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    sources: tuple[SourceRef, ...] = Field(min_length=1)
    requirements: tuple[str, ...] = Field(min_length=1)

    @field_validator("requirements")
    @classmethod
    def _requirement_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        bad = [item for item in value if not re.match(REQ_ID, item)]
        if bad:
            raise ValueError(f"not requirement IDs: {bad}")
        return value


class UserStory(_Artifact):
    actor: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    benefit: str = Field(min_length=1)


class AcceptanceCriteria(_Artifact):
    story: str = Field(min_length=1)
    predicates: tuple[str, ...] = Field(min_length=1)
    proofs: tuple[str, ...] = Field(min_length=1)


class Task(_Artifact):
    prerequisites: tuple[str, ...] = ()
    criteria: tuple[str, ...] = Field(min_length=1)
    targets: tuple[str, ...] = Field(min_length=1)
    proofs: tuple[str, ...] = Field(min_length=1)

    @field_validator("targets")
    @classmethod
    def _safe_targets(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for item in value:
            pure = PurePosixPath(item)
            if pure.is_absolute() or ".." in pure.parts or "\\" in item:
                raise ValueError(f"unsafe target path {item!r}")
        return value


class ArtifactDocument(_Strict):
    schema_version: Literal[1]
    spec_id: str = Field(pattern=r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*$")
    stories: tuple[UserStory, ...]
    criteria: tuple[AcceptanceCriteria, ...]
    tasks: tuple[Task, ...]

    @model_validator(mode="after")
    def _references(self) -> ArtifactDocument:
        ids = [a.id for a in (*self.stories, *self.criteria, *self.tasks)]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate artifact IDs: {dupes}")
        stories, criteria = {s.id for s in self.stories}, {c.id for c in self.criteria}
        tasks = {t.id: t for t in self.tasks}
        for c in self.criteria:
            if c.story not in stories:
                raise ValueError(f"criterion {c.id} references missing story {c.story}")
        for t in self.tasks:
            missing = [x for x in t.criteria if x not in criteria] + [x for x in t.prerequisites if x not in tasks]
            if missing:
                raise ValueError(f"task {t.id} references missing artifacts {missing}")
        state: dict[str, int] = {}

        def visit(node: str) -> None:
            if state.get(node) == 1:
                raise ValueError(f"cyclic task prerequisites through {node}")
            if state.get(node) == 2:
                return
            state[node] = 1
            for nxt in tasks[node].prerequisites:
                visit(nxt)
            state[node] = 2

        for name in tasks:
            visit(name)
        return self


def schema_digest() -> str:
    schema = json.dumps(ArtifactDocument.model_json_schema(), sort_keys=True)
    return hashlib.sha256(schema.encode()).hexdigest()[:16]


def _sha(text: str | bytes) -> str:
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()[:16]


def render(doc: ArtifactDocument) -> dict[str, str]:
    """The six standard files, deterministic and derived only from the validated document."""
    title = doc.spec_id
    reqs: dict[str, list[str]] = {}
    proven: tuple[AcceptanceCriteria | Task, ...] = (*doc.criteria, *doc.tasks)
    for item in proven:
        for rid in item.requirements:
            reqs.setdefault(rid, []).extend(item.proofs)
    for story in doc.stories:
        for rid in story.requirements:
            reqs.setdefault(rid, [])
    spec = [f"# {title} specification", ""]
    spec += [
        f"- {s.id}: As {s.actor}, I want {s.goal} so that {s.benefit}. ({', '.join(s.requirements)})"
        for s in doc.stories
    ]
    rows = [f"# {title} requirements", "", "| ID | Requirement | Verification |", "|---|---|---|"]
    for rid, proofs in sorted(reqs.items()):
        predicates = (
            "; ".join(p for c in doc.criteria if rid in c.requirements for p in c.predicates) or "See the user story."
        )
        proof = ", ".join(f"`{p}`" for p in dict.fromkeys(proofs)) or "No proof declared."
        rows.append(f"| `{rid}` | {predicates} | Run {proof}. |")
    plan = [f"# {title} plan", ""] + [f"- {t.id}: write {', '.join(t.targets)}" for t in doc.tasks]
    tasks = [f"# Tasks - {title}", ""]
    for number, t in enumerate(doc.tasks, 1):
        after = f" after {', '.join(t.prerequisites)}" if t.prerequisites else ""
        tasks.append(f"- [ ] T{number:03d} {t.requirements[0]} {t.id}: {', '.join(t.targets)}{after}")
    tests = [f"# {title} test specification", ""] + [f"- {c.id}: {'; '.join(c.proofs)}" for c in doc.criteria]
    checklist = [f"# {title} requirements checklist", ""] + [f"- [ ] {rid}" for rid in sorted(reqs)]
    texts = ("\n".join(x) + "\n" for x in (spec, rows, plan, tasks, tests, checklist))
    return dict(zip(OUTPUT_FILES, texts, strict=True))


def _output_dir(root: Path, raw: Path) -> Path:
    pure = PurePosixPath(raw.as_posix())
    if raw.is_absolute() or ".." in pure.parts or pure.parts[:1] == (".git",) or not pure.parts:
        raise CannotRun(f"spec-artifact-schema: unsafe output path {raw}")
    return root / raw


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="spec-artifact-schema", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--input", type=Path, required=True, help="generator-skill output (JSON)")
    parser.add_argument("--output", type=Path, help="new directory (relative to the repository) for the six files")
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    source = args.input if args.input.is_absolute() else root / args.input
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise CannotRun(f"spec-artifact-schema: schema authority input unavailable: {exc}") from exc
    if len(raw) > MAX_INPUT_BYTES:
        raise CannotRun("spec-artifact-schema: input exceeds the size bound")
    destination = _output_dir(root, args.output) if args.output else None
    try:
        doc = ArtifactDocument.model_validate(json.loads(raw.decode("utf-8")))
    except (ValueError, ValidationError) as exc:
        detail = exc.errors()[0] if isinstance(exc, ValidationError) else {"msg": str(exc), "loc": ()}
        print("FAIL: malformed spec artifacts.")
        print(f"  - {'.'.join(map(str, detail['loc'])) or 'document'}: {detail['msg']}")
        return 1
    files = render(doc)
    print(f"spec-artifact-schema: schema_version={SCHEMA_VERSION} schema={schema_digest()} source={_sha(raw)}")
    ids = [a.id for a in (*doc.stories, *doc.criteria, *doc.tasks)]
    print(f"artifacts: {' '.join(ids)}")
    print("references: stories=ok criteria=ok tasks=ok prerequisites=acyclic")
    for name, text in files.items():
        print(f"output {name} digest={_sha(text)}")
    print("receipt: schema compatibility only; no implemented behaviour, graph ingestion or runtime acceptance")
    if destination is not None:
        if any((destination / name).exists() for name in files):
            raise CannotRun(f"spec-artifact-schema: refusing to overwrite existing spec sources in {args.output}")
        for name, text in files.items():
            (destination / name).parent.mkdir(parents=True, exist_ok=True)
            (destination / name).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
