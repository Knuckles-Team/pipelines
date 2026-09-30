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
venv. This proves bootstrap, not the runtime resolver integration suite.

Maturin producer jobs now request native target receipts. The publisher requires
exactly the existing four target identities and one sdist receipt; it validates
source/contract identity, target interpreter and marker context, artifact bytes,
profiles, runtime closure, and exact bundle membership. The sdist producer code
safely extracts the exact archive, installs public build prerequisites, rebuilds
one Linux CPython wheel, and runs the same runtime-profile proof on it. Rebuilt
wheel bytes are separate evidence and are not uploaded as another release wheel.

The focused offline suite has 62 passing tests, including all four synthetic
target contexts, missing/substituted target receipts, duplicate wheel ownership,
changed bytes, wrong markers/profiles/source commits, changed resolver versions,
source-archive traversal and symlink rejection, and source-wheel substitution.
These synthetic contexts are **not native target execution evidence**.

The implementation remains a **draft**, not a consumer migration target. Exact
remaining acceptance tests and their blocking category follow:

| Acceptance test | Status / category |
| --- | --- |
| Actual pinned resolver installs a no-dependency wheel in a fresh profile venv and emits re-verifiable evidence | Pending integration implementation and execution |
| Public-index fixture supplies transitive requirements and base/mcp/agent/all profiles; actual pip resolves the correct closure | Pending integration implementation and execution |
| Actual resolver rejects unavailable versions, transitive conflicts, unknown extras, direct/local/editable dependencies, redirects and non-public transport | Pending adversarial integration implementation and execution |
| Poisoned pip/uv/project config, environment indexes/proxies, constraints, sources and installed packages cannot affect actual resolver results | Synthetic environment checks pass; actual integration pending |
| Missing/mismatched pinned resolver, unavailable index, malformed metadata, and absent checker produce no success receipt | Synthetic checks partly cover this; actual subprocess failures pending |
| Actual native macOS arm64 and Windows x86_64 receipts match built-wheel interpreter/ABI and all runtime profiles | Native target validation unavailable on this host; workflow interpreter selection still needs review |
| Actual native Linux aarch64 receipt for the existing cross-built wheel | **Architecture blocker**, not compute wait: the pinned action uses an x86_64 cross container and exposes no post-build hook. No host-side or invented cross-resolution proof is accepted |
| Exact sdist rebuild binds archive bytes, public build-prerequisite report, rebuilt runtime metadata and final publication bundle | Archive safety and synthetic aggregation pass; pure-Python backend integration and stricter prerequisite-report validation remain code work. No native ecosystem source build has been run |
| Workflow contracts enforce every producer proof, required target set, aggregation and reverification before every publication/release | Existing ordering tests pass; new producer/source-path negative contracts remain code work |
| Full test suite plus commit/manual hook suites at final head, with no weakened checks | Not run; request a new bounded slot only when implementation is ready |
| Final independent parent review, passing CI, immutable consumer pin | Blocked by the preceding items; keep PR draft |

The existing aarch64 runner/container choice must not be silently changed to
remove that blocker. This branch changes no runner, container image, security
setting, or consumer. It does not touch files from PR #7's separate Pages work.

The exclusive validation slot was released after bootstrap and focused checks;
no full suite or native ecosystem build remains running. No publication,
deployment, workflow rerun, or credential change has occurred.

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
