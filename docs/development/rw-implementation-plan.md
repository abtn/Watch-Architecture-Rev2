# RW — Implementation Plan and Proof Matrix

**Status:** RW-0 is closed by docs-only squash merge PR #126; RW-1 physical design is under Operator review; no RW implementation is authorized
**Sequence:** B6 → RW-0 → RW-1 → RW-2 → RW-3 → RW-4 → RW-5 → foundation exit gate → R8
**Code audit basis:** post-B6 static source/spec audit at `91169b4931e48cb7b2803ed2066ec365f563a0ea`; RW-0 docs-only closeout squash-merged by PR #126 at `cac63a01380624bbaf0c9965a363a352e46960d7`
**Decision record:** [RW-0 decision record](rw-0-decision-record.md)
**RW-1 physical design:** [RW-1 physical world-memory and EvidenceLink design proposal](rw-1-physical-design-proposal.md) — proposed, not accepted
**Value harness:** [Newsroom value harness](rw-value-harness.md)

This plan turns the accepted architecture and the RW proposal into bounded implementation slices. It does not authorize schema, code, tests, migrations, or provider changes. RW-0 must freeze unresolved decisions and the Operator must authorize each implementation slice.

## 1. Purpose and boundary

The RW foundation implements the missing world-memory reasoning loop:

Signal → Thread → competing Hypotheses → EvidenceLinks → ConfidenceChanges → Outcomes/Evaluations → retained Team experience → later Task Context

The model proposes. Application code validates. The existing Kernel/commit path writes durable state. The work must not introduce a second runtime, scheduler, authentication system, or direct model-to-database path.

The newsroom is the first value-harness domain. RW-0 freezes the measurement methodology and eligibility rules. The exact completed story and source package must be prepared and frozen before scored runs; any item deferred from documentation closeout must be tracked with a named owner and acceptance gate. Other domains belong to R8 after the foundation exit gate.

The minimum R7-C capabilities approved by RW-D99—claim-level `TaskKnowledgeReference` and typed `KnowledgeUseAssessment`—are required only to the extent defined by the frozen newsroom claim. Before authorizing any RW slice that implements them, this plan must assign each capability to a named slice and proof obligations. This plan does not authorize R7-C or RW implementation.

## 2. Post-B6 implementation audit

The following is a read-only static source audit of post-B6 `main` at exact commit `91169b4931e48cb7b2803ed2066ec365f563a0ea`. It inspects source, migration files, tests, and architecture/Task specifications; it is not a runtime verification. No tests, Alembic commands, database migrations, or provider calls were run during this audit.

| Entity / flow | Code state at post-B6 audit SHA | Evidence / qualification |
|---|---|---|
| Signal | Implemented — ingestion only | `core/models.py`; `core/ingestion.py` `IngestionService`; immutable Snapshot path. This does not implement triage. |
| SignalDisposition | Not implemented | No ORM model, triage service, or commit path found. `tests/test_ingestion.py` has a negative scope test rejecting `allowed_writes=["SignalDisposition"]` for `ingest_source`; that is not an implementation proof. |
| Thread | Not implemented | No ORM model, repository/service, or worker found in the audited source tree. |
| Hypothesis | Not implemented | No ORM model, repository/service, or worker found in the audited source tree. |
| EvidenceLink | Partial — Evaluation path only | `core/models.py` constrains `subject_kind` to `evaluation` and sources to `signal` or `outcome`; `core/evaluations.py` accepts only those source kinds and revalidates source Snapshot identity/quote data when supplied. Hypothesis subjects and Artifact/Consultation sources are absent. |
| ConfidenceChange | Not implemented | No ORM model or cause-validation/commit path found. |
| Artifact | Not implemented | No ORM entity or render path found. |
| Consultation | Not implemented | No ORM entity or Consultation Task path found; ADR-0020's source contract remains an accepted target. |
| F1 — ingestion and triage | Partial | Deterministic Signal ingestion exists; `triage_signal`, Thread matching, and per-Team dispositions are not implemented. |
| F2 — update / update_thread | Not implemented | `docs/tasks.md` specifies the contract; no `update_thread` service/worker/commit path found. |
| operator_update | Not implemented | ADR-0021 and Task contract exist; no dedicated manual Task adapter or world-memory commit path found. Existing learning approval adapters do not implement this Task type. |
| F3 — decay / apply_decay | Not implemented | Task contract exists; no deterministic decay service or commit path found. |
| F4 — render / Artifact output | Not implemented | No Artifact model or rendering worker/path found. |
| F8 — Consultation | Not implemented | Accepted ADR/specification exists; no Consultation model or request/answer Task path found. |

