# Architecture story producer (opt-in, not yet production-wired)

`story_contract.produce(**inputs)` validates a complete evidence-bearing input and
returns `architecture-story/1`. `export_atomic(path, **inputs)` performs the same
validation before touching the destination, then atomically replaces **one JSON
file**. This is not yet atomic promotion of the whole public HTML/details bundle.
The existing build, source readers, workflow and renderer are unchanged.

## Input and output

- Repositories: immutable GraphQL `id`, canonical `fullName` (`owner/name`), and
  `url` (`https://github.com/owner/name`). Display branding is never identity.
- Provenance: exactly `repository`, full 40-hex `commit`, `path`, `fragment`.
- Mapping: `state`, `keys`, `provenance`, optional `reason`. `complete` requires
  nonempty unique keys. Empty `none_declared` (or explicitly allowed
  `not_applicable`) requires reason and provenance. This is a reviewed declaration,
  not inference that no dependencies/specs exist in reality.
- Row: `key` (`repositoryId:rowId`), `id`, `repositoryId`, `title`, `family`,
  `status` (VERIFIED/LANDED/SPECIFIED/RETIRED), explicit boolean `functional` and
  `rollup`, `provenance`, `placement`, and dependency mapping with canonical target
  keys. Ambiguous bare IDs are rejected before the shared priority scorer runs;
  aliases must be explicitly resolved upstream, never guessed.
- Node: `id`, nullable `parentId`, `kind` (`internal_leaf|aggregate|external`),
  `label` and `purpose` (`text`, `provenance`), plus `ownership`, `specs`, and
  `relationships` mappings. Leaves own exactly one repo; aggregate effective
  ownership is deduplicated descendant/own-row evidence. External specs/ownership
  require explicit `not_applicable` with reason/source. Relationship references
  are **not** transformed into directional requirement dependencies.
- Call inputs also include `activity`, timezone-aware `built_at`, and a mandatory
  positive `max_age_seconds` policy. No universal production max-age is chosen here.

Output maps `nodes`, `rows`, `repositories`, and `activity` by canonical identity.
Node story fields: `nodeId`, `parentId`, `kind`, descriptions and mapping evidence,
`ownRows`, `subtreeRows`, explicit four-bucket `statusCounts`, `families`,
`readiness` (`ready|blocked|notApplicable` counts), `topPriorities` (up to five,
`rowKey` plus priority object), `dependencyEdges` (`source` requires `target`,
row dependency provenance), `repositoryIds`, `activityRefs`, `repositoryActivity`
(separate sums of open PRs and issues over distinct repos). Family counts use canonical `repositoryId:family` keys so same-named families
in different repositories cannot collapse.
Use activity refs to show freshness, not the rebuild timestamp. Label totals as
**Repository activity**, never imply all those PRs/issues affect a particular leaf.

Row priority has `state: scored`, `value`, `formulaVersion: goal-weighted/1`, and
inputs `competencyQuestions` (canonical row keys), `openDependents`, and
`functionalFactor`. Completed rows instead have `state: not_applicable`, reason,
empty inputs, and **no value**. Open score zero is retained. Readiness excludes
rollups from independent ready/blocked leaf counts; exported `rollup` stays explicit.

## Activity collection and cache

`story_activity.collect(repositories, request=callable, now=..., max_age_seconds=...,
cache=..., reserve=...)` accepts a caller-owned authorized JSON GraphQL transport.
No token discovery, new credentials, permission requests, browser polling, REST
`open_issues_count`, or network operations occur in this module. Each known repo
gets one sequential query with separate OPEN issue/PR `totalCount`, immutable repo
identity and rate-limit cost/remaining/reset evidence. This conservative first
version stops all further queries after any failure or reserve-budget exhaustion;
it does not retry or bypass denial. A future batching transport must preserve the
same all-fields and all-alias completeness checks. The default reserve is 100;
production must explicitly configure a reserve for the remaining source workload.

The returned observation records include original `observedAt`/`lastVerifiedAt`,
latest `attemptedAt`, `freshness: fresh|stale`, `refreshOutcome: ok|failed`, safe
failure category, separate integer counts, query version and SHA256 integrity over
immutable observation fields. Hashes detect accidental mutation, not authenticity;
cache input must come from the trusted producer-owned storage, not public clients.
A failed refresh can use a valid unexpired record only. It preserves original time
and counts and sets a visible failure state. No missing/partial record becomes zero.
The input cache is never mutated; persist the returned cache only after full build
validation. Raw transport errors/credentials are never serialized.

## Rebuild integration still required

1. Freeze full source SHAs and canonical repo IDs with the existing authorized
   build token. Make source reads strict: do not reuse permissive empty/default
   behavior from current `sources.rows_for` as evidence of a complete scan.
2. Resolve and review mapping declarations, including all zero-row leaves, and
   relationship applicability. Preserve separate containment/interfaces/row graphs.
3. Normalize canonical rows/dependencies; call the producer as a pre-render gate.
4. Refresh activity on **every rebuild**, independently of source SHA cache keys.
   Verify exact GraphQL authorization at the build runtime before enabling it.
   The separate `activity_probe` uses the existing Actions token to verify
   the current repository only; that observation is recorded in the draft PR
   receipt. It does not establish fleet or production refresh authorization.
   `frozen_activity_probe.qualify` is an opt-in integration function accepting the
   exact already-frozen `sources.scan_set` result and its registry provenance. It
   does not discover arbitrary repositories or wire itself into production.
5. Render HTML/details plus JSON/manifest into a private staging directory; run
   layout/browser validation, then atomically promote the complete directory.
   Failure must never upload partially generated public output.
6. Consumer must enforce authored short-label/display policies and actual measured
   box-space constraints; this producer preserves full Unicode source text and does
   not implement grapheme limits or truncate evidence.

The audited 598-node/8366-row snapshot is not an accepted producer input: full SHA
source evidence, relationship attestations, normalized mappings and live activity
are missing. The 19 zero-row leaves remain blocked pending reviewed evidence.
No exemption or delivery-state change was invented to make that fixture pass.

### Frozen-scan qualification boundary

`frozen_activity_probe.qualify` accepts the same `scanned` list passed by
`build.py` to `load_all`, with full frozen heads and registry source provenance.
It must not receive a separately rediscovered or hand-expanded repository list.
Request count is hard-bounded locally; before repository access it reserves a
conservative 10-point admission estimate for the exact scalar-only GraphQL query.
Unexpected query shape/cost fails qualification. The estimate is not a universal
GitHub cost guarantee: [GitHub's cost formula can change](https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api),
and concurrent token consumers can reduce remaining points. One bootstrap
rate-limit query is required before repository access. The elapsed setting is an
admission/receipt deadline, not cancellation of an already-running 30-second HTTP
call. REST requests are count-bounded but their separate core-rate budget is not
measured by this qualifier. Any denial, malformed response, or insufficient
headroom stops the run without a partial successful receipt or alternate route.
