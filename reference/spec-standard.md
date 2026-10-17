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

One repository owns each kind of requirement. The [ecosystem boundaries](ecosystem-boundaries.md) standard holds the repository table, the routing procedure, and the worked examples. Route each requirement with that procedure before any spec text.

A requirement that needs two answers becomes two linked rows, one in each owner. Each row cites the other by ID.

A client must read a served operation. A client must not compute a decision and must not call the engine directly.

graph-os must hold no policy table. agent-utilities must hold no fact store. Only the engine decides among options.

A design section in `plan.md` must trace the requirement to the live call path. It names the entry point, each function on the path, and the place the new behavior attaches. A row that no production caller reaches is not delivered.

## Extension forms

| Form | Use | Where |
|---|---|---|
| Child row | Narrow, split, or complete an existing requirement | `<ID>-R012.4` under `<ID>-R012` in `requirements.md` and `tasks.md` |
| New rollup | Add a requirement that the spec owns but does not state | Next free `R###` at the end of the same spec |
| Correction | Change a wrong or outdated statement | Edit the row and the `plan.md` text in place. The commit message states the reason. |

A spec states the current requirements only. A moved or renamed row takes its new ID in every file; no row is left behind under the old ID. A removed requirement is deleted from the spec. Git history holds every previous state. A delivered row keeps its ID, because tests and commit trailers bind to it; a row ID in an older form, such as `DS-01`, stays as it is.

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
- A requirement derived from a research paper cites the paper. The row carries `[arXiv:<id>]`. The spec's `plan.md` lists it under "References" as `arXiv:<id> — <authors>, "<title>" (<year>)`.
- A value taken from a paper is a starting default. A measurement on this platform replaces it.

A rollup must include a wiring row and a hot-path proof row. The wiring row names the production call site as `file:line`. The hot-path proof row is an integration test that enters at the real entry point and observes the effect through the wired call site. A unit test of a function that no production caller reaches does not prove a rollup.

## Names

| Item | Rule | Example |
|---|---|---|
| Spec ID | `<OWNER>-<AREA>`, upper case, hyphen-separated, no numeric suffix | `EG-IDENTITY` |
| Owner prefix | The owner map in the repository `specs/README.md` | `EG`, `AU`, `GRAPHOS`, `SDK`, `WEBUI`, `RM`, `PIPE` |
| Directory | The area in lower case, hyphen-separated | `specs/identity/` for `EG-IDENTITY` |
| Title line | The first line of `spec.md`: `# <ID> — <Title>` with an em dash | `# EG-IDENTITY — Engine identity and scope` |
| Row ID | `<ID>-R<nnn>`, children `.n`, three digits | `EG-IDENTITY-R007.2` |
| Index | One line per spec in `specs/README.md`: `` [`<ID>`](<dir>/spec.md) — <one sentence> `` | |

A connector repository uses its repository name as the area, in upper case, after the owner prefix `CONN`. Example: `CONN-JELLYFIN-MCP`.

A directory that predates this standard keeps its name until its spec is next extended. The ID and title rules apply now.

## Files

Each spec directory holds exactly these files:

| File | Content |
|---|---|
| `spec.md` | Outcome, scope, owner, non-goals, "Why a new spec" |
| `plan.md` | Architecture, reuse inventory, interfaces, wiring, and decisions, as they are now |
| `requirements.md` | One table row per requirement ID |
| `tasks.md` | One task per requirement row, producer first |
| `test-spec.md` | One test row per requirement, with the proving test name |
| `status.json` | Generated by `pipelines-hook spec-status --write`. Never hand-edited |

Design, architecture, coverage, and cross-repository notes are sections of `plan.md`. Files named `design.md`, `architecture.md`, `coverage.md`, or `cross-repo.md` must not exist.

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

Spec prose follows the EG-STE-Lite standard in [ste.md](ste.md):

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
| File set | A required file is absent, or a forbidden file exists |
| Title line | `spec.md` line 1 does not match `# <ID> — <Title>` |
| Spec ID | The ID has a numeric suffix, or a `-R###` row ID does not start with the ID |
| Names | The directory name or the ID contains a forbidden word |
| Index | `specs/README.md` does not list the spec |

The gate exits 0 when clean, 1 on a finding, and 2 when it cannot run. It has no baseline and no suppression.

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
- Regenerate owning `status.json` files with `spec-status --write`.

```rust
// Partial refusal coverage for DEMO-R001; successful-operation acceptance remains open.
```

Requirements, executable code, other comments, file modes, filenames, build configuration and workflows must remain unchanged.
Markers inside strings or block comments cannot qualify as a source withdrawal.
Missing reasons, unknown IDs, absent old bindings, retained bindings, and mixed feature changes fail closed.
Unsupported binding languages remain subject to the ordinary rule.
Other named IDs still need bound tests. The independent canonical status gate remains mandatory.
This mechanism withdraws verification evidence; it does not waive acceptance requirements or prove implementation completion.
