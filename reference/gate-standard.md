# Gate standard

Every repository in the fleet has at most eight blocking checks. Everything
else is advisory: it runs once a week, writes a report, and never fails a
pull request. Pipelines publishes the shared pieces; each repository
references them at `@main`.

## Blocking checks

| # | Check | Where it runs | What it is |
|---|---|---|---|
| 1 | `format` | pre-commit | `ruff format` and `ruff check --fix` for Python; `cargo fmt` for Rust. One logical check. |
| 2 | `hygiene` | pre-commit | The basic `pre-commit-hooks` file checks: end of file, trailing whitespace, merge conflict markers, large files, YAML/TOML/JSON validity. One group. |
| 3 | `secrets` | pre-commit, pre-push | One secret-and-identity check (pipelines hook `secrets`). |
| 4 | `types` | pre-push | `mypy` for Python; `cargo clippy -- -D warnings` for Rust. |
| 5 | `tests-fast` | pre-push | The tests the pushed diff affects, under a 120 s cap (pipelines hook `tests-fast`). |
| 6 | `spec` | pre-push, PR CI | One spec check (pipelines hook `spec`). |
| 7 | `tests` | PR CI, main, tags | The affected subset on pull requests; the full suite on main and on tags. |
| 8 | `supply-chain` | main, tags | One dependency audit: `pip-audit` or `cargo deny`. |

Pull request CI is authoritative. It runs the same pre-commit file as the
contributor (checks 1 to 6) and the affected tests (check 7). Release build and
publish are not gates; they stay in each repository's release workflow.

### What the shared hooks run

Pipelines publishes three hooks in `.pre-commit-hooks.yaml`. Each one is a
group of existing gates, so each check is one hook id and one line of output.

- `secrets`: `security-sanitizer` (credential patterns and root garbage in the
  tree), `secret-history` (credentials in any unpublished commit),
  `tracked-privacy` (host-specific data and local or model identities),
  `commit-identity` and `commit-identity-range` (allowlisted author and
  committer). The two range members, `secret-history` and
  `commit-identity-range`, run only when a commit range is known: at push, and
  in CI through `--from-ref`. A hosted runner without the private identity catalog skips
  `tracked-privacy` with `SKIP=tracked-privacy`; the group honours `SKIP` per
  member.
- `spec`: `spec-standard` (names, file set, index), `spec-decomposition`
  (requirement, task, test-spec and status IDs agree), `spec-status` (the
  generated `status.json` is fresh) and `spec-trailers` (`Spec:` trailers on
  the pull request commits, a range member like the two above). `gates_pipeline.yml` adds `spec-trailers` to
  `SKIP` on a push event.
- `tests-fast`: the `fast-tests` gate. Pass `--src-root <package>` in `args`.

`format`, `hygiene` and `types` come from their upstream hook repositories
(`astral-sh/ruff-pre-commit`, `pre-commit/pre-commit-hooks`) or a local
`mypy`/`clippy` hook, pinned to a full commit SHA.

### Consumer configuration

```yaml
default_install_hook_types: [pre-commit, pre-push]
default_stages: [pre-commit]
repos:
- repo: https://github.com/pre-commit/pre-commit-hooks
  rev: 3e8a8703264a2f4a69428a0aa4dcb512790b2c8c # v6.0.0
  hooks:
  - id: trailing-whitespace
  - id: end-of-file-fixer
  - id: check-merge-conflict
  - id: check-added-large-files
  - id: check-yaml
  - id: check-toml
  - id: check-json
- repo: https://github.com/astral-sh/ruff-pre-commit
  rev: 38bfb07c0c64c304f47eb52090f8288150c77730 # v0.17.1
  hooks:
  - id: ruff-check
    args: [--fix]
  - id: ruff-format
- repo: https://github.com/Knuckles-Team/pipelines
  rev: main
  hooks:
  - id: secrets
  - id: tests-fast
    args: [--src-root, <package>]
  - id: spec
- repo: local
  hooks:
  - id: types
    name: Types (mypy)
    entry: uv run --frozen mypy <package>
    language: system
    pass_filenames: false
    stages: [pre-push]
```

Install both stages with
`pre-commit install --hook-type pre-commit --hook-type pre-push`.

