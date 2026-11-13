# Bulk delivery (bulk-delivery)

This reference recommends how to deliver many spec rows at a high rate. It extends the [spec standard](spec-standard.md): every item below delivers rows that already exist in a repository's `specs/` tree.

**Status of this document.** The only requirement on a delivery is the "Delivered means" section of the spec standard: behaviour fully implemented, wired to its production entry point, every named test level passing, bound to the row, verified by the gates. Everything about grouping, staging, item size, who delivers and in what order is a recommendation, and a team may deliver differently. Only the "Capacity hygiene" and "Disk hygiene" sections state resource rules for protecting hardware.

## Recommended: separate the stages

Writing, validation and fixing can be separate stages run by different workers.

1. Writers implement items and push branches. Writers need not wait on builds, tests or CI; a later stage reports them.
2. Validation workers build branches in batches.
3. Fixers take only red results.
4. Merges happen automatically on green.

## Writer items (recommended)

- An item is one served-method slice: every row whose caller chain enters through the same served method or handler, or one library crate's family.
- An item can hold up to about 8 rows from one spec, ordered bottom-up so the row that creates the method or type comes first.
- Slices chain: a later chunk builds on the earlier chunk's branch.
- An item is ready when the items it depends on are written (pushed), not merged. It is stacked on their unmerged branches.
- A dependency counts as done only when its re-queued remainders are written too.

## Writer practice (recommended)

- Read only the item's extracted packet: its rows, their test-spec and task lines, the caller chain and the cited contracts. Never read whole spec files.
- Format with the build tool's formatter for each crate. Do not build or test locally.
- Run both hook stages before committing, and keep each writer's hook cache private.
- Only rows implemented completely, as their text says and with their bound test, go in the `Spec:` trailer.
- Partial or unwritten rows are re-queued as new items, not dropped.
- An item blocked by an unwritten prerequisite is released with that prerequisite named. The queue holds it until the prerequisite is written.
- Never share a worktree.

## Conventions every writer follows

- A new refusal is a registered, typed error code, never a detail string.
- A new served method regenerates the generated client and contract files with the repository generator, never by hand.
- An engine knob is a typed server-config field read from the command line or the environment, bounds-checked at startup.
- Writes go through the single mutation gateway.
- Tests live in the crate that owns the code. No visibility is widened for a test.

## Validation

- One batched build covers a group of branches: the format check, the linter on exactly the crate set PR CI would select (same lint config), then the bound tests.
- Each failure is attributed to the branch that touched the file. Unattributable failures are bisected.
- A green result is recorded as a commit status on the exact head SHA it proved.
- PR CI then skips its own build and test for that SHA. The required check stays an Actions job.
- Forks and pushes to main always run in full.

## PR size

One PR per green item or per green train. A train can carry 20 to 100 rows per PR; this is a recommendation.

## Decisions

A writer never makes an open design choice. It records the question. The orchestrator decides, using industry practice and the ecosystem north star: hard cutover, typed closed contracts, reuse, layering, one store. The decision is written into the owning spec row as current-state text before the row is implemented.

## Capacity hygiene

- Size each build host's concurrent work (build slots, validation loops, CI runners) to its cores.
- Above about 1.3 times the core count, add nothing and shed load.
- A writer never consumes build capacity.
- Periodically stop orphaned or duplicate build runs, remove failed pods, and scale CI runners down only when idle.

## Disk hygiene

- Every build host runs a guard that keeps each volume below its threshold.
- The guard treats a cache as idle when no file in it changed recently, prunes the largest idle caches first, and removes stale run directories, logs, tool caches and journals.
- At the end of every wave, remove finished worktrees. Never prune shared repositories. Push local-only commits to a backup branch first, and clear per-run scratch files and per-agent caches.

## Ramp up and ramp down

All pipeline state lives in files: queue, claims, results and decisions. A session can stop at any point and the next one resumes from those files.
Keep one ramp-up script and one ramp-down script, both driven by a single private config. The config lists the hosts, slot counts, validation loops and timers.

### Ramp down (end of a session, maintenance, or a hardware change)

1. Stop spawning agents. Tell running agents to finish their current item, then commit, push and enqueue it. Anything unfinished goes to a work-in-progress branch, and its claim is released.
2. Stop restarters and watchers first, then timers, then the stages. A restarter left running brings back whatever you stop.
3. Return in-flight builds to the queue. If the queue holds a newer commit for the same item, the newer one wins.
4. Stop builds that the stopped loops left running on build hosts. Match them by their build-slot directory, not by a process-name pattern, and leave CI jobs alone.
5. Write the state into the handoff: queue depth, red results, held items, worktrees kept, and anything still running.

Optional clean, before a toolchain bump, a hardware change, or when disks are tight:
- Drop build-slot caches and the compile cache.
- Drop CI caches that no running job is writing.
- Drop per-agent tool caches. Keep the shared base the copies are made from.
- Delete session logs.
- Remove worktrees that are clean, counting untracked files, and whose head is on the remote. List dirty or unpushed worktrees in the handoff instead.
- Keep the run logs that open fixes still need.

### Ramp up

1. **Preflight.** Confirm the installed tools match their tracked source and repository hooks are installed. Confirm each build host's load is below its core count and its disks are below the guard threshold.
2. **Warm.** Prime every build slot from main with one compile of the canonical build profile, in parallel across hosts, so the first validation run needs only incremental work. Never prime the development host.
3. **Start the stages in dependency order:** compile pre-check, validation loops, landing, supervisor, periodic snapshots.
4. **Staff.** Read the status file. Spawn fixers for red results before any writers. Then add writers until validation stays about one batch ahead, re-checking load after each addition.

### Sizing on any hardware

- **Build slots per host:** the smaller of (cores ÷ jobs per build) and (memory ÷ peak memory of one build). Each build gets cores ÷ slots jobs.
- **Validation loops:** one per host, plus one for every two further slots. Keep one slot free for fixes and one-off builds.
- **Pre-check:** small hosts run the compile-only pre-check. They never run validation loops.
- **CI runners:** count them against the same core budget as the build slots.
- **Writers:** match writers to validation throughput, so that writers × rows per hour ≈ rows validated per hour. More writers only lengthen the queue.

## Throughput levers, in order

1. Item sizing
2. Dependency stacking
3. Decision latency
4. Hook latency
5. Build-slot capacity
6. PR-CI deduplication