The `triage_signal`, `update_thread`, `operator_update`, and `apply_decay` strings in `core/ingestion.py` are members of an Event-scope allow-list only. `IngestionService` still limits its business scope to `ingest_source`, and `core/dispatcher.py` supports only the configured-source `ingest_source` worker. The repository migration files end at `0018_r7b_lifecycle_review_date` (revision `0018_r7b_lifecycle_review_date`, down-revision `0017_r7b_assessments`); this migration changes the R7-B lifecycle-assessment constraint and adds no RW entities. Runtime `alembic heads/current` was not executed. The test tree has no dedicated RW model/worker/commit test modules. Architecture and Task specifications describe intended behavior; source code, migrations, and focused tests establish implementation.

## 3. Proposed slice sequence

### RW-1 — durable world-memory schema and EvidenceLink reconciliation

**Purpose:** create the canonical records required for world memory and align the existing EvidenceLink implementation with ADR-0007 and ADR-0020.

**Pre-implementation design gate (RW-D131/RW-D132):** RW-0 freezes the shared EvidenceLink contract and vocabulary, not its physical relational design. Before any RW-1 schema, migration, or production-code implementation, prepare and obtain explicit Operator acceptance of the exact relational representation, columns/keys, foreign-key strategy, constraints, indexes, Team ownership enforcement, quote/Snapshot validation, uniqueness/replay behavior, compatibility/backfill behavior, forward migration, staged Artifact/Consultation handling, and downgrade/data-preservation behavior. Preserve current Evaluation→Signal/Outcome evidence and ADR-0007/ADR-0020. No related implementation begins before this design gate passes.
**Proposed scope:**
- Add Thread, Hypothesis, and ConfidenceChange persistence with same-Team ownership, explicit status/confidence/cause constraints, and the indexes needed by the first newsroom scenario.
- Add SignalDisposition in this slice only if RW-4 triage remains in the accepted scope; otherwise defer its schema with the triage slice.
- Extend the existing evidence_links table/model rather than creating a sibling evidence system. Preserve current Evaluation→Signal/Outcome rows and their hashes, quotes, references, and uniqueness.
- Implement the accepted subject vocabulary (hypothesis, evaluation) and source vocabulary (signal, outcome, artifact, consultation) in a way that preserves deterministic commit-time reference and Team validation. Artifact/Consultation source rows may be staged until their canonical source entities are implemented, but must not be treated as usable references before then.
- Define a forward migration and compatibility behavior. Do not rewrite or reinterpret historical evidence silently.

**Required proof:**
- schema and application validation reject invalid subject/source combinations and invalid cause pairings; use database constraints for the cases the relational representation can enforce without breaking the accepted polymorphic contract;
- existing Evaluation evidence remains readable and valid;
- cross-Team references fail closed;
- quote/hash validation remains deterministic;
- migration upgrade and downgrade behavior is explicitly reviewed; downgrade must not silently discard new evidence;
- uniqueness and replay behavior remain deterministic.

**Exit:** schema, migration, ORM, repository/service contract, and tests agree. No worker is introduced in this slice.

### RW-2 — deterministic Operator reasoning commit path

**Purpose:** prove the world-memory write contract without model nondeterminism.

**Proposed scope:**
- Implement operator_update as an ordinary manual Task through the host-invoked application adapter boundary.
- Reuse the same proposal envelope and commit-time validation contract as update_thread (ADR-0021).
- Enforce same-Team references, exact Snapshot quote/hash/offset checks, stance rules, legal Hypothesis transitions, exactly-one ConfidenceChange cause, idempotency, and atomic proposal-set commit.
- An unsubstantiated Hypothesis starts at low, regardless of whether its author is human or model.
- Keep Operator authentication/authorization at the host boundary; Watch receives trusted principal context. Do not add a deployed Watch API/CLI or a second auth system.

