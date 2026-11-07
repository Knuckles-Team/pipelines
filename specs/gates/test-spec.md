# Test contract — PIPE-GATES

The tests live under `tests/hooks/` and run the published gate entry points, never a reimplementation.

| Test ID | Requirement | Level | Setup and input | Expected observation |
|---|---|---|---|---|
| T-001 | PIPE-GATES-R001 | Contract | The published gate configuration declaring all eight blocking gates. | The fast set is exactly `format`, `hygiene`, `secrets`, `types`, `tests-fast`. The full set is exactly the remaining three. The sets are disjoint and their union is the eight blocking gates. |
| T-002 | PIPE-GATES-R002 | Unit | A recorded product failure, no fix-forward task, and a re-run that passes or fails. | The decision is auto-revert. The record carries the gate ID, the changeset ID, the verdict, the failure class, the threshold, and the evidence digest. |
| T-003 | PIPE-GATES-R002 | Unit | A product failure with a fix-forward task inside 300 s, and an infrastructure failure whose re-run passes. | The decision is fix-forward in the first case and `infrastructure-rerun` in the second. Both records are complete and replayable. |
| T-004 | PIPE-GATES-R003 | Integration | One blocking gate on an engine-tree fixture and on an identical materialized checkout. | Both runs produce the same verdict and the same evidence digest. The tree run creates no checkout. |

## Negative and boundary cases

T-001 also fails a configuration missing one blocking gate or declaring a ninth. T-002 covers a task opened after the 300 s window, which auto-reverts, and an unavailable re-run, which auto-reverts and records the unavailability. T-003 covers a task opened at the window boundary, which auto-reverts, and an infrastructure failure whose re-run fails, which auto-reverts. An unknown failure class is refused. T-004 covers an empty prefix and a tree revision with no checkout available at all.

## Quality and release proof

Run `uv run --frozen python -m pytest -q` and the pre-commit and pre-push hook stages on the implementation. Record the revision, each command, and the pass or fail. A test in this repository is not served acceptance for the engine-side tree reads.

## Gate verdicts published to the engine

| Row | Proving test |
|---|---|
| `PIPE-GATES-R004` | See each child. |
| `PIPE-GATES-R004.1` | `tests/test_verdict_publish.py::test_gate_run_posts_one_verdict` |
| `PIPE-GATES-R004.2` | `tests/test_verdict_publish.py::test_fast_set_publishes_and_survives_endpoint_error` |
## Migration waves and the product-name check (R005, R006)

| Test ID | Requirement | Level | Setup and input | Expected observation |
|---|---|---|---|---|
| T-R006.1 | PIPE-GATES-R006.1 | Unit | A fixture migration ledger | `tests/hooks/test_migration_waves.py::test_wave_1_entry_and_exit` evaluates a fixture ledger and asserts each criterion. |
| T-R006.2 | PIPE-GATES-R006.2 | Unit | A fixture migration ledger | `test_wave_2_entry_and_exit` asserts the size bound and the per-repository exit. |
| T-R006.3 | PIPE-GATES-R006.3 | Unit | A fixture migration ledger | `test_wave_3_entry_and_exit` asserts the criteria. |
| T-R006.4 | PIPE-GATES-R006.4 | Unit | A fixture migration ledger | `test_wave_4_entry_and_exit` asserts the criteria. |
| T-R006.5 | PIPE-GATES-R006.5 | Unit | A fixture migration ledger | `test_wave_5_entry_and_exit` asserts the criteria. |
| T-R006.6 | PIPE-GATES-R006.6 | Unit | A fixture migration ledger | `test_wave_6_entry_and_exit` asserts the criteria. |
| T-R006.7 | PIPE-GATES-R006.7 | Unit | A fixture migration ledger | `test_wave_7_entry_and_exit` asserts the criteria and the two restores. |
| T-R005 | PIPE-GATES-R005 | Contract | Fixture spec trees with named products, identifiers and allowances | `tests/test_spec_third_party_names.py` asserts a finding for each named product, a pass for identifiers, code, links and standards, and the per-repository allowance. |

## Legacy concept migration (PIPE-GATES-R007)

`tests/hooks/test_no_legacy_concepts.py` runs the registered CLI and a subprocess entry point. Positive and adversarial fixtures assert the original regex across Python/Rust/Markdown, exact historical exclusions, tracked versus ignored/untracked input, and relative line diagnostics. Foreign worktrees with polluted repository and index selectors must still inspect the requested tree. Deleted files are absent source; unreadable files and unavailable repositories fail closed. `tests/hooks/test_catalogue.py` binds the same CLI to the published hook and manual self-run configuration. This optional migration invariant does not change the eight-gate landing partition.

