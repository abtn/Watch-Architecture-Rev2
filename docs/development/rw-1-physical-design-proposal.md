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

The design is based on the repository state at the RW-0 squash merge, `cac63a01380624bbaf0c9965a363a352e46960d7`.

Static source inspection confirms:

- `core/models.py` contains no ORM models for Thread, Hypothesis, or ConfidenceChange.
- The existing `evidence_links` table is real and Evaluation-scoped. It has `subject_kind`, `subject_id`, `source_kind`, `outcome_id`, `signal_id`, `team_id`, Snapshot reference/hash, quote/offsets, stance, reference key, and created timestamp.
- Its subject constraint permits only `evaluation`; its source constraint permits only `signal` or `outcome`.
- The Evaluation subject and Outcome source have composite Team foreign keys. Signal has a direct foreign key, but is not itself Team-owned.
- `core/evaluations.py` is the existing application validation path for Evaluation evidence. It must remain valid and must not be replaced by a parallel evidence service.
- Migration `0012_learning_foundation.py` created the existing EvidenceLink table. The static migration audit records the repository migration chain through `0018_r7b_lifecycle_review_date`; the live Alembic head must be checked locally before implementation.
- ADR-0007 defines subjects `hypothesis | evaluation`, sources `signal | outcome | artifact`, and stances `supports | challenges | mentions`. ADR-0020 adds `consultation` as a source. Only `supports` and `challenges` may anchor a ConfidenceChange.

This is a static design review, not runtime or database verification.

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

The current architecture contract does not yet define a dedicated `superseded_by_hypothesis_id` column or a separate transition table. Do not add one merely for convenience. Before implementation, decide whether the existing Task-attributed Event payload is the canonical durable record of the successor/reason, or whether a narrowly justified typed relation is required to make the invariant queryable. Either choice must preserve the exact affected and surviving Hypothesis IDs.

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
| `decay_task_id` | Nullable same-Team Task FK |
| `created_by_task_id` | Task responsible for the change |
| `idempotency_key` | Stable per-Task operation key |
| `created_at` | UTC-aware timestamp |

Constraints/indexes:
- Composite FK `(hypothesis_id, team_id) → hypotheses(id, team_id)`.
- Composite FK `(evidence_link_id, team_id) → evidence_links(id, team_id)` once EvidenceLink has a unique `(id, team_id)`.
- Composite FK `(decay_task_id, team_id) → tasks(id, team_id)` and a Task-attribution FK for `created_by_task_id`.
- A CHECK must enforce exactly one cause: `cause_kind='evidence'` iff `evidence_link_id` is non-null and `decay_task_id` is null; `cause_kind='decay'` iff the reverse holds.
- The application validator must additionally require an evidence cause to reference a `supports` or `challenges` EvidenceLink, and a decay cause to originate from an `apply_decay` Task. The DB check alone cannot prove the referenced row's stance or Task type.
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
- Add unique `(id, team_id)` for ConfidenceChange's composite FK.
- Preserve `reference_key` uniqueness separately for each subject type, using unique constraints on `(evaluation_id, reference_key)` and `(hypothesis_id, reference_key)`. Null semantics must be verified on PostgreSQL.
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
- Add `added_by_task_id` (or one agreed equivalent) as a same-Team Task FK if required by the accepted EvidenceLink contract. Before implementation, verify the backfill source for existing Evaluation links—likely the creating Evaluation Task—and refuse migration if any historical row cannot be attributed honestly. Do not fabricate provenance.

The typed-column approach is intentionally explicit. It trades a small number of nullable columns for real foreign keys and Team constraints, while preserving one logical polymorphic model. A pure `subject_kind + subject_id` pair with no typed FK cannot provide the same database-level referential guarantee. A generic target registry table would add another entity and write path and is not recommended unless the typed-FK design proves unworkable.

## 5. Team isolation and source validation

- Thread is owned by one Team.
- Hypothesis carries the same `team_id` and a composite FK to its Thread.
- EvidenceLink subject and Team must match the referenced Evaluation or Hypothesis.
- ConfidenceChange, Hypothesis, EvidenceLink, and Task causes must share one Team.
- Outcome source must match EvidenceLink Team using the existing composite FK.
- Signal is global. The existing EvidenceLink Team association is not a direct Signal ownership relation. The application must validate that the Signal is admissible for the linking Team under the Signal/triage contract; when SignalDisposition is implemented in RW-4, the exact eligibility relationship must be enforced and tested there. Existing Evaluation→Signal behavior must not be silently narrowed or broken during RW-1.
- Artifact and Consultation references are rejected until their canonical entities and source-validation services exist.
- No query may accept a Team ID supplied only by a model proposal as proof of ownership. Resolve ownership from canonical rows at commit time.

## 6. Migration and data-preservation proposal

The implementation PR must first run local preflight and verify the actual Alembic head on a disposable database. The static audit's `0018` revision is not a substitute for `alembic heads/current`.