**Required proof:** all applicable RW proof-matrix rows for evidence, Hypothesis transitions, atomicity, replay, concurrency, Team scope, and Operator provenance.

**Exit:** the deterministic human path passes the complete negative and positive proof set. No LLM call is required.

### RW-3 — bounded model update_thread worker

**Purpose:** allow a temporary model worker to propose updates to the world model without making the model authoritative.

**Proposed scope:**
- Assemble bounded Task Context from the target Thread, active Hypotheses, relevant dispositions, accepted evidence, and policy-authorized Team Experience.
- Use the existing generation/provider and Task cost/accounting boundaries; no new provider or direct database access is implied.
- Validate a typed proposal envelope through the same commit service used by operator_update.
- Record deterministic rejection Events with stable reasons and preserve atomic proposal-set semantics.
- Do not add an automatic repair/re-proposal loop in the first implementation unless RW-0 explicitly decides otherwise; measure the rejection rate first.
- Tests use deterministic provider stubs for proofs. Any live model smoke test is separate and cannot replace deterministic tests.

**Required proof:** all RW-2 commit proofs plus malformed output, out-of-scope writes, provider failure, cost/deadline handling, stale Context, and replay.

**Exit:** model proposals can improve the world model only through the shared application validation and commit path. Model output cannot write TeamPolicy or KnowledgeItems directly.

### RW-4 — minimal triage and Domain Knowledge read path

**Purpose:** connect ingested Signals to the world model and make accepted active Hypotheses available to later Task Context.

**Proposed scope:**
- Implement deterministic triage_signal with the smallest matching/dedup behavior required by the frozen newsroom scenario.
- Keep ambiguous cases explicit as deferred; never silently discard a Signal or infer a Thread without the deterministic rule required by the Task contract.
- Use explicit same-Team Thread fixtures for RW-2/RW-3 commit-path proofs. The current `operator_update` contract does not create Threads; canonical Thread creation remains in `triage_signal` (RW-4) unless a separate Task contract is explicitly approved. Do not widen `operator_update` scope implicitly.
- Add a bounded, same-Team read path for active Hypotheses and verified evidence in Task Context.
- Preserve the accepted Task write-scope matrix and Event (K) limits. Triage may enqueue only the documented update_thread follow-up cases.
- Do not expand domain-pack machinery beyond the frozen scenario's demonstrated need.

**Required proof:** one disposition per (Signal, Team), legal deferred refinement, duplicate/noise/matched/new-thread behavior as included in the frozen scope, dormant Thread reactivation if implemented, same-Team Context filtering, and no unapproved Task enqueue.

**Exit:** the newsroom scenario can move from source material to a durable Thread/Hypothesis state and retrieve that state in a later Task without bypassing validation.

### RW-5 — deterministic decay

**Purpose:** implement the F3 lifecycle behavior for stale Hypotheses and dormant Threads.

**Proposed scope:**
- Implement apply_decay as a deterministic scheduled Task under the existing Task runtime and policy bounds.
- Record decay-caused ConfidenceChanges with exactly one decay Task cause.
- Decay lowers confidence only according to the accepted domain/team decay policy; it never rejects a Hypothesis and never changes last_touched_at.
- A Thread becomes dormant only under the specified condition; a matched Signal may reactivate a dormant Thread through triage.
- No new scheduler or runtime.

**Required proof:** decay boundary/time tests, cause pairing, no rejection, no last_touched_at mutation, repeated-run idempotency, and concurrent/replay safety.

**Exit:** decay is deterministic, auditable, idempotent, and cannot erase or reject a Hypothesis.

## 4. Requirement-to-test proof matrix

The matrix defines required proof obligations, not tests that already exist. Each implementation PR must replace the test-node placeholder with the exact test node ID and report the exact tested commit SHA. Database-backed invariants require disposable PostgreSQL tests. Mutation checks should remove or invert the relevant guard in a scratch copy and demonstrate that the test fails.