## Metadata and static import checks (PIPE-GATES-R008, PIPE-GATES-R009)

`tests/hooks/test_lockfile_version_mirrors.py` exercises the registered CLI on
optional artifacts, literal and editable self entries, dynamic version fallback,
and accepted or drifting direct pins and ranges. It rejects a package-directory
root instead of silently inspecting its parent.

`tests/hooks/test_coupling.py` exercises consumer-declared module prefixes through
the registered CLI. Client imports pass; runtime and sibling UI imports fail with
path and line diagnostics, including in former adapter files. Malformed source,
missing policy and untracked-only packages refuse. Ambient Git selectors cannot
replace the target's index; untracked generated files are outside the scan.
These checks prove static AST behavior, not dynamic runtime isolation.

## Connector fleet name (PIPE-GATES-R010)

`tests/hooks/test_connector_name.py` builds a fixture connector in a temporary directory. It checks agreement, a disagreeing literal in `connector_sources.py` and in a call, a leftover manifest that is ignored, the undeclared warning, `--strict` and a non-connector repository.

## Connector GraphQL declaration (PIPE-GATES-R012)

`tests/hooks/test_connector_graphql.py` builds fixture repositories in a temporary directory. It checks the declared extra, the default warning and `--strict` failure, direct declarations, function-level imports, skipped tests and exempt repositories.
## Scion SDK capability conformance (PIPE-GATES-R013)

`tests/hooks/test_sdk_conformance.py` builds fixture repositories in a temporary directory. It checks each pattern and the row it cites, clean Scion SDK use, one finding per pinned package, the skipped paths, non-connector and Scion SDK repositories, the default warning and `--strict` failure.

## Connector surface audit (PIPE-GATES-R014)

`tests/hooks/test_connector_surface.py` builds fixture connectors, a fixture core ontology and a two-repository fleet in a temporary directory.

| Row | Test |
|---|---|
| `PIPE-GATES-R014.1` | `tests/hooks/test_connector_surface.py::test_complete_connector_has_no_gaps` |
| `PIPE-GATES-R014.2` | `tests/hooks/test_connector_surface.py::test_action_routed_tools_and_action_dispatch_are_gaps`, `tests/hooks/test_connector_surface.py::test_no_tools_and_no_resources_are_gaps` |
| `PIPE-GATES-R014.3` | `tests/hooks/test_connector_surface.py::test_prompts_must_be_complete_agent_definitions`, `tests/hooks/test_connector_surface.py::test_a_connector_needs_an_operator_prompt`, `tests/hooks/test_connector_surface.py::test_every_business_role_needs_a_business_role_prompt` |
| `PIPE-GATES-R014.4` | `tests/hooks/test_connector_surface.py::test_orphans_and_imports_of_core_are_ontology_gaps`, `tests/hooks/test_connector_surface.py::test_without_parent_files_the_core_namespace_is_the_parent` |
| `PIPE-GATES-R014.5` | `tests/hooks/test_connector_surface.py::test_missing_contract_parts_are_gaps`, `tests/hooks/test_connector_surface.py::test_no_declarations_lists_every_missing_part_and_tool` |
| `PIPE-GATES-R014.6` | `tests/hooks/test_connector_surface.py::test_unlinked_prompt_skill_and_tool_are_link_gaps`, `tests/hooks/test_connector_surface.py::test_a_contributor_skill_needs_no_link`, `tests/hooks/test_connector_surface.py::test_contracts_declared_as_turtle_count` |
| `PIPE-GATES-R014.7` | `tests/hooks/test_connector_surface.py::test_incomplete_data_location_is_a_gap` |
| `PIPE-GATES-R014.8` | `tests/hooks/test_connector_surface.py::test_connector_standard_runs_the_surface_member` |
| `PIPE-GATES-R014.9` | `tests/hooks/test_connector_surface.py::test_fleet_census_reads_refs_without_touching_worktrees` |
| `PIPE-GATES-R014.10` | `tests/hooks/test_connector_surface.py::test_the_published_standard_names_every_checked_part` |
| `PIPE-GATES-R014.11` | `tests/hooks/test_connector_surface.py::test_the_surface_member_checks_the_served_tool_list`, `tests/hooks/test_connector_surface.py::test_a_server_that_does_not_build_is_unavailable_not_empty` |

