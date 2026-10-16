# Pre-commit standard

Every repository runs the same small set of local hooks. A local hook must be fast and must check only the files of the change. Every other check runs in CI.

This standard supersedes the 2026-10-15 plan in `plans/spec-audit/PRECOMMIT-STANDARD.md`. That plan moved slow gates to the pre-push stage. This standard takes them out of the local hooks.

## Stages

| Stage | Budget | Hooks |
|---|---|---|
| pre-commit | about 10 s in total, staged files only | `trailing-whitespace`, `end-of-file-fixer`, `check-merge-conflict`, `check-added-large-files` (2000 kB), `check-yaml`, `check-toml`, `check-json`, `detect-private-key`, `ruff-format`, `ruff-check` |
| pre-push | about 2 min, the pushed range | `uv-lock-check` (`uv lock --check`, never mutates), `spec-trailers`, `fast-tests` (affected tests, 120 s cap) |
| CI only | no local budget | everything else |

The reference files are:

- [`templates/pre-commit.yaml`](https://github.com/Knuckles-Team/pipelines/blob/main/templates/pre-commit.yaml): copy it to `.config/pre-commit.yaml`.
- [`templates/ci-gates.yaml`](https://github.com/Knuckles-Team/pipelines/blob/main/templates/ci-gates.yaml): copy it to `.config/ci-gates.yaml` and list the CI-only gates that the repository needs.

## Rules

1. Pin the third-party hooks: pre-commit-hooks `3e8a8703` (v6.0.0), ruff-pre-commit `cb8c523f` (v0.16.0), mirrors-mypy `fc0f09a2` (v1.20.2). Reference pipelines hooks at `rev: main`.
2. Do not use the `manual` stage. A check runs in CI or you delete it.
3. Put CI-only gates in `.config/ci-gates.yaml`. Examples are architecture gates, scanners, generator and drift checks, coverage, mypy, doc builds and catalog checks. The file uses the pre-commit format. No git hook installs it. `gates_pipeline.yml` runs it with the `ci-config` input over the pull-request diff, or over every file on a main push. A repository with its own workflow runs `pre-commit run --config .config/ci-gates.yaml` in that workflow.
4. Do not run a check both as a hook and as a workflow step. If a workflow step already runs a check, delete the hook.
5. The commit-stage secret scan is `detect-private-key`. `tracked-privacy` and `secret-history` scan the whole tree or the whole range, so they run in CI only (`tracked-privacy` takes about 85 s on agent-utilities).
6. You can change your copy of the reference only if you write the reason in a comment beside the change. Two examples are a workspace launcher for `uv lock --locked`, and a guard that only works in a local checkout.
7. Do not delete a test that reads the hook configuration. Change it so that it asserts this standard, or point it at `.config/ci-gates.yaml`.

## Shared hook ids

| Id | Stage | Purpose |
|---|---|---|
| `uv-lock-check` | pre-push | `uv lock --check`. It fails when `uv.lock` disagrees with `pyproject.toml` and never writes the file. Other arguments go to uv. |
| `spec-trailers` | pre-push | Every product-path commit has a verified `Spec:` trailer. |
| `fast-tests` | pre-push | Only the tests that the pushed diff affects, with a 120 s cap. |

The other ids in `.pre-commit-hooks.yaml` belong in `.config/ci-gates.yaml`.
