# Contract — owner-approval-receipt

Provider: arbora ARBORA-OPS-R896.10
Consumer: pipelines PIPE-IDENTITY-R001.1

## Wire shape

The provider arms a merge only under an owner approval receipt bound to the head commit. This spec consumes no wire data. It consumes the guarantee that the receipt gates every merge, whichever allowlisted identity authored the commits.

## Refusal codes

The identity gates refuse with exit 1 when an author or committer is off the allowlist, and with exit 2 when the allowlist cannot be read. The merge refusal belongs to the provider.

## Authoritative types

The allowlist entry is the `Identity` type in [`allowlist.py`](https://github.com/Knuckles-Team/pipelines/blob/main/pipelines_hooks/identity/allowlist.py). The receipt type is defined by `ARBORA-OPS-R896.10` in its owning repository.

## Test vectors

[`tests/hooks/test_identity_range.py`](https://github.com/Knuckles-Team/pipelines/blob/main/tests/hooks/test_identity_range.py) holds the identity vectors: an allowlisted service identity passes and an off-list one is refused.