## Hook cache and symlink snapshots (PIPE-GATES-R011)

`tests/hooks/test_jscpd_snapshot.py` commits a package manifest and a root symlink to it. The snapshot keeps the target and skips the link.

## Connector ontology orphan mapping (PIPE-GATES-R015)

`tests/hooks/test_ontology_orphan_map.py` builds a fixture parent ontology and connector ontologies in a temporary directory. It checks the exact, head-noun and synonym signals, the generic-class rule, a synonym entry that names a parent class the ontology lacks, the new-parent candidate, the override check, the `apply` output and its idempotence, and deterministic output.

## Ontology graph check (PIPE-GATES-R016)

`tests/hooks/test_ontology_graph_check.py` builds small fixture ontologies, a `connector_sources.py` declaration. It checks that every finding code fires, the parse error file, the orphan chain length, the dangling file and line, the island pack, the mapping and ingest checks, the conflicts, the competency question hops, the owner grouping of the fix plan, determinism, the exit codes with `--warn`, and the command against a temporary git repository.

The module-graph tests (PIPE-GATES-R016.1 to R016.3) cover an import-only module, an individuals-only module and the fixture-directory path rule.

The ontology codemod (`connector-ontology-map fix`, PIPE-GATES-R016.6 to R016.9) is tested on fixture packs in `tests/hooks/test_ontology_codemod.py`: one test per rule family, idempotence, input-order independence, the projected finding counts, the dry-run command, Medulla `skos:altLabel` matching with a shared alias sent to review, the override table, prefix-preserving rewrites with a `schema.org` fixture, and the refusal to write a file that does not re-parse. The manifest-cut codemod (`connector-ontology-map migrate`, PIPE-GATES-R016.10 to R016.16) is tested on a fixture connector in `tests/hooks/test_connector_migrate.py`: one test per transform, idempotence and determinism, and the review contract. R016.4 and R016.5 are in `tests/hooks/test_ontology_graph_check.py`.

## Planning mechanisms

| Test ID | Requirement | Level | Setup and input | Expected observation |
|---|---|---|---|---|
| T-028 | PIPE-GATES-R028 | Unit | A touched spec whose `plan.md` lacks template sections, and an untouched one. | Fails for the touched spec, advisory for the untouched one. |
| T-029 | PIPE-GATES-R029 | Unit | A spec with a row lacking a task or a test, an orphan label and an open marker in `plan.md`. | Each is a finding; failing only when the change adds the row or touches the file. |
| T-030 | PIPE-GATES-R030 | Unit | A checklist with an unchecked item, and one fully checked. | The first is a finding; the second is clean. |
| T-031 | PIPE-GATES-R031 | Unit | The constitution, and a copy with a missing plan check or a cited path that does not exist. | The constitution is clean; each defect is a finding. |
| T-032 | PIPE-GATES-R032 | Unit | A constitution whose limits table or hook list differs from the configs, and a hook ID the catalogue lacks. | `--check` exits 1 and writes nothing; the render fails on the unknown ID. |
| T-033 | PIPE-GATES-R033 | Unit | The repository template and the organization constitution version. | The template names the same version and links the organization file. |

## Graph automation mechanisms

