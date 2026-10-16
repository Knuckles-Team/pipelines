# Architecture — PIPE-CONNSPEC

## Approach

Each connector copies the reference callers named in PIPE-CONNSPEC-R004 and the hook configuration used in this repository. Nothing new is built here. Adoption is tracked per connector through the four child requirements, and the generated status rolls each connector up from its children.

## Order

Land the specs tree and hooks first, then the Pages caller, then the skill section, so each connector's dashboard shows real states from its first publish.

## Landing attribution compatibility

The generator uses Git trailer parsing in the existing single history scan, with historical Spec subjects, ranges and shorthand retained. Existing merged_head and landed_in receipts remain supported: they do not preserve enough provenance to distinguish valid migrations from old parser mistakes. Correct known false receipts through targeted review rather than global invalidation.

## Amendment: retired identities (2026-10-11)

PIPE-CONNSPEC-R006 reconciles ownership moves with permanent requirement IDs. Reuse the status generator retirement parser in the standard gate. Preserve the old row as RETIRED and name its replacement; active rows still obey prefix checks. This does not repair or retire existing rows automatically.

## Repository ownership

Resolve the repository slug offline from origin, or a sole configured remote when origin is absent. This authoritative identity overrides stale generated ownership. If remote identity cannot be established, keep the prior owner, with checkout basename only as a final fallback. Keep legacy landing validation independent of identity correction.

## Amendment: CI prose comparison (2026-10-11)

PIPE-CONNSPEC-R007 closes the clean-index gap in hosted `ste-staged` runs. Reuse sanitized Git access, commit resolution, and bounded event JSON loading. Resolve explicit refs first, then GitHub event bases, then pre-commit refs outside GitHub Actions. New-ref pushes and manual runs check the last commit with full history. Never guess when a requested base is absent. Preserve local staged-index checks and per-file `(code, message)` debt subtraction.

## Generated identity

The generator reuses `standard.check_title` for canonical spec identity. A valid title governs the generated ID. Historical specs without a canonical title retain their fallback; requirement identities and landing receipts are unchanged.

### 2026-10-16: withdraw invalid verification evidence

PIPE-CONNSPEC-R001 permits a narrow evidence-only correction without losing its Spec IDs.
A Spec-Withdraw trailer names the IDs, and Spec-Withdrawal-Reason records why acceptance evidence is invalid.
The whole PR range must preserve requirements and executable source.
Only actual Rust comment bindings may be removed, with owning plan additions, task reopening and generated status updates.
Every withdrawn ID must lose an existing binding and retain its reason in the owning plan.
Unknown IDs, missing reasons, altered code, requirements, modes, workflow or build configuration fail closed.
Other IDs still require ordinary acceptance bindings. Status remains generated from the corrected evidence.
