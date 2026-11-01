# Contract — spec-status-read

Provider: arbora ARBORA-OPS-R853
Consumer: pipelines PIPE-GATES-R004.5

## Wire shape

The served `spec.status` operation takes a repository and a revision and returns the engine's state for each row and task. The `states-agree` check compares that answer with the generator states.

## Refusal codes

An unreachable engine reports an advisory finding and never a failure. A mismatch fails the check and names the row and each side.

## Authoritative types

The comparison side is [`generator.py`](https://github.com/Knuckles-Team/pipelines/blob/main/pipelines_hooks/specs/generator.py); the served answer is defined by `ARBORA-OPS-R853` in its owning repository.

## Test vectors

[`tests/hooks/test_states_agree.py`](https://github.com/Knuckles-Team/pipelines/blob/main/tests/hooks/test_states_agree.py) holds the vectors once `PIPE-GATES-R004.5` lands: equal states pass and a mismatch names each side.