| Test ID | Requirement | Level | Setup and input | Expected observation |
|---|---|---|---|---|
| T-034 | PIPE-GATES-R004.3 | Unit | Fixture inputs named by the row. | `tests/hooks/test_states_publish.py::test_row_and_task_states_publish_with_the_verdict` passes and shows the observation the row states. |
| T-035 | PIPE-GATES-R004.4 | Unit | Fixture inputs named by the row. | `tests/hooks/test_states_publish.py::test_status_main_publishes_and_skips_without_endpoint` passes and shows the observation the row states. |
| T-036 | PIPE-GATES-R004.5 | Unit | Fixture inputs named by the row. | `tests/hooks/test_states_agree.py::test_mismatch_names_each_row_and_side` passes and shows the observation the row states. |
| T-037 | PIPE-GATES-R004.6 | Served L3 | Fixture inputs named by the row. | `tests/hooks/test_states_publish_served.py::test_spec_hook_publishes_states_through_arbora_to_the_engine` passes and shows the observation the row states. |
| T-038 | PIPE-GATES-R034.1 | Unit | Fixture inputs named by the row. | `tests/hooks/test_contract_coverage.py::test_contract_without_a_required_line_or_section_is_a_finding` passes and shows the observation the row states. |
| T-039 | PIPE-GATES-R034.2 | Unit | Fixture inputs named by the row. | `tests/hooks/test_contract_coverage.py::test_uncovered_citation_fails_for_touched_spec_and_warns_for_untouched` passes and shows the observation the row states. |
| T-040 | PIPE-GATES-R034.3 | Unit | Fixture inputs named by the row. | `tests/hooks/test_contract_coverage.py::test_spec_group_runs_contract_coverage` passes and shows the observation the row states. |
| T-041 | PIPE-GATES-R034.4 | Unit | Fixture inputs named by the row. | `tests/hooks/test_contract_coverage.py::test_dangling_and_duplicate_contracts_are_findings` passes and shows the observation the row states. |
| T-042 | PIPE-GATES-R034.5 | Served L3 | Fixture inputs named by the row. | `tests/hooks/test_contract_coverage_served.py::test_hook_refuses_uncovered_seam_and_engine_reads_the_covered_one` passes and shows the observation the row states. |
| T-043 | PIPE-GATES-R035 | Unit | The repository tree, and a tree with `specs/_template/`. | The seven templates exist; the directory is a finding. |
| T-044 | PIPE-GATES-R036 | Unit | An empty repository, then the sync script, then a drifted copy. | Check fails, write succeeds, check passes, drift fails without writing. |
| T-045 | PIPE-GATES-R037 | Unit | A copy with a missing, a changed and an unknown template. | Each is a finding; the check is a published hook and the wheel declares the package. |
| T-046 | PIPE-GATES-R038 | Unit | Upper-case, underscore and allowlisted names under `specs/`. | Only the non-allowlisted names are findings; untouched ones are advisory. |
| T-047 | PIPE-GATES-R039 | Unit | A numeric-prefixed directory and a misplaced plan, template and constitution. | Each is a finding. |
| T-048 | PIPE-GATES-R040 | Unit | The constitution. | Article XXII is traced and the version is at least 1.1.0. |
| T-049 | PIPE-GATES-R041 | Unit | A plan with a seam, with and without a contract document. | The missing or incomplete document is a finding. |
| T-050 | PIPE-GATES-R042 | Unit | A row naming new classes and tables, with and without `data-model.md`. | The missing file is a finding. |
| T-051 | PIPE-GATES-R043 | Unit | A `served` row, with and without `quickstart.md`. | The missing file is a finding; a quoted word is not. |
| T-052 | PIPE-GATES-R044 | Unit | A plan with and without unknowns, and a spec without a checklist. | Each mismatch is a finding that fails per touch. |
| T-053 | PIPE-GATES-R045 | Unit | Rows with and without a caller chain, a Shape sentence, a test and with TBD. | Each gap is a finding that fails only for an added row. |
| T-054 | PIPE-GATES-R046 | Unit | A conforming plan and one plan per failure type: heading, order, empty section, placeholder, unknown ID, broken link. | Each failure prints path:line: message and exits 1; the conforming plan exits 0. |
| T-054.1 | PIPE-GATES-R046.1 | Unit | A foreign ID in any section with a fixture index; an unknown foreign ID; no index with a foreign ID; no foreign ID and no index. | Resolvable passes; unknown prints `unknown ID <ID> (owner <repo>)`, exit 1; missing index exits 2 CANNOT RUN; no foreign ID runs clean. |
| T-055 | PIPE-GATES-R016.116.1 | Unit | Every workflow and template, and `reference/ci-standard.md`. | No file calls a merge or an auto-merge request. The CI standard states owner-only merge for platform pull requests. | |
| T-056 | PIPE-GATES-R016.116.2 | Unit | Every workflow and template, and `scripts/apply_repo_ci_settings.sh`. | No gate job has an actor or author condition. The ruleset holds no bypass actor. | |
| T-057 | PIPE-GATES-R047 | Unit | The job script run with each marker, a clean title and body, and the caller aggregate. | A marker in the title or body exits 1; clean text exits 0; the caller `CI required` needs `gates`. | |
| T-058 | PIPE-GATES-R048 | Unit | Fake API responses for good, old-check, extra-check and archived repositories. | The audit lists each drift, skips archived and excluded repositories, exits 1 and only reads. | `tests/test_ruleset_audit.py` |

## Reusable workflow gates and coverage refusal (PIPE-GATES-R017 to R021, R049)