| Proof ID | Requirement | Required test evidence | Slice |
|---|---|---|---|
| RW-EV-01 | Quote is the exact substring at the supplied offsets of the source's immutable hashed Snapshot. | Positive exact-quote test; altered quote, offsets, and hash rejected; no partial writes. | RW-1/RW-2 |
| RW-EV-02 | mentions evidence cannot anchor a ConfidenceChange. | Rejected proposal and no ConfidenceChange row. | RW-2 |
| RW-EV-03 | Every ConfidenceChange has exactly one valid cause. | Missing, dual, mismatched, or wrong-Task cause rejected by DB/application. | RW-1/RW-2/RW-5 |
| RW-HY-01 | Multiple active competing Hypotheses may coexist. | Create rival Hypotheses without implicit demotion/deletion. | RW-2 |
| RW-HY-02 | Supersede/reject requires legal transition, successor where required, reason, and Event. | Missing reason, stale status, invalid successor, and replay cases. | RW-2 |
| RW-HY-03 | An unsubstantiated Hypothesis starts at low for all authors. | Same proposal tested through Operator and model paths. | RW-2/RW-3 |
| RW-AT-01 | Valid proposals commit atomically as one set; invalid proposals are rejected with attributable Events, and the Task fails if all proposals fail. | Test an all-valid set, a mixed valid/invalid batch, and a failure during the valid-set transaction. Invalid proposals create no business writes; a failed valid-set transaction leaves none of that set committed. Preserve the current `docs/tasks.md` / `docs/architecture.md` semantics unless RW-0 explicitly approves a contract change. | RW-2 |
| RW-RP-01 | Task/proposal replay creates no duplicate evidence or state transition. | Repeated identical Task commit returns/reuses canonical result. | RW-2/RW-3/RW-4/RW-5 |
| RW-RC-01 | Concurrent updates cannot lose a Hypothesis/evidence change. | Repeated race test on one Thread; one winner or clean serialization, no lost update. | RW-2/RW-3 |
| RW-TS-01 | Cross-Team Thread, Hypothesis, Signal, and Snapshot references are rejected. | Database-backed negative tests for each reference type. | RW-1/RW-2/RW-4 |
| RW-LT-01 | last_touched_at changes only when evidence is accepted. | Accepted evidence updates it; mentions/rejected/replayed proposals do not. | RW-2/RW-3 |
| RW-DC-01 | Decay never rejects a Hypothesis and never changes last_touched_at. | Stale and boundary-time tests; no rejection transition; unchanged touch time. | RW-5 |
| RW-TR-01 | Triage is explicit and one-per-(Signal, Team). | Unique disposition, deferred refinement, dedup/noise/match/new-thread tests for frozen scope. | RW-1/RW-4 |
| RW-CT-01 | Task Context includes only bounded, current, same-Team accepted world memory. | Context manifest, active-status, scope, bound, and stale-reference tests. | RW-4 |
| RW-VAL-01 | The newsroom scenario demonstrates a repeatable end-to-end reasoning and retained-experience path. | Frozen corpus, baseline/experience-assisted runs, independent scoring, exact run artifacts and results. | All / exit gate |
| RW-KU-01 | Each claim-level TaskKnowledgeReference is application-written and immutable, binds an identified output claim to the exact KnowledgeItem ID/version, originating LearningChange, relevant Team eligibility, and Task Context evidence. | RW-4-KU: exact-identity/version, LearningChange, Team eligibility, Context-manifest linkage, immutability, replay, and stale/invalid-reference rejection. Proposed test node: `tests/test_task_knowledge_reference.py`; finalize before RW-4-KU authorization. | RW-4-KU (planned; not authorized) |
| RW-KU-02 | KnowledgeUseAssessment is typed and application-validated against the exact claim reference/knowledge version and the later Task's terminal Outcome; it grants no mutation or decision authority. | RW-4-KU: typed-value validation, exact claim/version/terminal-Outcome/Team/Context binding, immutability, replay, and forbidden-write/scope rejection. Proposed test node: `tests/test_knowledge_use_assessment.py`; finalize before RW-4-KU authorization. | RW-4-KU (planned; not authorized) |

