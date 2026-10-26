# Next composition — Preview candidate; proved e246/d460 receipts retained

## What the actual captures show

The existing chart is a placement/invariance proof, not the desired finished story. Four aligned state columns spend most of their area on zeros; Decision Engine's 565-row cell makes three-row circles practically disappear. Large row gaps amplify the sparseness. Family slugs are legible but not curated display names. The plot relocates between candidate screen slots while zooming. Arbora and Overstory reveal no chart in the centre-directed zoom sweep: the current rectangular footprint cannot use their fragmented gaps.

## One composition, two independently useful levels of detail

**First readable gap: concentration annotation (280 × 76 CSS px).** A short factual sentence and a proportional *specified-row concentration* mark, e.g. “186 of 219 specified rows — arbora app surface”. The denominator is explicit; this is NOT completion, priority or runtime health. Full family identity remains accessible. This reveals a real source-backed fact in a smaller gap without creating a toolbar or panel.

**Larger readable gap: compact family evidence comparison (280 × ~230 px).** Up to three rows, each:
- Family name + absolute contribution (`732 / 740 requirements`).
- A readable, equal-width **within-family** state-composition band.
- Only nonzero exact state counts, e.g. `166 Verified · 565 Specified · 1 Retired` (wrapped when needed). No zero cells, no tiny area marks.

The common **within-family** denominator is explicitly labelled: band lengths compare proportions, not family size. Family contribution is the printed absolute count/total, never encoded through misleading equal bar length. Other families are explicitly aggregated with exact family count and all counts conserved. A shared text legend uses full state names; color is redundant with numbers/text. A short concentration sentence replaces the former three-line scale explanation. If both modules would repeat the same fact, show the comparison only, not two copies.

This does not add a new child-card matrix: it compares requirement-family evidence within the existing native map. No panel background, divider dashboard, filter, selector or new zoom control. No missing dependency/activity/priority feed is fabricated.

## Anchor contract (no roaming)

Compute a small ordered list of node-local anchor points from unchanged source layout geometry once. Candidate identity is stable in world coordinates, not a fresh top-left screen-grid search each frame. Entry requires readable size + an 8px obstacle halo plus 12px spare space; keep the same anchor while safe. Any actual collision causes immediate deferral, never overlap-preserving hysteresis. Leaving the viewport defers rather than sliding to a new corner. Reappearance uses the same node-local anchor; another anchor is selected only at a documented native semantic-zoom tier transition. Caption/card/route obstacles remain authoritative.

## Titles and source truth

Frozen PAYLOAD has family IDs, not curated family display titles. Existing requirement headings sampled locally are machine prefixes, and those local files are not verified at the frozen snapshot SHA. Do NOT present them as verified source titles. Prefer explicit source family display metadata when available at a verified SHA; otherwise retain the humanized recorded family identifier with full ID accessible. Authored replacements need a reviewed title map with provenance, not an inferred claim that one child node names the whole family.

## Acceptance before any design publication

1. Keep all canonical rectangles, routes, camera, controls and gestures byte-identical.
2. Run existing exact pixel/geometry gates; no new masks beyond actual supplementary paint bounds.
3. Positive native mouse-wheel reveal for Arbora, Overstory and Decision Engine on both desktop and mobile; ordinary pan may explore an actual gap, but no injected camera or fabricated free area.
4. Check all text bounds/full labels and nonzero state counts at 11–12px minimum; inspect the full mobile canvas and footer.
5. Verify no anchor jump within a semantic tier, and safe deferral on path/caption/card intersection.
6. Review actual pixels before calling this richer or ready. This file is a proposal, not a screenshot or completed renderer implementation.

## Local implementation available for source review

`composition.js` and `preview.html` implement the two alternate encodings at the existing after-caption story seam. `preview.html` uses the exact e246 proven baseline/payload and unchanged surrounding renderer. One module is shown, not both. Runtime anchor sets are calculated once per focused node from original world rectangles; choices remain pinned within a documented native-width zoom tier. A collision immediately defers instead of choosing another gap. This candidate enters the approved isolated preview-only browser qualification lane; no live deployment or merge.

`check.cjs` passes all 598 count-conservation cases and pure stable-anchor/route-collision tests. Actual native reveal, legibility, route/caption safety and anchor behavior still require the unchanged strict browser/pixel gates after source review. There are no verified curated titles in the frozen model, so full recorded family IDs remain the provenance-safe fallback.

### Source-review corrections
- Accessible description now follows the visible module: concentration announces its SPECIFIED-row denominator only; comparison announces each family denominator and its absolute contribution.
- Text layout measures the right-aligned contribution first and reserves a 12px gap before fitting the family label. Unicode family-label caps/fitting preserve grapheme clusters.
- State legend and nonzero numeric labels wrap as complete items; none are ellipsized. Unrepresentable large text safely defers instead of clipping. Actual measured height is used in obstacle placement.
- Expanded pure tests cover uniform-family/zero-SPECIFIED data, very large numbers (complete or deferred), long Unicode labels, all text rectangles, kind-specific aria, tier entry/return, stable world anchors and immediate collision deferral. These use deterministic mock text metrics, not an Inter browser-render acceptance claim.

Because measured wrapping can increase height, the original ~230px comparison estimate is not a guarantee. The candidate uses the measured footprint, and smaller concentration annotations remain available where a full comparison cannot fit. Actual mobile/Arbora/Overstory reveal and typography are still unproven until the unchanged hosted tests and pixel review are authorized for this new LOCAL design.