| Test ID | Requirement | Level | Setup and input | Expected observation |
|---|---|---|---|---|
| T-059 | PIPE-GATES-R017 | Integration | A manifest with one entry that selects no test and one entry whose test fails. | Both entries exit non-zero; the empty entry reports `ZERO_SELECTED_TESTS`; every selected name reaches the job summary. |
| T-060 | PIPE-GATES-R018 | Unit | One spec text that repeats a worker policy value outside a citing row and one that cites the owning rows. | The first text fails and names the value; the second passes. |
| T-061 | PIPE-GATES-R019 | Integration | A fixture graph-loaded workflow, then the same output with one changed byte. | The matching readback passes; the tampered output fails on the digest. |
| T-062 | PIPE-GATES-R020 | Integration | A manifest with a failing entry and an entry with an unreviewed difference, then a clean manifest. | The first two exit non-zero; the clean manifest passes. |
| T-063 | PIPE-GATES-R021 | Integration | A fixture crate with a compile error, one with a clippy warning and a clean crate. | The first two fail; the clean crate passes. |
| T-064 | PIPE-GATES-R049.1 | Unit | An evidence file with percent, revision and tool, and one without a tool. | The first parses; the second is refused. |
| T-065 | PIPE-GATES-R049.2 | Unit | Baseline 80.00 with candidates 79.99, 80.00 and 80.01. | 79.99 exits 1 and names both values; the other two exit 0. |
| T-066 | PIPE-GATES-R049.3 | Unit | The `GATES` table and `.pre-commit-hooks.yaml`. | `coverage-decrease` is a published hook that resolves to its module. |
| T-067 | PIPE-GATES-R049.4 | Unit | No baseline, no candidate, and a baseline revision that is not an ancestor. | The first two exit 2 with `CANNOT RUN`; the third exits 1. |
| T-068 | PIPE-GATES-R049.5 | Unit | The same proposal twice. | Both runs print the same bytes with both revisions and both percentages. |
| T-069 | PIPE-GATES-R049.6 | Integration | A fixture repository whose candidate revision lowers coverage, run through `pipelines_hooks.cli.main`. | Exit 1 and the output names both percentages. |
| T-070 | PIPE-GATES-R060 | Unit | Workflow files with masked and honest test and cleanup steps. | A masked test or check step exits 1 and names the step. Honest steps and masked cleanup exit 0. |
| T-071 | PIPE-GATES-R061 | Unit | The real specs tree, and a temporary tree with a new directory. | The real tree has no unmapped directory. A new directory is listed and exits 1. |
| T-072 | PIPE-GATES-R062 | Unit | Fake API responses for held and unheld pull requests, armed and unarmed. | An armed held pull request is listed. The audit exits 1 and writes nothing. |
| T-073 | PIPE-GATES-R063 | Unit | The job script run with a head ref that has a merged pull request and with a new one. | The reused branch exits 1 and names the earlier pull request. A new branch exits 0. |
| T-074 | PIPE-GATES-R064 | Unit | A fixture workspace manifest and the workflow definition. | Each unit has one job with `--all-features` and `-p`. One failing unit fails the aggregate. |
| T-075 | PIPE-GATES-R065 | Unit | A fixture repository whose test command collects nothing, and one that collects a test. | Zero suites exits 1 and names the command. One suite exits 0. |
| T-076 | PIPE-GATES-R066 | Contract | The hook catalogue and the tests directory. | Every hook has a planted-violation test, or the missing hook ids are listed and the test fails. |
| T-077 | PIPE-GATES-R067 | Unit | A diff that renames a serialized variant, with and without a golden file change. | A stale golden file exits 1 and names the rename. A recomputed file exits 0. |
| T-078 | PIPE-GATES-R068 | Unit | The constitution file and the template. | The link, the article, the version and the template version all hold. |
| T-079 | PIPE-GATES-R070 | Unit | A fixture repository with a toolchain file, a slot definition whose cache sits inside the checkout, and one on a network mount. | The matching definition exits 0. The in-checkout cache and the network mount each exit 1 and name the path. A toolchain mismatch names the pin. |
| T-080 | PIPE-GATES-R071 | Unit | One configuration fixture rendered for each runtime. | Each runtime output names the same image, slot count, cache root and budget. The Kubernetes output has minimum runners 0 and a local volume per node. A missing field exits 1 and names it. |
| T-081 | PIPE-GATES-R072 | Unit | A fake runtime adapter with two slots, one held. | Status lists both slots with the held lock, sizes, free disk and toolchains. Up primes both at the head commit and fails naming a slot with too little disk. |
| T-082 | PIPE-GATES-R073 | Unit | A fake runtime adapter with one held slot and a second host that fails an install. | Down without force exits 1 naming the slot. Forced down marks all disabled and empties the caches. Upgrade installs on each host and names the failing host. |
| T-083 | PIPE-GATES-R074 | Unit | Workflow fixtures with fork routing and a release secret on a warm-slot job, and a target directory over its budget. | The violating workflows exit 1 naming the job. A compliant workflow exits 0. The over-budget target shrinks below the budget. |
| T-084 | PIPE-GATES-R075 | Unit | Recorded timing fixtures just under and just over each limit. | Under-limit timings exit 0. Each over-limit timing exits 1 and names the measurement. |

