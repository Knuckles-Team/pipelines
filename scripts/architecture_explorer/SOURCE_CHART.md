# Rebuild-derived architecture source charts

## Source-only chart integration

`story_chart_sources.capture_git(root, full_commit, canonical_repository)` reads
an existing exact Git commit without fetching or following mutable refs. It
checks Git errors, retains complete raw source inventories and rejects symlinked
source documents. `source_chart(captures=..., repositories=..., selection=...)`
normalizes every captured repository's raw requirement/status pairs, validates
frozen aliases with the shared spec gate, and calls the existing scorer/frontier.
It does not call APIs, write artifacts, bind model nodes or supply activity counts.
The caller must verify immutable repository IDs; a supplied capture is a trusted
boundary, not independent authentication of arbitrary supplied text.

Default `score_scope="complete-captured-repositories"` requires every declared
prerequisite to resolve in the captured scope. It is not a claim of full-fleet
incoming dependent coverage. An explicit
`score_scope="selected-family-prerequisite-closure"` selects all rows in the named
canonical `repositoryId:family` keys plus their transitive prerequisites. Any
missing/ambiguous edge in that closure fails the view. Unresolved edges wholly
outside it remain in `scope.excludedDependencyGaps` with exact declaration
context and full-SHA provenance. There is no automatic fallback from failed
complete-repository validation to a smaller scope.

The output schema `architecture-source-chart/1` exposes complete captured source
freezes, captured/score row counts, selected keys, prerequisite closure keys,
canonical edges, declared-to-canonical alias resolution provenance, source row
states, score inputs, shared readiness and SCC diagnostics. Family compositions
count actual source rows (including rollups), while readiness is leaf-only.
Consumers must label the scoring scope visibly and never compare a family-scope
score with a fleet/repository score as though denominators matched. A dependency
edge runs **dependent -> prerequisite**. A zero score is a computed scoped value;
LANDED/VERIFIED/RETIRED priority is not applicable, not zero. The absence of
recognized canonical prerequisite declarations does not prove no real dependency.

`activity.state="not_collected"`, `modelMapping.state="not_qualified"`, and
`scope.fleetComplete=false` are explicit capability boundaries, not fake metrics.
The real-build seam below wires this view into the canonical build and PR qualification path.
The dormant activity_probe module supplies only the shared NoRedirect helper. No activity-probe workflow, feed calls or feed configuration are activated.

Local real-source qualification uses the existing 2026-10-26 02:31:30 preview
freeze, not current production: Overstory
`0ccc3aa2c0019d2fb1aaab37b2acc99927f75669` and Arbora
`a729a462b7aa5b6d2029858fa7bf23b5ca1d1683`. Their complete 1446 raw rows yield two
selected Overstory families (244 rows) plus four prerequisite rows: 248 scoring
rows and six actual edges. Four outside-scope unresolved dependency declarations
remain recorded; full-repository mode fails. In particular the authored
ARBORA-HOST-R005.2.8 declaration `.2.1`-`.2.7` resolves under the current shared
grammar to missing ARBORA-HOST-R005.2.2.1, not a guessed replacement. This scoped
view is an intermediate design input, not completion of all-box mapping,
production rebuild integration or whole-bundle promotion.

Cross-family prerequisite rollups may refer to children outside the score scope.
Those children (and recursive rollup inventory) are exported separately in
`evidenceRows`, tagged `rollup_evidence_only_not_scored`, with source/status
provenance but no priority or readiness. They must not silently enlarge the
score denominator or graph. Every rollup evidence key resolves in `rows` or
`evidenceRows`; the real scoped preview includes two such evidence-only rows.

## Opt-in actual rebuild seam (runtime qualification required)

`build.py --mode github --source-families PATH --page site/architecture/index.html`
accepts an explicit nonempty JSON object mapping scanned logical repository names
to family names. For the first view:

```json
{"overstory":["arbora-api-consumer","arbora-app-surface"],"arbora":[]}
```

An empty family list captures that repository for prerequisite closure; it does
not select all its rows. Unknown repositories/families, JSON null, duplicate
configuration keys and redirect/source-mode combinations fail rather than
silently using the legacy path. The canonical explorer build and current-source PR visual workflow explicitly enable this option.

`story_build.load_build_sources` uses the one actual `sources.scan_set` result.
For configured repositories it verifies canonical identity and the full frozen
commit, complete recursive tree and each raw document blob identity/size/hash.
The same captured raw bytes feed existing `rows_for`/details and strict
`source_chart`. Selected graph and evidence-only row identities, statuses,
families and titles must match those public rows. Other repositories retain the
existing loader. An absent/malformed selected prerequisite fails before layout
or artifact writes; unrelated excluded gaps stay explicit in the scoped view.
The existing unmapped/error gates also fail before writes in source-chart mode.
This does not certify the old heuristic node mappings or exempt zero-row leaves.

Selected-source transport requires the existing token and allows only GETs on
fixed GitHub repository/commit/tree/blob endpoints. It rejects redirects, access
denial, incomplete trees and malformed data, without retry or anonymous fallback.
Its limits are 512 requests total, 4 MB per JSON response, 30 seconds per request,
and eight configured repositories. These bounds apply to **strict source capture
only**, not the earlier existing GraphQL discovery or remaining legacy fleet
loader; this is not a global request, rate-limit-reserve or wall-clock guarantee.
No permissions, credentials or activity-feed behavior change.

On success, emitted root data includes `sourceChart` with a `buildReceipt`:
`builtAt` equals the same page metadata timestamp; `sourceScope` contains full
commits; `publicHeads` matches same-run snapshot display heads; `sameCaptureParity`
is true only after source/public row checks. `sourceChartSha256` hashes canonical
sorted compact UTF-8 JSON (`ensure_ascii=False`) of the chart **excluding buildReceipt**. All object keys must be ASCII; Unicode string values are preserved. The receipt declares `canonicalEncoding="utf8-sorted-compact-ascii-keys/1"`. Already-sealed
charts and mismatched public/source heads are rejected. Consumers must use this
receipt and current emitted rows, never import the old design snapshot or its
hardcoded freeze. This source mode is presently github-only; local unpinned
registry fallback is deliberately not a qualifying path.

Pure tests exercise the real CLI call path, receipt attachment and exact details
bytes, malformed captures/configuration, denial/request limits and preservation
of previous page/details/tree on source validation failure. Actual current-head
source capture with the existing workflow token and source-rich hosted visual
validation remain required before production activation. General whole-bundle
atomic promotion remains a separate requirement; this change prevents source
validation failures from reaching current emitters but does not make arbitrary
post-validation filesystem failures atomic.

The candidate configuration is `scripts/architecture_explorer/source-families.json`.
Library callers remain opt-in; the canonical Pages build and PR visual qualification explicitly select it. Before converting the live chart to a
JavaScript layout model, call Python `story_build.verify_chart_receipt` with the
chart, current metadata `built_at`, `heads` and `slugs`. It checks the identical
Python canonical encoding, digest, time, source scope and public source mapping;
it is an integrity/same-build check, not a signed attestation or general JCS
cross-language number-format standard. The browser need not hash the payload.
