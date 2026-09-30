# Python wheel release readiness (draft)

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

`runtime-profiles` is a required JSON array. `base` is mandatory; other entries
must be actual wheel extras. When the wheel declares `mcp`, `agent`, or `all`,
each must be included. Test/development extras are not inferred as advertised
runtime profiles. Other advertised profiles must be explicitly supplied by the
consumer. Each profile installs independently in its own fresh environment.

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

## Draft implementation and acceptance status

The resolver is now pinned to pip 25.1.1, including the exact public wheel
SHA-256 in `resolver-pin.json`. Its bootstrap was exercised on CPython 3.13.15:
the reviewed wheel was downloaded, verified, and installed into a fresh checker
venv. Fresh-profile integration subsequently installed the exact synthetic wheel
in four separate profile venvs, reverified their reports, and rebuilt the same
wheel through a dependency-free backend in a fifth fresh build venv.

Maturin producer jobs now request native target receipts. The publisher requires
exactly the existing four target identities and one sdist receipt; it validates
source/contract identity, target interpreter and marker context, artifact bytes,
profiles, runtime closure, and exact bundle membership. The sdist producer code
safely extracts the exact archive, installs public build prerequisites, rebuilds
one Linux CPython wheel, and runs the same runtime-profile proof on it. Rebuilt
wheel bytes are separate evidence and are not uploaded as another release wheel.

The focused offline suite has 116 passing tests. It exercises the actual pinned
pip resolver with in-memory HTTP responses and no socket fallback, including
base/mcp/agent/all closure, unavailable versions, transitive conflicts, direct
sources, redirects, index errors, poisoned configuration, and preinstalled
packages. A small synthetic wheel installation verifies that package startup
files are not executed. A dependency-free Python backend exercises source-wheel
rebuilding without any native ecosystem build.

Source validation and aggregation require one root PKG-INFO with unique valid
identity fields matching both the archive filename and rebuilt wheel. Invalid
upload identity fails before any rebuild. Maturin selects CPython 3.13 explicitly
inside Linux build containers and uses setup-python 3.13 on macOS/Windows,
aligning producer selection with the checker without changing package Python
requirements or ABI3 features.

Source evidence now binds public build prerequisites to the exact archive's
build-system requirements and rechecks their transitive closure. Runtime metadata
includes normalized Requires-Python, so source/release range differences cannot
be hidden by a shared compatible interpreter. Requested extras and explicit
profiles use canonical case/hyphen/underscore/dot names; duplicate aliases fail.
Windows file URLs use the pinned pip decoder, with alternate-root and UNC
rejection tested under emulated Windows path semantics.

These tests use synthetic target contexts; they are **not native execution
receipts**. The implementation remains a draft and is not a consumer migration
target. Remaining acceptance work is explicit:

| Acceptance test | Status / category |
| --- | --- |
| Actual pinned resolver and adverse public-index responses | Focused offline integration passes; no live upstream availability claim |
| Fresh profile venv creation, exact pinned resolver seeding, installation and receipt reverification as one end-to-end operation | Passed on CPython 3.13.15 with the exact hash-pinned pip wheel and four disposable profile venvs |
| Source extraction, prerequisite closure, rebuild and source/release metadata binding | Focused synthetic and dependency-free backend tests pass; no native ecosystem build performed |
| Native target interpreter/ABI, missing proof and wrong-platform rejection | Offline contracts pass; genuine target execution remains required at publication time |
| Windows exact root file URL and canonical extras | Focused regressions pass; Windows filesystem semantics are emulated on Linux |
| Every producer, aggregation and pre-publication/release verification path | Focused workflow contracts pass; full configured suite remains pending |
| Full test suite and commit/manual hook suites at final head | Running against the final tree after test census refactoring and merging current main |
| Independent parent review, passing CI and immutable consumer pin | Pending; keep PR draft |

The existing aarch64 producer cross-builds on x86_64. Its host cannot supply a
native aarch64 runtime receipt, so publication deliberately remains blocked.
This is a consumer publication requirement, not a reason to invent target proof
or redesign infrastructure merely to test the guard. This branch changes no
runner, image, security setting, or consumer. It does not overlap PR #7's Pages
work. Full local validation uses a bounded exclusive slot. No publication, deployment, workflow rerun, credential change, or
native ecosystem build has occurred.

## Safe consumer migration after the guard is ready

1. Merge the reviewed guard only after its blockers are resolved and checks pass.
2. Pin each consumer workflow to the full immutable guard commit, recording its
   release version beside the pin. Declare `runtime-profiles` explicitly, for
   example `'["base", "mcp", "agent", "all"]'` when all are advertised.
3. Move only the repository-manager `dependency-readiness` hook to `manual`
   RELEASE use. Keep every actual code, test, security, and quality gate intact.
   Correct existing stale hook entries; do not rely on the current sweep to
   replace them automatically.
4. Verify the consumer's configuration and workflow contracts offline using
   exact pinned sibling sources where needed. Real publication stays blocked
   until the declared versions exist publicly. In particular, agent-utilities
   2.5.0's `epistemic-graph>=2.27` constraint must remain unchanged.
5. Review and merge each migration independently. Do not trigger publication or
   workflow reruns as part of migration validation.