## Gates moved from the repository governance spec (PIPE-GATES-R076 to R084)

Each row names its served test in `requirements.md`. The rows marked planned add the test beside the existing hook tests.

| Test ID | Requirement | Level | Setup and input | Expected observation |
|---|---|---|---|---|
| T-085 | PIPE-GATES-R076 | Integration | The fixture named in the row's test. | The gate verdict and exit code match the row. |
| T-086 | PIPE-GATES-R077 | Integration | The fixture named in the row's test. | The gate verdict and exit code match the row. |
| T-087 | PIPE-GATES-R078 | Integration | The fixture named in the row's test. | The gate verdict and exit code match the row. |
| T-088 | PIPE-GATES-R079 | Integration | The fixture named in the row's test. | The gate verdict and exit code match the row. |
| T-089 | PIPE-GATES-R080 | Integration | The fixture named in the row's test. | The gate verdict and exit code match the row. |
| T-090 | PIPE-GATES-R081 | Integration | The fixture named in the row's test. | The gate verdict and exit code match the row. |
| T-091 | PIPE-GATES-R082 | Integration | The fixture named in the row's test. | The gate verdict and exit code match the row. |
| T-092 | PIPE-GATES-R083 | Integration | The fixture named in the row's test. | The gate verdict and exit code match the row. |
| T-093 | PIPE-GATES-R084 | Integration | The fixture named in the row's test. | The gate verdict and exit code match the row. |

## Explicit state machines (PIPE-GATES-R085 to R086)

| Test ID | Requirement | Level | Setup and input | Expected observation |
|---|---|---|---|---|
| T-094 | PIPE-GATES-R085 | Unit | The organization constitution and the vended template. | Article XXXI states each rule, carries one plan check, and both files name version 1.8.0 or later. |
| T-095 | PIPE-GATES-R086 | Integration | The fixture corpora, Rust and Python: two assigners, a string compare, lifecycle flags, a machine without refusal tests, and a compliant machine. | Each violating fixture exits 1 naming file, line, type, code and rule; the compliant fixture exits 0. |
| T-096 | PIPE-GATES-R086.1 | Unit | Hand-built `Machine` records, one per rule and one compliant. | Each rule yields its code; the compliant record yields none. |
| T-097 | PIPE-GATES-R086.2 | Unit | Python source snippets for each declared form and each assignment form. | The reader builds the expected `Machine` fields. |
| T-098 | PIPE-GATES-R086.3 | Unit | Rust source snippets for each declared form and each assignment form. | The reader builds the expected `Machine` fields; a parse error exits 2. |
| T-099 | PIPE-GATES-R086.4 | Unit | A declared machine and test files with and without a test for each edge. | A missing edge or refusal test yields a finding that names it. |
| T-100 | PIPE-GATES-R086.5 | Integration | A git index with staged and unstaged fixture files, and the hook file. | Staged mode reports only touched types; census reports the whole tree; exit codes are 0, 1 and 2. |
| T-101 | PIPE-GATES-R086.6 | Unit | A pack with a state class that extends the core class, and one that does not. | The unrolled class is reported with `SM-ONTOLOGY-NOT-CORE-ROLLED`; the rolled class passes. |
| T-103 | PIPE-GATES-R087 | Unit | The organization constitution. | Articles XI and XXV carry each principle phrase. |
| T-102 | PIPE-GATES-R088 | Integration | A git repository fixture with a layers policy and imports that go downward, upward, into a private module, from an unlayered unit and around a cycle. | The downward import passes; each other case exits 1 naming file, line and rule. |
| T-104 | PIPE-GATES-R089 | Integration | A fixture environment repository with a thin wrapper, a behaviour-encoding script and a data file. | Only the behaviour-encoding script exits 1, naming the file. |
| T-105 | PIPE-GATES-R090 | Unit | The spec standard file. | The section names all seven design answers and the analysis finding. |
