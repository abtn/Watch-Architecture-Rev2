# RW-4 Readiness and Delivery Plan

**Status:** Active staged-delivery baseline. D1 and all six D2 decisions were accepted on 2026-11-24. D3-A/B/C were accepted on 2026-11-25 and reconciled: no invented Signal lifecycle state; eligibility derives from canonical Signal/Snapshot provenance plus active-Team, authorization, and source/domain/policy checks; existing Team/Signal disposition excludes another v1 decision; TaskRuntime owns lifecycle; terminal deferred is immutable and completes its Task as done, while technical failure remains failed/retryable under TaskRuntime. D4/D5/D6 and D4b actual pin values remain outstanding. Exact migration design/proofs remain outstanding. No individual production slice is blanket-authorized.
**Planning baseline:** `main` after PR #187 squash merge `94563be9e551ebf73faee626d952e9b839b57946` (2026-11-25); PR #184 is the earlier D1/D2 proposal baseline.
**Status authority:** `PLAN.md` remains the only authority for milestone status and authorization. This document owns the dependency-aware RW-4 readiness checklist and delivery sequence.
**Sequencing decision:** [RW-4/RW-5 sequencing decision](rw-4-rw-5-sequencing-decision.md) records the approved 2026-11-24 RW4-2-first serial order.
**Scope:** Reconcile the evidence audit in PR #175, the bounded RW4-0 proposal in PR #174, the minimal matching proposal in PR #176, the RW-4 design plan, Task specifications, and architecture.

## 1. Executive decision

The Operator's 2026-11-24 sequencing exception satisfies the overall RW3.4 sequencing gate while preserving formal acceptance as deferred and all seven PARTIAL qualifications. RW4-0 remains open. PR #176 is a merged design proposal, not acceptance of its experimental matcher or closure of D4–D6; D1/D2 and D3 are accepted, with implementation gates still separate. No individual RW-4 slice is blanket-authorized: each must satisfy its own prerequisites, independently reviewed proof subset, and explicit Operator authorization. PR #175's evidence findings are incorporated here; its audit branch is closed and is not a current baseline.

The delivery path is deliberately serial. The updated Operator order supersedes the earlier RW-5-first order:

1. **RW4-2 design/decision stage:** D1 is accepted: the Control Room is the single Task-creation authority; only active Teams are eligible; production host authentication is required before production use and scheduled after the R8 test; URL normalization is deferred until after the R8 test (exact comparison remains current, with hostname-case-only normalization proposed for later); greatest-version TeamPolicy selection under the canonical Team lock fails closed. All D1/D2 decisions are accepted. Reconcile the accepted contract across the specification and proof matrix, then review/freeze the exact Task-creator specification and implementation proof subset. This remains documentation/decision work only; it does not implement or enable the creator. The frozen creator protocol must explicitly require PostgreSQL READ COMMITTED and reject REPEATABLE READ/SERIALIZABLE before application data access. The triage-only BEFORE INSERT trigger guarantees Team-lock participation only; it does not enforce Control Room-only creation or attest writer origin. D1 remains a trusted-application-code boundary, with out-of-band SQL writers operationally excluded. Migration design, existing-writer compatibility, and PostgreSQL proof remain required before separate authorization.
2. **RW4-1 — SignalDisposition persistence:** follow the RW4-2 D1/D2/D3 design gates; D3 is accepted, but D5's complete disposition vocabulary/reference matrix remains required before implementation. Implement only the bounded persistence slice and preserve linear Alembic history. D3 acceptance does not authorize this migration or implementation.
3. **RW-5 canonical lock helper, Team revision, and writer retrofit:** separately authorize the migration and RW3.4-adjacent WorldMemoryCommitService/Operator compatibility changes; prove every supported writer through real entrypoints. This must land before the RW4-2 creator and RW4-3.
4. **RW4-2 creator implementation:** return to the RW4-2 implementation stage only after RW4-1 and the canonical helper/Team-revision/writer retrofit have landed and passed real PostgreSQL lock tests. Reuse the one canonical helper; no bespoke lock path.
5. **RW4-3 — deterministic matching and commit:** requires the RW4-2 creator, accepted D4/C1/D5, and the helper from step 3. No dormant reactivation, new Thread creation, noise classification, or near-duplicate classification.
6. **RW-5 decay implementation:** follow RW4-3; scheduler/host invocation remains a separate RW5-P gate.
7. **RW4-4 — bounded Context retrieval:** only after its own Context-consumer gate and Experiment A disposition.
8. **D6 / RW4-5:** dormant reactivation and integrated race proof only after explicit D6 acceptance.

