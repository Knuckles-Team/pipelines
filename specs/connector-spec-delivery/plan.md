# Architecture — PIPE-CONNSPEC

## Approach

Each connector copies the reference callers named in PIPE-CONNSPEC-R004 and the hook configuration used in this repository. Nothing new is built here. Adoption is tracked per connector through the four child requirements, and the generated status rolls each connector up from its children.

## Order

Land the specs tree and hooks first, then the Pages caller, then the skill section, so each connector's dashboard shows real states from its first publish.

## Landing attribution compatibility

The generator uses Git trailer parsing in the existing single history scan, with historical Spec subjects, ranges and shorthand retained. Existing merged_head and landed_in receipts remain supported: they do not preserve enough provenance to distinguish valid migrations from old parser mistakes. Correct known false receipts through targeted review rather than global invalidation.

## Amendment: retired identities (2026-10-11)

PIPE-CONNSPEC-R006 reconciles ownership moves with permanent requirement IDs. Reuse the status generator retirement parser in the standard gate. Preserve the old row as RETIRED and name its replacement; active rows still obey prefix checks. This does not repair or retire existing rows automatically.
