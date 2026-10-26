# A visual story for every architecture part — local design study v2

Theme/hosted-preview packaging: see `PREVIEW-PLAN.md` and `theme-provenance.json`. No browser QA or publication has occurred.

## Refined recommendation: requirement mosaics + interface spines

The first study leaned too heavily on status underlines already present in the explorer. **The richer v2 contribution is a discrete, inspectable requirement mosaic and a recorded input/output fan**, composed around the existing capability map—not four more dashboard panels.

- **Requirement mosaic:** one visible square represents exactly one unique `(repo, requirement ID)`, grouped by its actual `(repo, spec family)`. Color encodes only recorded status. Each tile has a named accessible source link; every family has an explicit ID/status/title list loaded on disclosure. Only one focused family is drawn as requirement tiles, paged at 64 rows. Other families appear as explicitly aggregated, labelled summaries (12 per page), with a native selector to reach any family directly. Larger families state the exact visible row range and total rather than implying the visible area is the full distribution. Counts describe all unique rows. Source order is stable, not an importance ranking. This is not an effort treemap or completeness metric.
- **Interface spine:** exact incoming and outgoing architecture edges form a small input → selected part → output fan. Curves occupy reserved gutters only, never port-label or child rectangles. Port names/verbs are native buttons. One-sided interfaces remain one-sided; unrecorded interfaces are labelled, not symmetrically invented. Cross-links without direction stay outside the fan. On narrow screens the same ports stack in readable order and the curves disappear, not the facts.
- **Map remains the centerpiece:** the production design reuses its existing child boxes and routed graph. Mosaic and spine use explicit reserved surrounding space or existing selected-detail content. The standalone prototype still uses a compact child/evidence matrix as a navigable composition surrogate, **not an integration of the actual canvas**; the production map must not be replaced with this matrix or duplicated. This limitation is explicit, not a live implementation claim.

### Four reusable archetypes, one grammar

Deterministic precedence is external → hub (at least three recorded incident directed edges) → container (has children) → leaf. A structurally childless node may therefore use the hub treatment when its actual interface density warrants it. All four share type, spacing, evidence meaning and navigation.

| Archetype | Current nodes | Curated treatment |
|---|---:|---|
| Hub | 29 | Existing capability map, readable interface fan/spine, family-grouped requirement mosaic |
| Container | 49 | Existing child map takes visual priority; smaller fan when edges exist, evidence mosaic follows real family composition |
| Leaf | 517 | No fake child map: contract excerpt and code anchors, requirement tiles/ID disclosure, actual ports if recorded |
| External | 3 | Actor purpose + ancestry + recorded boundary fan; explicit external ownership, no fabricated spec tile field |

No interface and no rows are independently represented states, not reasons to invent decoration. A sparse leaf can be a strong, quiet contract composition. Do not force all slots to appear if their underlying facts are absent.

### Actual v2 examples

- **Arbora:** hub; 13 direct parts; 8 boundary interfaces; **14 spec families / 1,052 unique requirements**. The largest source families are Hosted API Operations (278), Host Composition Boundary (205), and Fleet Catalog and Tools (192). These numbers describe rows, not implementation effort.
- **Overstory:** container; 7 direct parts; 2 boundary interfaces; **7 families / 350 unique requirements**. Incoming People “asks” and outgoing Arbora “typed operations” form a simple readable spine. Application Surface contributes 221 rows; the API Consumer family contributes 23.
- **Medulla → Decision Engine:** hub; 12 direct parts; 3 boundary interfaces; **5 families / 740 unique requirements**. The Decision Engine family supplies 732; the other four families contribute real cross-cutting rows (1, 3, 3, 1), not decorative filler.
- **Generated Client (`webui.api.gen`):** leaf; **2 families / 5 unique requirements** (4 API Consumer, 1 Application Surface). The first focused family has four individually linked squares; selecting the other shows its one square, forming a genuinely different small-scale story; no invented children or flow history.

### v2 render schema and checks

