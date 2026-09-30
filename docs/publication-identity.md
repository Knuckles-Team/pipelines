# Exact PyPI publication identity

`.github/actions/wheel-readiness/publication.py` supplements the existing local
wheel/readiness proof. It does not replace target-platform completeness, runtime
proof, release dependency readiness, or GitHub release asset verification.

Check out the reviewed pipelines commit at `.pipeline-contract`, with credentials
not persisted. Set `SOURCE_COMMIT` and `PIPELINES_CONTRACT_COMMIT` to the exact
checked-out commits. `GITHUB_RUN_ID` and `GITHUB_RUN_ATTEMPT` must identify the
current execution. Invoke with an isolated Python interpreter containing pip:

```sh
python -I .pipeline-contract/.github/actions/wheel-readiness/publication.py preflight \
  --directory dist --package example --version 1.0 --manifest publication.json
```

Preflight freezes the staged filenames/SHA256, package/version, source and contract
commits, run and attempt, then emits a JSON list of missing filenames. Only a real
PyPI 404 means absent. An existing version must contain an exact matching subset:
extra files, conflicting digests, malformed results and index failures stop work.
Links, directories and unrelated package/version files are rejected in staging.

Immediately before upload, invoke `missing` with the same arguments. It rechecks
staging and execution identity and returns the current missing list. Upload only
those explicit paths with Twine, without `--skip-existing`. Afterwards invoke
`postverify` with the same arguments: every staged filename and digest must appear
on PyPI. Missing files receive eight bounded propagation checks; conflicts and
index errors fail immediately. Do not modify staging between these calls.

Uploads are not atomic. A concurrent conflicting upload fails; a retry can reuse
only byte-identical existing files. Remote JSON digest equality is an additional
publication check, not proof of source provenance by itself. Callers retain their
own artifact provenance, runtime proof and required-platform policy.