This supersedes the earlier 2026-11-24 RW-5-first order and clarifies the later RW4-2 creator dependency without changing the Operator's RW4-2-first design/decision priority. RW4-2 is deliberately split: D1/D2 specification and decision closure first; RW4-1 persistence next; RW-5 helper/Team revision/writer retrofit next; then RW4-2 creator implementation; then RW4-3. This split is required because the creator must use the canonical helper, while RW4-1 does not depend on the creator. It is a review-load and migration-linearity constraint, not a claim that unrelated work is technically dependent. Only one production implementation stream may be active. No production implementation starts without its own reviewed spec, accepted prerequisites, explicit authorization, exact-head hosted CI, and Programmer-local disposable-database verification.

### RW3.4 PARTIAL residual touchpoint map

These are slice touchpoints, not blanket blockers. Carry a row into a slice's proof subset only when that slice changes or relies on the corresponding contract; do not relabel any row PASS.

| RW3.4 PARTIAL row | RW-4 / RW-5 touchpoints | Handling |
|---|---|---|
| RW-REQ-01 — production host authentication/composition | RW4-2 D1 trusted principal/grant boundary and active-Team replay check; RW4-3 commit authority; RW-5 Operator-authorized bootstrap/rebase | Prove Watch-side validation only. Deployed host authentication remains external; do not fabricate it. |
| RW-POL-01 — production TeamPolicy publisher/lock serialization | RW4-2 immutable policy pin; RW4-3 under-lock policy revalidation; RW-5 Team revision helper and writer retrofit | Test supported writer/lock compatibility in the RW-5 retrofit. Production publisher remains external unless separately implemented. |
| RW-CTX-06 — broader Context tuple/state coverage | RW4-3 evidence-profile/provenance inputs; RW4-4 Context membership and provenance | Add only directly relevant tuple/state cases. The broad cross-product remains residual until separately proven. |
| RW-REPLAY-01 — duplicate write outcomes across replay states | RW4-2 Task/request-Event replay; RW4-1 disposition uniqueness; RW4-3 C1 receipt and business-commit replay; RW-5 decay Task replay | Prove each slice's supported replay boundary; do not claim the entire RW3.4 replay matrix is closed. |
| RW-RT-02 — deadline/recovery boundary | RW4-2 TaskRuntime attempt/deadline contract; RW4-3 receipt recovery; RW-5 bounded decay transaction and TaskRuntime finalization | Preserve existing fail-closed behavior; prove only the new supported recovery paths. |
| RW-REC-01 — locked Session/Task/attempt matrix | RW4-2 Task/attempt fencing; RW4-3 receipt/business commit locks; RW-5 shared lock helper and Task lock | Add focused real-session lock/revalidation tests for changed paths. |
| RW-RP-01 — repeated recovery idempotency | RW4-2 creator replay; RW4-3 receipt and business-result replay; RW-5 decay replay/supersession | Assert repeated calls are no-ops for each new path; broad historical outcome matrix remains PARTIAL. |


### Per-slice implementation and review discipline

Apply this sequence to every production slice:

1. Write a one- or two-page slice spec: goal, non-goals, files/surfaces, migration yes/no, focused and regression tests, and applicable RW3.4 residual rows. Reference the accepted threat model and shared contracts; do not reopen them without a named blocker.
2. Run one bounded spec review against the invariant/blocker rubric.
3. Obtain explicit written Operator authorization for that exact slice and scope.
4. Implement test-first as a thin vertical slice. Before pushing, run the focused tests, full suite, Ruff, Mypy, and required disposable-PostgreSQL checks locally; record exact branch and HEAD, cleanup, environment restoration, and worktree state.
5. Obtain one bounded PR review from a named reviewer who did not author the implementation. Review only regressions, factual contradictions, or demonstrated supported-path invariant failures. Any third round requires explicit Operator authorization and a named blocker.
6. Generate the PR verification/description section from the completed CI run and exact tested commit. Do not hand-edit test counts, statuses, or verification claims.
7. Merge only after local and hosted evidence agree; then update PLAN.md and the relevant proof matrix. Move out-of-rubric concerns to the residual register with a concrete trigger.

The RW-5 contract's final bounded regression review was performed by the editing agent, not an independent code reviewer. That was accepted as a documentation-contract review under the Operator's stated rubric; it is not a precedent for implementation PRs. Code PRs require the independent named reviewer above.

## 2. Current evidence baseline