Recommended forward sequence (one migration unless PostgreSQL constraint/backfill safety requires a staged sequence):
1. Create `threads`, `hypotheses`, and `confidence_changes` with constraints and indexes.
2. Add `evaluation_id` and `hypothesis_id` to `evidence_links`.
3. Backfill `evaluation_id = subject_id` for every existing Evaluation row; verify row counts and no null/unmapped rows.
4. Add composite FKs, unique constraints, and the subject-kind/exactly-one check.
5. Add the EvidenceLink `(id, team_id)` unique key required by ConfidenceChange.
6. Add Task attribution only after its historical backfill source has been verified; if provenance cannot be reconstructed, preserve the field as explicitly nullable for legacy rows only if the accepted contract permits that distinction, and require non-null for every new row. Do not invent a Task ID.
7. Remove the old Evaluation-only subject FK/column only after the replacement mapping and application code are ready in the same release.
8. Keep current source columns and supported source vocabulary unchanged in RW-1. Stage Artifact/Consultation source support with their future canonical tables.

Downgrade:
- Never cascade-delete or silently discard Thread, Hypothesis, ConfidenceChange, or Hypothesis-subject EvidenceLink history.
- Refuse downgrade with a clear exception if any RW-created world-memory records or Hypothesis-subject links exist.
- For a clean empty RW installation, restore the previous Evaluation-only EvidenceLink representation and constraints without changing historical Evaluation link IDs, source IDs, hashes, quotes, offsets, stances, reference keys, or timestamps.
- Test upgrade and downgrade on disposable PostgreSQL, including a populated pre-RW fixture and a post-RW fixture that must cause downgrade refusal.

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
| Confidence cause | Missing, dual, mismatched, cross-Team, mentions-only, or wrong-Task causes rejected. |
| Evidence subject | Evaluation and Hypothesis subjects both accepted through one logical EvidenceLink API; invalid/missing/dual typed subject rejected. |
| Evidence source | Signal and Outcome remain supported; invalid/missing/dual source rejected. Artifact/Consultation remain rejected until later source slices. |
| Legacy preservation | Existing Evaluation→Signal/Outcome rows retain IDs and all provenance fields; current evaluation service behavior remains green. |
| Team isolation | Cross-Team subject, Outcome, Hypothesis, Task and ConfidenceChange references rejected. Signal follows the explicit Team-eligibility rule. |
| Quote integrity | Exact quote/offset/hash accepted; altered quote, offset, Snapshot ref, or hash rejected. |
| Uniqueness/replay | Duplicate reference keys and same-Task replay handled deterministically; concurrent conflicting commits cannot corrupt records. |
| Migration | Upgrade on populated pre-RW DB, fresh upgrade, migration head, downgrade refusal with new records, safe downgrade on empty RW tables. |
| Immutability | EvidenceLink and ConfidenceChange history cannot be rewritten or deleted through application paths. |

Use real disposable PostgreSQL for database-backed constraints, migration, race, and mutation proofs. Unit-only SQLite substitutes are not sufficient for PostgreSQL-specific constraints.

## 9. Design decisions requiring Operator acceptance before implementation

The following are the review points. The proposal recommends a direction but does not mark them accepted:

1. **Typed EvidenceLink subject FKs:** accept `evaluation_id` + `hypothesis_id` physical columns behind one logical polymorphic model, replacing the current Evaluation-only `subject_id` FK after a verified backfill.
2. **Legacy EvidenceLink Task attribution:** confirm the valid historical source for `added_by_task_id`; accept the migration only if every old row can be attributed without fabrication or if the contract explicitly permits a legacy-null distinction.
3. **Hypothesis supersession provenance:** decide whether the Task-attributed Event payload is sufficient as the canonical record of successor/reason, or whether a typed successor reference is necessary.
4. **Initial confidence semantics:** the current contracts say an unsubstantiated Hypothesis starts at `low`, but do not fully specify whether an evidence-backed Hypothesis may be created above `low` or must always start at `low` and move through ConfidenceChange. Freeze one rule before schema/service implementation.
5. **Signal Team eligibility:** preserve existing Evaluation evidence behavior and define the precise Team relevance check for new Hypothesis links before the RW-2 commit path; complete the SignalDisposition-backed proof when RW-4 triage is implemented.
6. **Projection timing:** keep Thread summaries/embeddings out of RW-1's authoritative schema unless an accepted RW-4 retrieval requirement proves they are needed earlier.

## 10. Entry and exit gates

RW-1 documentation/design PR is complete only when:
- this proposal is reconciled with ADR-0007/ADR-0020/ADR-0021 and current architecture/Task specifications;
- each review point above is explicitly accepted, rejected, or assigned to a later named gate;
- the implementation plan and proof matrix name the exact RW-1 scope and test nodes;
- the migration/backfill/downgrade strategy is internally consistent with existing Evaluation evidence;
- the Operator explicitly accepts the physical design under D132.

RW-1 implementation remains separately authorized. After design acceptance, prepare a bounded implementation instruction and local preflight; do not silently begin coding as part of this documentation PR.

**Current boundary:** this is a design/planning artifact only. It does not close RW-1, implement Hypothesis, authorize any migration or production code, authorize RW-2–RW-5, authorize R7-C, or authorize newsroom scored runs.
