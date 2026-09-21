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
module exposes `main(argv) -> int`.

Reusable workflows under `.github/workflows/` build Python packages, native
wheels, containers, desktop artifacts, services, and Pages sites. They execute
with the caller's checkout, credentials, and permissions. `scripts/readiness/`
contains the Pages readiness validator and delivery planning code.

## Commands

Install the locked environment and run focused or complete checks with:

```bash
uv sync --locked
uv run pytest -q
pre-commit run --all-files
```

Use `pipelines-hook <id>` to run one published gate. The command lists the
available IDs when called without an ID.

## Quality gates

Every gate returns zero for clean, one for findings, and two when it cannot
produce a trustworthy verdict. The public-surface gate checks README and AGENTS
structure, canonical offline badges, contained local links, Pages
discoverability, and absence of checkout or planning details. No network
request is made by a local documentation gate.

Workflow changes also receive YAML and contract validation. CI builds the
relevant workflow artifacts with the caller's declared permissions.

## Development rules

Keep one focused change per commit and preserve explicit branch and worktree
boundaries. Read the relevant module and tests before editing. Add a positive
case and an adversarial case for every new invariant. For a workflow change,
update its contract test; for a hook change, update the CLI registry, published
catalogue, self-run configuration when appropriate, and README example.

Stage only reviewed paths and use `uv run --locked` for Python commands.

## Documentation

`README.md` is the concise public entry point. The [Pages site](https://knuckles-team.github.io/pipelines/)
contains the navigable reference surface, while `docs/` contains workflow and
readiness reference material. Keep examples synchronized with the published
hook catalogue and configuration schema.

## Branching & isolation

Use an explicit branch or repository worktree for changes. Do not mix unrelated
edits, share a mutable checkout between concurrent lanes, or commit generated
environment output. Before a commit, inspect the complete staged diff and run
the applicable focused checks.

## Release

Release from a reviewed commit after the full test and hook suites pass. Keep
the package version in `VERSION` and project metadata synchronized. Consumers
pin published workflow references to an immutable commit and record the release
version beside that pin. Pages artifacts are promoted only after strict
contract checks succeed.