- **PR #174** records bounded D1–D6 proposals; it did not close RW4-0 or authorize implementation.
- **PR #175** found: D1 host-invoked Task-creator precedent but no production host composition/authentication; D2 canonical Task identity needs DB uniqueness and is not the existing `update_thread` identity; D3 conflict between deferred-refinement prose and the proposed terminal-deferred contract; D4 matching inputs are not source-ready; D5 no safe canonical Signal title for Thread creation; D6 no shared RW-5 timestamp/lock contract.
- **PR #176** proposes a minimal representation: derive Thread evidence from EvidenceLink → Hypothesis → Thread; require same-Team ingestion provenance and matching Snapshot provenance; exact-hash duplicate detection within one Team; reuse KnowledgeChunk projections; keep maximum-pairwise cosine experimental only; first-slice outcomes `matched`, `duplicate`, `deferred`; disable `new_thread` and automatic `noise`; and require a separately committed canonical assessment receipt before the Kernel business commit.
- **RW3.4** implementation and corrective proofs are merged, but formal acceptance is deferred. The ledger remains 28 PASS / 7 PARTIAL / 0 OPEN. The bounded residual proof work and external integration limitations remain as recorded in `PLAN.md`.
- **RW-5** is independently implementable. Its integration with triage is blocked on D6 timestamp and concurrency decisions, not on all RW-5 work.
- **Experiment A** informs RW4-4 representation only. Its canonical fixtures are offline artifacts; the experiment has not been executed. It does not block RW4-0 through RW4-3 or RW-5.
- **RWN-01** is a separate newsroom value-harness package and is not a substitute for matching fixtures or Experiment A.

## 3. Staged readiness gates and authorization

RW4-0 is the umbrella design-closure milestone: it closes only when D1–D6 and the cross-cutting contracts are reconciled, evidence-backed, and explicitly accepted. **That does not mean every D1–D6 deliverable blocks every implementation slice.** A slice may begin under its own narrower gate while RW4-0 remains open, provided the overall RW3.4 gate and that slice's prerequisites have been satisfied and the Operator explicitly authorizes that slice.

### Gate A — RW3.4 formal disposition

Current disposition: **formal acceptance deferred; sequencing exception approved on 2026-11-24**.

The seven PARTIAL rows remain outstanding. The exception removes formal RW3.4 acceptance as a universal blocker for independently gated RW-4/RW-5 work; it does not close or downgrade any row. Carry a residual into an RW-4/RW-5 PR only when that slice changes or relies on the same contract, and add the directly relevant proof. Keep unrelated residuals in the RW3.4 ledger. `RW-REQ-01` (production host authentication/composition) and `RW-POL-01` (production TeamPolicy publisher/lock serialization) remain external integration boundaries; do not fabricate either integration. The local PR #169 environment-restoration assertion failure remains a qualification; do not rerun the 1,296-test suite solely for that script defect.

The bounded proof questions remain recorded for possible later disposition: broader Context identity tuple/recovery-state coverage; targeted duplicate/future commit and rejection-marker outcomes where existing guards require them; and the supported in-session attempt contract. Do not build an exhaustive Cartesian recovery matrix or reopen merged production code without a demonstrated defect.

**Exit:** the overall sequencing gate is satisfied for staged RW-4/RW-5 progression by this explicit exception, while RW3.4 remains formally unaccepted. Each implementation slice still requires its own accepted prerequisites, reviewed requirement-to-test subset, and explicit Operator authorization.

### Gate B — RW4-0 decision closure

RW4-0 closes only after D1–D6 are reconciled, evidence-backed, and explicitly accepted. PR #174 and #176 preserve proposals; neither substitutes for this gate. The staged slice gates below allow bounded implementation to proceed before umbrella RW4-0 closure only where explicitly stated; they do not imply that the remaining decisions are accepted.

#### D1 — Trusted host invocation and authority

Freeze an explicit trusted host-invoked operation for one Signal and one Team. Define trusted principal fields and the exact Team/action grant checked by Watch. The caller cannot select a Team from untrusted payload data. Every caller is independently authorized, including a caller resolving an existing Task. Both creation and replay require the Team's persisted state to be exactly `active`; replay rechecks this under the Task → Team lock order before disclosing/resolving the Task.

No automatic `ingest_source → triage_signal` Task creation, scheduler, or TaskDispatcher expansion in the first slice. The production host composition/authentication boundary remains external; Watch-side grant validation is not proof of deployed host authentication.

### D2 — Canonical Task and disposition identity

