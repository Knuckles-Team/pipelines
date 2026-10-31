# [ID] — Implementation plan

Governing spec: [spec.md](spec.md). Rows: [requirements.md](requirements.md).

## Summary

[The primary requirement and the chosen technical approach, in a few sentences. Name the live caller, the existing owner and the reuse candidates found by searching the code first.]

## Technical Context

- **Language/Version**: [for example Python 3.14, or NEEDS CLARIFICATION]
- **Primary Dependencies**: [libraries and services]
- **Storage**: [store, or N/A]
- **Testing**: [test framework and the proof level the rows name]
- **Target Platform**: [runtime and operating system]
- **Project Type**: [library, service, connector, web, CLI]
- **Performance Goals**: [measurable, or N/A]
- **Constraints**: [limits that bound the design]
- **Scale/Scope**: [volumes, rows, users]

## Constitution Check

[One line per principle of `.specify/memory/constitution.md`: the principle, pass or fail, and the justification. A failure is carried to Complexity Tracking.]

## Project Structure

[The real repository paths this change adds or edits, as a tree. No invented layout; mark each path new or existing.]

## Phase 0: Research

[Each unknown from Technical Context and its resolution. Write the findings to `research.md` when any unknown exists; otherwise state "no unknowns".]

## Phase 1: Design

[Architecture, ownership, dependency direction, data flow and failure modes. Write entities to `data-model.md`, interface schemas to `contracts/` and the shortest working path to `quickstart.md`, as applicable.]

## Phase 2: Task approach

[How `tasks.md` is generated from the rows: ordering, producer first, which tasks run in parallel.]

## Complexity Tracking

[Each constitution violation, why it is needed, and the simpler alternative that was rejected. Write "none" when the check passed.]

## Build contract

[The real gate thresholds and code shapes the change must meet: the applicable complexity, duplication, type, contract, package and release gates with their exact repository commands. No scanner gaming and no duplicate implementation.]

## Production caller chain

[Trace the entrypoint through the real consumer to the owner and the persistence or effect boundary, with file and line. Name the obsolete paths to delete.]

## Cross-repo seams

[Each seam as the row ID that owns it in the other repository, or "none".]
