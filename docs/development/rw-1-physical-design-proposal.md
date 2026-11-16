# RW-1 — Physical World-Memory and EvidenceLink Design Proposal

**Status:** design proposal for Operator review; not accepted for implementation
**Parent milestone:** RW-0 documentation closeout, squash-merged PR [#126](https://github.com/abtn/Watch-Architecture-Rev2/pull/126)
**Design authority:** RW-D131/RW-D132; ADR-0007, ADR-0009, ADR-0011, ADR-0014, ADR-0020, ADR-0021
**Implementation authority:** none. This document does not authorize schema, ORM, migration, production code, tests, provider changes, or scored execution.

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
- No physical delete path. Rejection and supersession are explicit state transitions with reason and Task-attributed Event, as required by INV-07.

The current architecture does not require a dedicated `superseded_by_hypothesis_id` column or a separate transition table. The RW-1 recommendation is to use one immutable, Task-attributed Event as the canonical supersession record, with an event type such as `hypothesis_superseded` and payload fields for the superseded Hypothesis ID, successor Hypothesis ID, and non-empty reason. The Event's Task supplies Team and actor attribution. Do not add a second successor relation unless a concrete invariant or query cannot be enforced through the canonical Event and Hypothesis status. The commit service must validate that both Hypotheses belong to the same Team and that the successor is not the superseded Hypothesis.

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
1. Create `threads`, `hypotheses`, and `confidence_changes` with constraints and indexes.
2. Add `evaluation_id`, `hypothesis_id`, and non-null `originating_task_id` to `evidence_links` while retaining the old `subject_kind`/`subject_id` columns and FK.
3. Backfill `evaluation_id = subject_id` and `originating_task_id = evaluations.created_by_task_id` through the existing parent Evaluation. Check that every old EvidenceLink has exactly one parent Evaluation, every parent Task exists, and all Team IDs agree. Verify pre/post row counts and zero null/unmapped values. Where practical, recompute each Evaluation proposal hash from its normalized EvidenceLink set using the existing canonicalization contract; any mismatch is a migration blocker, not a repair opportunity.
4. Add the typed same-Team subject FKs, `originating_task_id` same-Team Task FK, `(id, team_id)` and `(id, hypothesis_id, team_id)` unique keys, per-subject reference-key uniqueness, and subject-kind/exactly-one CHECK.
5. Add ConfidenceChange's same-Hypothesis EvidenceLink FK and Task attribution FK; omit a redundant `decay_task_id`.
6. Only after all backfill checks and replacement constraints succeed, remove the old Evaluation-only subject FK/column. The migration must execute transactionally on PostgreSQL so any failed assertion rolls back the DDL and data changes together.
7. Keep current source columns and supported source vocabulary unchanged in RW-1. Stage Artifact/Consultation source support with their future canonical tables.

Downgrade:
- Never cascade-delete or silently discard Thread, Hypothesis, ConfidenceChange, or Hypothesis-subject EvidenceLink history.
- Refuse downgrade with a clear exception if any RW-created world-memory records or Hypothesis-subject links exist.
- For a clean installation with no Thread, Hypothesis, ConfidenceChange, or Hypothesis-subject EvidenceLink rows, restore the previous Evaluation-only EvidenceLink representation and constraints without changing historical Evaluation link IDs, source IDs, hashes, quotes, offsets, stances, reference keys, or timestamps. The `originating_task_id` column is removed on downgrade with the new schema.
- Test upgrade against a populated pre-RW fixture containing Evaluation→Signal/Outcome links; include invalid parent, missing Task, cross-Team mismatch, unmapped row, and proposal-hash mismatch fixtures that must abort with no partial DDL/data change. Test downgrade refusal when new world-memory rows exist and safe downgrade when they do not.

No migration number is assigned here. Use the revision that follows the verified live Alembic head at implementation time; never infer the next revision from filenames alone.

## 7. D99/D133 capability mapping

D99's two minimum retained-knowledge attribution capabilities are assigned to a named RW-4 sub-slice, **RW-4-KU (claim-level knowledge-use attribution)**. This is a planning assignment only; it does not authorize implementation.

| Capability | Named slice | Required behavior | Required proof nodes (proposed names; confirm before slice authorization) |
|---|---|---|---|
| TaskKnowledgeReference | RW-4-KU | Application-written, immutable reference from an identified output claim to exact KnowledgeItem ID/version, originating LearningChange, Team eligibility, and immutable Task Context evidence. | `tests/test_task_knowledge_reference.py`: exact identity/version, LearningChange binding, Team eligibility, Context-manifest binding, immutability, replay, invalid/stale reference rejection. |
| KnowledgeUseAssessment | RW-4-KU | Minimal typed, application-validated record binding the exact claim reference/knowledge version to the later Task's terminal Outcome. No mutation, approval, causal, or autonomous learning authority. | `tests/test_knowledge_use_assessment.py`: accepted/rejected typed values, exact claim/version/Outcome binding, Team and Context linkage, immutable record, replay, forbidden-write/scope rejection. |

RW-4-KU is part of the existing RW-4 retrieval/Context slice; it is not a new runtime or a separate R7-C programme. The implementation plan and proof matrix must be updated with exact test nodes before RW-4-KU is authorized. Any additional benchmark, blinded review, adjudication, statistical reporting, or score aggregation remains in the experiment harness, not production Watch.

## 8. RW-1 proof plan

The RW-1 implementation PR must identify exact test nodes for at least:

| Proof | Required assertion |
|---|---|
| Thread ownership | Cross-Team Thread access/reference rejected; status vocabulary enforced. |
| Hypothesis ownership | Hypothesis must reference a Thread in the same Team; competing active Hypotheses coexist. |
| Hypothesis lifecycle | Invalid status transitions and delete attempts rejected; rejection/supersession requires reason and Task-attributed Event. |
| Confidence bands | Only low/moderate/high accepted. |
| Confidence cause | Missing, dual, mismatched, cross-Team, wrong-Hypothesis, mentions-only, or wrong-Task causes rejected; evidence cause is constrained to the same Hypothesis by a composite FK. |
| Evidence subject | Evaluation and Hypothesis subjects both accepted through one logical EvidenceLink API; invalid/missing/dual typed subject rejected. |
| Evidence source | Signal and Outcome remain supported; invalid/missing/dual source rejected. Artifact/Consultation remain rejected until later source slices. |
| Legacy preservation | Existing Evaluation→Signal/Outcome rows retain IDs and all provenance fields; `originating_task_id` backfills from the parent Evaluation Task; parent/Task/Team mapping and proposal-hash checks pass; current evaluation service behavior remains green. |
| Team isolation | Cross-Team subject, Outcome, Hypothesis, Task and ConfidenceChange references rejected. Signal domain must equal the linking Team's domain for both subject kinds. |
| Quote integrity | Exact quote/offset/hash accepted; altered quote, offset, Snapshot ref, or hash rejected. |
| Uniqueness/replay | Duplicate reference keys and same-Task replay handled deterministically; concurrent conflicting commits cannot corrupt records. |
| Migration | Upgrade on populated pre-RW DB and fresh DB; verify complete Task attribution, row counts, Team consistency, and proposal hashes; all invalid fixtures abort transactionally without partial DDL/data changes; verify migration head, downgrade refusal with new records, and safe downgrade on empty RW tables. |
| Immutability | EvidenceLink and ConfidenceChange history cannot be rewritten or deleted through application paths. |

Use real disposable PostgreSQL for database-backed constraints, migration, race, and mutation proofs. Unit-only SQLite substitutes are not sufficient for PostgreSQL-specific constraints.

## 9. Design decisions requiring Operator acceptance before implementation

The source/schema audit supports the following six proposed decisions. They remain recommendations for Operator acceptance under D132; this document does not accept them on the Operator's behalf:

1. **Typed EvidenceLink subject FKs — recommend accept.** Use `evaluation_id` and `hypothesis_id` physical columns behind one logical polymorphic EvidenceLink model. Keep the old Evaluation-only representation until the transactional backfill and replacement constraints pass.
2. **Legacy EvidenceLink attribution — recommend accept with a strict migration gate.** Use non-null `originating_task_id`, backfilled from the parent Evaluation's `created_by_task_id`. The existing service creates the Evaluation and its EvidenceLinks atomically. The migration must verify parent/Task existence, Team equality, complete row mapping, and (where practical) proposal-hash consistency. Any failure aborts; no legacy-null exception and no guessed Task ID. This is a source-supported mapping, not a claim that the actual persistent database has already passed it.
3. **Hypothesis supersession — recommend Task-attributed Event only.** Record the old Hypothesis ID, successor Hypothesis ID, and non-empty reason in one canonical immutable Event. Do not add a redundant successor FK or transition table unless a later concrete invariant cannot be enforced through the Event and status validation.
4. **Initial confidence — recommend every new Hypothesis starts at `low`.** This applies even when creation includes evidence. A higher band can only result from a later ConfidenceChange, with an explicit cause and Task attribution. This avoids an unrecorded initial confidence jump.
5. **Signal eligibility — recommend preserve the existing domain rule.** For both Evaluation and Hypothesis links in RW-1/RW-2, require `Signal.domain == Team.domain`, exactly as `EvaluationService._normalize_evidence()` and `_revalidate_link()` do today. SignalDisposition may add later triage context in RW-4, but must not silently narrow or invalidate this existing eligibility rule.
6. **Projection timing — recommend defer.** Thread summaries, embeddings, and retrieval projections remain outside RW-1's authoritative schema and are introduced only with the accepted retrieval slice.

## 10. Entry and exit gates

RW-1 documentation/design PR is complete only when:
- this proposal is reconciled with ADR-0007/ADR-0020/ADR-0021 and current architecture/Task specifications;
- each review point above is explicitly accepted, rejected, or assigned to a later named gate;
- the implementation plan and proof matrix name the exact RW-1 scope and test nodes;
- the migration/backfill/downgrade strategy is internally consistent with existing Evaluation evidence;
- the Operator explicitly accepts the physical design under D132.

RW-1 implementation remains separately authorized. After design acceptance, prepare a bounded implementation instruction and local preflight; do not silently begin coding as part of this documentation PR.

**Current boundary:** this is a design/planning artifact only. It does not close RW-1, implement Hypothesis, authorize any migration or production code, authorize RW-2–RW-5, authorize R7-C, or authorize newsroom scored runs.