Keep three identities distinct: (a) business identity `(signal_id, team_id)`; (b) the accepted deterministic Task identity, UUIDv5 under namespace `383bbdde-37be-4895-8fb7-1afa196b5cf7`, with canonical name `triage_identity_v1|triage_signal|team:<team-uuid>|signal:<signal-uuid>`; and (c) immutable request provenance/fingerprint. The accepted golden vector is Team `00000000-0000-4000-8000-000000000001`, Signal `00000000-0000-4000-8000-000000000002`, Task `5b45ed53-a50f-51e8-ba81-ce52512aa922`. The UUID primary key rejects a second insert using the same canonical UUID, but does not enforce logical-pair uniqueness against a writer supplying a different UUID. **Accepted v1 canonical-identity guarantee:** persist `signal_id` and `identity_version` on triage Tasks and add a database unique constraint on `(team_id, signal_id, identity_version)`, while retaining the canonical UUIDv5 primary key, one narrow creator, and recompute-on-load validation. The triage Task must require these identity fields; callers cannot supply or override them. The current audited Task schema has neither persisted identity column nor the pair-level constraint, so this guarantee requires a Task-schema migration that adds both columns and the composite constraint, with the applicable triage-row constraints and validation. It is not a no-migration option or equivalent to a single-creator-only application invariant. Re-audit the schema and assess migration/writer compatibility against the implementation PR's base and head before Stage B. The Operator accepted the Task-schema migration and composite constraint on 2026-11-24. Exact migration/preflight/backfill and writer-compatibility design remain implementation review requirements. The Operator also accepted the partial unique request-Event index, atomic Task/Event creation, and replay validation; duplicate-history preflight and PostgreSQL proof remain required. The index enforces at-most-one; atomic creation establishes existence and replay validation verifies exactly one. Same-pin replay/original-requester provenance, changed-pin conflict, v1 identity occupancy, separately approved v2, immutable first-writer watermark semantics, and code-owned v1 matching-pin ownership are accepted. D4b still supplies actual pin values. Freeze atomic Task/request-Event creation, same-request replay, and conflict behavior. Requester identity is provenance, not semantic equivalence, as recorded in the PR #174 correction.

Separately freeze SignalDisposition uniqueness for `(signal_id, team_id)`, its canonical persisted identity, Task attribution, reason, timestamp fields, and database constraints. The immutable Task request must pin Team ID, Signal ID, canonical Signal Snapshot reference and hash, TeamPolicy version, matcher identifier/version, embedding-space key, and chunking version. Same-request replay compares semantic pins while excluding requester identity and first-writer `as_of`/Team revision metadata; it validates and returns the original provenance and watermark unchanged. A changed semantic pin conflicts. The existing `update_thread` idempotency namespace is precedent for transaction/replay shape only; it must not be reused as triage identity.

### D3 — Deferred lifecycle and Task write-scope reconciliation — ACCEPTED 2026-11-25

D3-A/B/C are accepted and reconciled across the RW4-2 specification, Task definition, architecture lifecycle summary, and Task/write-scope matrix. Signal has no lifecycle/status column; eligibility derives from canonical Signal/Snapshot integrity and provenance plus active-Team, caller-authorization, and source/domain/policy checks. Existing Team/Signal disposition excludes another first-release decision. TaskRuntime owns lifecycle; `done`/`failed` are terminal and v1 identity remains occupied. A valid deferred disposition is immutable/terminal and its Task completes successfully as `done`; technical failures follow TaskRuntime retry/recovery and may end `failed`. The `update_thread` and `operator_update` SignalDisposition write permissions are removed. D5 still owns the complete vocabulary/reference matrix, and D6 owns dormant-Thread reactivation. D3 acceptance does not authorize RW4-1 persistence or RW4-2 creator implementation.

### D4 — Minimal matching representation and evidence

Use the PR #176 representation as the bounded experimental candidate:
- derive Thread evidence profiles at read time through Team-scoped EvidenceLink → Hypothesis → Thread;
- preserve Hypothesis lifecycle state and EvidenceLink stance for analysis;
- validate every incoming and historical Signal's same-Team ingestion Event and exact Signal/Snapshot/hash association;
- validate EvidenceLink Snapshot reference/hash against its canonical Signal Snapshot; absent provenance is excluded, partial/corrupt/conflicting provenance fails closed;
- detect exact raw content-hash duplicates only within the Team's own intake history, with a deterministic canonical winner;
- use current KnowledgeChunk projections with pinned embedding-space and chunking identities;
- do not introduce Thread embeddings, summary projections, entity/alias tables, or a general Domain subsystem.

Maximum pairwise chunk cosine similarity is an **experimental heuristic only**. It is vulnerable to high-scoring outlier chunks and larger-profile bias. Do not accept a numeric threshold or margin without labeled fixture evidence.

Required offline fixtures: same-origin replay; cross-origin exact bytes within one Team; same hash across Teams; near-duplicate syndicated copy; clear match; broad-topic hard negative; multiple candidates/ties; dormant and resolved Threads; mentions-only and no-evidence Threads; active/superseded/rejected Hypotheses; supporting/challenging stances; missing/stale/mismatched/corrupt projections and Snapshots; same-Domain cross-Team provenance; candidate/evidence scan overflow; threshold/margin boundaries; high-scoring outlier chunks; multiple Hypotheses/subtopics; and differently sized evidence profiles.

