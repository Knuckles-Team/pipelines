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
branch/worktree conventions to contributors (`gates-and-code-placement`,
`git-in-shared-repos`) live in universal-skills under `development/`, so the
ecosystem host can serve them; read them before explaining a gate's caps.

Reusable workflows under `.github/workflows/` build Python packages, native
wheels, containers, desktop artifacts, services, and Pages sites. They execute
with the caller's checkout, credentials, and permissions. `scripts/readiness/`
contains the Pages readiness validator and delivery planning code.

Container callers may opt into a producer-qualified offline wheel context using
an immutable same-run artifact ID, pinned source-freeze/lock digests and an
explicit build target. Runtime manifests use /2 and bind the profile's image
stage and exact root version/extras to that target; /1 contexts are rejected.
The shared staging action verifies the complete byte inventory and source
bindings before forwarding provenance arguments. Legacy
agent/mcp detection remains the default. See [the runtime contract](reference/container-runtime.md)
for inputs, producer prerequisites and the boundary between transport checks and
runtime qualification.

## Setup

From a fresh clone (locally, or in a Claude Code cloud session where
`.claude/hooks/session-start.sh` runs it automatically when
`CLAUDE_CODE_REMOTE=true`):

```bash
scripts/bootstrap.sh              # uv >= 0.9, locked env + test deps, pre-commit and pre-push hooks
scripts/bootstrap.sh --scanners   # also the pinned cccc, kiss fork, dupehound and jscpd builds
```

The script is idempotent. Without the scanners, or without a sibling checkout
or the operator's privacy identity catalog, the affected hooks print
`SKIPPED (<gate>): <reason>` and pass locally; CI fails them closed.

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
(`pipelines_hooks.core.errors.Unavailable`) is exit two only when `CI` is set;
locally the command line prints `SKIPPED (<gate>)` with the install command and
returns zero. The public-surface gate checks only reader-visible
breakage: a missing README, relative links or images in README/AGENTS that
point nowhere or outside the repository, and a README with no install or
quick-start path. No network
request is made by a local documentation gate.

Workflow changes also receive YAML and contract validation. CI builds the
relevant workflow artifacts with the caller's declared permissions.

## Development rules

Keep one focused change per commit and preserve explicit branch and worktree
boundaries. Read the relevant module and tests before editing. Add a positive
case and an adversarial case for every new invariant. For a workflow change,
update its contract test; for a hook change, update the CLI registry, published
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
remain independent of external network reachability. The narrow exception is release-only wheel readiness immediately
before PyPI upload and GitHub package release: it must prove the exact artifact's
runtime dependency closure is available from the public index, and fail closed
on index errors. Repository-manager continues to own manual RELEASE readiness
and fleet ordering. This publication proof must never run as an ordinary code
or pre-push gate.

## Release

Release from a reviewed commit after the full test and hook suites pass. Keep
the package version in `pyproject.toml`, the single version source
(`bump2version --config-file .config/bumpversion.cfg`). Consumers
pin published workflow references to an immutable commit and record the release
version beside that pin. Pages artifacts are promoted only after strict
contract checks succeed.
