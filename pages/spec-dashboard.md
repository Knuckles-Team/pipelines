# Spec delivery dashboard (v1)

The shared Pages workflow adds a static dashboard to the site. It does not change
the MkDocs build, the readiness checks, the publish environment or the access settings.
The generator uses only the Python standard library. The page has no browser
credentials, backend, framework, CDN or script.

## Configuration

Put this configuration in the repository, for example in `.github/spec-dashboard.json`:

```json
{"version":1,"sources":[{"glob":"specs/*/status.json","kind":"spec"}]}
```

Version 1 reads only canonical JSON status files. The generator always excludes `_template`.
Explicit source paths are also valid. Missing status data is unknown. The generator does
not infer a state from prose, checkbox counts, source commits or PR counts. An empty
match shows "No documented records". It does not show a successful delivery.

In the existing call to the Pages reusable workflow, add these inputs:

```yaml
with:
  spec_dashboard_enabled: true
  spec_dashboard_config: .github/spec-dashboard.json
```

Keep the existing content-source, theme and readiness inputs. Fleet caller workflows use
`Knuckles-Team/pipelines/.github/workflows/pages_pipeline.yml@main`, as the repository
policy requires. The reusable workflow checks out its scripts and theme at the resolved,
immutable `job.workflow_sha`. Record that SHA in the delivery evidence.
Rebuild on every push to main, and remove restrictive path filters. Then each status
change shows on the page. Link `spec-delivery/` from the documentation landing page.

An inline workflow runs this command after the build, readiness and privacy gates.
Use the policy-approved pipeline checkout and the existing read-only GitHub token:

```sh
python .pipeline-contract/scripts/spec_dashboard.py --root . \
  --config .github/spec-dashboard.json --output site/spec-delivery \
  --repository Knuckles-Team/REPOSITORY
```

## Outputs

The command writes `site/spec-delivery/index.html` and `snapshot.json` (version 1).
The snapshot holds the UTC `captured_at` time, the repository and the exact source revision.
It also holds the records, the GitHub collections and the history availability.
The snapshot keeps only public status fields. From GitHub, it keeps only the number,
title, link, and created and updated times. It never holds issue bodies, evidence
descriptions, remaining-work prose, credentials or other source fields.

## Page layout

The page is one engineering drawing sheet. A double frame has zone markers.
Columns 1 to 8 are on the top and bottom. Rows A to D are on the sides. Each panel has a letter tab,
a title and a monospace caption.

| Panel | Content |
|-------|---------|
| A | Delivery structure: a tree of the repository, its specs and the requirement count of each spec. It also shows the records that are not done. |
| B | Delivery states: one limit bar for each state, with a tick scale. The scale end is the total of that record kind. |
| C | State definitions: one line for each `delivery_state`, with a ✓ or ✕ mark and a word. |
| D | Specifications: one row for each spec, with requirement, landed and done counts. |
| E | Observed delivery history: burndown and velocity charts for specs and requirements. |
| F | Timeline: the first observed commit, the dates with the most landed requirements, and the capture date. |
| G | Open issues and pull requests at capture time. |
| H | Observed changes: the scope table and the state-change table for each commit. |
| J | Record inventory: every spec and requirement record, with links to the source. |

A title block is at the bottom right. It shows the repository, the commit and the capture time.
It also shows the snapshot link, the source pattern and the sheet number.
A mark always has a glyph and a word. The meaning never depends on colour alone.
Dark mode follows `prefers-color-scheme`. At phone width, the panels stack in one column.
The frame stays, and the page does not scroll horizontally.

## Record rules

Each status file gives one whole-spec row. Nested `requirements` and declared
`requirement_ids` give separate requirement rows. A child without a declared state
stays unknown. It never takes the state of its parent. The whole-spec state never comes
from the requirement slices. `SPECIFIED` means documented. `BUILDING` means in progress.
`BUILT` is different from `LANDED`. Done needs `LANDED` or `CLOSED`, and `ACCEPTED`.
Source-landed and done do not show a release or a deployment.

## History

The current status bars and the remaining counts include unknown and unaccepted work.
The dashboard opt-in fetches 100 commits. Other Pages builds keep a checkout depth of one commit.
The generator reads 100 first-parent snapshots or fewer (the default).
For a local checkout, `--history-limit` accepts a value from 2 to 200.
The generator never fetches history itself. An inline workflow can set `fetch-depth: 100` on its checkout.
A shallow checkout of one commit shows that history is not available.
The generator uses no unbounded fetch, database, persistence service or extra credentials.

The JSON `history` object holds the availability and the reason, and the shallow and truncated flags.
It also holds the configured limit, the sampled commit count, the points and the source-state events.
Each point has its commit and observation time. It has separate spec and requirement counts:
total, remaining, unknown, added, removed, newly source-landed, accepted-completed and reopened.
The burndown charts show the remaining count and the total scope in commit order.
The velocity charts add the observed changes to `LANDED` or `CLOSED` for each UTC commit date.
The tables in panel H show the exact state changes and counts.

Dates are commit observations. They are not build or release dates. A state that is
already landed at the first snapshot has no known earlier change. It is not a new
completion. A new record that is already landed adds scope. It is not an observed completion.
Removed scope lowers the remaining count. It does not add velocity. When a record loses
accepted-done or source-landed status, the page records it as reopened work.
The whole-spec status never takes requirement completion. Malformed or unreadable history
shows as not available. It never shows as an empty success. The page labels a bounded
or shallow history, and it does not extrapolate earlier points. Release and deployment
dates stay unavailable without explicit release evidence. Git status changes do not give them.

## GitHub snapshot

The build reads open issues and PRs one page at a time, as separate collections.
If one page fails, the full collection shows as not available. It never shows as empty or partial.
The build uses the existing `GITHUB_TOKEN` and asks for no extra permissions.
If a repository refuses a read, the collection shows as not available.
The snapshot is not live, and the page makes no API requests.