Labels must be independent of the matcher. Report false positives and false negatives by case, lifecycle state, and profile size. Measure eligible candidate/evidence cardinalities, bounded overflow detection, query plan, and cost on a disposable PostgreSQL fixture database. Never rank a truncated set as complete. If acceptable false-positive tolerance or query cost cannot be demonstrated, keep matching deferred or narrow the first slice; do not tune by intuition.

### D5 — Disposition vocabulary and Thread-creation eligibility

The PR #176 first-slice proposal is:
- `matched`: one existing same-Team/domain Thread;
- `duplicate`: one canonical exact-content duplicate in the same Team's intake history;
- `deferred`: explicit reason and terminal in this release.

`new_thread` is disabled because no safe canonical title source exists. Automatic `noise` is disabled because no deterministic source-backed classifier exists. Near-duplicate classification is excluded. The exact duplicate canonical-winner rule, intake-history scope, and valid reference combinations still require explicit acceptance.

Freeze every disposition/reference combination and its Task-attributed Event semantics. No disposition may mutate Hypothesis, EvidenceLink, ConfidenceChange, TeamPolicy, or enqueue follow-up Tasks. If a later release wants `new_thread` or `noise`, it needs a separate source-backed rule and design decision.

### D6 — Dormant Thread reactivation and RW-5 contract

Agree before RW4 reactivation implementation:
- whether matching/reactivation changes a Thread-level timestamp;
- which timestamp is authoritative, if any;
- whether a reactivated Thread can immediately become dormant under unchanged Hypothesis touch times;
- the durable recovery/reconsideration behavior for every lifecycle transition that can make a Thread unavailable to triage; dormancy must not ship before this path exists;
- exact rows/records locked by triage and decay, including Task FKs on both Hypothesis EvidenceLink and ConfidenceChange writes;
- database-captured non-decreasing time, Team revision watermark, epoch/cutover baseline, and per-Hypothesis history-watermark semantics;
- exact lock modes (Task `FOR UPDATE`; Team/Thread/Hypothesis `FOR NO KEY UPDATE`), canonical one-at-a-time sorted lock helper, new-path session guard, and under-lock revalidation;
- decay-first and triage-first outcomes;
- replay behavior and at-most-one reactivation Event.

Decay age is reconstructed from immutable accepted supporting/challenging EvidenceLink history and the immutable current-epoch baseline; `Hypothesis.last_touched_at` is only a mutable cache/prefilter and is never historical authority. A pre-epoch EvidenceLink timestamp cannot anchor decay in a later epoch. Only a newly accepted eligible EvidenceLink in the current epoch replaces that epoch's baseline anchor. Decay does not update `last_touched_at`, and triage must not use it as a proxy for Thread activity. The RW-5 shared contract is authoritative for clock, epoch, evidence-age, and locking semantics; RW-5 implementation remains its own serial engineering stream.

### Cross-cutting gate — Assessment receipt and recovery

Freeze the PR #176 C1 contract before code:
- one canonical assessment receipt per Task, identity derived from Task plus fixed assessment kind/version and explicitly **independent of Task attempt** (retries/attempts reuse the same receipt identity);
- database-enforced uniqueness on the canonical `(task_id, assessment_kind, assessment_version)` identity, not application pre-check only;
- concurrent losing attempts load and validate the winning receipt;
- request/schema/assessment fingerprints are validated;
- receipt and identity commit in a transaction that completes **before** the distinct Kernel business-commit transaction begins;
- TaskRuntime remains the only attempt, retry, interruption, and recovery authority;
- valid receipt replays exactly without rerunning matching;
- absent receipt follows existing retry/recovery policy; corrupt, duplicate, or mismatched receipt fails closed;
- committed business result replays without a second disposition, Thread transition, or Event.

Define the exact Event schema, unique identity, Task type/write scope, Kernel path, transaction ownership, and recovery proofs. A shared receipt/business transaction is not equivalent to durable-before-business ordering.

### Cross-cutting gate — Later Task Context consumer and representation

Name the later Task type that consumes world-memory Context and the existing assembler to extend. Define Team/Thread scope, eligible active Hypotheses and EvidenceLinks, source/Snapshot/hash/quote validation, interaction with Domain Knowledge and Team Experience, deterministic order, count/character/token bounds, overflow behavior, immutable Context Snapshot/manifest Event/hash, and replay.

Do not broaden RW-3's target-Thread Context or create a parallel Context subsystem. Experiment A informs only the RW4-4 model-facing evidence representation. Before RW4-4 freezes it, use an accepted result or an explicit Operator disposition with rationale and residual uncertainty.

### Gate C — Requirement-to-test matrix and implementation authorization

Before each production RW-4 slice, freeze and independently review that slice's requirement-to-test subset. Maintain the complete RW-4 matrix as the umbrella proof plan; exact test node IDs and tested SHAs are added as each slice is implemented. The complete integration matrix must be frozen before RW4-5.

