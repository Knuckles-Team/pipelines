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

## Explicit merge blockers

This implementation is a **draft**, not a consumer migration target:

- Maturin's existing publication bundle contains cross-platform wheels and an
  sdist. The publisher's interpreter cannot prove those target installations.
  The same guard is wired there and deliberately blocks this bundle. Before
  merge, complete target-specific proof and aggregation, or agree a separately
  reviewed rollout boundary. Do not add a bypass. This branch does not change
  any file touched by the separate PR #7 Pages receipt/parser work.
- Resolver transport restrictions currently wrap pip internal preparation and
  session interfaces. The existing host's pip 25.1.1 passed a no-network,
  no-dependency wheel dry-run. Full isolated-interpreter integration, including
  a pinned supported pip/interpreter combination and adversarial transitive
  fixtures, remains necessary before this is release-ready.
- Full test and hook validation awaits the bounded GR1080 slot. No live index
  proof, package publication, deployment, workflow rerun, or consumer migration
  has been performed.

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
