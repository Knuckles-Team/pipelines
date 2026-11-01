# Spec standard (spec-standard)

This standard governs every `specs/` tree in the ecosystem. Each repository links here and keeps no local copy of these rules. The `spec-standard` gate enforces the mechanical rules. The `spec-status`, `spec-decomposition`, and `spec-trailers` gates enforce the row lifecycle.

## Extend first

Read the existing specs before any code change and before any new spec text.

1. Search the owning repository: `git grep -n "<term>" -- specs`. Search the other owners by ID prefix.
2. If a spec owns the behavior, extend that spec. Use one of the three extension forms below.
3. If a spec in another repository owns the behavior, add the row there. Link the row from the dependent spec by ID.
4. Create a new spec only for a capability that no spec owns. Record the search and its result in the `spec.md` section "Why a new spec".

One capability has one owning spec. A second spec, planner, selector, or store for an owned capability is a defect.

## Ownership boundaries

One repository owns each kind of requirement. Ask these questions in order. The first "yes" names the owner.

| Question about the requirement | Owner | Examples |
|---|---|---|
| Is it a fact, a vocabulary term, a query, or a choice among options? | medulla | Model facts, the decision that selects tools, run-trace vocabulary |
| Is it a mechanism inside a run, or the application of a decision? | agent-utilities | The run loop, context management, the signed dispatch envelope |
| Is it a check when work enters the system, or a served operation? | arbora | Admission, the operation registry, the gateway |
| Is it a property of a tool, a source, or a connector contract? | agent-connector-sdk | Read-only flags, argument schemas, certification |
| Is it the behavior of one external system? | That connector repository | One vendor's operations and mappings |
| Is it something a person sees or does? | agent-webui, agent-terminal-ui, geniusbot | Views, controls, honest states |
| Is it a gate, a page, or a release rule for every repository? | pipelines | Hooks, the spec-delivery page, this standard |

A requirement that needs two answers becomes two linked rows, one in each owner. Each row cites the other by ID.

A client must read a served operation. A client must not compute a decision and must not call the engine directly.

arbora must hold no policy table. agent-utilities must hold no fact store. Only the engine decides among options.

A design section in `plan.md` must trace the requirement to the live call path. It names the entry point, each function on the path, and the place the new behavior attaches. A row that no production caller reaches is not delivered.

## Extension forms

| Form | Use | Where |
|---|---|---|
| Child row | Narrow, split, or complete an existing requirement | `<ID>-R012.4` under `<ID>-R012` in `requirements.md` and `tasks.md` |
| New rollup | Add a requirement that the spec owns but does not state | Next free `R###` at the end of the same spec |
| Correction | Change a wrong or outdated statement | Edit the row and the `plan.md` text in place. The commit message states the reason. |

A spec states the current requirements only. A moved or renamed row takes its new ID in every file; no row is left behind under the old ID. A removed requirement is deleted from the spec. Git history holds every previous state. A delivered row keeps its ID, because tests and commit trailers bind to it. Every active row ID matches `^[A-Z][A-Z0-9]*(-[A-Z0-9]+)*-R[0-9]{3}(\.[0-9]+)*$`; an older form such as `DS-01` is renamed, and the `.config/spec-aliases.toml` entry `"DS-01" = "<ID>-R012"` keeps old `Spec:` trailers resolving. An exact retired standard ID can also map to its current row, for example `"FOO-R002.2.2.3.1" = "FOO-R002.2.3.1"`. The old ID must have no current requirement row, including a retired tombstone, and the target must be an active requirement row. Alias chains, cycles and targets that start with a retired prefix are refused. An exact alias whose key starts with a retired prefix is allowed; it applies before the prefix mapping. Exact aliases apply only to the named ID, not its children. Trailer validation still requires a bound test for the canonical target and refuses unknown IDs.

## Audits, reviews, and carry-overs

An audit, a review, a gap analysis, and a carry-over produce findings. Findings are not a capability, so they never get a spec directory.