`schemaVersion: 2` adds a single global `rowIndex` keyed by `repo:rowID`; each story has `families: {"repo/family": [rowKeys...]}` and `archetype`. Within each story, a row occurs in exactly one family and once overall. Different ancestor/descendant stories intentionally reuse rows; never sum their mosaics as independent work. Family partition uniqueness, row-index resolution and count conservation are asserted for all 598 nodes. The generated artifact is roughly 5 MB because it is a standalone study with its row data inlined; production should reuse the existing payload and lazy detail path, not add a parallel payload.

`check_render.cjs` additionally evaluates real JavaScript render functions against a minimal DOM stub for all 598 nodes, with detailed examples for Arbora, Overstory, Decision Engine, Generated Client and People. It verifies that the relevant tiles/fans render without undefined/NaN output and no node exceeds 64 visible row tiles or 12 family summaries. This is **render-model testing, not browser, layout, screenshot or accessibility acceptance**. No second Chromium launch was attempted after the previously reported sandbox denial.

## Bounded rendering budget (implemented in local study)

At most **one selected story**, **12 family summary controls**, **64 requirement tiles**, and (only after disclosure) **64 named row links** are mounted for the mosaic. Native family selection reaches every family without a multi-thousand-tab-stop wall. Family and requirement paging preserve an explicit range/total and return focus to the family control. A 64-row page is labelled as source ordered and **not a representative status sample**; full-family/subtree counts remain exact. Only current selected-node DOM is mounted. No animation or additional fetch is introduced by this study. Source row lookup is shared rather than duplicated per story; production must reuse current payload/shards. These are hard DOM-count budgets, not measured frame-time or accessibility acceptance.

## Original composition foundation

Use one **capability landscape**: the existing child map becomes the visual story, rather than surrounding it with four new dashboards. Every focused part explains **what it does, what it contains, what crosses its boundary, and what the specification records**. Meaningful visual variation comes from that part’s real composition, named interfaces and spec distribution. No new product/Atlas label is introduced.

Keep the ocean/Overstory atmosphere continuous. Use quiet ink, sparse hairlines, flat source-derived texture, editorial typography and the current layer accent; **no new glass swimlanes, white pill labels, glass-on-glass cards, fake activity or ornamental diagrams**. Empty space is not a defect when the model has no additional fact to show.

### The composed surface

1. **Purpose anchor:** role, title, one existing description. A bounded reading column, not a panel.
2. **The actual capability map:** reuse each child box and all existing routed edges. Add a slim segmented spec-distribution underline within each child’s reserved footer. It compares status composition, not throughput, importance, health or completion. Full label/count meaning is available in native detail. Do not draw a second set of child cards beside the first.
3. **Boundary rail:** selected-node incoming/outgoing interfaces in a reserved reading strip, with named counterpart and verb. It is a textual/graphical key to actual edges, not another network or implied execution sequence. Unoriented `links` appear separately as “Related capability · direction unspecified.”
4. **Evidence texture:** parent summary band and an on-demand source ledger. The band is 100%-normalized composition with an explicit raw-row total, equally styled across nodes. Its segments are VERIFIED / LANDED / SPECIFIED / RETIRED, never renamed “healthy / running / failed.” Segment proportions are **rows**, not effort. Keep the status legend visible whenever the band is shown; do not turn zero rows into an empty 100% bar.

The standalone HTML deliberately substitutes a compact child/evidence matrix for the explorer canvas to make this reusable composition inspectable. It is **not an integration patch or approved final appearance**. In production those same child marks belong on existing child geometry, not a second matrix.

## Layout contract: reserve, never overlay

Add explicit `storyInsets` to the per-level build layout. Purpose uses a header reservation; boundary/evidence reading content uses a footer reservation; all child positions and edge routes are translated into the remaining graph rectangle. Edge-label collision policy continues to own the graph rectangle. Never discover a blank spot at paint time and cover it with a story.

If graph geometry cannot accommodate the additional reservations at readable size, keep the existing geometry unchanged and show story content in the **existing selected-part detail region**. At narrow width, use the same selected-part content in normal document flow below the map, with named return controls. Do not alter fixed-layout root geometry until it has its own measured layout fixture. Text cannot cross into child or edge regions, and must wrap rather than shrink. Existing IDs, deep links, navigation history and hit targets are retained.

## Semantic zoom / progressive disclosure

These are proposed starting rules for testing, not measured acceptance thresholds:

