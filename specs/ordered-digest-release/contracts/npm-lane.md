# Contract — shared npm release lane

Provider: pipelines PIPE-RELEASE-R033
Consumer: arbora-city CITY-PACKAGE-R001.6
Consumer: arbora-city CITY-PACKAGE-R003.1

## Wire shape

A consumer calls `Knuckles-Team/pipelines/.github/workflows/npm_pipeline.yml@main` with `with:` inputs `node-version`, `package-manager`, `typecheck`, `lint`, `test`, `build`, `pre-publish` and `publish`. `publish` is a boolean; the others are strings. The consumer passes `secrets: inherit` so that the lane can read `NPM_TOKEN`.

## Refusal codes

- `TAG_VERSION_MISMATCH`: the tag is not `v` plus the `package.json` version. Nothing publishes.
- `VERSION_EXISTS`: the registry already holds the version. Nothing changes.
- `GATE_FAILED`: a gate step exited non-zero. The message names the step.

## Authoritative types

The `on.workflow_call.inputs` block of `.github/workflows/npm_pipeline.yml` (planned by `PIPE-RELEASE-R033`).

## Test vectors

`tests/hooks/test_npm_tag_version.py` and `tests/workflows/test_npm_pipeline.py` (planned by `PIPE-RELEASE-R033`).