## 4.1 RW-1 physical design preparation

The [RW-1 physical design proposal](rw-1-physical-design-proposal.md) is the current design artifact for D132. It recommends typed subject foreign keys behind one logical EvidenceLink model, same-Team composite references, append-only ConfidenceChange records, preservation/backfill of existing Evaluation evidence, and staged Artifact/Consultation support. Its review points are not yet accepted.

RW-1 implementation entry remains blocked until the Operator explicitly accepts the physical design and resolves or assigns every design decision in proposal §9. In particular:
- confirm the historical Task attribution source for existing EvidenceLinks before adding required provenance;
- settle Hypothesis supersession successor/reason representation;
- freeze initial confidence semantics;
- define Signal Team eligibility without breaking existing Evaluation evidence;
- confirm that Thread projections remain deferred to retrieval.

D133 mapping is now explicit: both minimum D99 capabilities are assigned to the planned RW-4-KU sub-slice, with proposed test modules recorded in the proof matrix. These test paths must be confirmed and the proof rows completed before RW-4-KU authorization. This assignment is not implementation authorization and does not create a separate R7-C programme.

## 5. Foundation exit gate

R8 may start only when all of the following are true:

1. B6 is formally accepted and closed.
2. RW-0 decisions are complete and recorded; unresolved capability questions have an explicit disposition.
3. RW-1 through RW-5 are implemented only to the accepted scope, merged, and individually accepted.
4. Every proof-matrix row has an exact test node, passes on the exact implementation SHA, and has required mutation/race evidence.
5. Existing R6/R7 tests and contracts remain green; migrations are verified on disposable PostgreSQL.
6. Ruff, Mypy, focused tests, integrated tests, full suite, and hosted CI pass on exact heads as required by repository policy.
7. The newsroom value harness has been run against the frozen corpus and rubric; results, limitations, and cost/latency are recorded.
8. Architecture/task implementation-state markers match the code and migration state after RW.
9. No unresolved critical/high-severity defect, scope violation, or accepted-contract conflict remains.
10. The Operator explicitly accepts the foundation exit gate.

A green CI run or a completed checklist alone does not constitute Operator acceptance.

## 6. Stop conditions

Stop and return to the Operator before proceeding if:
- implementation requires a new Kernel write path, second Task runtime, scheduler, dispatcher, or authentication system;
- a model or worker would gain direct DB/object-store access or writes to TeamPolicy/KnowledgeItem outside accepted paths;
- the EvidenceLink design cannot preserve ADR-0007/ADR-0020 and current Evaluation evidence;
- cross-Team ownership or immutable Snapshot/quote validation cannot be enforced;
- the newsroom scenario requires an unapproved Artifact, Consultation, R7-C, TeamDraft, or domain-pack capability;
- the proof matrix cannot demonstrate a required invariant or tests rely on live model output for deterministic guarantees;
- a proposed change expands beyond the frozen slice or introduces a new dependency without explicit justification and approval.

## 7. Delivery rules

- One bounded slice at a time; code, migration, tests, docs, and proof evidence belong in the same slice PR.
- Write or identify the regression proof before the implementation change; demonstrate the defect/failure before fixing it where applicable.
- Use the repository's exact-head and disposable-PostgreSQL operating rules. Never run migrations/tests against a persistent user database.
- Do not begin RW-1 schema or migration implementation until the RW-D132 physical EvidenceLink design gate is explicitly accepted.
- Before authorizing a slice that implements D99 capabilities, assign the relevant RW-KU proof rows to that named slice and replace their placeholders with exact test nodes or approved non-automated evidence.
- Report both the verified implementation SHA and current PR head, each with its CI evidence. Never transfer a test result to a different SHA.
- Re-audit implementation markers after B6 and after each RW slice. A specification or Task allow-list is not implementation evidence.
- Do not begin R8 until the foundation exit gate is explicitly accepted.
