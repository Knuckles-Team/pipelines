# Contract — published-states

Provider: pipelines PIPE-GATES-R004.3
Consumer: medulla MEDULLA-SDLC-R005.7

## Wire shape

A state record binds repository, revision, row or task ID, state and input digest. The state is one of `SPECIFIED`, `LANDED`, `VERIFIED` or `RETIRED`. The record travels over plain HTTP to the arbora `source.*` operations (`PIPE-GATES-R004.1`).

## Refusal codes

A publish failure never changes the gate verdict. With no endpoint the publish is skipped and logged. The engine refuses a record whose state is outside the four values.

## Authoritative types

The computed states come from [`generator.py`](https://github.com/Knuckles-Team/pipelines/blob/main/pipelines_hooks/specs/generator.py); the row grammar comes from [`narrative.py`](https://github.com/Knuckles-Team/pipelines/blob/main/pipelines_hooks/specs/narrative.py).

## Test vectors

[`tests/hooks/test_states_publish.py`](https://github.com/Knuckles-Team/pipelines/blob/main/tests/hooks/test_states_publish.py) holds the vectors once `PIPE-GATES-R004.3` lands: one record per row and task, and a skip without an endpoint.
