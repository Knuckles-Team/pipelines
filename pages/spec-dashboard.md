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

Keep the existing content-source/theme/readiness inputs and immutable pipeline pin.
Rebuild on every main push (remove restrictive path filters) so source/status changes
are reflected. Link `spec-delivery/` from your existing documentation landing page.
For inline workflows run the following after existing build/readiness/privacy gates,
using the same pinned pipeline checkout and existing read-only GitHub token:

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
The first adapter deliberately reports timeline, daily velocity, historical burndown,
and release evidence as unavailable: these schemas do not contain verified transition
history. No dates or historical points are invented. Source files remain the authority;
a future history adapter must preserve actual additions, removals, and status reversals.

Open issues and PRs are paginated separately at build time. A failed page makes the
entire affected collection unavailable, not empty or partial. Existing `GITHUB_TOKEN`
is used without requesting expanded permissions; a repository denying a read displays
unavailable. These snapshots are not live, and no client-side API requests are made.
