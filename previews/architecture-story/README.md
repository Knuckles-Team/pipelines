# Architecture story study

This draft is a preview-only composition study, not the live explorer.
The central capability matrix stands in for the current map. Integration would
keep that map, its arrows, stable IDs and zoom. No live renderer, model or Pages
workflow changes are included.

The study uses the current architecture's ocean scene, neutral glass tokens and
Inter font. The font and its license are copied from the existing renderer assets
at preview build time; no duplicate font is committed. Theme source and font
hashes are in `theme-provenance.json`.

The compressed source snapshot covers 598 nodes and 8,366 mapped spec rows, built
at 2026-10-26 02:31:30 UTC. The build verifies its archive hash, unique row mapping
and font hash. The standalone HTML embeds the study data for review only.
Production must reuse existing data and lazy detail shards, not this payload.

## Review

The PR-only workflow builds a downloadable artifact and captures Arbora,
Overstory, Decision Engine and Generated Client at desktop, mobile, dark/reduced
motion and CSS 200% layout stress. It uses the runner's browser and only Python
and Node standard libraries. It uploads HTML, screenshots and receipts; it does
not deploy or require write permissions.

Each selected story shows at most 12 family summaries and 64 requirement tiles.
One tile is one unique requirement. Recorded spec state does not mean runtime
health, effort or guaranteed completion. Family/row paging reaches all rows.
Directed interface fans only use recorded architecture edges.

The capture harness checks geometry, fonts, budgets, source links, trusted-key
native disclosure, example navigation, focus and Back. CSS 200% stress is not
native browser zoom proof. Screenshots still require visual/contrast review.
The local sandbox blocked Chromium before launch; no local browser pass is
claimed. See actual workflow receipts before drawing conclusions.

No merge or live deployment is part of this draft's authorization.