| Mode | Show | Never do |
|---|---|---|
| Overview / small projected node | Existing title and native role, selected/focus state; retain current diagram | Squeeze story prose or tiny charts into every overview card |
| Focused part, children opening | Purpose header and existing children/edges; child evidence underlines only when their usable footer is at least 100 CSS px wide and the shared legend is readable | Animate edges as traffic, infer runtime activity, reveal multiple levels of prose at once |
| Focused part with adequate screen space | Parent spec mix + clearly scoped count; recorded-interface rail; selected child's evidence detail through the existing inspector | Repaint every descendant DOM story or duplicate every child as a panel |
| Leaf | Keep purpose + parent context; use available contract description, code anchors and mapped rows as the rich view; “No child decomposition recorded” | Invent a pipeline/stages to give the leaf something to draw |
| Deep evidence | Native list/table of source rows and lazy-loaded requirement/test/evidence detail | Treat VERIFIED source status as independent current acceptance proof |

Use projected CSS space, not numeric zoom alone. Keep the canvas camera and its continuous/infinite zoom behavior. Bind a single native story surface to the settled/selected node; virtualization is by visible node. Use selection hysteresis to avoid swapping text near thresholds. Explicit click/keyboard navigation and list/search/breadcrumb alternatives reach every node. Updating focus or newer navigation must cancel any older pending transition. No essential information is hover-only.

## Concrete schema and provenance

`stories.json` implements version 2 of a small render model. `build_story.py` derives it directly from the generated payload without dependencies or modifying any repository source.

| Story field | Source / rule |
|---|---|
| `id`, `title`, `role`, `purpose`, `layer`, `level`, `repo` | Existing generated node fields (`description` becomes `purpose`); never rewrite stable IDs |
| `parent`, `parts` | Containment tree; direct children only; preserve source ordering, not a fake relevance ranking |
| `relationships` | Explicit generated `layout.edges` incident to this node; keep original endpoint IDs, label and direction; do not derive “dependencies” from geometry |
| `references` | Node `links`; relationship direction is explicitly unspecified |
| `internalEdges` | Explicit edges connecting direct children, available to existing child-map renderer |
| `evidence.ownRows`, `ownStatuses` | This node’s directly mapped specification rows |
| `evidence.subtreeRows`, `subtreeStatuses` | Deduplicated `(repo, row ID)` across this node and descendants; never sum parent and child totals in a grand total |
| `evidence.rows` | Bounded first three mapped source rows for prototype anchors, explicitly labelled source order, not “most important”; production uses existing full/lazy evidence viewer |
| `evidence.codePaths` | Existing paths; absence means no recorded anchor, not no implementation |
| `evidence.state` | `external`, `mapped`, `unmapped`; no synthetic zero-success or completeness state |
| `empty.parts`, `empty.relationships` | Explicit presentation decisions, with honest text |
| `provenance` | Payload build time, source revision map, payload digest, `snapshotOnly: true` |

Do not conflate architecture edges, spec prerequisites, and runtime activity. The payload’s root `delivery` graph is a separate row-prerequisite view; it can later drive an explicitly labelled evidence drill-down but must not be mixed into boundary arrows. Requirement/test evidence lives in lazy `spec-details` shards and is not fully present in this preview ZIP; no test-passing assertion is inferred.

## Actual examples, same grammar

Snapshot: **2026-10-26 02:31:30 UTC**, 598 parts, 8,366 mapped rows. The local model/template and latest known deployed-payload ZIP were read; this report is snapshot evidence, not a new live fetch.

### Arbora (`arbora`)

Purpose: governed runtime gateway/composition host — authenticate, admit, audit and serve operations. Thirteen direct parts become the existing capability map. Eight recorded boundary interfaces include entry-client requests and outgoing runtime/connector/skill relationships. Evidence mix across descendants: **1,052 rows: 264 VERIFIED, 86 LANDED, 698 SPECIFIED, 4 RETIRED**. Zero rows assigned directly; the UI must say “this part + descendants,” not imply Arbora itself owns 1,052 independent implementation checks.

### Overstory (`webui`)

