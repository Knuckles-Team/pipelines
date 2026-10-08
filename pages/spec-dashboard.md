# Spec delivery dashboard (v1)

The shared Pages workflow can append a static dashboard without changing the existing
MkDocs build, readiness checks, publishing environment, or access settings.
It uses Python's standard library; no browser credentials, backend, framework, or CDN.

Copy this repository-owned configuration (for example `.github/spec-dashboard.json`):

```json
{"version":1,"sources":[{"glob":"specs/*/status.json","kind":"spec"}]}
```

Only canonical JSON status files are supported in v1. `_template` is always excluded.
Explicit source paths are also accepted. Missing status metadata is unknown. No state
is inferred from prose, checkbox counts, source commits, or PR counts. An empty match
is displayed as no documented records, not successful delivery.

In the existing Pages reusable-workflow call, add:

```yaml
with:
  spec_dashboard_enabled: true
  spec_dashboard_config: .github/spec-dashboard.json
```

Keep the existing content-source/theme/readiness inputs. Fleet caller workflows use
`Knuckles-Team/pipelines/.github/workflows/pages_pipeline.yml@main`, as required by
the repository policy. The reusable workflow checks out its scripts and theme at the
resolved immutable `job.workflow_sha`; record that SHA in delivery evidence.
Rebuild on every main push (remove restrictive path filters) so source/status changes
are reflected. Link `spec-delivery/` from your existing documentation landing page.
For inline workflows run the following after existing build/readiness/privacy gates,
using the policy-approved pipeline checkout and existing read-only GitHub token:

```sh
python .pipeline-contract/scripts/spec_dashboard.py --root . \
  --config .github/spec-dashboard.json --output site/spec-delivery \
  --repository Knuckles-Team/REPOSITORY
```

Outputs: `site/spec-delivery/index.html` and `snapshot.json` (version 1), with UTC
`captured_at`, repository, exact source revision, records, GitHub collections, and
explicit history availability. The snapshot allowlists public status fields and GitHub
number/title/link/created/updated timestamps. It never includes issue bodies, evidence
descriptions, remaining-work prose, credentials, or arbitrary source fields.

Each status file produces one whole-spec row. Nested `requirements` and declared
`requirement_ids` produce separate requirement rows; undeclared child state stays
unknown and never inherits the parent state. Whole-spec state never derives from
requirement slices. `SPECIFIED` means documented; `BUILDING` means in progress;
`BUILT` is distinct from `LANDED`. Done requires explicit `LANDED` or `CLOSED` plus
`ACCEPTED`. Source-landed and done never establish release/deployment.

Current status charts and remaining-count bars include unknown and unaccepted work.
The dashboard opt-in fetches a bounded depth of 100 commits; other Pages builds retain
one-commit checkout depth. The generator reads at most 100 first-parent snapshots
(default), accepts `--history-limit` from 2 through 200 for an existing local checkout,
and never fetches history itself. Inline workflows may set their existing checkout's
`fetch-depth: 100`; a shallow one-commit checkout remains visibly history-unavailable.
No unbounded fetch, database, persistence service, or additional credentials are used.

The JSON `history` object includes availability/reason, shallow/truncated flags, the
configured limit, sampled commit count, per-commit points, and source-state events.
Each point has its commit and observed timestamp plus separate spec/requirement totals,
remaining, unknown, added, removed, newly source-landed, accepted-completed, and reopened
counts. SVG burndown charts show actual remaining and total scope in commit order;
velocity charts aggregate observed transitions to LANDED/CLOSED by UTC commit date.
The expandable timeline and scope table show exact state changes and counts.

Dates are commit observations, not implementation or release dates. States already
landed at the first available snapshot are baseline-unknown, not new completions.
New records already landed are scope additions, not observed completion events.
Scope removal lowers remaining scope without adding velocity. Losing accepted-done
or source-landed status is recorded as reopened work. Whole-spec status still never
inherits requirement completion. Malformed or inaccessible history is unavailable,
not a fabricated empty success. Bounded/shallow history is labeled, and no earlier
points are extrapolated. Release/deployment dates remain unavailable without explicit
release evidence; Git status transitions do not establish them.

Open issues and PRs are paginated separately at build time. A failed page makes the
entire affected collection unavailable, not empty or partial. Existing `GITHUB_TOKEN`
is used without requesting expanded permissions; a repository denying a read displays
unavailable. These snapshots are not live, and no client-side API requests are made.
