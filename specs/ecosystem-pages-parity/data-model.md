# PIPE-PAGES — Data model

The records below are the types this spec adds or extends. Each is a frozen record or a strict Pydantic model. Files named `new` do not exist on the default branch. The row that defines each type is in `requirements.md`.

## Pages parity and receipt

- Consumer declaration `{repository, revision, content_source, shared_theme_enabled}` with an optional site URL. Read by `load` in `scripts/pages_fleet_declaration.py`. Revisions are full commit IDs.
- Verification result per consumer: repository, commit, tree, status, reason and one entry per shared asset with expected and actual digests. Built by `verify` in `scripts/pages_fleet_parity.py`.
- Receipt: schema version, fleet input digest, pipeline commit, results and generation time. Built by `receipt` in `scripts/pages_fleet_receipt.py`. A receipt is historical when a referenced revision changes.

## Hook records

- `DocClaim` (file, line, kind, text) in `pipelines_hooks/docs/claims.py` with kind one of `path`, `command`, `gate`, `count`, `diagram-node`.
- `LocatedFinding` in `pipelines_hooks/docs/claims.py`: repository-relative path, line, rule and source digest.
- `ChangelogPolicy`, `ReleaseSection` and `ChangelogFinding` in new `pipelines_hooks/docs/changelog.py`.
- `RuntimeEnvContract`, `EnvUse` and `LauncherEnvBinding` in new `pipelines_hooks/docs/env_documentation.py`.
- `ProjectConfigInventory` and `TemplateReceipt` in new `pipelines_hooks/hygiene/config_inventory.py`.
- `ValidationReport` in new `pipelines_hooks/core/validation_report.py`, nesting repository snapshot, category, executed identity and stable rule records.
- `ToolDocMapping` in new `pipelines_hooks/docs/tool_mapping.py`; `GuideMigrationManifest` in new `pipelines_hooks/docs/guide_migration.py`; `DeploymentDocMatrix` in new `pipelines_hooks/docs/deployment_docs.py`.
- `ReadmeHeaderContract` in new `pipelines_hooks/docs/readme_header.py`; `ThemeImageContract` in new `pipelines_hooks/docs/image_theme.py`.
- `TestQualityFinding`, `OutcomeContract`, `OutcomeProof`, `CoverageClosurePolicy` and `UnitProfile` in new `pipelines_hooks/code/test_quality.py`.
- `CodeQualityPolicy` and `AnalyzerInvocation` in new `pipelines_hooks/code/lint_type.py`; `AnalyzerHealthPolicy`, `HealthSummary`, `SkillDependencyAudit` and `SolutionSizeEvidence` in new `pipelines_hooks/code/repository_validation.py`.
- `MutationPolicy` and `SurvivingMutation` in new `pipelines_hooks/code/mutation_gaps.py`.
- `SkillGradePolicy` and `SkillGradeReport` in `pipelines_hooks/docs/skill_grade.py`, extended with an external rule-pack inventory.
- `UserStory`, `AcceptanceCriteria` and `Task` in new `pipelines_hooks/specs/artifacts.py`.
- `RoleContract`, `RoleBinding` and `RoleProof` in `pipelines_hooks/release/packaging_roles.py`.
- `PathPortabilityPolicy`, `PathViolation` and `PathReport` in `pipelines_hooks/hygiene/path_portability.py`.
- `PromptDiskDocument` and `PromptDifference` in `pipelines_hooks/prompt_format.py`.
- `ProjectEvidence` and `LayoutReport` in `pipelines_hooks/ci_replica/test_layout.py`.

## Canopy

- `RowDrawer` in `scripts/architecture_explorer/details.py`: excerpts, tasks, checklist items, evidence links and exact file paths for one row.
- `SddPhase` in `scripts/architecture_explorer/sdd.py`: six ordered phases of a spec family.
- `ExportRow` and `ViewSpec` in new `scripts/architecture_explorer/export.py`: one agent-export row per spec row and the saved view description.
- Family card `{t, p, k, d, w}` built by `family_card` in `scripts/architecture_explorer/sdd.py`: title, phase, `[done, open]` tasks, document bits and warnings.