Purpose: browser experience with typed Arbora operations and projections, holding no data of its own. Seven direct parts: Arbora API Consumer, Application Surface, Browser Design System, Decision Evidence, Markets App, Identity Screens and Overstory Studio. Boundary rail shows **People → asks → Overstory → typed operations → Arbora** as two recorded interfaces, not an observed request or animation. Evidence mix: **350 rows: 99 VERIFIED, 32 LANDED, 219 SPECIFIED**. No rows assigned directly. The design-system leaf can replace the map with its mapped requirements and code anchors rather than fabricated subcomponents.

### Medulla → Decision Engine (`eg.decide`)

Purpose: typed questions and decision assembly. Twelve direct parts; three recorded interfaces. Its capability composition is genuinely different from Overstory, despite identical visual grammar. Evidence mix: **740 rows: 166 VERIFIED, 573 SPECIFIED, 1 RETIRED**. Code anchors include `crates/eg-types/src/decision` and `src/server/handlers/decide`; show these only as recorded anchors, not proof of current compiled delivery.

## Sparse and special states are first-class

The audit found **535 leaves, 335 nodes without any recorded incident interface/reference, 19 non-external nodes without mapped rows, and 3 external participants**. These are source-snapshot counts, not operational metrics.

- Leaf: expand the evidence/contract reading surface, preserving ancestry. No fictional children.
- No recorded interface: “No interface is recorded here. This does not imply independence.” Do not draw disconnected decorative tendrils.
- No mapped rows: “No spec rows map to this part.” No progress meter or 0%-complete badge.
- External: identify the participant as external; connected internal parts own obligations.
- Unknown status in a future payload: keep the exact status text in an “other recorded status” segment/list; never silently drop it or coerce it to SPECIFIED.
- Source error/stale metadata: distinguish unavailable from empty, keep provenance, and label snapshot age rather than claiming “live.”

## Theme, performance and accessibility gates before integration

Read: `overstory-pr197-main-check/specs/browser-design-system/requirements.md` and `interaction-contract.md`, plus current architecture model/template and generated payload. Relevant requirements: purposeful density R002.1; full responsive access R004.1; readable native semantic zoom R005.1; evidence-bound topology R005.3.2; optional/bounded effects R005.4. The latest user rejection of busy swimlane glass and white badges takes precedence over copying historical white-card material examples.

- The review study now reuses the current renderer's exact ocean/neutral-glass tokens, abstract ocean scene and same-origin Inter font; see `theme-provenance.json`. Local CSS adds composition layout and semantic aliases only. Production must reuse the existing theme source rather than add a second theme package.
- No new library, renderer, network request, telemetry, remote font or per-node animation.
- Precompute status counts/relationship indices at build time; mount one active native story, not 598 story DOMs. Keep evidence shards lazy.
- Reduce motion means immediate state changes; this prototype has no motion. Normal mode needs no new animation either.
- Legend text, numeric count and status words remain available independently of color. Target 4.5:1 normal text, 3:1 meaningful graphics/focus, and test actual composited pixels.
- Preserve minimum readable text and 44px touch controls. Test 320px width, 200% browser zoom, low-height/ultrawide, light/dark/forced colors, keyboard navigation and screen-reader reading order.
- Test interrupt/repeat/back/ancestor flows, empty/unlinked/external fixtures, count conservation, stale evidence and unknown status.
- Pixel collision assertions must include story reservations, every label's bounding box, existing arrows and child cards. Compare frame/input/memory measurements on the same exact candidate before claiming performance acceptance.

## Local validation and limitations

`python architecture-visual-story-local/build_story.py` passes derivation checks across all **598 nodes**, reconciles the root count to **8,366**, checks status conservation, containment and all relationship destinations. Python compilation and extracted JavaScript syntax are separate checks.

`check_browser.py` prepares desktop/mobile, light/dark, reduced-motion, overflow and child-navigation/back checks. The first Chromium launch was blocked by sandbox `socket() failed: Operation not permitted`; no alternative launch or bypass was attempted. **No screenshots or browser/contrast/performance/visual acceptance are claimed.** The HTML is inspectable locally but must receive browser/visual review before integration. Annotation cleanup can ship independently; no annotation-branch file was edited and no external writes were performed.
