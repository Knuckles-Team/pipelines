# Release digest seam with the connector SDK

Provider: scion-sdk SCION-CONNECTOR-CONTROL-R650
Provider: scion-sdk SCION-CONNECTOR-CONTROL-R650.1.2
Consumer: pipelines PIPE-RELEASE-R019

## Wire shape

The release workflow runs `connector-release-digest WHEEL --sdist FILE` from the current `scion-sdk`, writes its stdout to `release-digests.json` and prints it in the job summary: `distribution`, `version`, `wheel_sha256`, `sdist_sha256`, `content_sha256` and `artifact_digests`, the sorted strings `sha256:<hex>` (wheel and sdist) and `content-sha256:<hex>`. The job then publishes. It posts nothing: arbora reads the same sha256 digests from the package index and records the release itself (`ARBORA-HOST-R037`). No key, signature, trust file, endpoint or credential is involved.

## Refusal codes

- `connector-release-digest` exits 2 with no output for an unreadable wheel, and the release stops before publication.

## Authoritative types

- scion-sdk `scion_sdk/certify/release_cli.py` (`main`) and `scion_sdk/manifest/release_digest.py`.
- `.github/actions/publish-python-package/action.yml` step `Compute the release digests`.

## Test vectors

- `tests/test_python_pipeline_contract.py::test_connector_release_pins_digests_before_publication_and_holds_no_key`.

## Owner rows

- Provider: scion-sdk SCION-CONNECTOR-CONTROL-R650 and SCION-CONNECTOR-CONTROL-R650.1.2.
- Consumer: pipelines PIPE-RELEASE-R019.
