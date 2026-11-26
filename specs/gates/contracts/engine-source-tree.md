# Contract — engine-source-tree

Provider: arbora ARBORA-OPS-R848.1
Provider: arbora ARBORA-OPS-R850
Consumer: pipelines PIPE-GATES-R003

## Wire shape

The served `source.tree` operation lists the files of a repository at a revision. The served `source.blob` operation returns one file's bytes with the `sha256:` digest of those bytes. A gate that runs a project's own tools runs in the sandbox on the virtual checkout of the same revision (`ARBORA-OPS-R850`) and reads no served operation for it.

## Refusal codes

A blob whose bytes miss the declared digest fails the gate closed. An unreachable engine is exit code 2, never a clean verdict.

## Authoritative types

The reading side is [`source_provider.py`](https://github.com/Knuckles-Team/pipelines/blob/main/pipelines_hooks/source_provider.py): `FileProvider`, `blob_digest` and `EngineTreeProvider`. The served operations are defined by `ARBORA-OPS-R848.1` and `ARBORA-OPS-R850` in their owning repository.

## Test vectors

[`tests/hooks/test_gate_tree.py`](https://github.com/Knuckles-Team/pipelines/blob/main/tests/hooks/test_gate_tree.py) holds the vectors: the same revision gives the same verdict and evidence digest from the engine tree and from a checkout, and a digest mismatch fails closed.