At minimum map:
- host authority, Team grant, active-Team eligibility on both creation and replay, canonical Task identity, database-enforced Team-lock participation for triage inserts, race, replay, conflict;
- Signal/Team ownership and disposition uniqueness;
- Signal and EvidenceLink Snapshot/hash provenance;
- each allowed and prohibited disposition/reference combination;
- duplicate canonicalization and matching thresholds/ties/overflow;
- receipt uniqueness, separate transaction durability, and recovery;
- atomic deferred disposition, Task attribution/reason, TaskRuntime Outcome, terminal Task status, and terminal Event commit/rollback in one TaskRuntime-owned transaction;
- fail-closed replay when a disposition exists without exactly one valid canonical Task/request Event; no synthesized history or replacement;
- TaskRuntime terminal supersession of stale-pin queued Tasks using the existing failed/terminal_failure path and a stable non-technical supersession reason;
- no dormant-Thread reactivation before D6 acceptance;
- dormant reactivation and decay races;
- Context membership, provenance, ordering, bounds, and replay;
- no direct Task lifecycle writes, unapproved follow-up Task creation, or dispatcher expansion;
- disposable-PostgreSQL migration/constraint proofs.

**Overall project gate before any RW-4 production implementation:** RW3.4 formal acceptance or an explicit sequencing exception, with residuals retained.

**Staged slice gates (each also requires a reviewed requirement-to-test subset and explicit Operator authorization):**

| Slice | Required decisions/evidence before that slice |
|---|---|
| **RW4-2 — Task boundary** | **Design/decision stage:** D1/D2, immutable request pins, identity/replay contract, Task envelope, and proof subset accepted; no production creator code. **Creator implementation stage:** after RW4-1 and the RW-5 canonical helper/Team-revision/writer retrofit have landed, with PostgreSQL lock proof; then separately authorize the creator. The two stages are serial and must not be collapsed. |
| **RW4-1 — persistence** | D3 lifecycle semantics are accepted. Before implementation, D5 disposition vocabulary/reference matrix, uniqueness scope, and physical constraints must be accepted; the persistence design must integrate deferred disposition writes into the existing TaskRuntime-owned terminal transaction (same Session/commit as Task Outcome/status/Event), with rollback proof and no independent disposition commit. No matching algorithm, D6 reactivation, receipt, or Context decision is required for this persistence-only slice. |
| **RW4-3 — matching and commit** | D4 matching/duplicate evidence and measured query cost accepted, or a narrower deterministic subset explicitly accepted; C1 receipt/recovery contract accepted; stale-pin TaskRuntime supersession mapping and no-retry proof accepted before enabling execution. D6 shared timestamp/lock/revalidation contract is required before any dormant-Thread reactivation; if reactivation is excluded, D6 does not block unrelated matching/commit work. |
| **RW4-4 — Context** | Named later Task consumer, existing assembler, eligible records, provenance, bounds, overflow, snapshot/manifest and replay contract accepted; Experiment A result or explicit Operator disposition recorded before representation freeze. |
| **RW4-5 — integration** | RW4-1 through RW4-4 accepted as applicable, RW-5 decay implementation available, D6 accepted for reactivation, and integrated race/post-decay retrieval proof completed. |

RW4-0 umbrella closure remains a separate milestone requiring D1–D6 and cross-cutting contracts to be fully reconciled and accepted. A staged implementation does not close RW4-0 by implication.

## 4. Serial delivery and independent preparation

The approved serial delivery order is RW4-2 Stage A (design/decision) → RW4-1 → RW-5 canonical lock helper/Team revision/writer retrofit → RW4-2 Stage B (creator implementation) → RW4-3 → RW-5 decay → RW4-4 → D6/RW4-5. Only one production implementation stream may be active. Preparation that does not alter the implementation stream may continue independently.

### RW-5 — deterministic decay

The shared RW-5 clock, decay, and locking contract is frozen in PR #182. Its implementation follows RW4-3 and remains separately gated; RW5-P periodic host/scheduler integration is also a separate gate. Before RW-5 decay implementation, prove:
1. a typed idempotent `apply_decay` Task creator and the separate RW5-P periodic host/scheduler integration gate;
2. one database-captured UTC `as_of` persisted in an immutable canonical Task request and reused on retry/recovery;
3. evidence age reconstructed from accepted EvidenceLink and ConfidenceChange history, with mutable current-state fields used only as accelerators;
4. inclusive decay-window boundaries, deterministic catch-up, and cross-Task database uniqueness;
5. database-enforced immutable request records, identity, and common Task → Team → sorted Thread → sorted Hypothesis lock order;
6. under-lock history/state/policy revalidation, decay/triage race outcomes, and bounded lock/query/transaction work;
7. a TaskRuntime-owned atomic business commit, summary Event, Outcome, and terminal Task transition, proven with transaction fault injection.

