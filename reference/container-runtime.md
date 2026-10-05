# Container runtime publication

`container_pipeline.yml` retains its default `docker/Dockerfile`, local `.`
context, agent/mcp matrix, tags, registry login and three build attempts.
Callers without runtime inputs download no runtime artifact and pass no additional
build arguments. Missing legacy agent/mcp stages remain clean no-ops.

## Selecting one image

Set `build_target: default` to build the Dockerfile's final stage once, including
single-stage recipes. A named `build_target` builds that stage once and fails if
it is absent. Explicit `mcp` selection retains the mcp leg's existing suffixes
and tags; other explicit targets use the agent leg's unsuffixed tags. The other
leg skips the build. Runtime staging requires explicit
selection so one profile cannot accidentally feed both images. Separate callers
can publish separate profiles.

## Opt-in inputs

| Input | Required value for runtime staging |
| --- | --- |
| `dockerfile` | The caller's offline runtime recipe, for example `docker/graphos-unified.Dockerfile`. |
| `build_context` | Existing caller-relative local directory, default `.`. |
| `build_target` | `default` or one named Dockerfile stage. |
| `runtime_artifact_id` | One immutable numeric artifact ID produced earlier in the same workflow run. |
| `runtime_profile` | `graphos` or `connector/<normalized-distribution>`. |
| `source_revision` | Full lowercase caller commit SHA equal to `github.sha`, checkout HEAD and the frozen caller source. |
| `graph_os_revision` | Full frozen `graph-os` SHA when present in the profile; otherwise empty. Required for `graphos`. |
| `runtime_lock_sha256` | Expected SHA256 of `requirements.lock`, obtained from the qualified producer. |
| `source_freeze_sha256` | Expected SHA256 of `source-freeze.json`, obtained from the qualified producer. |

The caller must depend on its successful producer job and pass the producer's
artifact ID and digests through job outputs. Pin the reusable workflow to its
reviewed immutable commit. Preserve the caller's publication approval and checks.
These inputs do not provision a producer or imply that any current artifact has
passed qualification. A missing producer or digest blocks adoption.

The artifact contains exactly `requirements.lock`, `source-freeze.json`, and
the manifest's selected `wheels/*.whl` and `eg-wheel/*.whl`. It has no enclosing
directory. Upload the context directory as one artifact and retain the immutable
upload ID. Artifact names, patterns, cross-run downloads and arbitrary URLs are
not accepted. The workflow needs no additional token or permission.

## Producer and manifest contract

The source freeze uses schema `graphos-runtime-wheel-inputs/1`:

- `profile` contains `name`, the exact target `{python: "3.14", implementation:
  "cpython", os: "linux", arch: "x86_64"}`, `first_party`, and
  `explicit_third_party_roots`.
- Every first-party entry contains `distribution`, `version`, `repository`,
  `source_sha`, `extras`, and `pyproject_sha256`.
- `requirements_lock` contains `path: requirements.lock` and its `sha256`.
- Each `artifacts` entry contains `distribution`, `version`, relative `path`,
  `sha256`, `source`, and `payload_manifest_sha256`. First-party `source` contains
  `repository`, `source_sha`, and `receipt_sha256`; third-party `source` is null.
- `resolver_receipt_sha256` and `verification_receipt_sha256` bind the producer's
  resolution and static verification evidence. All SHA256 fields are full,
  nonzero lowercase digests. Source revisions are full lowercase commit SHAs.

The producer resolves the complete target-specific closure from actual wheel
metadata with every requested extra. It qualifies wheel RECORD/payloads, Python
and platform compatibility, collisions, native EG CPU/ABI/store requirements,
and the enabled product features. It retains the evidence behind the receipt
digests. The publication caller supplies the approved freeze digest through its
trusted producer dependency; a digest from an unqualified upload is insufficient.

Staging validates those bindings and bytes; it does not recreate or assert the
producer's qualification. It performs no package imports, dependency resolution,
native builds, index requests, or runtime acceptance tests.

The lock must be fully selected for this target: one requirement per selected
wheel, with matching SHA256 hashes, no remaining markers, directives, editable
paths, VCS URLs or remote references. Comments and backslash continuations are
accepted. All first-party entries use
`distribution[extras] @ file:///opt/graphos-runtime/wheels/<basename>`;
`epistemic-graph` uses `eg-wheel` instead. Extras must equal the frozen selection.
Third-party entries may use an equivalent local wheel reference or an exact
`distribution==version` pin. Every declared wheel must appear in the lock.
Connector profiles must select the caller distribution's `mcp` extra and have
their own complete closure; the GraphOS lock is not interchangeable.

## Staging and recipe responsibilities

Before checking out the reusable workflow, the publisher rejects an existing
`.pipeline-contract` file, directory or symlink, including dangling symlinks.
It never lets the checkout action clean or replace caller content at that path.
The action loads its helper from the reusable workflow's own pinned checkout,
checks both checkout revisions, and validates the request before downloading.
It hashes the freeze, lock and every wheel; rejects missing, duplicate or extra
files, source/profile mismatches and symlinks; then verifies a copied candidate
before placing it at `<build_context>/build-artifacts/runtime`. It refuses an
existing destination. It never overlays caller files or trusts a downloader's
digest warning as acceptance.

After verification, every build attempt receives `SOURCE_REVISION`,
`RUNTIME_LOCK_SHA256`, `SOURCE_FREEZE_SHA256`, and `GRAPH_OS_REVISION` when the
profile includes GraphOS. These values come from the validated caller inputs;
they are not inferred from tags or substituted index packages.

The selected Dockerfile must copy `build-artifacts/runtime/` to
`/opt/graphos-runtime/`, verify its digests and install with offline, no-index,
no-build and require-hashes options. Keep that path in the Docker build context
and out of `.dockerignore` exclusions. Existing recipe preflights, feature checks
and caller release gates still apply. This workflow change alone does not
publish a complete GraphOS runtime.
