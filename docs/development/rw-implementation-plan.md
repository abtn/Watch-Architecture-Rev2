# RW — Implementation Plan and Proof Matrix

**Status:** RW-0, RW-1, and RW-2 are formally accepted. RW-2 was accepted on 2026-11-18 after correcting both P1 review findings and adding PostgreSQL regression proofs. PR [#134](https://github.com/abtn/Watch-Architecture-Rev2/pull/134) passed hosted CI run [#1359](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/44322369751) on exact head `a8f453dec7a4668c91fd4df113bf597c1751dac8` (**1,105 passed; 130 existing Alembic deprecation warnings**) and Programmer-local Windows verification on that same exact SHA (**23 focused RW-2 tests; 1,105 full-suite tests; Ruff, Mypy, disposable PostgreSQL migration, Alembic single-head/current, patch whitespace, cleanup, environment restoration, and clean exact-head worktree all passed**). The accepted RW-2 scope and two regression proofs are recorded below and in `docs/testing.md`. PR #134 was squash-merged to `main` on 2026-11-18 at `601f7816eaa51495d7d40d4b9d32d846122b4a59`; the tested documentation-inclusive PR head was `61071de2e0c2cce3e33313b2bae73d3e7296a002`.
**Sequence:** B6 → RW-0 → RW-1 → RW-2 → RW-3 → RW-4 → RW-5 → foundation exit gate → R8
**Code audit basis:** post-B6 static source/spec audit at `91169b4931e48cb7b2803ed2066ec365f563a0ea`; RW-0 docs-only closeout squash-merged by PR #126 at `cac63a01380624bbaf0c9965a363a352e46960d7`
**Decision record:** [RW-0 decision record](rw-0-decision-record.md)
**RW-1 physical design:** [RW-1 physical world-memory and EvidenceLink design proposal](rw-1-physical-design-proposal.md) — accepted under D132 on 2026-11-16
**Value harness:** [Newsroom value harness](rw-value-harness.md)

This plan turns the accepted architecture and RW proposal into bounded implementation slices. RW-1 and RW-2 are formally accepted. RW-3 is the next proposed slice, but it requires a separate explicit authorization. RW-4–RW-5, R7-C implementation, persistent-database access, and newsroom scored execution remain separately gated.

## 1. Purpose and boundary

The RW foundation implements the missing world-memory reasoning loop:

Signal → Thread → competing Hypotheses → EvidenceLinks → ConfidenceChanges → Outcomes/Evaluations → retained Team experience → later Task Context

The model proposes. Application code validates. The existing Kernel/commit path writes durable state. The work must not introduce a second runtime, scheduler, authentication system, or direct model-to-database path.

The newsroom is the first value-harness domain. RW-0 freezes the measurement methodology and eligibility rules. The exact completed story and source package must be prepared and frozen before scored runs; any item deferred from documentation closeout must be tracked with a named owner and acceptance gate. Other domains belong to R8 after the foundation exit gate.

The minimum R7-C capabilities approved by RW-D99—claim-level `TaskKnowledgeReference` and typed `KnowledgeUseAssessment`—are required only to the extent defined by the frozen newsroom claim. Before authorizing any RW slice that implements them, this plan must assign each capability to a named slice and proof obligations. The historical post-B6 audit did not authorize R7-C or RW implementation; RW-1 was subsequently authorized under D132 and is the only current RW implementation slice. RW-2–RW-5 remain separately gated.

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

**Design gate (RW-D131/RW-D132): SATISFIED on 2026-11-16.** The Operator explicitly accepted all six D132 recommendations in the [RW-1 physical design proposal](rw-1-physical-design-proposal.md) §9, including the exact typed-subject representation, strict legacy attribution/backfill gate, supersession Event contract, initial confidence rule, Signal-domain eligibility, and projection deferral. RW-1 implementation is separately authorized as the current bounded slice. The design gate is closed; do not repeat it as a pending prerequisite.
**Authorized scope:**
- Add Thread, Hypothesis, and ConfidenceChange persistence with same-Team ownership, explicit status/confidence/cause constraints, and the indexes needed by the first newsroom scenario.
- Add SignalDisposition in this slice only if RW-4 triage remains in the accepted scope; otherwise defer its schema with the triage slice.
- Extend the existing evidence_links table/model rather than creating a sibling evidence system. Preserve current Evaluation→Signal/Outcome rows and their hashes, quotes, references, and uniqueness.
- Implement the accepted subject vocabulary (hypothesis, evaluation) and source vocabulary (signal, outcome, artifact, consultation) in a way that preserves deterministic commit-time reference and Team validation. Artifact/Consultation source rows may be staged until their canonical source entities are implemented, but must not be treated as usable references before then.
- Define a forward migration and compatibility behavior. Do not rewrite or reinterpret historical evidence silently.

**Required proof:** all applicable RW-2 commit proofs through the model entry path, plus deterministic Context ordering and overflow rejection, Team Experience exclusion, malformed and oversized output, the 8-proposal model cap, authority escalation attempts, reservation-before-call, provider failure, known/unknown/overrun cost reconciliation before commit, empty no-op, all-invalid and mixed batches, atomic rollback, parser-versus-proposal failure recording, replay, concurrency, admission ordering, actor attribution, and interrupted Task recovery. The current Operator-only `WorldMemoryCommitService` cannot be called unchanged; reuse its validation/transaction core behind a narrow trusted `operator`/`model_worker` actor seam while preserving RW-2 Operator events and identity. TaskRuntime needs only task-type-specific admission, result validation, finalization, and recovery support. Ordinary CI uses a deterministic fake provider; live smoke tests, if later requested, are separate.
- schema and application validation reject invalid subject/source combinations and invalid cause pairings; use database constraints for the cases the relational representation can enforce without breaking the accepted polymorphic contract;
- existing Evaluation evidence remains readable and valid;
- cross-Team references fail closed;
- quote/hash validation remains deterministic;
- migration upgrade and downgrade behavior is explicitly reviewed; downgrade must not silently discard new evidence;
- uniqueness and replay behavior remain deterministic.

**Exit:** schema, migration, ORM, repository/service contract, and tests agree. No worker is introduced in this slice.

### RW-2 — deterministic Operator reasoning commit path

**Purpose:** prove the world-memory write contract without model nondeterminism.

**Authorization:** explicitly granted by the Operator on 2026-11-18 within this section's scope.

**Implementation and acceptance status: ACCEPTED on 2026-11-18.** Corrected exact head `a8f453dec7a4668c91fd4df113bf597c1751dac8` passed hosted CI run [#1359](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/44322369751) and Programmer-local Windows verification. Hosted and local full suites each reported **1,105 passed**. Local focused RW-2 tests: **23 passed**. Both P1 findings were fixed: cross-Thread successors are rejected without a supersession transition/Event; terminal validation uses immutable creation-time confidence evidence and tolerates a later valid confidence increase. The deterministic interleaving proof verifies both Tasks finalize successfully. Full commands/results and cleanup are recorded in `docs/testing.md`.

**Proposed scope:**
- Implement operator_update as an ordinary manual Task through the host-invoked application adapter boundary.
- Reuse the same proposal envelope and commit-time validation contract as update_thread (ADR-0021).
- Enforce same-Team references, exact Snapshot quote/hash/offset checks, stance rules (a `mentions` link cannot cause a ConfidenceChange), legal Hypothesis transitions, exactly-one ConfidenceChange cause, idempotency, and atomic proposal-set commit.
- Every new Hypothesis starts at `low`; initial evidence does not establish a higher starting band. A higher band can result only from a later ConfidenceChange with an explicit valid cause and Task attribution.
- Keep Operator authentication/authorization at the host boundary; Watch receives trusted principal context. Do not add a deployed Watch API/CLI or a second auth system.

**Required proof:** all applicable RW proof-matrix rows for evidence, Hypothesis transitions, atomicity, replay, concurrency, Team scope, and Operator provenance.

**Exit:** the deterministic human path passes the complete negative and positive proof set. No LLM call is required.

### RW-3 — bounded model update_thread worker

**Purpose:** let a temporary model worker propose updates to one existing Thread while keeping authority, validation, and persistence in application/Kernel code.

**Planning status:** the RW3-0 decision proposal is recorded in [RW-3 design and acceptance plan](rw-3-design-and-acceptance.md); independent design review remains pending. RW-3 implementation is not authorized.

**Proposed boundary:** TaskRuntime owns admission, attempt lifecycle, terminalization, and recovery. Trusted Task/database state fixes Team and target Thread. Application code assembles bounded Context. The existing generation/provider and cost-accounting boundary returns untrusted output. A strict typed parser validates it. The shared RW-2 proposal-validation and atomic transaction core is reused through a narrow trusted actor seam; the current Operator-only `WorldMemoryCommitService` cannot be called unchanged. Preserve Operator principal checks and Event behavior. No second runtime, scheduler, provider abstraction, auth system, direct model-to-database path, or generic dispatcher framework.

**Proposed Context:** target Thread; all active same-Thread Hypotheses; relevant accepted EvidenceLinks; exact immutable source Snapshot references/content; current applicable policy. Order Hypotheses by `(created_at ASC, id ASC)` and EvidenceLinks by `(hypothesis_id ASC, created_at ASC, id ASC)`; order unique Snapshot references lexically. Bound the set to 8 Hypotheses, 8 EvidenceLinks, 8 unique Snapshots, and 8,000 Unicode characters of evidence text; overflow fails closed after admission and before provider invocation rather than silently ranking/truncating canonical records. Team Experience is excluded: the current Task Context assembler is scoped to `propose_strategy`, and RW-3 does not add a new retrieval integration. SignalDisposition and triage state remain RW-4. Preserve ADR-0031's 8-passage/8,000-character retrieval ceiling and 32,000-token provider context ceiling unchanged.

**Business write scope:** exactly `EvidenceLink`, `Hypothesis`, and `ConfidenceChange`. Event/Outcome remain Kernel/TaskRuntime side effects. Reuse RW-2 proposal types and validation/transaction logic through the narrow actor seam; do not call the Operator-specific service unchanged. Preserve all RW-2 validation, ownership, Snapshot/quote/hash, stance, confidence-cause, initial-low-confidence, legal-transition, same-Thread successor, idempotency, replay, concurrency, and atomicity rules.

**Explicit exclusions:** SignalDisposition refinement/triage; Thread creation/reactivation/summary projections; TeamPolicy or KnowledgeItem mutation; Artifact/Consultation creation; worker-written Outcomes; other-Thread mutations; automatic semantic repair or model re-proposal loops.

**Provider limits:** retain ADR-0031's exact Cloudflare Workers AI model; the provider's 32,000-token context window is not a Watch Context budget. Retrieval-derived passages remain capped at 8 passages/8,000 Unicode characters. The exact prompt quote uses UTF-8 byte lengths plus 128 framing tokens; quoted input plus output must fit 32,000 tokens. The existing configured output cap is at most 1,024 tokens (lower is permitted); do not raise it. The adapter makes one synchronous non-streaming request, uses no tools, and does not retry internally; it requires valid prompt/completion usage and an exact model identifier. TaskRuntime alone owns retry eligibility.

**Generation sequence:** read-only validation of immutable Task request/target/policy → TaskRuntime admission → attempt-bound Context assembly and validation → reserve maximum generation cost → call existing provider → reconcile raw provider usage and validate the exact current-attempt charge → strict parse and bound output → shared RW-2 validation/transaction core through the trusted actor seam → TaskRuntime finalization. Reconcile known usage even when the response body is malformed; missing/unknown/unreconciled/overrun usage fails closed and cannot authorize business writes. Context failure after admission is recorded through TaskRuntime without a provider call. No hidden provider retries; only existing bounded TaskRuntime retry policy may apply.

**Batch/failure semantics:** preserve RW-D18/RW-2 semantics: invalid proposals receive attributable rejection Events; valid proposals commit atomically as one accepted set; transaction failure rolls back that set; the Task fails only when all proposals are rejected. Mixed valid/invalid batches may commit the valid set only. The model response permits at most 8 proposals; the existing Operator request cap of 64 is unchanged. An explicit empty proposal list is a successful no-op finalized as `success_no_change` only after cost reconciliation, with no commit call or business writes. Parser/schema/authority/count/output-bound failures are non-retryable TaskRuntime failures without proposal rejection Events; domain-invalid typed proposals use the existing per-proposal rejection Events. Provider/Context/reservation failures cannot create business writes. Unknown usage follows existing accounting and is never treated as zero.

**Cost-service change required:** extend the existing `TaskGenerationCostService` narrowly with one distinct `update_thread` operation mapped to Task type `update_thread` and the exact ordered allowed-write scope `[EvidenceLink, Hypothesis, ConfidenceChange]`. Add operation-specific provider/model/rate-card/output-bound validation; preserve Task/attempt attribution, cumulative budget enforcement, and known/unknown/overrun rules. The current service has no such operation, so RW-3 cannot reserve cost until this extension is implemented. Provider/model authorization must remain within ADR-0031; any expansion requires a separate decision.

**Required proof:** all applicable RW-2 commit proofs through the model entry path, plus Context isolation/integrity/determinism/bounds, malformed and oversized output, authority escalation attempts, reservation-before-call, provider failure, known/unknown/overrun cost reconciliation before commit, all-invalid and mixed batches, atomic rollback, replay, concurrency, admission ordering, and interrupted Task recovery. Ordinary CI uses a deterministic fake provider; live smoke tests, if later requested, are separate.

**RW3-0 design exit:** the six decisions in the RW-3 design plan are recorded: stable bounded Context selection with fail-closed overflow; Team Experience excluded; one host-invoked adapter without TaskDispatcher expansion; at most 8 model proposals while preserving accepted batch semantics; empty response as `success_no_change` after charge reconciliation; and parser failures separated from per-proposal domain rejections. The actor-neutral commit seam is explicitly identified. Independent design review must confirm consistency with the existing TaskRuntime, Task/Event, cost, and RW-2 contracts. RW3-0 completion is design approval only, not implementation authorization.

**RW-3 implementation exit (separate future gate):** the model can affect world memory only through the same application validation and commit path as `operator_update`; all RW-3 acceptance criteria and exact-head verification pass. This exit does not authorize RW-4 or RW-5.

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
| RW-HY-03 | Every new Hypothesis starts at low, including when evidence is supplied at creation; higher confidence requires a later Task-attributed ConfidenceChange. | Explicitly reject a proposal attempting an elevated initial band; prove low initial state and a later valid confidence change through Operator and model paths. | RW-2/RW-3 |
| RW-AT-01 | Valid proposals commit atomically as one set; invalid proposals are rejected with attributable Events, and the Task fails if all proposals fail. | Test an all-valid set, a mixed valid/invalid batch, and a failure during the valid-set transaction. Invalid proposals create no business writes; a failed valid-set transaction leaves none of that set committed. Preserve the accepted `docs/tasks.md` / `docs/architecture.md` semantics. | RW-2/RW-3 |
| RW-RP-01 | Task/proposal replay creates no duplicate evidence or state transition. | Repeated identical Task commit returns/reuses canonical result. | RW-2/RW-3/RW-4/RW-5 |
| RW-RC-01 | Concurrent updates cannot lose a Hypothesis/evidence change. | Repeated race test on one Thread; one winner or clean serialization, no lost update. | RW-2/RW-3 |
| RW-TS-01 | Cross-Team Thread, Hypothesis, Signal, and Snapshot references are rejected. | Database-backed negative tests for each reference type. | RW-1/RW-2/RW-4 |
| RW-LT-01 | last_touched_at changes only when evidence is accepted. | Accepted evidence updates it; mentions/rejected/replayed proposals do not. | RW-2/RW-3 |
| RW-DC-01 | Decay never rejects a Hypothesis and never changes last_touched_at. | Stale and boundary-time tests; no rejection transition; unchanged touch time. | RW-5 |
| RW-TR-01 | Triage is explicit and one-per-(Signal, Team). | Unique disposition, deferred refinement, dedup/noise/match/new-thread tests for frozen scope. | RW-4 |
| RW-CT-01 | Task Context includes only bounded, current, same-Team accepted world memory. | Context manifest, active-status, scope, bound, and stale-reference tests; RW-3 additionally proves target-Thread scope and exact source-Snapshot provenance. | RW-3/RW-4 |
| RW-GC-01 | Generation cost is reserved for the admitted `update_thread` Task attempt before provider invocation. | Prove reservation denial makes zero provider calls; reservation binds the exact Task, attempt, operation, provider/model, rate card, and write scope; duplicate reservation is rejected. | RW-3 |
| RW-GC-02 | A valid, reconciled current-attempt charge is a precondition to business commit. | Reconcile raw provider usage before parsing; prove known usage is accounted even when output JSON is malformed; unknown, unreconciled, model-mismatched, and overrun charges cannot reach the commit core or leave business writes; preserve the applicable charge state. | RW-3 |
| RW-GN-01 | The model worker uses only the authorized generation operation and provider configuration. | Prove operation-to-Task/write-scope mapping, provider/model/rate-card validation, token quote and output ceiling; reject unauthorized operation, Task type, scope, model, or quote. | RW-3 |
| RW-PR-01 | Provider output is strictly parsed and bounded before commit. | Reject malformed JSON, unknown fields, unsupported proposal types, invalid references, excessive proposal count, and output beyond the configured token cap; prove no business writes. | RW-3 |
| RW-PV-01 | Provider failure and retry behavior remains bounded and TaskRuntime-owned. | Fake-provider tests cover timeout/transport failure, zero business commit, exact retry eligibility and attempt accounting, no adapter-level retry, and recovery after interruption. | RW-3 |
| RW-ID-01 | Model output cannot override trusted identity or write authority. | Supply forged/conflicting Task, Team, Thread, policy, principal, budget, allowed-write, and attribution fields; prove they are rejected by the strict schema or ignored as untrusted data and cannot alter application-resolved authority. | RW-3 |
| RW-LC-01 | Task admission owns attempt-specific Context and generation work. | Prove admission precedes Context assembly; Context failure after admission is recorded through TaskRuntime without provider invocation; interrupted attempts recover without duplicate writes or charges. | RW-3 |
| RW-CT-02 | Canonical Thread Context selection is deterministic and bounded. | Seed equal-time/multiple Hypotheses and EvidenceLinks; prove stable ordering, exact Snapshot provenance, 8-item limits, 8,000-character evidence bound, and fail-closed overflow without provider call. | RW-3 |
| RW-CT-03 | Team Experience is excluded from the RW-3 Context. | Prove the worker makes no Team Experience retrieval call and no Team Experience passage enters the manifest. | RW-3 |
| RW-WK-01 | The worker uses one narrow host-invoked application adapter. | Prove it consumes an existing `update_thread` Task; TaskDispatcher remains ingestion-only; no second runtime or scheduler is introduced. | RW-3 |
| RW-PR-02 | Model proposal batches are bounded without changing the Operator contract. | Accept at most 8 model proposals; reject 9 before commit; prove `OperatorUpdateRequest` retains its existing 64-proposal limit and mixed-batch semantics. | RW-3 |
| RW-NO-01 | An explicit empty model proposal list is a successful no-op. | Reconcile charge first; finalize as `success_no_change`; prove no commit call, business writes, or retry. | RW-3 |
| RW-PF-01 | Parser failures and proposal-level domain rejections remain distinct. | Malformed/unknown/unsupported/forged/oversized responses fail through TaskRuntime without per-proposal rejection Events; typed domain-invalid proposals receive existing rejection Events; all-invalid and mixed-batch outcomes remain correct. | RW-3 |
| RW-ACT-01 | Model commits preserve trusted actor attribution without weakening RW-2 Operator identity. | Prove model actor is application-defined and Task-attributed; model-supplied actor/principal fields are rejected; Operator events and principal validation remain unchanged. | RW-3 |
| RW-VAL-01 | The newsroom scenario demonstrates a repeatable end-to-end reasoning and retained-experience path. | Frozen corpus, baseline/experience-assisted runs, independent scoring, exact run artifacts and results. | All / exit gate |
| RW-KU-01 | Each claim-level TaskKnowledgeReference is application-written and immutable, binds an identified output claim to the exact KnowledgeItem ID/version, originating LearningChange, relevant Team eligibility, and Task Context evidence. | RW-4-KU: exact-identity/version, LearningChange, Team eligibility, Context-manifest linkage, immutability, replay, and stale/invalid-reference rejection. Proposed test node: `tests/test_task_knowledge_reference.py`; finalize before RW-4-KU authorization. | RW-4-KU (planned; not authorized) |
| RW-KU-02 | KnowledgeUseAssessment is typed and application-validated against the exact claim reference/knowledge version and the later Task's terminal Outcome; it grants no mutation or decision authority. | RW-4-KU: typed-value validation, exact claim/version/terminal-Outcome/Team/Context binding, immutability, replay, and forbidden-write/scope rejection. Proposed test node: `tests/test_knowledge_use_assessment.py`; finalize before RW-4-KU authorization. | RW-4-KU (planned; not authorized) |

## 4.1 RW-1 physical design preparation

The [RW-1 physical design proposal](rw-1-physical-design-proposal.md) is the current design artifact for D132. A source/schema audit was completed against branch head `a8c6b489cfa9dba05ae143474d7a86399b4382a6`, including `core/models.py`, `core/evaluations.py`, `core/task_runtime.py`, and `core/experience_distiller.py`, plus a disposable PostgreSQL migration/schema audit through `0018_r7b_lifecycle_review_date`. No persistent database rows were inspected. The revised proposal records these source findings and recommends typed subject foreign keys behind one logical EvidenceLink model, non-null `originating_task_id` backfilled from the parent Evaluation Task under fail-closed migration checks, same-Hypothesis ConfidenceChange evidence FKs, Task-attributed supersession Events, initial `low` confidence, the existing Signal-domain eligibility rule, append-only ConfidenceChange records, and staged Artifact/Consultation support. The six decisions were explicitly accepted by the Operator on 2026-11-16; their exact terms are recorded in proposal §9.

RW-1 implementation was delivered by PR [#128](https://github.com/abtn/Watch-Architecture-Rev2/pull/128), merged at `7213a17e5ae96c3cae22ec1082af05d47b9c0d1d`. The merged slice adds Thread, Hypothesis, and ConfidenceChange persistence with PostgreSQL constraints; changes EvidenceLink to typed Evaluation/Hypothesis subject FKs; and backfills non-null legacy Task attribution with fail-closed validation. Migration proofs cover proposal-hash, Signal-domain, and EvidenceLink reference-hash failures; a focused model proof covers the initial `low` confidence default. This remains the RW-1 schema/ORM/migration slice: it does not implement the Operator or model commit path, triage, decay, or retrieval. Application-level Hypothesis evidence validation, confidence-cause semantics, cross-Team Signal/Snapshot checks, competing-Hypothesis behavior, lifecycle Events, atomic commit, replay, concurrency, and touch-time behavior remain assigned to their later slices; the aligned proof allocation is recorded in the RW-1 proposal §8 and the RW-EV-01/RW-EV-02/RW-EV-03/RW-TS-01/RW-HY-01/RW-HY-02/RW-AT-01/RW-RP-01/RW-RC-01/RW-LT-01 rows below. RW-1 merge and migration verification do not satisfy those later runtime proofs. Operator-local verification is recorded below and in `docs/testing.md`; hosted GitHub Actions run [#1247](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/43901592622) passed on the exact final code/test commit `aa947983fc72f771946ebf5b0d9a781aba80d7f3`. RW-1 was formally accepted by the Operator on 2026-11-18 within the documented physical schema/ORM/migration boundary. The earlier empty disposable audit did not establish that persistent historical rows pass migration validation; no persistent database was inspected for RW-1.

### RW-2 implementation record — pre-acceptance snapshot (historical)

This subsection preserves the implementation and verification record captured before RW-2's final review corrections and formal acceptance. It is historical, not the current acceptance record. RW-2 was subsequently corrected, accepted, and squash-merged as PR [#134](https://github.com/abtn/Watch-Architecture-Rev2/pull/134); the authoritative accepted-head evidence is in `PLAN.md` and `docs/testing.md`. The implementation path described here is the deterministic host-invoked Operator path:

- `core/world_memory.py`: typed proposal models, immutable request Event envelope, source/Team/Snapshot validation, atomic commit/rejection, replay proof, and interrupted-execution recovery proof.
- `core/operator_application.py`: host-principal grant check, ordinary manual Task creation, request fingerprint/idempotency, and synchronous adapter orchestration.
- `core/task_runtime.py`: Operator Task admission, terminal-result validation, finalization, and recovery integration through the existing TaskRuntime.
- `tests/test_world_memory.py`: PostgreSQL proofs for quote/hash/offset checks, source and Team scope, confidence causes, Hypothesis creation/transitions, competing Hypotheses, mixed/all-invalid proposal sets, atomic rollback, replay, concurrency, touch-time behavior, and recovery.

No migration or schema change is included. The Task writes only Hypothesis, EvidenceLink, and ConfidenceChange; Event and Outcome are Kernel/TaskRuntime side effects. SignalDisposition/triage remain RW-4; Thread-summary/retrieval projections remain deferred; Artifact/Consultation source rows remain staged until their canonical entities exist.

Hosted GitHub Actions run [#1357](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/44313224977) passed on exact current PR head `d5bc764b8196cbed1bff1681fa8b55a88f8cfb83`: fresh disposable PostgreSQL migration to `0019_rw1_world_memory`, Alembic single-head/current verification, Ruff, Mypy (39 source files), patch whitespace, and full suite (**1,103 passed, 130 existing Alembic deprecation warnings**). Programmer-local Windows verification passed on exact tested tree `9860281eff7e79c2a720df4b3d899884376f0b3e`: fresh disposable PostgreSQL migration; one Alembic head; 21 focused RW-2 tests; Ruff; Mypy (39 source files); full suite (**1,103 passed**); and `git diff --check`. The disposable container was removed and both database URL environment variables were restored. The local run emitted 130 existing Alembic `path_separator` deprecation warnings. The current PR head adds only a README change after the local test run. RW-2 was formally accepted by the Operator on 2026-11-18. The two correctness fixes and their deterministic PostgreSQL regression proofs are included in the accepted exact head. PR #134 merge disposition and resulting `main` SHA are recorded in `PLAN.md` and `docs/testing.md`.

D133 mapping is now explicit: both minimum D99 capabilities are assigned to the planned RW-4-KU sub-slice, with proposed test modules recorded in the proof matrix. These test paths must be confirmed and the proof rows completed before RW-4-KU authorization. This assignment is not implementation authorization and does not create a separate R7-C programme.

### RW-1 implementation proof nodes (PR #128; locally verified)

- `tests/test_evaluations.py::test_evaluation_propose_record_and_replay` — legacy Evaluation subject is stored through `evaluation_id`, with Task provenance, while the logical `subject_id` query remains compatible.
- `tests/test_evaluations.py::test_evaluation_record_rejects_changed_originating_task` — Task attribution cannot be changed before Evaluation recording.
- `tests/test_evaluations.py::test_hypothesis_evidence_uses_one_typed_evidence_link` — Hypothesis subject uses the same EvidenceLink model and the initial confidence default is `low`.
- `tests/test_evaluations.py::test_hypothesis_cannot_reference_another_teams_thread` — composite Thread/Team ownership FK rejects cross-Team Hypotheses.
- `tests/test_evaluations.py::test_confidence_change_evidence_fk_is_bound_to_same_hypothesis` — composite EvidenceLink/Hypothesis/Team FK rejects a mismatched evidence cause.
- `tests/test_rw1_schema_migration.py::test_0019_backfills_typed_subject_and_task_without_changing_legacy_rows` — populated legacy EvidenceLink identity and provenance survive upgrade.
- `tests/test_rw1_schema_migration.py::test_0019_refuses_proposal_hash_mismatch_and_rolls_back_schema` — a legacy proposal-hash mismatch aborts and leaves revision/schema at 0018.
- `tests/test_rw1_schema_migration.py::test_0019_refuses_signal_domain_mismatch_and_rolls_back_schema` — a legacy Signal from another domain aborts before the old representation is removed.
- `tests/test_rw1_schema_migration.py::test_0019_refuses_evidence_reference_hash_mismatch_and_rolls_back_schema` — a tampered legacy EvidenceLink reference hash aborts transactionally.
- `tests/test_rw1_schema_migration.py::test_0019_backfills_multiple_links_in_canonical_reference_order` — a multi-link Evaluation proves canonical ordering and complete typed-subject/Task backfill.
- `tests/test_rw1_schema_migration.py::test_0019_downgrade_refuses_hypothesis_confidence_history` — downgrade refuses to discard Hypothesis EvidenceLink and ConfidenceChange history.
- `tests/test_rw1_schema_migration.py::test_0019_downgrade_refuses_world_memory_then_restores_legacy_shape` — downgrade refuses to discard Thread history and safely restores the Evaluation-only shape when empty.

The PR #128 proof nodes above are supplemented by test-only PR [#132](https://github.com/abtn/Watch-Architecture-Rev2/pull/132), which adds focused PostgreSQL negative proofs in `tests/test_evaluations.py`:

- `test_rw1_thread_status_check_rejects_invalid_values`
- `test_rw1_hypothesis_vocabulary_checks_reject_invalid_values`
- `test_rw1_evidence_subject_check_rejects_missing_dual_and_mismatched_subjects`
- `test_rw1_evidence_source_check_rejects_missing_dual_and_mismatched_sources`
- `test_rw1_confidence_change_cause_check_rejects_invalid_cause_shapes`
- `test_rw1_confidence_change_checks_reject_unknown_cause_kind`
- `test_rw1_evidence_subject_and_task_fks_enforce_team_ownership`

Hosted CI run [#1269](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/44087840152) and Operator-local verification passed on the then-exact test head `61fa0a214e05993637695e75d8aa019449fc540d`, including fresh disposable PostgreSQL migration/single-head checks, Ruff, Mypy, patch whitespace, 31 focused tests, and the full suite (**1,029 passed, 130 existing Alembic deprecation warnings**). The new tests add 16 parameterized database-negative cases across the declared CHECK/FK constraints. The change is test-only. PR #132 was subsequently updated with `main` after PR #133 merged; its current head is `3c77a52af6b4fc619b6274fadabb97f3738248c5`. Hosted CI run [#1309](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/44265244934) passed on that exact updated head, including disposable PostgreSQL migrations, Alembic single-head verification, Ruff, Mypy, patch whitespace, and the full test suite. Operator-local verification on exact head `3c77a52af6b4fc619b6274fadabb97f3738248c5` also passed: fresh disposable PostgreSQL migration to `0019_rw1_world_memory`, 31 focused Evaluation tests, Ruff, Mypy (38 source files), full suite (**1,082 passed, 130 Alembic `path_separator` deprecation warnings**), and patch whitespace. The disposable container and anonymous volume were removed; follow-up confirmed both database URL variables empty, exact branch/HEAD intact, and worktree clean. The script's final environment-equality assertion reported a mismatch after cleanup, so exact restoration of the pre-run variable state is not claimed. The Operator separately recorded formal RW-1 acceptance on 2026-11-18; do not infer acceptance from green CI alone. Test-only PR #132 was squash-merged on 2026-11-18 at `a16a931ea79e915323447a1379cd0d9fe7063fb8`; documentation PR #131 was squash-merged the same day at `db5f19928f0a853df244da465e50b26fa848309d`. These merges close the schema-negative test and documentation follow-ups; they do not authorize RW-2 or waive any remaining proof-matrix row.

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
- RW-D132 is accepted. Keep all RW-1 schema and migration work within the accepted physical design and fail-closed legacy-data migration gate; stop if implementation would require changing an accepted decision.
- Before authorizing a slice that implements D99 capabilities, assign the relevant RW-KU proof rows to that named slice and replace their placeholders with exact test nodes or approved non-automated evidence.
- Report both the verified implementation SHA and current PR head, each with its CI evidence. Never transfer a test result to a different SHA.
- Re-audit implementation markers after B6 and after each RW slice. A specification or Task allow-list is not implementation evidence.
- Do not begin R8 until the foundation exit gate is explicitly accepted.
