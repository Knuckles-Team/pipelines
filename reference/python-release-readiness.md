# Python wheel release readiness

A successful code gate is not proof that a package can be installed from PyPI.
In particular, tests against pinned sibling sources may pass before those
siblings' required versions are published. Never remove or downgrade such
runtime dependencies to make a release pass.

The release action builds wheels, checks their actual metadata and dependency
closure, and rechecks their bytes immediately before upload and before creating
an associated GitHub release. It publishes those wheels without rebuilding or
`--skip-existing`. `requirements.txt` is a build prerequisite only; a missing
file is allowed, but a failing install is not ignored. The Python path now
builds/uploads wheels only: an sdist is not interchangeable with a checked wheel.

## Ownership and inputs

Repository-manager remains authoritative for manual RELEASE readiness, fleet
scope, and dependency-wave ordering. Its current checker queries declared
fleet version ranges and can honor configured private indexes. Reusing that
verdict as built-wheel proof would omit transitive requirements, interpreter
compatibility, and the final metadata. This action therefore checks **all
runtime dependencies**, including fleet and third-party packages, without a
fleet-name allowlist or an optional sibling checker. There is no empty/missing
fleet scope that can turn this action into a successful no-op. Missing scripts,
missing proof, malformed metadata, resolver failures, and index errors block.

`runtime-profiles` is an optional JSON array of additional runtime extras,
defaulting to `[]`. The exact wheel's metadata always selects `base` plus each
of its declared `mcp`, `agent`, and `all` extras. Explicit inputs are additive;
`["base"]` cannot omit a declared standard runtime profile. Existing full lists
remain valid. Unknown/malformed profile inputs and duplicate input aliases fail. Other advertised
runtime extras must still be explicitly supplied. Test/development extras are
not inferred. Each selected profile installs in a separate fresh environment.
Verification recomputes the profile set from those same digest-bound wheel bytes.

Raw wheel `Provides-Extra` declarations are checked before normalization.
For Core Metadata 2.3+, names must already be normalized and unique. For older
metadata, valid name aliases (including repeated punctuation) and canonical
collisions are accepted with a warning and compared as one canonical name;
invalid names still fail. This reader compatibility does not excuse a modern
producer writing invalid declarations. See the [Core Metadata specification](https://packaging.python.org/en/latest/specifications/core-metadata/#provides-extra-multiple-use).

## Central hook and caller wiring

The pipelines hook catalogue owns `dependency-readiness` and its `[manual]`
stage. Consumers keep an immutable `rev` and hook ID, without copying an entry,
stage, or release policy paragraph. Link this document from consumer guidance.
The hook invokes `repository_manager.release_readiness_hook` in an already
prepared interpreter. Missing RM, empty/invalid fleet scope, index errors and
overridden verdicts block locally as well as in CI. It never downloads a checker.
Prepare RM in the hook environment using an explicitly pinned
`additional_dependencies` entry, or supply `args: [--python, /prepared/python]`
for an existing RM environment. That runtime reference is operator wiring, not
an alternate policy source. An older RM lacking the strict entry point blocks.

RM's existing `scripts/sweep_dependency_readiness_hook.py` owns reconciliation.
Review its dry-run diff and all actual publisher paths before applying: package
publishers must use immutable guarded workflows, and downstream runtime image
publishing must depend on successful guarded package publication. The updater
preserves custom entries for manual review. It does not audit arbitrary workflow
scripts or claim that changing a hook makes a release ready.

Necessary local references are the shared workflow SHA, the hook repository SHA,
and any prepared RM runtime reference. Only nonstandard runtime extras need a
profile input. Pinned consumers still require deliberate reference updates when
the shared interface changes; centralization does not make immutable pins float.

The guard runs only during publication, never in ordinary push/pre-push code
gates. This is the narrow network exception documented in AGENTS.md, consistent
with repository-manager's manual RELEASE migration at
`0be91491a809e50c719cf4c729114f638c5a2b64`.

## Evidence and isolation

`release-readiness.json` records source and pipeline commits, wheel SHA-256,
interpreter/platform, explicit profiles, public-index identity, and pip reports
containing resolved dependency versions, artifact URLs/hashes, and marker
context. The receipt is preserved as a workflow artifact. Verification rejects
changed wheel sets, bytes, profiles, scope, source identity, or interpreter.
Existing before/after source-verification actions remain in place.

The resolver uses an isolated Python interpreter and disposable stdlib venv,
`--ignore-installed`, `--only-binary=:all:`, and no package cache. Its working
and home directories are outside the consumer checkout. Caller pip/uv config,
indexes, constraints, source overrides, proxies, and Python import settings are
not passed through. Global pip configuration is disabled with the null config
file. The root wheel is the only permitted local candidate. Direct URLs,
editable candidates, source distributions, unknown transitive extras, and
non-public artifacts are rejected. Transport accepts only HTTPS PyPI and
files.pythonhosted.org URLs and does not follow redirects. Resolution installs the wheels but does not execute package build backends or
import runtime packages. No interpreter is restarted in a populated venv, so
installed .pth files are not evaluated.

The receipt is workflow evidence, not a signature or an independent attestation
against a malicious runner or build step. The guard does not establish runtime
behavior, API correctness, future index availability, or publication of upstream
versions. Existing quality, tests, security, and source-provenance checks remain
necessary. There is a small verification-to-upload interval; this prototype does
not provide filesystem-level immutability against concurrent hostile mutation.

## Validation boundaries

Offline tests exercise the pinned resolver against synthetic index responses,
profile closures, poisoned configuration, exact artifact and source identity,
and target interpreter contracts. Fresh disposable environments validate a
synthetic wheel and dependency-free source backend. These are not receipts for
real consumer artifacts or native target execution.

A publisher must obtain genuine execution evidence for each required target.
An aarch64 wheel cross-built on x86_64 cannot use its host's runtime receipt.
The guard fails closed when native target proof is absent; this interface change
does not deploy target infrastructure or relax that requirement. Source tests
against pinned siblings likewise do not prove public-index availability.

## Safe consumer migration after the guard is ready

1. Merge the central interface after code checks and independent review pass.
   Native runtime receipts and public-index availability remain publication
   requirements; source validation cannot substitute for them.
2. Pin each consumer workflow to the full immutable guard commit, recording its
   release version beside the pin. Standard runtime profiles derive from the
   exact wheel; declare only additional advertised runtime extras.
3. Move only the repository-manager `dependency-readiness` hook to `manual`
   RELEASE use. Keep every actual code, test, security, and quality gate intact.
   Use the RM updater for recognized legacy entries after reviewing its diff;
   custom entries require explicit review. Inherit the shared manual stage.
4. Verify the consumer's configuration and workflow contracts offline using
   exact pinned sibling sources where needed. Real publication stays blocked
   until the declared versions exist publicly. In particular, agent-utilities
   2.5.0's `epistemic-graph>=2.27` constraint must remain unchanged.
5. Review and merge each migration independently. Do not trigger publication or
   workflow reruns as part of migration validation.
