# CI standard (shared pieces)

Pipelines owns the reusable parts of the fleet CI standard; each repository calls them at `@main`.

- `gates_pipeline.yml`: one `gates` job. Pull requests run the caller's pre-commit file at the commit stage and the pre-push stage over `--from-ref/--to-ref`; a main push sets `all-files: true`. Then the affected-test subset from `pr-test-scope`. Inputs: `config`, `ci-config`, `test-scope`, `src-root`, `runner`, `rust`, `all-files`, `extra-manual-hooks`, `skip-hooks`, `setup-command`, `docs-only-paths`, `timeout-minutes`. Every input has a default. On `push` events the workflow adds `spec-trailers` to `SKIP`: trailers are a property of pull request commits and a squash merge does not carry them; pull request runs always enforce the hook.
- Concurrency belongs to the caller: PR group `pr-<workflow>-<number>` and main group `main-<workflow>` cancel superseded runs; release and pages groups never cancel. The workflow header carries the copyable block.
- Input `docs-only-paths` (default empty): space-separated bash patterns of docs and spec paths. When every file in a pull request diff matches one, the job passes right after checkout. A caller that sets it drops `paths-ignore` from `pull_request` and has no skip companion, so exactly one `gates / gates` check exists. A skip run under the same name can then never mask a failing real run on a mixed code and docs pull request.
- `templates/workflows/gates-skip.yml`: the older companion that reports the required `gates` check for docs/spec-only changes that `paths-ignore` skips. On a mixed pull request both workflows report the same name; prefer `docs-only-paths`.
- `python_pipeline.yml` input `require-tag` (default `false`): when `true` the job fails before building unless the ref is a `v*` tag. A release workflow triggered by `push: tags: ['v*']` sets it.
- Hook `fast-tests` (pre-push): affected tests only, 120 s cap, base from `PRE_COMMIT_FROM_REF`.
- Local hooks follow the [pre-commit standard](precommit-standard.md): only fast checks at pre-commit and pre-push. The CI-only gates are in `.config/ci-gates.yaml`, and the `ci-config` input of `gates_pipeline.yml` runs them.

## Required status check

A repository that adopts `gates_pipeline.yml` through a caller job named `gates` requires the single status check `gates / gates` in its branch ruleset. The docs and spec-only skip companion reports the same name.
