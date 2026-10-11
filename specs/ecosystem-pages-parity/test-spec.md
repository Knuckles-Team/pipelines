# Test contract — PIPE-PAGES

Use disposable Git fixtures with six consumer shapes and a pinned shared theme commit. Assert exact JSON fields and exit status; retain sanitized output and commit refs as release evidence.

| ID | Requirement | Test and expected result |
|---|---|---|
| P-1 | FR-1 | Six valid declarations resolve exact commits/trees without sibling workspace. |
| N-1 | FR-1 | Duplicate, absent, malformed, or mutable revision fails before comparison. |
| N-2 | FR-1 | Untracked theme overlay or dirty fetched tree fails even when tracked assets match. |
| P-2 | FR-2 | Byte-identical assets compare equal and every path/digest appears in receipt. |
| N-3 | FR-2 | One changed byte names repository/asset and prevents current-pass receipt. |
| N-4 | FR-2 | Missing content source, escaped symlink, or required asset fails closed. |
| P-3 | FR-3 | Exact-input runs yield identical verification fields; presentation carries schema/time. |
| N-5 | FR-3 | Changed revision makes prior receipt historical; cached pass is not reused. |
| P-4 | FR-4 | Promotion consumes success; unrelated code PR runs without Pages access. |
| N-6 | FR-4 | Failed parity prevents theme promotion with actionable reason. |
| P-5 | FR-5 | Consumer results link own commits; checker does not mutate consumer trees. |

Contract tests inspect `pages_pipeline.yml` for least-privilege checkout, immutable shared source, and release condition. Hosted Pages URL and browser probe are release acceptance evidence, not unit-test prerequisites. Run YAML parse, relevant pytest, and configured CCCC/jscpd/Dupehound/KISS gates on implementation. Record unavailable scanners as gaps, never as passes.
