# Delivery practice (delivery-practice)

This reference states how agents, lanes and people execute a change. It covers waiting, branches, merges, worktrees, verification and automation. The [constitution](../.specify/memory/constitution.md) holds the articles. The [spec standard](spec-standard.md) holds how specs are written. This file holds the working rules that sit between them. The `spec-kit` and delivery skills link here and do not copy it.

## Waiting and polling

1. **Never end a turn while work is pending.** A run, a hook, a push or a build that is still going is pending work. A turn that ends while it runs never resumes, and the work is lost. Wait inside one blocking command that polls until the run finishes or a stated timeout passes.
2. **Push after every green step.** A local commit is not delivered. Push as soon as the fast checks pass, so a lost session loses nothing.
3. **Poll the real status.** A poll reads the status of the run itself. It never reads a cached or summarized state.
4. **Check the automation first on resume.** Before new work, confirm that the automation which arms merges and collects finished runs is running. Confirm that its queue of finished runs is not growing.

*Why*: a lane that ended its turn "waiting for the results" stalled for hours, and its commits stayed local.

## Branches

1. **One branch per change.** Each change starts on a new branch from the current default branch.
2. **Never reuse a merged branch.** After a squash merge, the old branch no longer shares history with the default branch. A second change on it conflicts with its own earlier commits. Start the next change on a new branch from the default branch.
3. **Rebase onto the default branch before the push**, and again when the default branch moves while the pull request waits.
4. **A commit is atomic.** Split a change that touches several concerns into commits that each pass the fast checks.

*Why*: fifteen pull requests conflicted with their own earlier squash commits because lanes reused the merged branch.

## Merge order and the hold

1. **A pair whose order matters is held.** When pull request B is only correct after pull request A merges, both carry the `hold` label until the owner releases them in order.
2. **Automation honors the hold.** Automation that arms merges must skip a held pull request and must not arm it. A held pull request that is already armed is disarmed.
3. **Create the label through the API and read it back.** A silent failure to create the label leaves the pair unprotected, so confirm that the label exists.
4. **Arm auto-merge only where `main` requires a status check**, as the constitution article on merges states. Verify the result with the pull request's `autoMergeRequest` field.
5. **Never put a CI-skip marker in a title, body or commit.**

*Why*: a stale loop re-armed a held pair twice, and either order would have broken the consumer.

## Automation scripts

A running script is not reloaded when its file changes. The shell reads the file as it executes, so an edit can corrupt the live loop or leave the old logic running. Stop the script, edit it, and start it again. Verify the new behavior on a pull request that must not merge.

## Worktrees, stashes and shared state

A shared checkout keeps some state in a common directory that every linked worktree sees. These rules protect that state.

1. **One linked worktree per change.** Create it from the default branch with a new branch name.
2. **Never stash.** A stash is one stack for all worktrees. A pop in one worktree can restore the uncommitted work of another. To compare with the default branch, use `git diff <base> -- <path>`, `git show <base>:<path>` or a throwaway detached worktree.
3. **Never prune a shared checkout.** `git worktree prune` and `git gc --prune` remove the records of worktrees whose paths are not visible from the current host. Remove only your own worktree, by path, from the host that created it.
4. **Never use a tool that rewrites the shared repository configuration to isolate a session.** Use a real `git worktree add`.
5. **Stage explicit paths.** Review `git status` and the complete diff first. Never stage a whole tree.
6. **Remove your worktree when the pull request lands.** A leftover worktree is a defect.
7. **Never trace secrets.** Keep shell tracing away from any command that reads a credential.

## Verification

1. **Step exit honesty.** A test or check step exits with the tool's real status. It never masks a failure with `; true`, `|| true`, `|| exit 0` or an ignored-failure flag. A run that discovers zero test suites is a failure, not a pass.
2. **Verify the way CI verifies.** Use the feature set that CI uses, such as `--all-features`. In a multi-unit workspace, build and test each unit alone with `-p <unit>`, in addition to the unified build. A unit that builds only when its neighbors enable features is broken.
3. **Test-only behavior moves with a feature.** Code that behaves differently under the language's test-only compile flag changes behavior when its tests move to another unit, because that flag applies only to the unit under test. After you split code across units, move that behavior behind a named `test-support` feature, and enable it from the dependent unit's tests.
4. **Measure the merged tree.** A question about a merge result is answered on the materialized merge, never on a branch tip. The tip of an unsynced branch always lacks newer fixes, and that is not a revert.
5. **A mechanical merge needs a parse.** After a mechanical conflict resolution, parse or compile every touched file and every manifest before the push. A resolution that interleaves two sibling items leaves files that do not parse.
6. **A rename of a serialized name is a wire change.** Recompute every digest, golden vector and receipt that covers the renamed name in the same commit, and run the tests against the final tree.
7. **A release gate runs on a published tool.** A hook that installs its tool from the package index passes only when the index holds the version with the code.
8. **Prove reachability.** Before a row is called delivered, search for a production importer or registration outside the new code and its tests.
9. **Wire a control at the chokepoint.** Put an authorization, validation or lifecycle control in the function that every caller reaches. A test enters through each entry point.
10. **Fix a flake, do not retry it.** A run that failed and then passed is a defect to fix. Re-run only an infrastructure failure, and say so in the report.

## Registries keyed on spec directories

A page, explorer or index that maps by spec directory name must change in the same pull request that adds, renames or removes a spec directory. A new family without a node fails the page build after the merge, which blocks every later change to the page.

## Reporting

A lane report states counts and links, the checks that ran, and any check that did not. It never reports a result it did not observe.
