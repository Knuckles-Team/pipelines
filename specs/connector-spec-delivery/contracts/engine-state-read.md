# Engine state read seam

Consumer: pipelines PIPE-CONNSPEC-R009.1
Consumer: pipelines PIPE-CONNSPEC-R009.2
Provider: medulla MEDULLA-SDLC-R005.3

## Wire shape

- The status gate reads the arbora `spec.status` operation over plain HTTP at an endpoint set by repository configuration.
- The response holds one entry per requirement: the row ID and its state, one of SPECIFIED, LANDED, VERIFIED or RETIRED.
- The gate compares the entries with the states `generate` computes and reports every row whose state differs.

## Refusal codes

- An unset endpoint skips the comparison; the gate stays as it is today.
- An unreachable endpoint or a malformed response fails the gate with the message `engine-state-unreadable`.
- A differing row fails the gate with the row ID and both states.

## Owner rows

- Consumer side: `PIPE-CONNSPEC-R009.1` and `PIPE-CONNSPEC-R009.2`.
- Provider side: `MEDULLA-SDLC-R005.3`.
