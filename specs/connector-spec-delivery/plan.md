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

## Amendment: exact standard-ID renumbering (2026-10-23)

PIPE-CONNSPEC-R011 extends the existing alias loader, not trailer acceptance rules. Parse current requirement rows with the shared parser before accepting an exact standard-ID alias. The source must have no current requirement row, including a retired tombstone; the target must be an active row, not a prose mention or another alias. Reject source or target collisions with retired prefixes. Existing prefix aliases and pre-standard exact aliases retain their one-hop behavior. The ordinary trailer gate still requires a bound target test and refuses unrelated unknown IDs. A renumbering fixture checks the historical range and the current PR range independently, and preserves the original landing receipt under the new ID.

PIPE-CONNSPEC-R012 to R016 add competency-question priority. A competency question is an ordinary `MEDULLA-CQ-` row, so the Depends-on graph already carries the signal. The scorer in `priority.py` is shared by the status generator and the architecture page.

## Amendment: distinguish CQ paths from architecture links (2026-10-25)

PIPE-CONNSPEC-R016 labels the existing unserved filter “No CQ dependency path”.
Its explanation states the direction: CQ → Depends-on → requirement. The label
does not report missing architecture placement or implementation links. Keep
the existing filter, scores, classification, requirement states and evidence.
This wording change adds no dependencies and changes no competency questions.

## Amendment: canonical aggregate-hook mapping (2026-10-26)

The child `.2` verification rows use the phrase "the three spec hooks" for the
canonical spec gate contract. The current connector template publishes the
single `spec` aggregate hook alongside the other aggregate gates. At the
provider source, `pipelines_hooks/cli.py:73` defines that aggregate as
`spec-standard`, `spec-decomposition`, `spec-status`, and `spec-trailers`.
Therefore `spec` is the accepted canonical replacement for the three literal
spec hooks in the connector adoption rows; the validation test must assert this
source mapping before binding a `.2` row. This mapping changes no consumer
configuration or runtime behavior.