### Workflows

Each repository has three workflows:

- A pull request workflow that calls `gates_pipeline.yml` (checks 1 to 7).
- A main and tag workflow that calls `main_pipeline.yml` (full `tests` and
  `supply-chain`), next to the repository's unchanged release workflow.
- A weekly workflow that calls `advisory_pipeline.yml`.

[The CI standard](ci-standard.md) lists the inputs.

### Python version

Python 3.14 is the environment version. Python 3.12 is the backward-support
floor.

- Package metadata sets `requires-python = ">=3.12"`. The classifiers list
  3.12, 3.13 and 3.14.
- Tooling targets the floor: ruff `target-version = "py312"` and mypy
  `python_version = "3.12"`. Code never uses syntax newer than 3.12.
- Everything that runs uses 3.14: `.python-version`, uv venvs, the gates,
  tests and build jobs, release builds, Dockerfile bases
  (`python:3.14-slim`, pinned by digest), devcontainers and docs. The
  reusable workflows default `python-version` to `'3.14'`. A caller that
  passes a value keeps that value.
- Each repository has one backward leg on 3.12: the `backward-python: '3.12'`
  input of `main_pipeline.yml`. It runs an install and import smoke test, plus
  an optional fast subset in `backward-test-scope`. It is never a full matrix.
- A native abi3 package keeps its own abi3 floor. Only its CI and tooling move
  to 3.14.
- If a dependency has no 3.14 wheel and would need a source build, that
  repository's CI stays on 3.12 until a wheel is published. The repository
  records the dependency.

## Advisory checks

These run only in `advisory_pipeline.yml`. The report lists each check with
its exit status and the tail of its output. A finding is information for the
next cleanup, not a blocked merge.

- Clone detection: `jscpd-census`, `jscpd-differential`, `dupehound-changed`.
- Complexity: `complexity-census`, `complexity-staged`, `kiss-census`,
  `kiss-staged`, and the scanner version proof `scanner-versions`.
- Dead code: `vulture`.
- Spelling: `codespell`.
- Security lint: `bandit`.
- Documentation: `ste-census`, `ste-staged`, `ste-staleness-census`,
  `ste-staleness-staged`, `public-surface`, `mermaid`.
- Code shape: `no-stub`, `stubs`, `swallowed-errors`, `event-loop-blocking`,
  `import-cycles`, `env-sprawl`, `stdout-writes`.
- Repository layout: `root-hygiene`, `gitignore-convergence`, `sprawl`,
  `pre-commit-patch-safety`.
- Workflow and dependency pinning: `supply-chain` (the pipelines pin check,
  distinct from the blocking dependency audit).
- Architecture scanners, bumpversion checks, `hadolint`, license and SBOM
  checks, and repository-specific contract or "gate replica" checks, through
  the workflow's `extra-commands` input.

## Rules

- A repository-specific check that guards real correctness is an ordinary
  test inside `tests`, never an extra hook. Each one has a one-line reason in
  the pull request that adds it.
- A hook that duplicates another, checks code that no longer exists, or exists
  only to keep another gate passing is deleted, not moved to advisory.
- Removing a hook id from `.pre-commit-hooks.yaml` breaks every repository
  that still references it at `@main`. Repositories drop a reference first;
  pipelines deletes the id last. Ids that are still referenced carry a
  `DEPRECATED (<id>)` name in the hooks file until then.

## Rationale

- Speed decides whether contributors keep the hooks installed. The commit
  stage runs in seconds: formatting, file hygiene and secrets. Type checks and
  affected tests run at push, where a slower check is acceptable.
- One check per concern gives one clear failure. Five secret and identity
  hooks and four spec hooks became one each, because a contributor fixes one
  concern, not one implementation.
- Metrics are not correctness. Complexity, clone, dead-code and documentation
  scanners measure trends. Blocking a merge on them produced gate-satisfaction
  work instead of product work, so they report weekly.
- The spec lifecycle is the program's delivery mechanism, so `spec` stays
  blocking.
- Supply-chain audits depend on advisories published after a change merges, so
  they run on main and on tags, where a new advisory is visible without
  blocking unrelated pull requests.
