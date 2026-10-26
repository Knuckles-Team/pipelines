# Architecture story study

This draft is a preview-only in-box study, not the live explorer. Each selected
node contains its recorded child rectangles and routed edge polylines, followed
by purpose, interface and requirement-family evidence in reserved in-box space.
The matrix surrogate is removed. The study does not change the canonical
renderer, model, Pages or source metadata, and must not be merged as production.

The study reuses current architecture ocean/neutral-glass tokens and Inter. The
font and license are copied from existing renderer assets at build time. Theme,
font and snapshot hashes are in `theme-provenance.json`. The timestamped snapshot
has 598 nodes, 8,366 unique root rows and 63 recorded decompositions. Its XZ archive
hash, row uniqueness and font identity are checked before preparing the preview.

## Interaction and rendering

Primary story sections stay within an explicit selected-node boundary. Family
area is proportional to unique mapped requirements; state texture is recorded
spec status, never health, effort or guaranteed completion. At most 12 family
regions are drawn, with small families grouped as Other when needed. The native
family selector reaches all families. Secondary inspection pages at most 64 row
tiles and 64 disclosed row links; no multi-thousand-link wall is mounted.

Text caps use Unicode graphemes (codepoint fallback): purpose 96, role 42, child
label 22 and interface verb 18. Full text remains in accessible names, SVG titles
and the full inspection route. Labels are measured at 12 CSS px and hide only
when their projected rectangles cannot fit readable text. Bounded SVG diagram
zoom (1x-4x) reveals them again. Native scrolling and child selection remain.
This is **not the live continuous/infinite canvas**; hash navigation is not camera
zoom. Semantic detail disclosure separately shows Overview/Structure/Focused.

Every focusable SVG node handles Enter and Space explicitly. Activation opens the
exact child; browser Back restores the parent and originating SVG-node focus.

## Preview validation

The PR-only read-only workflow captures Arbora, Overstory, Decision Engine and
Generated Client at desktop, mobile, dark/reduced motion and CSS 200% layout
stress. It uses runner Chrome and Python/Node built-ins, with no dependencies or
lockfile changes. HTML, viewport/full-page PNGs and receipts are retained as
artifacts; nothing is deployed.

Checks cover selected-box containment, child-label geometry/readability, overlap,
fonts, bounded row/family counts, source links, trusted-key SVG Enter/Space exact
child activation and Back/focus, bounded zoom, and native inspection disclosure.
CSS 200% stress is not native browser zoom proof. Actual pixels and contrast still
require review; no final visual acceptance is inferred from a passing test.

## Strict production-data gate remains separate

This timestamped legacy fixture is not an accepted `architecture-story/1` input.
Exact prerequisite edges, normalized priority inputs, verified repository PR/issue
snapshots and reviewed coverage/applicability are not fully available. No fake
priority, dependency or activity chart fills those gaps. They remain production
build blockers, not zero/unknown placeholder metrics. Future production integration
must refresh/validate required sources on every rebuild and atomically promote
only a complete validated bundle. It must reuse existing data/lazy detail shards,
not ship this standalone review payload.

No merge or live deployment is authorized by this preview draft.
