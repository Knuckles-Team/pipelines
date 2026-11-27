# Release digest seam with the connector SDK

Provider: scion-sdk SCION-CONNECTOR-CONTROL-R650
Provider: scion-sdk SCION-CONNECTOR-CONTROL-R650.1.2
Consumer: pipelines PIPE-RELEASE-R019

## Wire shape

The release workflow runs `connector-release-digest WHEEL --sdist FILE` from the current `scion-sdk` and writes its stdout to `release-digests.json`: `distribution`, `version`, `wheel_sha256`, `sdist_sha256`, `content_sha256` and `artifact_digests`, the sorted strings `sha256:<hex>` (wheel and sdist) and `content-sha256:<hex>`. After publication `scripts/release_record.py` merges those `artifact_digests` with the sha256 of the built files into the `release.record` request (`repo`, `version`, `git_ref`, `changeset_head`, `published_at`, `artifact_digests`). The runner requires its wheel's `content-sha256:` string in the sealed record. No key, signature or trust file is involved.

## Refusal codes

- `connector-release-digest` exits 2 with no output for an unreadable wheel, and the release stops before publication.
- `scripts/release_record.py` exits 1 for a connector release with no `release-record-url`.
- The runner side refuses with `RELEASE_DIGEST_UNREPORTED`, `RELEASE_EVIDENCE_INVALID`, `RELEASE_PIN_UNAVAILABLE`, `RELEASE_PIN_MISSING` or `RELEASE_DIGEST_MISMATCH`.

## Authoritative types

- scion-sdk `scion_sdk/certify/release_cli.py` (`main`) and `scion_sdk/manifest/release_digest.py`.
- `.github/actions/publish-python-package/action.yml` step `Compute the release digests` and `scripts/release_record.py` `build_record`.

## Test vectors

- `tests/test_python_pipeline_contract.py::test_connector_release_pins_digests_before_publication_and_holds_no_key`.
- `tests/test_release_record_step.py::test_connector_record_carries_the_content_digest_and_must_be_recorded`.

## Owner rows

- Provider: scion-sdk SCION-CONNECTOR-CONTROL-R650 and SCION-CONNECTOR-CONTROL-R650.1.2.
- Consumer: pipelines PIPE-RELEASE-R019.
