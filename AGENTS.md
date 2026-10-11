# pipelines engineering contract

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

`scripts/spec_dashboard.py` owns the opt-in static spec delivery dashboard. The adjacent source, history, metrics, chart, and renderer modules keep canonical normalization and bounded first-parent accounting separate. Its version 1 JSON configuration, status semantics, and snapshot contract are documented in `pages/spec-dashboard.md`. Fixtures live in `tests/test_spec_dashboard.py`.

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
uvx pre-commit run --config .config/pre-commit.yaml --all-files
uvx pre-commit run --config .config/pre-commit.yaml --all-files --hook-stage manual
```

CI (`.github/workflows/ci.yml`) runs the same two pre-commit invocations with
the scanners installed by `scripts/install_scanners.sh`.

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

Release from a reviewed commit after the full test and hook suites pass. Keep
the package version in `pyproject.toml`, the single version source
(`bump2version --config-file .config/bumpversion.cfg`). Consumers
pin published workflow references to an immutable commit and record the release
version beside that pin. Pages artifacts are promoted only after strict
contract checks succeed.

## Specs: extend first

Find the spec row that owns the behavior before any code change. Search with `git grep -n "<term>" -- specs`. Cite the row ID in the commit `Spec:` trailer. Extend the owning spec before any new spec text. Add a child row, a new rollup, or a dated `plan.md` "Amendments" entry. Create a new spec only for a capability that no spec owns. Audits, reviews, and carry-overs land in the owning spec. They never get a spec directory. Reuse an existing function, module, or store before adding one. The rules are the ecosystem [spec standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/spec-standard.md).