- A finding against a row lands as a child row or a correction in the spec that owns the row.
- A missing requirement lands as a new rollup in the spec that owns the capability.
- A finding against another repository lands in that repository's owning spec.
- An audit leaves no record in the spec beyond the rows it changed. The commit message and the pull request hold the method and the result.

Directory names and spec IDs must not contain `audit`, `review`, `gap`, `carryover`, `followup`, or `fix`.

## Own words

A requirement states what this platform must do, in this platform's terms.

- A requirement must not name another product, vendor, harness, framework, or competing system.
- A requirement must not define itself by comparison, such as "like X" or "parity with X".
- A requirement may name an open protocol, format, or standard that the platform implements.
- A connector requirement names the one external system it integrates. No other spec names that system.
- Spec content is self-contained. A spec row must not reference third-party products, systems, papers, or repositories as inspiration, analysis, or comparator — no product or system names, no "surveyed/comparator/inspired-by" framing, no paper or arXiv citations in rows or in plan References sections. External names may appear only where the row is about integration support, interop, or use of that product's API/protocol (for example a connector for an external service, a git-compatible export, or an arXiv API source type). Comparative analysis, research grounding, and source records (with digests) live outside the repository, never in its `specs/` tree.
- A value taken from a paper is a starting default. A measurement on this platform replaces it.

A rollup must include a wiring row and a hot-path proof row. The wiring row names the production call site as `file:line`. The hot-path proof row is an integration test that enters at the real entry point and observes the effect through the wired call site. A unit test of a function that no production caller reaches does not prove a rollup.

## Names

| Item | Rule | Example |
|---|---|---|
| Spec ID | `<OWNER>-<AREA>`, upper case, hyphen-separated, no numeric suffix | `MEDULLA-IDENTITY` |
| Owner prefix | The owner map in the repository `specs/README.md` | `MEDULLA`, `MERISTEM`, `ARBORA`, `SCION`, `OVERSTORY`, `TUIG`, `AXIL`, `PIPE`, `US` |
| Directory | The area in lower case, hyphen-separated, with no numeric prefix | `specs/identity/` for `MEDULLA-IDENTITY` |
| File and directory names | Lower-case kebab-case. Upper case only for `README.md`, `AGENTS.md`, `CLAUDE.md`, `SKILL.md`, `LICENSE` and `CHANGELOG.md`. Recorded `evidence/` files keep the name of their tool | `test-spec.md` |
| Headings and row titles | Sentence case headings. A row title is a bold sentence that ends with a period | `**Short name.**` |
| Placement | Plans only in `specs/<family>/plan.md`, templates only in `.specify/templates/`, the constitution only in `.specify/memory/` | |
| Title line | The first line of `spec.md`: `# <ID> — <Title>` with an em dash | `# MEDULLA-IDENTITY — Engine identity and scope` |
| Row ID | `<ID>-R<nnn>`, children `.n`, three digits | `MEDULLA-IDENTITY-R007.2` |
| Index | One line per spec in `specs/README.md`: `` [`<ID>`](<dir>/spec.md) — <one sentence> `` | |

Prefixes follow the owning repository name; old prefixes resolve through spec-aliases (`"EG-" = "MEDULLA-"` in `.config/spec-aliases.toml` of the owning repository). `pipelines-hook spec-prefix-rename` performs the rewrite in a repository checkout and is idempotent.

A connector repository uses its repository name as the area, in upper case, after the owner prefix `CONN`. Example: `CONN-JELLYFIN-MCP`.

A directory that predates this standard keeps its name until its spec is next extended. The ID and title rules apply now.

## Files

