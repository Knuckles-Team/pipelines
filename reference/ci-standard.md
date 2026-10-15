# CI standard (shared pieces)

Pipelines owns the reusable parts of the fleet CI standard; each repository calls them at `@main`.

- `gates_pipeline.yml`: one `gates` job. Pull requests run the caller's pre-commit file at the commit stage and the pre-push stage over `--from-ref/--to-ref`; a main push sets `all-files: true`. Then the affected-test subset from `pr-test-scope`. Inputs: `config`, `test-scope`, `src-root`, `runner`, `rust`, `all-files`, `extra-manual-hooks`, `skip-hooks`, `timeout-minutes`. Every input has a default. On `push` events the workflow adds `spec-trailers` to `SKIP`: trailers are a property of pull request commits and a squash merge does not carry them; pull request runs always enforce the hook.
- Concurrency belongs to the caller: PR group `pr-<workflow>-<number>` and main group `main-<workflow>` cancel superseded runs; release and pages groups never cancel. The workflow header carries the copyable block.
- `templates/workflows/gates-skip.yml`: the companion that reports the required `gates` check for docs/spec-only changes that `paths-ignore` skips.
- `python_pipeline.yml` input `require-tag` (default `false`): when `true` the job fails before building unless the ref is a `v*` tag. A release workflow triggered by `push: tags: ['v*']` sets it.
- Hook `fast-tests` (pre-push): affected tests only, 120 s cap, base from `PRE_COMMIT_FROM_REF`.
