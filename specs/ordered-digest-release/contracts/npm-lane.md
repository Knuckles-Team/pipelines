# Contract — shared npm release lane

Provider: pipelines PIPE-RELEASE-R033
Consumer: arbora-city CITY-PACKAGE-R001.6
Consumer: arbora-city CITY-PACKAGE-R003.1

## Wire shape

A consumer calls `Knuckles-Team/pipelines/.github/workflows/npm_pipeline.yml@main` with `with:` inputs `node-version`, `package-manager`, `typecheck`, `lint`, `test`, `build`, `pre-publish` and `publish`. `publish` is a boolean; the others are strings. The consumer passes `secrets: NPM_TOKEN: ${{ secrets.NPM_TOKEN }}` (or `secrets: inherit`) and grants `id-token: write` to the calling job. The lane uses `NPM_TOKEN` for a package's first publish only and registers the trusted publisher afterwards; every later publish uses trusted publishing with the token empty (PIPE-RELEASE-R033.2 to R033.4).

## Refusal codes

- `TAG_VERSION_MISMATCH`: the tag is not `v` plus the `package.json` version. Nothing publishes.
- `VERSION_EXISTS`: the registry already holds the version. Nothing changes.
- `NPM_AUTH_MISSING`: a new package and no `NPM_TOKEN`, or a known package and no `id-token: write`. Nothing publishes.
- `REGISTRY_UNREADABLE`: the package lookup failed for a reason other than `E404`. Nothing publishes.
- `BUMPVERSION_MISMATCH`: a bump2version `current_version` differs from `package.json`. Nothing publishes.
- `GATE_FAILED`: a gate step exited non-zero. The message names the step.

## Authoritative types

The `on.workflow_call.inputs` block of `.github/workflows/npm_pipeline.yml`.

## Test vectors

`tests/hooks/test_npm_tag_version.py` and `tests/workflows/test_npm_pipeline.py`.
