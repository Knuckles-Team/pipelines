# Contract — contract-seam-graph

Provider: pipelines PIPE-GATES-R034.1
Consumer: medulla MEDULLA-SDLC-R014.4

## Wire shape

A contract is the file `specs/<family>/contracts/<seam>.md`. It holds one `Provider: <repository> <ROW-ID>` line, one `Consumer: <repository> <ROW-ID>` line and the sections Wire shape, Refusal codes, Authoritative types and Test vectors. The engine ingests each file as one seam edge.

## Refusal codes

A contract that lacks a required line or section is a finding. A contract that names a row absent from the owning spec, or the same pair as another contract, is a finding (`PIPE-GATES-R034.4`).

## Authoritative types

The parser is [`artifacts.py`](https://github.com/Knuckles-Team/pipelines/blob/main/pipelines_hooks/specs/artifacts.py) today and `pipelines_hooks/specs/contracts.py` once `PIPE-GATES-R034.1` lands; the ingest uses the same fields.

## Test vectors

[`tests/test_spec_artifacts.py`](https://github.com/Knuckles-Team/pipelines/blob/main/tests/test_spec_artifacts.py) holds the vectors for the required lines and sections.