RW-5 first release changes confidence only. It does not transition Threads to dormant. Dormancy is prohibited until D6, a durable RW-4 reactivation/recovery path, and separate authorization exist. `last_touched_at` is not historical authority and decay never changes it. RW5-P remains a separate host integration and must be accepted before foundation exit/R8 can claim autonomous periodic decay. TaskRuntime remains the sole lifecycle/recovery authority.

### Experiment A

Preparation and offline protocol work may proceed independently. Its scope is limited to informing RW4-4 representation. The merged canonical fixture package is not an executed experiment. Provider/model execution requires separate explicit authorization. Before RW4-4 representation freeze, record either the accepted experiment result or an explicit Operator rationale and residual uncertainty. Before foundation exit/R8, retain an accepted report or explicit inconclusive/not-required disposition with limitations.

### RWN-01

RWN-01 is the separate newsroom value-harness scenario. Freeze publisher PDF and Supplementary Material review, corpus manifest, task brief, answer key, independent outcome set, scoring examples, reviewer calibration, and execution configuration before scored runs. It is not a prerequisite to starting RW-4 and is not a substitute for matching fixtures or Experiment A.

## 5. RW-4 implementation sequence

Each stage has its own reviewed scope, acceptance evidence, and explicit authorization.

### RW4-2 — Triage Task boundary (two-stage delivery)

**Stage A — design and decisions (first):** D1 and all six D2 decisions are accepted. The accepted contract includes the Task-schema logical-pair constraint and request-Event partial unique index; same-pin replay/provenance and re-triage rules; immutable first-writer watermarks; and code-owned v1 matching pins. Freeze/review the full creator contract, migration/preflight design, existing-writer compatibility, lock-path contract, and proof subset. Actual matching-pin values remain for D4b. This stage creates no production code.

**Stage B — creator implementation (deferred):** only after RW4-1 persistence and the separately authorized RW-5 canonical lock-helper/Team-revision/writer retrofit have landed with real PostgreSQL lock proofs. Implement the host-invoked creator and TaskRuntime-owned boundary: atomic Task/request Event, canonical helper paths, database/race behavior, fingerprint/replay/conflict rules, exact Task envelope, admission/failure/recovery. Obtain separate explicit implementation authorization.

Keep TaskDispatcher unchanged. Do not add automatic post-ingestion enqueueing.

### RW4-1 — SignalDisposition persistence

Implement the accepted physical representation only: ORM, migration, one row per Signal/Team, Team-isolation and reference constraints, Task attribution, reason, timestamps, indexes.

Proof: fresh disposable PostgreSQL migration; uniqueness/FK/check violations; cross-Team/domain rejection; all valid/invalid reference combinations; upgrade compatibility; no unapproved changes to Signal, Thread, or EvidenceLink semantics.

### RW4-3 — Deterministic triage and commit

Implement only the evidence-approved duplicate/matching rules: bounded candidate/evidence retrieval; same-Team ingestion and Snapshot provenance; deterministic result/reason; canonical durable assessment receipt; separate receipt transaction; Kernel-authorized business commit; and atomic disposition/Event commit. Matched active-Thread handling may proceed under the accepted D4/C1/D5 contracts. **Dormant-Thread reactivation is a separately gated addition:** after D5 is accepted and until D6 is accepted, dormant candidates must not be reactivated or receive a `matched` disposition that implies reactivation; resolve them only through the terminal `deferred` disposition with an explicit D5-approved reason. Do not change Thread status/activity timestamps or emit a reactivation Event in this variant.

Proof for the non-reactivation slice: positive/negative fixtures, threshold/tie/overflow, duplicate and concurrent request replay, receipt recovery across the two transactions, rollback, no Hypothesis/EvidenceLink/ConfidenceChange mutation, and no automatic `update_thread` Task. Add decay-first/triage-first races, under-lock revalidation, and at-most-one reactivation Event only in the separately authorized D6 reactivation slice.

### RW4-4 — World-memory Context retrieval

Extend the selected existing Task Context path. Implement same-Team active Hypothesis and eligible EvidenceLink selection, canonical source/Snapshot/hash/quote validation, deterministic serialization/order, explicit bounds and fail-closed overflow, immutable Context Snapshot/manifest Event/hash, exact replay, and stale-reference rejection.

Experiment A result or explicit Operator disposition is required before representation freeze. Prove only eligible verified current records reach the model and existing retrieval behavior remains intact.

### RW4-KU — claim-level attribution (separate gate)

Keep immutable application-written `TaskKnowledgeReference` and typed application-validated `KnowledgeUseAssessment` separately gated. Decide whether required for RW-4 acceptance or only the foundation/value-harness gate. Do not broaden into a general learning/evaluation subsystem.

