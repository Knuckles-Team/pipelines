# Controlled language and document currency (ste)

The ste gates handle the prose side. They also check the argparse strings. One shared engine applies the EG-STE-Lite standard. It serves the four published gate IDs.

## Gate IDs

| Gate ID | Checks | Stage |
|---------|--------|---------------|
| `ste-staged` | In-scope files staged for the commit | `pre-commit` |
| `ste-census` | Every tracked in-scope document | `pre-push`, `manual` |
| `ste-staleness-staged` | Staged hunks against the staleness patterns | `pre-commit` |
| `ste-staleness-census` | Every tracked in-scope document | `pre-push`, `manual` |

The staged gates diff against the committed text. A finding present in the committed file does not re-fire on a formatting touch. Each added occurrence fails the run. Moving existing occurrences to other lines does not fail. A newly staged file checks in full.

The staleness gates judge currency. They fire the configured patterns on matching lines. The census pair defaults to `pre-push` and the `manual` hook stage.

## The standard

The standard sets seven rules on prose lines:

1. Keep each sentence to 20 words or fewer.
2. Use the active voice with a named actor.
3. State present tense for live behavior and past tense for recorded events.
4. Use `must`, `should`, or `may` as the only modals.
5. State a measured value, or mark an estimate with `measured: ~N`.
6. Pick one term per concept from its cluster.
7. Drop idioms. Drop first and second person.

Rules 2, 4, 5, 6, and 7 run through the wordlist tiers below. Rule 3 runs through the modal tiers plus review. Passive voice and long noun chains report as advisory findings. Advisory findings never fail a gate.

## Wordlist tiers

The wordlist ships at `pipelines_hooks/ste/ste_words.toml` as package data. An unreadable file fails the run, and a missing file does not.

- Banned words: enforced. Each finding names the replacement. The table covers hedged filler and weak verb choices, such as `additionally`, `essentially`, `utilize`, and `leverage`.
- Modal hedges: enforced. `would`, `might`, `could`, `need to`, `ought to`, and `be able to` must give way to a stated requirement.
- Capability claims: advisory. `can` reports; keep `can` to capability statements.
- Fuzzy quantities: enforced. `several`, `a few`, `many`, `numerous`, `a lot of`, `lots of`, `couple of`, `plenty`, and `handful of` must state a value.
- Fuzzy quantity `some`: advisory.
- Person forms: enforced. `I`, `we`, `our`, `you`, `your`, and their inflections report; name the actor.
- Idioms: enforced. The list covers phrases such as `quick win` and `out of the box`.
- Clusters: enforced. Both terms of a pair in one document report once. The pairs bind `fetch` to `retrieve`, `run` to `execute`, and `build` to `construct`, among others.

## Masking

The scanner masks non-prose before it reads a line:

- Fence blocks and inline code spans.
- Image targets and link URLs. A plain link keeps its text in scope.
- All-caps tokens, `CONCEPT:` identifiers, and `Method::` names.
- Generated blocks. The marker line toggles the rest of the block off.
- Line structure on headings, list starters, and table rows. A structured line becomes its own paragraph unit. Its content stays in scope.

Badges, tables, and code stay masked. The prose around them stays in scope.

## Configuration

Consumers configure the gates under `[tool.pipelines_hooks.ste]` in the repository `pyproject.toml`:

```toml
[tool.pipelines_hooks.ste]
paths = ["README.md", "docs"]
exempt = ["docs/generated/**"]
code_paths = ["src/pkg/cli.py", "src/pkg/commands"]
```

- `paths`: in-scope Markdown (`.md`) files and directories. Directory entries select Markdown files, including architecture documents. Images and diagram assets stay outside prose scope. The default set is `README.md`, `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, and `docs`. A bare file name matches by base name, so a nested `README.md` counts.
- `exempt`: path patterns that skip the check. A pattern matches the relative path or the bare file name.
- `code_paths`: Python files or directories to scan for argparse `help`, `description`, and `epilog` strings. The wordlist tiers cover these strings; sentence shape does not apply.
- `staleness`: a list of tables, each with a `pattern` and a `message`.

```toml
[[tool.pipelines_hooks.ste.staleness]]
pattern = "agent-utilities"
message = "name the current package"
```

The table rejects unknown keys. A pattern that does not compile fails the run. The staleness gates pass on an empty pattern list. They print the notice and exit zero.

## Exit contract

All four gates share the contract:

- Zero: no failing findings. Advisory findings still print.
- One: at least one failing finding, with the advice block.
- Two: the gate cannot produce a trustworthy verdict.

The exit-two cases for ste: an unknown configuration key, a pattern that does not compile, and an unreadable wordlist. A census run with no in-scope document takes two. A missing prerequisite elsewhere in the gate toolchain prints `SKIPPED (<gate>)` and returns zero locally. The same condition fails closed with two when `CI` is set.

## Consumer wiring

The published entries live in the pipelines `.pre-commit-hooks.yaml`:

- `ste-staged` and `ste-staleness-staged` run at `pre-commit`.
- `ste-census` and `ste-staleness-census` run at `pre-push` and in the `manual` hook stage.

Consumers pin the pipelines repository to a reviewed full commit SHA. Every ste entry in a consumer hooks file carries that pin.

## Staleness model

The patterns describe currency claims, not vocabulary. Each pattern names a claim that must not survive in a document without an updating edit. The message explains the replacement. A document that imports a retired namespace carries that name in the pattern. The message names the current package.