The standard adopts the file layout of the [upstream spec-driven toolkit](https://github.com/github/spec-kit) and adds the requirement register. Each spec directory holds these required files:

| File | Content |
|---|---|
| `spec.md` | Outcome, prioritized user stories, edge cases, `FR-` and `SC-` labels, assumptions, scope, "Why a new spec" |
| `plan.md` | The plan template sections (see "Plan format"), as they are now |
| `requirements.md` | One table row per requirement ID |
| `tasks.md` | One numbered task per requirement row, producer first |
| `test-spec.md` | One test row per requirement, with the proving test name |

Each repository also holds `.specify/memory/constitution.md`. It is one page. It links the organization standards by public URL and adds only the rules of that repository. `.specify/templates/constitution-template.md` is the starting text.

The templates live only in `.specify/templates/`: `spec-template.md`, `plan-template.md`, `tasks-template.md`, `checklist-template.md`, `constitution-template.md`, plus `requirements-template.md` and `test-spec-template.md`. Pipelines owns them. `scripts/sync_spec_templates.py` copies them into a repository, and the published `spec-templates` hook fails when a repository's copy differs. A `specs/_template/` directory is a finding.

Status is derived, never committed. `pipelines-hook spec-status --write` computes `specs/<dir>/status.json` (gitignored) from `requirements.md`, `Spec:` trailers in Git history, test bindings and the frozen `.config/spec-legacy-landings.json`. Page builders, the architecture explorer and CI gates compute it the same way at read time, so pull requests carry only source and two pull requests on one spec never conflict on status. A tracked `specs/*/status.json` fails the `spec-status` gate.

The four states are `SPECIFIED`, `LANDED`, `VERIFIED` and `RETIRED`. No spec file writes a state. The upstream `Status:` header is not used.

Design, architecture, coverage, and cross-repository notes are sections of `plan.md`. Files named `design.md`, `architecture.md`, `coverage.md`, or `cross-repo.md` must not exist.

## Optional artifacts

A spec directory may also hold these optional artifacts. The plan step adds each one only where it carries real content, and the analysis check requires it there:

| Artifact | Content | Required when |
|---|---|---|
| `contracts/` | One human-written `.md` contract document per cross-repo seam: a Wire shape section, a Refusal codes section, and `Provider:` and `Consumer:` lines that name the row IDs on both sides (see "Contracts"). No generated contract | `plan.md` lists a seam under `## Cross-repo seams` |
| `data-model.md` | Entities, fields and relations | A row adds types, ontology classes or tables |
| `quickstart.md` | The shortest path that shows the feature working; it names the scenario or test command that runs the served proof | A row is a served behaviour row (its text says "served" or "hot-path proof") |
| `research.md` | Findings that support a decision in `plan.md`, stated in this platform's terms | `## Phase 0` lists unknowns; the file must not exist when it says "no unknowns" |
| `checklists/` | Requirement-quality checklists; `checklists/requirements.md` is filled before landing from `.specify/templates/checklist-template.md` | Always, for a touched spec |

The `spec-verifier` skill writes its report to `checklists/analysis.md`. The check fails for a touched spec and is advisory for any other spec; a row finding fails when the change adds the row.

## Contracts

A contract is the boundary registry entry for one seam between two repositories. The file is `specs/<family>/contracts/<seam>.md`. An author writes it by hand. No generator writes a contract.

A contract holds these lines and sections:

| Part | Content |
|---|---|
| `Provider: <repository> <ROW-ID>` | The repository and the row that provide the seam |
| `Consumer: <repository> <ROW-ID>` | The repository and the row that consume the seam |
| `## Wire shape` | The request and the response, or the record, that crosses the seam |
| `## Refusal codes` | Each code the provider returns and what it means |
| `## Authoritative types` | Links to the code types in the owning repositories |
| `## Test vectors` | Links to the files that hold the vectors both sides test against |

A row that cites a row of another repository must be covered by a contract that names both rows. The `contract-coverage` check enforces this on touched specs. The engine ingests contracts as a seam graph, and routing uses that graph to find the owners on both sides.

## Narrative and task format

`spec.md` uses these sections, in this order after the delivery mapping:

1. `## User Scenarios & Testing` holds stories headed `### User Story N - <title> (Priority: P1)`. Each story lists acceptance scenarios as `**Given** …, **When** …, **Then** …`. The subsection `### Edge Cases` closes the section.
2. `## Requirements` holds `FR-` labels. `## Success Criteria` holds `SC-` labels. Each label names the `-R` rows it maps to. Each named row must exist in `requirements.md`. The labels restart at 001 in each spec; only the row IDs are unique across the ecosystem.
3. `## Assumptions` holds the assumptions that bound the scope.

A question that blocks a row carries the marker `[NEEDS CLARIFICATION: <question>]`. The marker must be resolved and deleted before the row lands; the gate fails while one remains in `spec.md` or `requirements.md`.

A task line in `tasks.md` reads `- [ ] T001 [P] [US1] <ID>-R012.4 description`. The task number and the row ID are required. The `[P]` and `[US1]` tokens are optional.

## Plan format

`plan.md` follows the plan template of the [upstream spec-driven toolkit](https://github.com/github/spec-kit), plus three sections of this platform. The sections, in order:

1. `## Summary`
2. `## Technical Context` with the fields Language/Version, Primary Dependencies, Storage, Testing, Target Platform, Project Type, Performance Goals, Constraints and Scale/Scope
3. `## Constitution Check`: each principle of the repository constitution, pass or fail, with the justification
4. `## Project Structure`: real repository paths
5. `## Phase 0: Research`: unknowns and their resolution, written to `research.md` when any unknown exists
6. `## Phase 1: Design`: written to `data-model.md`, `contracts/` and `quickstart.md` as applicable
7. `## Phase 2: Task approach`
8. `## Complexity Tracking`: each constitution violation with its justification
9. `## Build contract`: the real gate thresholds and code shapes
10. `## Production caller chain`: entrypoint to owner, with file and line
11. `## Cross-repo seams`: each seam by the row ID that owns it

## Consistency analysis

The gate also runs a cross-file analysis of each spec directory, the counterpart of the upstream analyze step. It reports an active row with no task line, a task naming no existing row, a behaviour row with neither a bound test nor a test-spec entry, an `FR-` or `SC-` label cited but not defined (or defined twice) in `spec.md`, and an open clarification marker in any design file. A rollup parent is covered by its child rows. A row finding fails when the change adds the row; the others fail when their file is touched.

## Complete rows

A behaviour row holds enough text to implement without an assumption. Each active row that is not a rollup parent carries a `Caller chain:` sentence (entry point to the new code), a `Shape:` sentence (files, types and the existing helper to reuse) and a served test as `path::name`. It also names, where they apply, the files, types and fields, refusal codes from the one taxonomy, the write path, the knobs with starting values, the `Depends on:` row IDs and each cross-repository seam by ID on both sides. A row never says TBD. The check fails a row the change adds and is advisory for any other row.

## Requirements checklist

Before a spec lands its author fills `checklists/requirements.md` from `.specify/templates/checklist-template.md`. An unchecked item is a finding.

## Rows

- One requirement per row. One row is one five-minute unit of work, or a rollup of such rows.
- A row names the file it touches and the test that proves it.
- A cross-repository prerequisite is a row in the owning repository. The dependent row links it by ID.

## States

| State | Definition |
|---|---|
| `SPECIFIED` | The requirement is written. No code for it is on the default branch. |
| `LANDED` | A commit that carries its ID in a `Spec:` trailer is on the default branch. |
| `VERIFIED` | It is `LANDED` and a test bound to its ID exists. |

A spec's state is the lowest state of its rows.

No other state, acceptance value or status label exists. Do not write a status line in `spec.md`, `plan.md`, `tasks.md` or `test-spec.md`; the generator owns the state.

## Wording

Spec prose follows the STE-Lite standard in [ste.md](ste.md):

- Keep each sentence to 20 words or fewer.
- Use the active voice with a named actor.
- Use `must`, `should`, or `may` as the only modals.
- State a measured value, not a fuzzy quantity.
- Use one term per concept.

New and changed spec text must pass `ste-staged`. A repository opts in by adding `specs` to `[tool.pipelines_hooks.ste].paths`.

## The gate

`pipelines-hook spec-standard` checks each spec directory:

| Check | Finding |
|---|---|
| File set | A required file is absent, a forbidden file exists, or an optional artifact has the wrong kind |
| Clarification | `spec.md` or `requirements.md` holds an open `[NEEDS CLARIFICATION: …]` marker |
| Narrative | `spec.md` lacks prioritized stories, Given/When/Then scenarios, Edge Cases or Assumptions, or an `FR-` or `SC-` label names no existing row |
| Task line | A `tasks.md` task does not match the numbered task line or names no existing row |
| Plan | `plan.md` lacks a template section or a Technical Context field |
| Analysis | A row has no task line or no test, a task names no row, a label is orphaned, or a design file holds an open marker |
| Checklist | A `checklists/*.md` file holds an unchecked item |
| Status | A spec file writes a `Status:` line |
| Constitution | The repository has no `.specify/memory/constitution.md` (advisory) |
| Title line | `spec.md` line 1 does not match `# <ID> — <Title>` |
| Spec ID | The ID has a numeric suffix, or an active row ID does not match the row-ID regex or does not start with the ID |
| Names | The directory name or the ID contains a forbidden word |
| Artifact names and placement | A name under `specs/` or `.specify/` is not lower-case kebab-case (allowlist above), a spec directory has a numeric prefix, or a plan, template or constitution sits outside its one place. A path the change does not touch is advisory |
| Optional artifacts | A required optional artifact is absent, or `research.md` exists without unknowns |
| Templates | `.specify/templates/` differs from the vended templates (`spec-templates`) |
| Index | `specs/README.md` does not list the spec |
| Contract coverage | A touched spec's row cites another repository's row and no contract names the pair |
| Third-party names | Authored `specs/**/*.md` text names a product or project on the denylist in `pipelines_hooks/specs/third_party_names.toml` |

The clarification, file-set, title, ID, name, index and third-party checks always fail on a finding. The narrative, task-line, plan, analysis, checklist and status checks fail for a file the change touches, that is a staged file or a file that differs from the base revision, and are advisory for every other file. An advisory finding prints with the prefix `ADV` and does not change the exit code. An older spec is rewritten when it is next extended.

The gate exits 0 when clean, 1 on a finding, and 2 when it cannot run. It has no baseline and no suppression.

The third-party name check ignores inline code, fenced code, URLs, link targets, spec IDs and recorded `evidence/` files. A lowercase identifier, such as a connector ID, is not a product name. The `[allow]` table in the same file lists the target system that a connector repository may name.

## Delivery relationships and implementation mapping

Every core repository and connector uses the shared spec-delivery generator.
The generator reads declarations from `spec.md` and `plan.md` outside fenced examples.
These source files survive status regeneration. Do not hand-edit generated status fields.

```markdown
Component: Gateway
Depends-on: LOCAL-SPEC-R001, [Remote host](https://github.com/OWNER/REPO/blob/REV/specs/host/spec.md)
Extends: [Base spec](../base/spec.md)
References: [Related spec](../related/spec.md)
Code: ../../src/gateway.py:42 ../../tests/test_gateway.py
```

- `Depends-on` declares a prerequisite. Local spec or requirement IDs resolve to their owning spec.
- Cross-repository targets must supply a public GitHub source link. Prefer an immutable revision.
- `Extends` and `References` do not imply prerequisite order. An ordinary spec link is a reference.
- Shared files, prose mentions, and `Unblocks` statements never create prerequisite edges.
- `Code` names source files. Relative paths resolve beside the declaration, then from the repository root.
- Existing source citations also provide file mappings. The view separates implementation, test, and documentation paths.
- A file link proves neither coverage nor delivery. Missing paths stay unresolved; external paths stay unverified.
- `Component` groups specs within their repository. Missing component metadata produces an `Unassigned` group.
- Missing declarations mean unknown dependencies or unmapped code. They never establish completeness.

The shared page must show every spec, including isolated specs, through repository and component groups.
The page replaces the Concepts column with Code references. The concept corpus remains a separate documentation surface.
The architecture view uses accessible package diagrams and exports escaped Mermaid source with labelled dependency edges.
Existing Mermaid diagrams in `plan.md` remain available as source. Absence of a plan diagram stays visible.
Relationships and code mappings must not change delivery states, recorded history, or timelines.


References declarations accept explicit links, canonical spec or requirement identifiers, and relative file paths. Other prose remains unparsed source evidence; its words do not become relationship targets. Unknown canonical identifiers remain unresolved references.

## Priority from competency questions

A competency question is an ordinary spec row whose ID starts with `MEDULLA-CQ-`. No registry, goal type, or `Serves:` field exists. A row serves a competency question when that question row reaches it through `Depends-on` edges, including edges across repositories. List prerequisites in the requirement cell:

```markdown
| `X-R001` | **Title.** Text. Depends-on: MEDULLA-FOO-R004, SCION-BAR-R002. | Verification |
```

The organization architecture page computes `priority` for each open row. No `status.json` carries it and a person never edits it.

```text
priority = (10 x competency-question rows that transitively depend on the row
            + 2 x open rows it transitively unblocks) x 0.5 if non-functional
```

- An open row is `SPECIFIED`. A `LANDED`, `VERIFIED`, or `RETIRED` row is done and has no `priority`.
- A row in a spec whose ID holds `GATES`, `PAGES`, `DOCS`, `HYGIENE`, or `STANDARD` is non-functional.
- The page also lists `frontier` (open leaf rows whose prerequisites are all done) and `unserved` (open functional leaf rows that no competency question reaches).
- Only the page sees every repository, so cross-repository `Depends-on` edges count. It labels the unserved rows "No CQ dependency path". This means no CQ reaches the row through CQ → Depends-on → requirement edges, not that architecture placement or implementation links are missing.
- A release bundle is a group of open rows joined by cross-repository `Depends-on` edges. The page derives it and nobody declares it. Its steps follow the release train: medulla, agent-connector-sdk, agent-utilities, arbora, the front ends, then connectors. Its priority is the maximum row priority.

## Withdrawing invalid verification evidence

Keep the owning IDs in `Spec:` trailers when correcting invalid acceptance evidence.
Add these trailers to a commit in the correction PR:

```text
Spec: DEMO-R001
Spec-Withdraw: DEMO-R001
Spec-Withdrawal-Reason: Refusal tests do not prove the required successful query.
```

The reason must contain at least 20 characters. Repeat it exactly in the owning `plan.md`, with each withdrawn ID.
The declaration applies to the entire PR range from its merge base.
It may follow earlier correction commits; history need not be rewritten.
Every withdrawn ID must be known, remain in a `Spec:` trailer, and lose an existing Rust comment binding.
No acceptance binding for that ID may remain in the current tree.

Allowed changes are deliberately narrow:

- Remove standalone Rust `// spec: ID` comments, or replace them with the canonical comment below.
- Add text to owning `plan.md` files without deleting existing text.
- Reopen owning task checkboxes for the declared IDs.

```rust
// Partial refusal coverage for DEMO-R001; successful-operation acceptance remains open.
```

Requirements, executable code, other comments, file modes, filenames, build configuration and workflows must remain unchanged.
Markers inside strings or block comments cannot qualify as a source withdrawal.
Missing reasons, unknown IDs, absent old bindings, retained bindings, and mixed feature changes fail closed.
Unsupported binding languages remain subject to the ordinary rule.
Other named IDs still need bound tests. The independent canonical status gate remains mandatory.
This mechanism withdraws verification evidence; it does not waive acceptance requirements or prove implementation completion.