### RW4-5 — integrated verification and acceptance

Prove the full path:

`canonical Signal → authorized Team triage → durable disposition/Thread → later Task Context`

Include RW-5 integration: matched Signal reactivates the correct dormant Thread; decay and triage cannot overwrite stale decisions; retrieval sees canonical post-decay state; only eligible active Hypotheses and verified EvidenceLinks reach the later Task.

Close with exact-head local verification, exact-head hosted CI, disposable PostgreSQL evidence, requirement-to-test matrix, docs/CHANGE_MAP reconciliation, residual-risk ledger, and explicit Operator acceptance.

## 6. Explicit non-goals

Do not build these merely to unblock RW-4:
- Thread embeddings or summaries;
- new Domain ORM/configuration subsystem;
- entity extraction/alias infrastructure;
- near-duplicate detection without validated rules;
- model-based triage or model-generated Thread titles;
- automatic noise classification;
- automatic triage after ingestion;
- second scheduler/runtime or TaskDispatcher expansion;
- deferred refinement through RW-2/RW-3 Task types is prohibited by accepted D3; no v1 refinement path exists;
- parallel Context subsystem;
- live provider calls or scored newsroom runs.

Reconsider only when a concrete scenario and evidence justify a separate design and authorization.

## 7. Brief execution sequence

1. **Reconcile docs and evidence:** bring PR #175 findings onto current main; update architecture, Task matrix, PLAN, README, CHANGE_MAP, and historical labels.
2. **Apply the sequencing exception:** retain all seven RW3.4 PARTIAL rows and formal acceptance deferred; do not require their unrelated closure before RW-4/RW-5 work.
3. **Prepare RW4-2 Stage A:** close D1/D2 and review the design/proof subset; no creator implementation is included in this stage.
4. **Continue the serial implementation order:** after RW4-2 Stage A decisions are accepted, RW4-1 may begin when D5, its reviewed proof subset, and explicit authorization are satisfied; D3 is accepted and reconciled. After RW4-1, separately authorize and implement the RW-5 canonical lock helper/Team revision/writer retrofit, including real PostgreSQL lock proof. Only then separately authorize RW4-2 Stage B creator implementation. RW4-3 follows after the creator/helper are reviewed/closed and D4/C1/D5 are accepted. RW-5 decay follows RW4-3. RW4-0 remains open unless separately closed.
5. **Close umbrella RW4-0:** reconcile and explicitly accept all D1–D6 and cross-cutting contracts, including matching evidence/query cost, receipt/recovery, and Context representation. This is a separate design-closure milestone; it does not retroactively authorize implementation.
6. **Implement RW4-3 and RW4-4 when their own gates are met:** RW4-3 matching/commit without reactivation requires D4, C1, and D5; dormant reactivation is a separately gated addition requiring D6. RW4-4 requires its named Context consumer/contracts and an accepted Experiment A result or explicit Operator disposition before representation freeze.
7. **Integrate and accept:** complete RW4-5 with RW-5 race and post-decay retrieval proofs; decide RW4-KU; complete foundation-exit evidence and explicit acceptance.

## 8. Readiness checklist

- [x] RW3.4 sequencing exception recorded with all seven PARTIAL qualifications retained; formal acceptance remains deferred.
- [x] D1 trusted invocation/authority accepted before RW4-2.
- [x] All six D2 decisions accepted: canonical UUIDv5 identity; Task-schema logical-pair uniqueness; partial unique request-Event index with atomic creation/replay validation; replay/provenance/re-triage rules; immutable first-writer watermarks; code-owned v1 matching pins (actual values deferred to D4b).
- [x] D3-A/B/C lifecycle and terminal-deferred semantics accepted and reconciled; deferred is immutable/terminal and TaskRuntime completes the Task as `done`; technical failure remains distinct; no Signal lifecycle column is added.
- [ ] D4 matching and duplicate representation supported by independent fixtures and measured query cost before RW4-3.
- [ ] D5 disposition vocabulary/reference matrix and new-Thread/noise exclusions accepted.
- [ ] D6 shared decay/reactivation timestamp, lock order, and race outcomes accepted before reactivation and integrated proof.
- [ ] Assessment receipt transaction/recovery accepted before RW4-3; later Task Context consumer/bounds accepted before RW4-4.
- [ ] Architecture lifecycle and Task/write-scope matrix reconciled.
- [ ] Requirement-to-test matrix independently reviewed.
- [ ] Slice-specific prerequisite checklist and proof-matrix subset reviewed before each implementation PR.
- [ ] First bounded implementation PR explicitly authorized after its own gate and reviewed proof subset.

No R8 date is assigned here. R8 remains TBD until RW-0 through RW-5 and the formal foundation exit gate are complete and accepted.
