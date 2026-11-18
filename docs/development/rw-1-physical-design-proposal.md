# RW-1 — Physical World-Memory and EvidenceLink Design Proposal

**Status:** physical design accepted under D132 on 2026-11-16; RW-1 implementation merged by PR #128; formal Operator acceptance pending
**Parent milestone:** RW-0 documentation closeout, squash-merged PR [#126](https://github.com/abtn/Watch-Architecture-Rev2/pull/126)
**Design authority:** RW-D131/RW-D132; ADR-0007, ADR-0009, ADR-0011, ADR-0014, ADR-0020, ADR-0021
**Implementation authority:** RW-1's bounded schema/ORM/migration/test implementation was explicitly authorized on 2026-11-16 after D132 acceptance. This authority is limited to the scope and proof obligations in this proposal and the implementation plan; it does not authorize RW-2–RW-5, R7-C, provider changes, persistent-database access, or scored execution.

## 1. Purpose

RW-1 creates the durable relational foundation for the world-memory reasoning loop:

Signal → Thread → competing Hypotheses → EvidenceLinks → ConfidenceChanges.

It must preserve one canonical EvidenceLink model, existing Evaluation evidence, same-Team boundaries, immutable Snapshot provenance, and the existing Task/Kernel commit architecture.

RW-1 is a schema-and-contract slice. It does not implement triage, human or model update workers, decay, retrieval, rendering, Artifacts, or Consultations. Those belong to later slices or remain explicitly staged.

## 2. Source baseline and observed gap

The design is based on the RW-0 squash merge, `cac63a01380624bbaf0c9965a363a352e46960d7`, and a source/schema audit of the RW-1 planning branch at `a8c6b489cfa9dba05ae143474d7a86399b4382a6`.

Static source inspection confirms:

- `core/models.py` contains no ORM models for Thread, Hypothesis, or ConfidenceChange.
- The existing `evidence_links` table is real and Evaluation-scoped. It has `subject_kind`, `subject_id`, `source_kind`, `outcome_id`, `signal_id`, `team_id`, Snapshot reference/hash, quote/offsets, stance, reference key, and created timestamp.
- Its subject constraint permits only `evaluation`; its source constraint permits only `signal` or `outcome`.
- The Evaluation subject and Outcome source have composite Team foreign keys. Signal has a direct foreign key, but is not itself Team-owned.
- `core/evaluations.py` is the existing application validation path for Evaluation evidence. It must remain valid and must not be replaced by a parallel evidence service.
- `EvaluationService.propose()` creates the Evaluation with `created_by_task_id=task.id`, flushes it, creates its EvidenceLinks, and records `evaluation_proposed` in one database transaction. This establishes a source-supported originating-Task value for Evaluation evidence links.
- `core/task_runtime.py` and `core/experience_distiller.py` both query EvidenceLinks using `subject_kind='evaluation'` and the Evaluation ID. Both are compatibility-sensitive consumers that must be updated without changing their Evaluation behavior.
- Migration `0012_learning_foundation.py` created the existing EvidenceLink table. A disposable PostgreSQL database successfully migrated to `0018_r7b_lifecycle_review_date`; its Evaluation-only subject FK, Outcome same-Team FK, Signal FK, source/stance/Snapshot/quote checks, and reference-key uniqueness were inspected.
- ADR-0007 defines subjects `hypothesis | evaluation`, sources `signal | outcome | artifact`, and stances `supports | challenges | mentions`. ADR-0020 adds `consultation` as a source. Only `supports` and `challenges` may anchor a ConfidenceChange.

This audit verifies source paths and the migrated schema on an empty disposable PostgreSQL database. It does not inspect the user's persistent database or prove the integrity, quantity, or provenance of its historical rows. Those rows must be validated by the forward migration before any old representation is removed.

## 3. RW-1 scope boundary

### Included

1. Thread persistence and Team ownership.
2. Hypothesis persistence and Thread/Team ownership.
3. ConfidenceChange persistence and exactly-one-cause representation.
4. Reconciliation of the existing EvidenceLink table/model so one model can represent both accepted subject kinds while preserving Evaluation evidence.
5. The currently usable EvidenceLink sources: Signal and Outcome.
6. ORM and repository/service contracts required by later commit slices, without implementing those workers.
7. Forward migration, explicit downgrade/data-preservation behavior, and schema-level proof plan.

### Explicitly deferred

- SignalDisposition and triage. Add them with RW-4 unless the Operator explicitly moves that scope.
- `operator_update` and `update_thread` commit services/workers (RW-2/RW-3).
- Confidence decay execution (RW-5).
- Artifact and Consultation entities or source rows. Their accepted EvidenceLink vocabulary is retained, but they are not usable references until their canonical entities and validation paths exist.
- Thread summaries, embeddings, vector indexes, and retrieval projections. They are non-authoritative projections under INV-11; introduce them with the retrieval slice when model identity, refresh, and Context requirements are specified.
- Persistent production Artifacts, rendering, publishing, distribution, and delivery, excluded by RW-D100.
- Any second runtime, scheduler, dispatcher, authentication stack, or direct model-to-database path.

## 4. Proposed relational representation

The following is the recommended starting design for review. Names are proposed physical names, not accepted schema. Exact column types, nullability, constraint names, index expressions, and migration ordering must be finalized before implementation authorization.

### 4.1 `threads`

| Column | Proposed role |
|---|---|
| `id` | UUID primary key |
| `team_id` | Non-null FK to Team; ownership boundary |
| `domain` | Non-empty domain identifier |
| `title` | Non-empty human-readable subject |
| `status` | `active | dormant | resolved` |
| `created_at` | UTC-aware creation timestamp |
| `last_updated_at` | UTC-aware last canonical update timestamp |

Constraints/indexes:
- Unique `(id, team_id)` to support composite same-Team references.
- Check the status vocabulary and non-empty required text.
- Index by `(team_id, status, last_updated_at)`; add a domain filter only if an actual query requires it.
- No cascade delete of a Thread with Hypotheses or history.

### 4.2 `hypotheses`

| Column | Proposed role |
|---|---|
| `id` | UUID primary key |
| `team_id` | Non-null, denormalized ownership key used for composite constraints |
| `thread_id` | Non-null FK to `threads(id, team_id)` |
| `statement` | Non-empty proposition |
| `status` | `active | superseded | rejected` |
| `confidence` | `low | moderate | high` |
| `created_at` | UTC-aware creation timestamp |
| `last_touched_at` | UTC-aware timestamp updated only by accepted evidence |

Constraints/indexes:
- Composite FK `(thread_id, team_id) → threads(id, team_id)`.
- Unique `(id, team_id)` for same-Team EvidenceLink and ConfidenceChange references.
- Check status and confidence vocabularies and non-empty statement.
- Index `(team_id, thread_id, status)` for Thread hypothesis loading.
- Index `(team_id, status, last_touched_at)` for later decay selection.
- No physical delete path. Rejection and supersession are explicit state transitions with reason and a Task-attributed Event, as required by INV-07.

The current architecture does not require a dedicated `superseded_by_hypothesis_id` column or a separate transition table. The RW-1 recommendation is to use one Task-attributed Event as the canonical historical supersession record, with an event type such as `hypothesis_superseded` and payload fields for the superseded Hypothesis ID, successor Hypothesis ID, and non-empty reason. Append it through the existing Task/Kernel application path; the Event's Task supplies Team and actor attribution. This proposal does not claim database-enforced Event immutability: the source audit verified the Event model's Task attribution, not a database-level prohibition on Event updates or deletion. Any stronger immutability guarantee must be established by an existing or explicitly approved application/database mechanism before it is claimed. Do not add a second successor relation unless a concrete invariant or query cannot be enforced through the canonical Event and Hypothesis status. The commit service must validate that both Hypotheses belong to the same Team and that the successor is not the superseded Hypothesis.

### 4.3 `confidence_changes`

| Column | Proposed role |
|---|---|
| `id` | UUID primary key |
| `team_id` | Non-null ownership key |
| `hypothesis_id` | Non-null same-Team Hypothesis FK |
| `from_confidence` | Previous ordinal band |
| `to_confidence` | New ordinal band |
| `cause_kind` | `evidence | decay` |
| `evidence_link_id` | Nullable same-Team EvidenceLink FK |
| `created_by_task_id` | Task responsible for the change |
| `idempotency_key` | Stable per-Task operation key |
| `created_at` | UTC-aware timestamp |

Constraints/indexes:
- Composite FK `(hypothesis_id, team_id) → hypotheses(id, team_id)`.
- Composite FK `(evidence_link_id, hypothesis_id, team_id) → evidence_links(id, hypothesis_id, team_id)`; this requires a matching unique key on EvidenceLink and ensures an evidence cause belongs to the same Hypothesis.
- Composite FK `(created_by_task_id, team_id) → tasks(id, team_id)` for Task attribution. For `cause_kind='decay'`, this same Task is the decay Task; do not store a redundant `decay_task_id`.
- A CHECK must enforce exactly one cause: `cause_kind='evidence'` iff `evidence_link_id` is non-null; `cause_kind='decay'` iff `evidence_link_id` is null. `created_by_task_id` is always required.
- The application validator must additionally require an evidence cause to reference a `supports` or `challenges` EvidenceLink attached to this Hypothesis, and a decay cause's `created_by_task_id` to be an `apply_decay` Task. The DB check/FKs cannot prove the referenced row's stance or Task type.
- Require `from_confidence` and `to_confidence` to be valid bands and different. Under the proposed initial-confidence rule, the first state is `low`; every later change records the exact previous and next bands. The service must lock/re-read the Hypothesis and verify `from_confidence` equals its current value before appending the change and updating current confidence atomically.
- Unique `(created_by_task_id, idempotency_key)` for replay-safe append operations.
- Index by `(team_id, hypothesis_id, created_at)`.
- Append-only: no update/delete service. Confidence changes are historical facts, not mutable current-state rows.

### 4.4 One shared `evidence_links` table

Do not create a HypothesisEvidenceLink table or duplicate quote validation.

The current table's single `subject_id` FK cannot represent two subject tables with conventional foreign-key enforcement. The recommended physical design is therefore typed nullable subject references behind one logical EvidenceLink model:

- Retain `subject_kind`.
- Replace the Evaluation-only physical `subject_id` reference with nullable `evaluation_id` and `hypothesis_id` columns.
- Backfill every existing row's `evaluation_id` from its current `subject_id` before dropping/retiring the old column.
- Add composite same-Team FKs for both `evaluation_id` and `hypothesis_id`.
- A CHECK enforces exactly one subject FK and its agreement with `subject_kind`.
- Keep the application/domain representation polymorphic (`subject_kind`, logical `subject_id`) through one repository/model adapter; do not leak two competing EvidenceLink concepts into callers.
- Add unique `(id, team_id)` for ConfidenceChange's composite FK, plus unique `(id, hypothesis_id, team_id)` so a ConfidenceChange evidence cause can be constrained to the same Hypothesis.
- Preserve `reference_key` uniqueness separately for each subject type, using unique constraints on `(evaluation_id, reference_key)` and `(hypothesis_id, reference_key)`. PostgreSQL NULL behavior must be covered by the real-database proof.
- Preserve existing `team_id`, source, stance, Snapshot, quote, offset, and timestamp data.

For the source side in RW-1:
- Keep `source_kind`, `signal_id`, and `outcome_id` as the physical typed references already present.
- Enforce exactly one populated source column and agreement with `source_kind`.
- Preserve the current Outcome composite Team FK.
- Preserve Signal existence validation. Signal is global rather than Team-owned; the application must enforce the accepted Team relevance/eligibility rule. Do not pretend a Signal FK alone proves Team ownership.
- Add Artifact and Consultation source columns/FKs only in the later slice that creates their canonical source entities. Until then, no Artifact/Consultation EvidenceLink row is accepted. The logical vocabulary remains reserved and documented; no dangling UUID references are permitted.

Quote/Snapshot rules:
- Keep the existing paired Snapshot reference/hash and quote/offset CHECK constraints.
- The application commit service must load the immutable Snapshot, verify its content hash, and verify that the quote equals the exact substring at the supplied offsets. SQL CHECK constraints validate shape, not the actual content-addressed object.
- Keep `mentions` valid as a descriptive link, but reject it as a ConfidenceChange cause.
- Add non-null `originating_task_id` as a same-Team Task FK. Define it as the Task that originated the subject's evidence association: for an Evaluation subject, it is the parent Evaluation's `created_by_task_id`; for a Hypothesis subject, it is the Task that commits the EvidenceLink association. This does not claim to identify a physical SQL inserter outside the application contract. `EvaluationService.propose()` creates the Evaluation and all its links in one transaction, so the parent Task is the source-supported legacy mapping. The migration must verify every legacy EvidenceLink joins to exactly one Evaluation, that the Evaluation and Task Team IDs agree, and that no row remains unmapped. If any check fails, abort the migration transaction and preserve the old representation. Do not make the field nullable for legacy rows and do not fabricate a Task ID. The empty disposable database audit does not establish that the user's historical rows pass these checks.

The typed-column approach is intentionally explicit. It trades a small number of nullable columns for real foreign keys and Team constraints, while preserving one logical polymorphic model. A pure `subject_kind + subject_id` pair with no typed FK cannot provide the same database-level referential guarantee. A generic target registry table would add another entity and write path and is not recommended unless the typed-FK design proves unworkable.

## 5. Team isolation and source validation

- Thread is owned by one Team.
- Hypothesis carries the same `team_id` and a composite FK to its Thread.
- EvidenceLink subject and Team must match the referenced Evaluation or Hypothesis.
- ConfidenceChange, Hypothesis, EvidenceLink, and Task causes must share one Team.
- Outcome source must match EvidenceLink Team using the existing composite FK.
- Signal is global. The existing EvidenceLink Team association is not a direct Signal ownership relation. The application must require `Signal.domain == Team.domain`, matching `EvaluationService._normalize_evidence()` and `_revalidate_link()`. Apply that same deterministic rule to new Hypothesis links in RW-1/RW-2. SignalDisposition is a later triage record; it may add context in RW-4 but does not replace or silently narrow this existing domain-eligibility rule.
- Artifact and Consultation references are rejected until their canonical entities and source-validation services exist.
- No query may accept a Team ID supplied only by a model proposal as proof of ownership. Resolve ownership from canonical rows at commit time.

## 6. Migration and data-preservation proposal

The implementation PR must first run local preflight and verify the actual Alembic head on a disposable database. The static audit's `0018` revision is not a substitute for `alembic heads/current`.

Recommended forward sequence (one migration unless PostgreSQL constraint/backfill safety requires a staged sequence):
1. Create `threads`, `hypotheses`, and `confidence_changes` with their constraints and indexes.
2. Add `evaluation_id`, `hypothesis_id`, and `originating_task_id` to `evidence_links` as nullable columns, while retaining the old `subject_kind`/`subject_id` columns and FK. Do not add `originating_task_id` as `NOT NULL` while legacy rows still exist.
3. Backfill `evaluation_id = subject_id` and `originating_task_id = evaluations.created_by_task_id` through the existing parent Evaluation. Check that every old EvidenceLink has exactly one parent Evaluation, every parent Task exists, and all Team IDs agree. Verify pre/post row counts and zero null/unmapped values. Recompute every Evaluation proposal hash from its normalized EvidenceLink set using the existing canonicalization contract; any mismatch is a migration blocker, not a repair opportunity.
4. After the backfill checks pass, add the typed same-Team subject FKs, `originating_task_id` same-Team Task FK, `(id, team_id)` and `(id, hypothesis_id, team_id)` unique keys, per-subject reference-key uniqueness, and subject-kind/exactly-one CHECK. Then alter `originating_task_id` to `NOT NULL`; this must occur only after the backfill has proven that every legacy row has a valid Task attribution. Keep `evaluation_id`/`hypothesis_id` nullable as appropriate for the mutually exclusive subject kinds.
5. Add ConfidenceChange's same-Hypothesis EvidenceLink FK and Task attribution FK; omit a redundant `decay_task_id`.
6. Only after all backfill checks and replacement constraints succeed, remove the old Evaluation-only subject FK/column. The migration must execute transactionally on PostgreSQL so any failed assertion rolls back the DDL and data changes together.
7. Keep current source columns and supported source vocabulary unchanged in RW-1. Stage Artifact/Consultation source support with their future canonical tables.

Downgrade:
- Never cascade-delete or silently discard Thread, Hypothesis, ConfidenceChange, or Hypothesis-subject EvidenceLink history.
- Refuse downgrade with a clear exception if any RW-created world-memory records or Hypothesis-subject links exist.
- For a clean installation with no Thread, Hypothesis, ConfidenceChange, or Hypothesis-subject EvidenceLink rows, restore the previous Evaluation-only EvidenceLink representation and constraints without changing historical Evaluation link IDs, source IDs, hashes, quotes, offsets, stances, reference keys, or timestamps. The `originating_task_id` column is removed on downgrade with the new schema.
- Test upgrade against populated pre-RW fixtures containing Evaluation→Signal/Outcome links. Exercise integrity failures that can occur under the pre-RW schema (including Signal-domain mismatch, EvidenceLink reference-hash mismatch, and Evaluation proposal-hash mismatch) and verify transactional rollback. Existing foreign keys already prohibit orphaned Evaluation/Task references and cross-Team Evaluation links; document those pre-existing guarantees rather than constructing impossible legacy fixtures. Verify complete row/Task mapping and downgrade refusal when new world-memory rows exist, plus safe downgrade when they do not.

No migration number is assigned here. Use the revision that follows the verified live Alembic head at implementation time; never infer the next revision from filenames alone.

## 7. D99/D133 capability mapping

D99's two minimum retained-knowledge attribution capabilities are assigned to a named RW-4 sub-slice, **RW-4-KU (claim-level knowledge-use attribution)**. This is a planning assignment only; it does not authorize implementation.

| Capability | Named slice | Required behavior | Required proof nodes (proposed names; confirm before slice authorization) |
|---|---|---|---|
| TaskKnowledgeReference | RW-4-KU | Application-written, immutable reference from an identified output claim to exact KnowledgeItem ID/version, originating LearningChange, Team eligibility, and immutable Task Context evidence. | `tests/test_task_knowledge_reference.py`: exact identity/version, LearningChange binding, Team eligibility, Context-manifest binding, immutability, replay, invalid/stale reference rejection. |
| KnowledgeUseAssessment | RW-4-KU | Minimal typed, application-validated record binding the exact claim reference/knowledge version to the later Task's terminal Outcome. No mutation, approval, causal, or autonomous learning authority. | `tests/test_knowledge_use_assessment.py`: accepted/rejected typed values, exact claim/version/Outcome binding, Team and Context linkage, immutable record, replay, forbidden-write/scope rejection. |

RW-4-KU is part of the existing RW-4 retrieval/Context slice; it is not a new runtime or a separate R7-C programme. The implementation plan and proof matrix must be updated with exact test nodes before RW-4-KU is authorized. Any additional benchmark, blinded review, adjudication, statistical reporting, or score aggregation remains in the experiment harness, not production Watch.

## 8. RW-1 proof boundary

RW-1 is the physical schema/ORM/migration slice. Its proof obligations are limited to persistence shape, relational ownership and cause references, legacy preservation, and migration behavior. The merged PR #128 implementation identifies these exact proof nodes:

| Proof | Test node | What it establishes |
|---|---|---|
| Evaluation compatibility and Task provenance | `tests/test_evaluations.py::test_evaluation_propose_record_and_replay` | Existing Evaluation evidence remains recordable through the typed subject representation, with Task provenance and logical subject compatibility. |
| Evaluation Task attribution stability | `tests/test_evaluations.py::test_evaluation_record_rejects_changed_originating_task` | The originating Task cannot be changed before Evaluation evidence recording. |
| Shared Hypothesis EvidenceLink and initial confidence | `tests/test_evaluations.py::test_hypothesis_evidence_uses_one_typed_evidence_link` | Hypothesis evidence uses the shared EvidenceLink model and a newly created Hypothesis defaults to `low`. |
| Hypothesis/Thread Team ownership | `tests/test_evaluations.py::test_hypothesis_cannot_reference_another_teams_thread` | A Hypothesis cannot reference a Thread owned by another Team. |
| ConfidenceChange evidence ownership | `tests/test_evaluations.py::test_confidence_change_evidence_fk_is_bound_to_same_hypothesis` | The composite foreign key prevents a ConfidenceChange from citing an EvidenceLink attached to another Hypothesis. |
| Populated legacy-row preservation and Task backfill | `tests/test_rw1_schema_migration.py::test_0019_backfills_typed_subject_and_task_without_changing_legacy_rows` | Existing Evaluation EvidenceLink identity/provenance is preserved and originating Task attribution is backfilled. |
| Proposal-hash migration failure | `tests/test_rw1_schema_migration.py::test_0019_refuses_proposal_hash_mismatch_and_rolls_back_schema` | A legacy proposal-hash mismatch aborts the migration without leaving the new schema partially applied. |
| Signal-domain migration failure | `tests/test_rw1_schema_migration.py::test_0019_refuses_signal_domain_mismatch_and_rolls_back_schema` | A legacy Signal from another domain aborts the migration transactionally. |
| Evidence reference-hash migration failure | `tests/test_rw1_schema_migration.py::test_0019_refuses_evidence_reference_hash_mismatch_and_rolls_back_schema` | A tampered legacy EvidenceLink reference hash aborts the migration transactionally. |
| Canonical multi-link backfill | `tests/test_rw1_schema_migration.py::test_0019_backfills_multiple_links_in_canonical_reference_order` | Multiple legacy links are backfilled in canonical reference order with complete typed-subject and Task attribution. |
| Downgrade data-loss protection | `tests/test_rw1_schema_migration.py::test_0019_downgrade_refuses_hypothesis_confidence_history` and `tests/test_rw1_schema_migration.py::test_0019_downgrade_refuses_world_memory_then_restores_legacy_shape` | Downgrade refuses to discard world-memory history and restores the legacy Evaluation-only shape only when the new records are absent. |

The exact local verification qualification and hosted-CI evidence are recorded in the implementation plan and `docs/testing.md`. They establish the delivered schema/ORM/migration tree; they do not establish that the user's persistent database has passed the migration.

### RW-1 schema-level negative-test follow-up (PR #132)

The initial PR #128 suite declared the following database constraints in the ORM/migration but did not contain focused negative tests for each of them. Test-only PR [#132](https://github.com/abtn/Watch-Architecture-Rev2/pull/132) now adds those PostgreSQL proofs in `tests/test_evaluations.py`:

- `test_rw1_thread_status_check_rejects_invalid_values` — `ck_threads_status`.
- `test_rw1_hypothesis_vocabulary_checks_reject_invalid_values` — `ck_hypotheses_status` and `ck_hypotheses_confidence`.
- `test_rw1_evidence_subject_check_rejects_missing_dual_and_mismatched_subjects` — `ck_evidence_links_subject`, covering missing, dual, and kind/column-mismatch subjects.
- `test_rw1_evidence_source_check_rejects_missing_dual_and_mismatched_sources` — `ck_evidence_links_source`, covering missing, dual, and kind/column-mismatch sources.
- `test_rw1_confidence_change_cause_check_rejects_invalid_cause_shapes` and `test_rw1_confidence_change_checks_reject_unknown_cause_kind` — `ck_confidence_changes_cause` and `ck_confidence_changes_cause_kind`.
- `test_rw1_evidence_subject_and_task_fks_enforce_team_ownership` — `fk_evidence_links_evaluation_subject_team`, `fk_evidence_links_hypothesis_team`, and `fk_evidence_links_originating_task_team`.

Hosted GitHub Actions run [#1269](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/44087840152) passed on the then-exact test head `61fa0a214e05993637695e75d8aa019449fc540d`: fresh PostgreSQL migration and single-head/current verification, Ruff, Mypy, patch whitespace, and the full suite (**1,029 passed, 130 existing Alembic deprecation warnings**). CI removed its disposable PostgreSQL container and network. The follow-up changes tests only; no production code, ORM model, migration, or schema changed. PR #132 was subsequently updated with `main` after PR #133 merged; its current head is `3c77a52af6b4fc619b6274fadabb97f3738248c5`, with fresh hosted CI run [#1309](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/44265244934) passed on that exact updated head. Its disposable PostgreSQL migrations, Alembic single-head verification, Ruff, Mypy, patch whitespace, and full test suite all completed successfully. The historical run above remains a separate earlier-SHA record.

The schema-level negative-test gap is covered by hosted and Operator-local verification on exact head `61fa0a214e05993637695e75d8aa019449fc540d`: disposable PostgreSQL migration/current-head checks, Ruff, Mypy (38 source files), 31 focused Evaluation/schema tests, and the full suite (**1,029 passed, 130 existing Alembic deprecation warnings**). The disposable container was removed and environment variables restored. Those results apply to that exact head, not the subsequently updated PR #132 head `3c77a52af6b4fc619b6274fadabb97f3738248c5`; hosted CI run #1309 is the fresh qualification for the updated head. Formal RW-1 acceptance remains pending. These proofs do not establish that the user's persistent database has passed migration validation, and they do not authorize RW-2.

### Application-level proofs deferred to later slices

The following requirements remain binding. They are not RW-1 schema/ORM/migration acceptance criteria and are not satisfied by PR #128's merge or its migration tests.

| Behavior | Required proof | Allocation |
|---|---|---|
| Hypothesis EvidenceLink quote and Snapshot validation | For Hypothesis evidence, load the immutable Snapshot, verify its content hash, and require the supplied quote to equal the exact substring at the supplied offsets. RW-1 preserves the existing Evaluation path and stores the typed fields; the Hypothesis commit path is not present yet. | RW-2, `RW-EV-01` |
| Hypothesis Signal eligibility and Team/Snapshot references | Require `Signal.domain == Team.domain` for Hypothesis links; resolve Signal and Snapshot references from canonical records and reject cross-Team or stale references. The RW-1 schema proves relational ownership where composite FKs exist, not these application checks. | RW-2/RW-4, `RW-TS-01` |
| ConfidenceChange cause semantics and history | DB constraints enforce the structural cause shape and same-Hypothesis evidence FK. The application must additionally reject `mentions`, missing/dual/mismatched or wrong-Task causes, and must preserve ConfidenceChange history as append-only. | RW-2/RW-5, `RW-EV-02`/`RW-EV-03` |
| Competing Hypotheses | Multiple active Hypotheses may coexist without implicit demotion or deletion. The RW-1 schema permits this; the application path must prove it. | RW-2, `RW-HY-01` |
| Hypothesis lifecycle | Legal status transitions; rejection and supersession require a non-empty reason; supersession identifies a valid same-Team successor; no silent deletion; canonical Task-attributed Event. | RW-2, `RW-HY-02` |
| Atomic proposal commit and rejection | Valid proposal sets commit atomically; invalid proposals produce attributable rejection Events; failed transactions leave no partial business writes. | RW-2, `RW-AT-01` |
| Task/proposal replay | Replaying the same Task does not duplicate evidence or repeat a state transition. | RW-2/RW-3/RW-4/RW-5, `RW-RP-01` |
| Concurrent Thread updates | Conflicting updates serialize or one is rejected without lost updates. | RW-2/RW-3, `RW-RC-01` |
| Initial confidence through commit paths | Every new Hypothesis starts at `low`; any higher band is a later, valid Task-attributed ConfidenceChange through Operator and model paths. RW-1 proves only the persistence default. | RW-2/RW-3, `RW-HY-03` |
| Evidence-driven touch time | Only accepted evidence changes `last_touched_at`; mentions, rejected proposals, and replay do not. | RW-2/RW-3, `RW-LT-01` |
| Signal triage/disposition | Per-(Signal, Team) disposition and triage behavior are deferred; RW-1 intentionally creates no SignalDisposition model or triage path. | RW-4, `RW-TR-01` |

In particular, D132 decision 3 remains unchanged: supersession must be represented by one canonical Task-attributed Event containing the old Hypothesis ID, successor Hypothesis ID, and non-empty reason. Deferring its commit path to RW-2 does not weaken or waive that requirement.

Use real disposable PostgreSQL for database-backed constraints and migration proofs. The later application-level race and mutation proofs must also use the database behavior they are intended to verify; unit-only SQLite substitutes are not sufficient for PostgreSQL-specific guarantees.

## 9. D132 Operator decisions — accepted 2026-11-16

The Operator explicitly accepted all six recommendations on 2026-11-16. They are binding design decisions for RW-1 implementation:

1. **Typed EvidenceLink subject FKs — accepted.** Use `evaluation_id` and `hypothesis_id` physical columns behind one logical polymorphic EvidenceLink model. Keep the old Evaluation-only representation until the transactional backfill and replacement constraints pass.
2. **Legacy EvidenceLink attribution — accepted with a strict migration gate.** Use non-null `originating_task_id`, backfilled from the parent Evaluation's `created_by_task_id`. The existing service creates the Evaluation and its EvidenceLinks atomically. The migration must verify parent/Task existence, Team equality, complete row mapping, and proposal-hash consistency. Any failure aborts; no legacy-null exception and no guessed Task ID. This is a source-supported mapping, not a claim that the actual persistent database has already passed it.
3. **Hypothesis supersession — accepted: Task-attributed Event only.** Record the old Hypothesis ID, successor Hypothesis ID, and non-empty reason in one canonical historical Event appended through the existing Task/Kernel application path. The source audit verified Event Task attribution but did not establish database-level immutability; do not claim that guarantee unless an existing or explicitly approved mechanism enforces it. Do not add a redundant successor FK or transition table unless a later concrete invariant cannot be enforced through the Event and status validation.
4. **Initial confidence — accepted: every new Hypothesis starts at `low`.** ADR-0021 explicitly requires `low` for an unsubstantiated Hypothesis but leaves the initial band for an evidence-backed Hypothesis unspecified. This proposal deliberately chooses the stricter rule for both cases: evidence at creation does not set a higher initial band. A higher band can only result from a later ConfidenceChange, with an explicit cause and Task attribution. This avoids an unrecorded initial confidence jump.
5. **Signal eligibility — accepted: preserve the existing domain rule.** For both Evaluation and Hypothesis links in RW-1/RW-2, require `Signal.domain == Team.domain`, exactly as `EvaluationService._normalize_evidence()` and `_revalidate_link()` do today. SignalDisposition may add later triage context in RW-4, but must not silently narrow or invalidate this existing eligibility rule.
6. **Projection timing — accepted: defer projections to the retrieval slice.** Thread summaries, embeddings, and retrieval projections remain outside RW-1's authoritative schema and are introduced only with the accepted retrieval slice.

## 10. RW-1 implementation gate

The D132 design gate is satisfied by explicit Operator acceptance of all six decisions above. The implementation slice is separately authorized on 2026-11-16 and is limited to the RW-1 scope and proof obligations in this proposal and `docs/development/rw-implementation-plan.md`.

**Implementation disposition:** RW-1 implementation was merged by PR [#128](https://github.com/abtn/Watch-Architecture-Rev2/pull/128) at `7213a17e5ae96c3cae22ec1082af05d47b9c0d1d`. Operator-local verification and exact-tree qualification, plus hosted GitHub Actions run [#1247](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/43901592622) on the exact final PR code/test commit `aa947983fc72f771946ebf5b0d9a781aba80d7f3`, are recorded in `docs/testing.md`; that hosted run passed all CI steps. Formal Operator acceptance of RW-1 remains pending; this proposal's design acceptance under D132 is not a substitute for implementation acceptance.

**Boundary retained:** the RW-1 merge does not authorize RW-2–RW-5, R7-C, persistent-database access, or newsroom scored runs.
