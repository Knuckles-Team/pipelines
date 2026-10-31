# pipelines engineering contract

<!-- agent-contract:start -->
## Agent contract

Tool-neutral rules for any AI agent or human working in this repository. This block is maintained by the fleet standard; edit outside the markers.

- **Owner boundary:** this repository owns the gates, pages, release rules, the spec standard and the routing standard (spec prefix `PIPE-`). Feature routing across repositories: [ecosystem boundaries](https://github.com/Knuckles-Team/pipelines/blob/main/reference/ecosystem-boundaries.md).
- **Setup:** run `scripts/bootstrap.sh`. It is idempotent and non-interactive: it pins uv and Python, syncs the locked environment, installs the git hooks and prints the gate command.
- **Gates:** `uvx pre-commit run --all-files` must pass before you push. Do not bypass hooks to get green.
- **Commits:** one logical change per commit with a `Spec: <ID>` trailer (or `Spec: none (<reason>)`), plus a `Co-Authored-By:` trailer naming the assisting agent. Stage explicit paths only; never `git add -A` or `git add .`. Use your own configured Git identity, never a tool or bot name.
- **Org rules:** [organization AGENTS.md](https://github.com/Knuckles-Team/.github/blob/main/AGENTS.md).
<!-- agent-contract:end -->

## Spec-driven development

Every feature starts with a spec, in this order. Read `.specify/memory/constitution.md` first; it inherits the [organization constitution](https://github.com/Knuckles-Team/pipelines/blob/main/.specify/memory/constitution.md). Route the feature with the [ecosystem boundaries](https://github.com/Knuckles-Team/pipelines/blob/main/reference/ecosystem-boundaries.md) and file each part in its owner's `specs/`. Run the flow with the skills in the table (universal-skills). Rules: [spec standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/spec-standard.md); templates: pipelines `specs/_template/`.

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
| Release | repository development skill | pipelines `releases/*.yml` bundles (PIPE-RELEASE-R020 to R024) | `release-standard` |

Never write code for a row that is not SPECIFIED in this repository's `specs/`. If no row owns the behavior, extend the owning spec first. Never write `status.json` or a `Status:` line; the state is computed.

This file is the current engineering contract for the shared hooks and reusable
workflows in this repository. Keep it accurate when an implementation,
workflow interface, or release rule changes.

## What this repository owns

This repository owns shared gate behavior, workflow templates, Pages readiness
validation, and their contract tests. Gate code remains generic: product
repositories supply their own policy through the documented TOML configuration.

## Architecture and module map

`pipelines-hook` is the single command entry point for the Python quality-gate
package. `pipelines_hooks/cli.py` maps published IDs to gate modules, and each
module exposes `main(argv) -> int`. The skills that explain these gates and the
branch/worktree conventions for contributors (`gates-and-code-placement`,
`git-in-shared-repos`) live in universal-skills under `development/`. The
ecosystem host serves them; read them before explaining a gate's caps.

Reusable workflows under `.github/workflows/` build Python packages, native
wheels, containers, desktop artifacts, services, and Pages sites. They run
with the caller's checkout, credentials, and permissions.
`scripts/readiness/`
contains the Pages readiness validator and delivery planning code.

Container callers may opt into a producer-qualified offline wheel context.
That context uses an immutable same-run artifact ID, pinned
source-freeze/lock digests, and an explicit build target. Runtime manifests use /2 and bind the profile's image
stage and exact root version/extras to that target; /1 contexts are rejected.
The shared staging action checks the complete byte inventory and source
bindings before forwarding provenance arguments. Legacy
agent/mcp detection remains the default. See [the runtime contract](reference/container-runtime.md)
for inputs, producer prerequisites, and the boundary between transport and
runtime qualification.

`scripts/architecture_explorer/` builds the Arbora Architecture Explorer that `pages_pipeline.yml` publishes at `/architecture/` on each core repository site (input `architecture_explorer`, default `auto`). `model.json` holds the architecture parts, `registry.json` the scanned repositories, `layout.mjs` precomputes every level with the pinned layout engine in `package.json`, and `build.py --mode local --workspace PATH` builds it from local clones. Tests live in `tests/test_architecture_explorer.py`.

`scripts/spec_dashboard.py` owns the opt-in static spec delivery dashboard. The adjacent source, history, metrics, chart, and renderer modules keep canonical normalization and bounded first-parent accounting separate. Its version 1 JSON configuration, status semantics, and snapshot contract are documented in `pages/spec-dashboard.md`. Source mappings and grouped architecture live in `scripts/spec_dashboard_metadata.py` and `scripts/spec_dashboard_architecture.py`. They read spec/plan declarations without changing generated status. Fixtures live in `tests/test_spec_dashboard.py` and `tests/test_spec_dashboard_metadata.py`.

## Setup

From a fresh clone (locally, or in a Claude Code cloud session where
`.claude/hooks/session-start.sh` runs it automatically when
`CLAUDE_CODE_REMOTE=true`):

```bash
scripts/bootstrap.sh              # uv >= 0.9, locked env + test deps, pre-commit and pre-push hooks
scripts/bootstrap.sh --scanners   # also the pinned cccc, kiss fork, dupehound and jscpd builds
```

The script is idempotent. Without the scanners, a sibling checkout, or the
operator's privacy identity catalog, the affected hooks print
`SKIPPED (<gate>): <reason>` and pass locally. CI fails them closed.

## Commands

Run focused or complete checks with:

```bash
uv run --frozen python -m pytest -q
uvx pre-commit run --config .config/pre-commit.yaml --all-files --hook-stage pre-commit
uvx pre-commit run --config .config/pre-commit.yaml --all-files --hook-stage pre-push
```

The blocking checks are the [gate standard](reference/gate-standard.md).
CI (`.github/workflows/ci.yml`) calls `gates_pipeline.yml` on pull requests
and `main_pipeline.yml` on main and release tags. `advisory.yml` runs the
advisory scanners weekly with the pinned native scanners from
`scripts/install_scanners.sh`; its report never fails a check.

Use `pipelines-hook <id>` to run one published gate. The command lists the
available IDs when called without an ID.

## Quality gates

Every gate returns zero for clean, one for findings, and two when it cannot
produce a trustworthy verdict. A missing native scanner or sibling checkout
(`pipelines_hooks.core.errors.Unavailable`) is exit two only when `CI` is set.
Locally the command line prints `SKIPPED (<gate>)` with the install command
and returns zero. The public-surface gate checks reader-visible breakage in
README/AGENTS: a missing README, and links or images outside the repository.
It also flags a README without an install or quick-start path. A local
documentation gate makes no network request.

Workflow changes also receive YAML and contract validation. CI builds the
relevant workflow artifacts with the caller's declared permissions.

## Development rules

Keep one focused change per commit and preserve explicit branch and worktree
boundaries. Read the relevant module and tests before editing. Add a positive
case and an adversarial case for every new invariant. For a workflow change,
update its contract test. For a hook change, update the CLI registry, published
catalogue, self-run configuration when appropriate, and README example.

Stage only reviewed paths and use `uv run --frozen` for Python commands.

## Documentation

`README.md` is the concise public entry point. The [Pages site](https://knuckles-team.github.io/pipelines/)
contains the navigable reference surface, while `reference/` contains workflow and
readiness reference material. Keep examples synchronized with the published
hook catalogue and configuration schema.

## Branching & isolation

Use an explicit branch or repository worktree for changes. Do not mix unrelated
edits, share a mutable checkout between concurrent lanes, or commit generated
environment output. Before a commit, inspect the complete staged diff and run
the applicable focused checks.

Work on a topic branch, push it, and open a pull request against `main`; the
`CI` workflow must pass before merge. Ordinary code gates and push hooks must
remain independent of external network reachability. The narrow exception is
release-only wheel readiness, immediately before PyPI upload and GitHub package
release. It must prove the exact artifact's dependency closure resolves from
the public index. Otherwise it fails closed on index errors. Repository-manager continues to own manual RELEASE readiness
and fleet ordering. This publication proof must never run as an ordinary code
or pre-push gate.

## Release

Release from a reviewed commit after the full test and hook suites pass.
Bump first, then tag: (1) bump the version with the repository's own method
(`bump2version` plus `pyproject.toml`) and refresh the lock and fixtures;
(2) merge the bump; (3) run `python3 -I .github/actions/verify-release-version/verify_release_version.py --root . --ref refs/tags/vX.Y.Z`
on the merged commit; (4) only then push the tag; (5) confirm wheel and sdist on
PyPI; (6) wrong-commit tag with nothing published: delete and re-tag, otherwise
cut the next patch. The shared release workflows run the same guard before any
build. Full text: `reference/python-release-readiness.md`. Keep
the package version in `pyproject.toml`, the single version source
(`bump2version --config-file .config/bumpversion.cfg`). Consumers
pin published workflow references to an immutable commit and record the release
version beside that pin. Pages artifacts are promoted only after strict
contract checks succeed.

## Specs: extend first

Find the spec row that owns the behavior before any code change. Search with `git grep -n "<term>" -- specs`. Cite the row ID in the commit `Spec:` trailer. Extend the owning spec before any new spec text. Add a child row, a new rollup, or a dated `plan.md` "Amendments" entry. Create a new spec only for a capability that no spec owns. Audits, reviews, and carry-overs land in the owning spec. They never get a spec directory. Reuse an existing function, module, or store before adding one. The rules are the ecosystem [spec standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/spec-standard.md).
