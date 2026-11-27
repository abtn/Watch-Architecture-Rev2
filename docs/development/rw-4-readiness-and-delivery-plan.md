# RW-4 Readiness and Delivery Plan

**Status:** Active staged-delivery baseline. D1 and all six D2 decisions were accepted on 2026-11-24; D3-A/B/C, D4.1/D4.1a/D4.2/D4.3, D5.1–D5.4, and D6.1–D6.6 were accepted on 2026-11-25. D4's policy shape is frozen, but canonical Team/hash persistence, measured matcher thresholds/margins/bounds/score serialization/query cost, and actual matching-pin values remain open evidence/design gates. D6's contract is accepted; implementation and integrated proof remain a later, separately authorized RW4-5 slice. This plan is subordinate to PLAN.md for current milestone status and authorization.
**R8-ready relationship:** Path A is selected for R8-ready planning. SignalDisposition and the full `triage_signal` workflow are deferred from that bounded path; this RW4 plan remains the Full Design authority for the RW4 capability chain. This deferral does not close accepted decisions, satisfy RW4 gates, or authorize implementation. See [R8-ready scope and capability matrix](r8-ready-scope-and-capability-matrix.md) and [PLAN.md](../../PLAN.md).
**Planning baseline:** `main` after PR #203 merge commit `5d3370127718cee839834b6473b8b5883be95d0b` (2026-11-26); PR #190, #187, and #184 remain earlier D1/D2/D3 reconciliation baselines.
**Status authority:** `PLAN.md` remains the only authority for milestone status and authorization. This document owns the dependency-aware RW-4 readiness checklist and delivery sequence.
**Sequencing decision:** [RW-4/RW-5 sequencing decision](rw-4-rw-5-sequencing-decision.md) records the approved 2026-11-24 RW4-2-first serial order.
**Scope:** Reconcile the evidence audit in PR #175, the bounded RW4-0 proposal in PR #174, the minimal matching proposal in PR #176, the RW-4 design plan, Task specifications, and architecture.

## 1. Executive decision

The Operator's 2026-11-24 sequencing exception satisfies the overall RW3.4 sequencing gate while preserving formal acceptance as deferred and all seven PARTIAL qualifications. RW4-0 remains open. PR #176 is a supporting design/evidence artifact; D1/D2, D3, and D4.1/D4.1a/D4.2/D4.3 are accepted, while D4 evidence closure and implementation gates remain separate; D5.1–D5.4 and D6.1–D6.6 are accepted. No individual RW-4 slice is blanket-authorized: each must satisfy its own prerequisites, independently reviewed proof subset, and explicit Operator authorization. PR #175's evidence findings are incorporated here; its audit branch is closed and is not a current baseline.

The delivery path is deliberately serial. The updated Operator order supersedes the earlier RW-5-first order:

1. **RW4-2 Stage A — design/decision closure:** D1 and all six D2 decisions are accepted. D1's ten existing Task producers are centralized by PR #207/#208; D2's canonical identity migration `0020_rw4_task_identity.py` is merged by PR #203. The remaining Stage A closure is the exact request Event v1 schema/fingerprint, cross-document status reconciliation, and independent review, recorded in [the Stage A closure record](rw4-2-stage-a-contract-closure.md). The creator remains unimplemented. Its frozen protocol requires PostgreSQL READ COMMITTED and rejects REPEATABLE READ/SERIALIZABLE before application data access. The triage-only BEFORE INSERT trigger guarantees Team-lock participation only; it does not enforce Control Room-only creation or attest writer origin. D1 remains a trusted-application-code boundary, with out-of-band SQL writers operationally excluded. Creator runtime validation, replay, and creator-specific PostgreSQL concurrency/retry proofs remain mandatory Stage B work.
2. **RW4-1 — SignalDisposition persistence:** follow the RW4-2 D1/D2/D3 design gates; D3 and D5.1–D5.4 are accepted. Before implementation, RW4-1 still needs a reviewed physical persistence design, requirement-to-test subset, and explicit authorization. Implement only the bounded persistence slice and preserve linear Alembic history. D3 acceptance does not authorize this migration or implementation.
3. **RW-5 canonical lock helper, Team revision, and writer retrofit:** separately authorize the migration and RW3.4-adjacent WorldMemoryCommitService/Operator compatibility changes; prove every supported writer through real entrypoints. This must land before the RW4-2 creator and RW4-3.
4. **RW4-2 creator implementation:** return to the RW4-2 implementation stage only after RW4-1 and the canonical helper/Team-revision/writer retrofit have landed and passed real PostgreSQL lock tests. Reuse the one canonical helper; no bespoke lock path.
5. **RW4-3 — deterministic matching and commit:** requires the RW4-2 creator, accepted D4/C1/D5, and the helper from step 3. No dormant reactivation, new Thread creation, noise classification, or near-duplicate classification.
6. **RW-5 decay implementation:** follow RW4-3; scheduler/host invocation remains a separate RW5-P gate.
7. **RW4-4 — bounded Context retrieval:** only after its own Context-consumer gate and Experiment A disposition.
8. **D6 / RW4-5:** D6 decisions are accepted. Implement dormant reactivation and integrated race/recovery proof only after RW4-4, the canonical RW-5 helper/retrofit, and separate explicit RW4-5 implementation authorization.

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
- **RW-5** is independently implementable. The D6 timestamp, revision, and canonical lock decisions are accepted; triage/reactivation integration remains gated on the RW-5 helper/retrofit, RW4-5 implementation, and the required PostgreSQL race/recovery proofs.
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

RW4-0 closes only after D1–D6 and the cross-cutting contracts are reconciled and evidence-backed. D1–D6 are accepted; remaining evidence/design gates are not thereby closed. PR #174 and #176 preserve earlier proposals and do not substitute for this gate. The staged slice gates below allow bounded implementation to proceed before umbrella RW4-0 closure only where explicitly stated.

#### D1 — Trusted host invocation and authority

Freeze an explicit trusted host-invoked operation for one Signal and one Team. Define trusted principal fields and the exact Team/action grant checked by Watch. The caller cannot select a Team from untrusted payload data. Every caller is independently authorized, including a caller resolving an existing Task. Both creation and replay require the Team's persisted state to be exactly `active`; replay rechecks this under the Task → Team lock order before disclosing/resolving the Task.

No automatic `ingest_source → triage_signal` Task creation, scheduler, or TaskDispatcher expansion in the first slice. The production host composition/authentication boundary remains external; Watch-side grant validation is not proof of deployed host authentication.

### D2 — Canonical Task and disposition identity

Keep three identities distinct: (a) business identity `(signal_id, team_id)`; (b) the accepted deterministic Task identity, UUIDv5 under namespace `383bbdde-37be-4895-8fb7-1afa196b5cf7`, with canonical name `triage_identity_v1|triage_signal|team:<team-uuid>|signal:<signal-uuid>`; and (c) immutable request provenance/fingerprint. The accepted golden vector is Team `00000000-0000-4000-8000-000000000001`, Signal `00000000-0000-4000-8000-000000000002`, Task `5b45ed53-a50f-51e8-ba81-ce52512aa922`. The UUID primary key rejects a second insert using the same canonical UUID, but does not enforce logical-pair uniqueness against a writer supplying a different UUID. **Accepted v1 canonical-identity guarantee:** persist `signal_id` and `identity_version` on triage Tasks and add a database unique constraint on `(team_id, signal_id, identity_version)`, while retaining the canonical UUIDv5 primary key, one narrow creator, and recompute-on-load validation. The triage Task must require these identity fields; callers cannot supply or override them. The current audited Task schema has neither persisted identity column nor the pair-level constraint, so this guarantee requires a Task-schema migration that adds both columns and the composite constraint, with the applicable triage-row constraints and validation. It is not a no-migration option or equivalent to a single-creator-only application invariant. Re-audit the schema and assess migration/writer compatibility against the implementation PR's base and head before Stage B. The Operator accepted the Task-schema migration and composite constraint on 2026-11-24. Exact migration/preflight/backfill and writer-compatibility design remain implementation review requirements. The Operator also accepted the partial unique request-Event index, atomic Task/Event creation, and replay validation; duplicate-history preflight and PostgreSQL proof remain required. The index enforces at-most-one; atomic creation establishes existence and replay validation verifies exactly one. Same-pin replay/original-requester provenance, changed-pin conflict, v1 identity occupancy, separately approved v2, immutable first-writer watermark semantics, and code-owned v1 matching-pin ownership are accepted. D4b still supplies actual pin values. Freeze atomic Task/request-Event creation, same-request replay, and conflict behavior. Requester identity is provenance, not semantic equivalence, as recorded in the PR #174 correction.

Separately freeze SignalDisposition uniqueness for `(signal_id, team_id)`, its canonical persisted identity, Task attribution, reason, timestamp fields, and database constraints. The immutable Task request must pin Team ID, Signal ID, canonical Signal Snapshot reference and hash, TeamPolicy version, matcher identifier/version, embedding-space key, and chunking version. Same-request replay compares semantic pins while excluding requester identity and first-writer `as_of`/Team revision metadata; it validates and returns the original provenance and watermark unchanged. A changed semantic pin conflicts. The existing `update_thread` idempotency namespace is precedent for transaction/replay shape only; it must not be reused as triage identity.

### D3 — Deferred lifecycle and Task write-scope reconciliation — ACCEPTED 2026-11-25

D3-A/B/C are accepted and reconciled across the RW4-2 specification, Task definition, architecture lifecycle summary, and Task/write-scope matrix. Signal has no lifecycle/status column; eligibility derives from canonical Signal/Snapshot integrity and provenance plus active-Team, caller-authorization, and source/domain/policy checks. Existing Team/Signal disposition excludes another first-release decision; missing or inconsistent canonical Task/request-Event history fails closed without repair or replacement. TaskRuntime owns lifecycle; `done`/`failed` are terminal and v1 identity remains occupied. A valid deferred disposition is immutable/terminal and its Task completes successfully as `done`; the disposition, Task attribution/reason, TaskRuntime Outcome, terminal Task status, and terminal Event commit or roll back together in one TaskRuntime-owned transaction. Technical failures follow TaskRuntime retry/recovery and may end `failed`. Stale-pin supersession uses the existing TaskRuntime terminal non-success path and requires an RW4-3 no-retry proof. The `update_thread` and `operator_update` SignalDisposition write permissions are removed. D5.1–D5.4 and D6.1–D6.6 are accepted. An active Thread may be matched directly; a dormant Thread may be matched only when the same TaskRuntime-owned transaction reactivates it under D6. Until RW4-5 implementation is separately authorized and proven, dormant candidates defer with `dormant_thread_requires_reactivation`. D3/D5/D6 acceptance does not authorize RW4-1 persistence or RW4-2 creator implementation.

### D4 — Accepted duplicate and existing-Thread decision rules; evidence gate remains open

**Accepted 2026-11-25:** D4.1 exact raw content-hash equality within the same Team's intake history regardless of origin; D4.1a first successfully committed Signal for Team + hash is canonical, with database arbitration and stable association; D4.2 narrow evidence-based existing-Thread matcher shape; D4.3 no automatic Thread creation in v1.

- Duplicate scope is same Team + exact raw content hash. Origin is irrelevant; cross-Team equal hashes are not duplicates; near-duplicates and semantic duplicates are excluded. Duplicate detection references the canonical Signal and never selects or mutates a Thread.
- Canonical winner is the first successfully committed Team/hash association. Current Signal rows are not Team-owned and ingestion Event provenance establishes Team association; existing origin_url + content_hash uniqueness does not implement the accepted cross-origin Team/hash rule. A reviewed persistence design and real two-session PostgreSQL arbitration/stability proof remain mandatory before RW4-3.
- Build Thread evidence profiles at read time through Team-scoped EvidenceLink → Hypothesis → Thread. Candidate scope is same Team and Domain, status active or dormant; resolved is excluded. supports and challenges EvidenceLinks count; mentions alone does not. Validate incoming and historical same-Team ingestion provenance and exact Signal/Snapshot/hash and EvidenceLink Snapshot/hash associations. Absent legacy provenance is excluded; partial/mismatched/corrupt provenance fails closed.
- Use only existing KnowledgeChunk projections with compatible immutable embedding-space and chunking pins. No Thread embeddings, summary/entity/alias subsystem, model calls, re-embedding, or recency bonus.
- Maximum pairwise chunk cosine similarity is an experimental baseline only; outlier chunks and profile-size bias must be measured. Numeric minimum threshold, runner-up margin, score serialization, candidate/evidence bounds, actual pin values, fixture labels/results, false-positive tolerance, query plan, and cost remain open. One candidate must pass the minimum threshold; when a runner-up exists the winner must also clear the measured margin. Ties are deferred; no UUID/incidental-order tie-break.
- Bound candidate Threads, evidence Signals, and evidence chunks separately; detect overflow before ranking; measure cardinalities and PostgreSQL query plans/cost on disposable fixtures. Never rank truncated evidence as complete.
- Under accepted D6, a dormant candidate may receive a v1 `matched` disposition only when it is the deterministic unambiguous winner and no active candidate wins; the same TaskRuntime-owned commit must reactivate it. Until RW4-5 implementation is separately authorized, implemented, and proven, dormant would-be winners with no active winner continue to defer with `dormant_thread_requires_reactivation`. No standalone or model-directed reactivation is permitted.
- No automatic Thread creation: no qualifying active-Thread match or ambiguous/insufficient valid evidence resolves to terminal deferred. A dormant candidate that would otherwise win and has no active winner defers with `dormant_thread_requires_reactivation`. Corrupt or inconsistent provenance is a technical/integrity failure, not deferred. URL-derived and model-generated titles are not permitted. Automatic noise and near-duplicate classification remain excluded.

Required independent-label fixtures: same-origin replay; cross-origin exact bytes in one Team; same hash across Teams; near-duplicate negative; clear match and broad-topic hard negative; multiple candidates/ties; active/dormant/resolved Threads; mentions-only/no-evidence; Hypothesis lifecycle states and EvidenceLink stances; absent vs partial/mismatched/corrupt provenance; cross-Team same-Domain evidence; incompatible pins; high-scoring outliers; multiple subtopics; varied profile sizes; threshold/margin boundaries; and candidate/evidence overflow. Report false positives/negatives by case, lifecycle state, and profile size. If tolerance or query cost is not demonstrated, keep the affected cases deferred or narrow the slice; do not tune by intuition.

### D5 — Disposition vocabulary, references, reasons, and terminal evidence (ACCEPTED 2026-11-25)

D5.1–D5.4 are accepted and recorded in [issue #193](https://github.com/abtn/Watch-Architecture-Rev2/issues/193) and the [RW4-2 Stage A specification](rw-4-2-decision-and-specification-draft.md). V1 has exactly three values: `matched`, `duplicate`, and `deferred`; `new_thread` and `noise` are excluded. The accepted reference matrix requires `thread_id` only for matched, `duplicate_of_signal_id` only for duplicate, `reason_code` only for deferred, and `decided_by_task_id` for all three. Every row is unique per (Signal, Team), immutable, and DB-timestamped without `updated_at`.

Deferred reasons are `no_eligible_thread`, `ambiguous_thread_match`, `insufficient_evidence`, `no_compatible_evidence`, `evidence_limit_exceeded`, and `dormant_thread_requires_reactivation`. Corrupt provenance is a technical/integrity failure, not deferred. Superseded matching pins use TaskRuntime's existing terminal failure path with `matching_pins_superseded`, not a disposition.

Every disposition references the canonical Task for the same Team/Signal. The disposition, Task-attributed evidence, TaskRuntime `task_execution` Outcome, terminal Task status, and `task_completed` Event commit or roll back together in one TaskRuntime-owned transaction. Deferred is successful (`done`). Kernel persistence uses the active Session and cannot commit independently. Dormant Threads may be reactivated only under the accepted D6 contract and after the separately authorized RW4-5 implementation and proof. Before that implementation ships, dormant candidates continue to defer with `dormant_thread_requires_reactivation`.

D5 decision acceptance does not authorize RW4-1 implementation. RW4-1 still requires a reviewed physical design for relational/cross-record integrity, a frozen proof subset, disposable-PostgreSQL migration/constraint/rollback proofs, and explicit authorization.

#### F2 — Thread writer ownership and lifecycle gate (Operator decisions, 2026-11-26)

The target owner is accepted: Watch's trusted application/Kernel boundary owns Thread creation and supported lifecycle writes. `activate_team` is the canonical intended creator for Operator-approved starter Threads; a trusted host authenticates and delegates, but never writes Thread rows directly. Resolution is an explicit Operator-authorized Task/application operation that records a reason and one immutable Task-attributed Event atomically with the status transition. This is a design target, not an implemented path: `activate_team` remains unimplemented in Checkpoint 3. The Operator confirmed on 2026-11-26 that Watch has no production deployment; the checked-in development credential/process/Thread-writer inventory is recorded in [RW4-1B §10.4](rw4-1b-physical-schema-and-integrity-design.md#104-development-only-database-credential-process-and-thread-writer-inventory-2026-11-26).

The checked-in source/configuration inventory is complete and the production-deployment uncertainty is resolved. F2 remains OPEN/BLOCKING because local untracked processes/credentials have not been inspected and the current development topology does not enforce the accepted boundary: Compose/CI/migration/test credentials are bootstrap superusers, no restricted runtime/owner role split exists, and Thread domain/lifecycle guards are absent. Every future supported status/profile writer must use Task → Team → sorted Thread → sorted Hypothesis locks, required Team-revision stamping, and one transaction through commit. Resolution needs exact authorization, reason, Event identity/cardinality, rollback, and replay proof. RW-5 first-release decay remains confidence-only; no dormancy writer is added here, and RW4-5 reactivation remains separately gated.

Closure sequence: (1) reconcile the documented inventory with actual local PostgreSQL roles, active sessions, environment variables, and untracked processes; (2) provision distinct owner/migrator/runtime/test-maintenance principals and DSNs; (3) implement the role-to-writer/column privilege matrix and Thread domain/lifecycle guards; (4) implement the canonical application operations and Task/Event contract in separately authorized slices; (5) prove lock/revision and F3 guard compatibility; (6) run real PostgreSQL forbidden-write, writer/race, resolution replay/rollback, and role-bypass tests; (7) independent F2 closure review. Do not enable matched dispositions before this evidence is complete.

### D6 — Accepted dormant Thread reactivation contract (2026-11-25)

D6.1–D6.6 are accepted (issue #195). This freezes the lifecycle decision; it does not authorize implementation. Dormant reactivation remains a separately authorized RW4-5 implementation slice after RW4-4 and the required RW-5 helper/retrofit.

- **Trigger and scope (D6.1, Option A):** only a valid `triage_signal` may reactivate a dormant Thread, and only when the accepted deterministic matcher selects it as the unambiguous winner and no active candidate wins. Reactivation is part of that Task's Kernel commit. No standalone Operator operation, background process, `update_thread`, `operator_update`, decay, or model-directed reactivation.
- **Timestamp (D6.2, Option A):** do not mutate `Thread.last_updated_at` or add a timestamp projection merely for reactivation. Preserve existing timestamp semantics. One immutable, DB-timestamped `thread_reactivated` Event is the authoritative history.
- **Atomicity (D6.3):** Thread `dormant → active`, the one Task-attributed `thread_reactivated` Event, matched SignalDisposition, TaskRuntime `task_execution` Outcome, terminal Task status/completion time, and `task_completed` Event commit or roll back together in one TaskRuntime-owned transaction. Kernel persistence participates in the active Session and never commits independently.
- **Revision/stale fencing (D6.4):** use the frozen RW-5 PostgreSQL clock and Team revision protocol. Increment `world_memory_revision` for the lifecycle transition because it changes the triage candidate set. Under the canonical locks, revalidate Team eligibility, Thread Team/domain/status, matcher winner, and relevant Hypothesis/evidence watermarks. A stale matcher receipt cannot authorize reactivation or a matched disposition.
- **Locks/races (D6.5):** use only the canonical RW-5 helper and order: Task `FOR UPDATE` → Team `FOR NO KEY UPDATE` → sorted Thread `FOR NO KEY UPDATE` → sorted Hypothesis `FOR NO KEY UPDATE`. No bespoke lock path. Prove both decay-first and triage-first interleavings on disposable PostgreSQL, including the Team revision and Hypothesis watermarks each observes. RW-5 first-release decay remains confidence-only; it does not gain Thread lifecycle ownership.
- **Replay/recovery (D6.6):** committed replay returns the canonical disposition and Task result without another transition/Event. Enforce at-most-one reactivation Event at the database boundary. Lost responses resolve to the committed result; pre-commit failures leave no partial transition/disposition/terminal bundle; inconsistent status/Event/Task history fails closed without repair or synthesized history. TaskRuntime alone owns retry, interruption recovery, and terminalization.

The exact Event identity/schema and uniqueness, cross-record Team/domain/Task/Signal integrity, stale-receipt fencing, affected lock rows, both PostgreSQL race proofs, rollback/lost-response/replay/recovery proofs, and review of any RW3.4 residuals touched remain required engineering work. Any future transition that makes a Thread unavailable to triage needs its own durable recovery/reconsideration path before it ships; D6 does not authorize a dormancy writer.

Decay age continues to be reconstructed from immutable accepted supporting/challenging EvidenceLink history and the immutable current-epoch baseline; `Hypothesis.last_touched_at` remains only a mutable cache/prefilter, never historical authority. A pre-epoch EvidenceLink timestamp cannot anchor decay in a later epoch. Decay does not update `last_touched_at`. The RW-5 shared contract remains authoritative for clock, epoch, evidence-age, Team revision, and locking semantics.

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
- no dormant-Thread reactivation before separately authorized and proven RW4-5 implementation;
- dormant reactivation and decay races;
- Context membership, provenance, ordering, bounds, and replay;
- no direct Task lifecycle writes, unapproved follow-up Task creation, or dispatcher expansion;
- disposable-PostgreSQL migration/constraint proofs.

**Overall project gate before any RW-4 production implementation:** RW3.4 formal acceptance or an explicit sequencing exception, with residuals retained.

**Staged slice gates (each also requires a reviewed requirement-to-test subset and explicit Operator authorization):**

| Slice | Required decisions/evidence before that slice |
|---|---|
| **RW4-2 — Task boundary** | **Stage A:** D1/D2 decisions accepted; D1 ten-writer centralization (PR #207/#208) and D2 Task identity migration (PR #203) are implemented and merged. The exact request Event v1 schema/fingerprint and creator lock/retry contract are recorded for independent review in [the Stage A closure record](rw4-2-stage-a-contract-closure.md). No triage creator is implemented. **Stage B:** only after RW4-1 and the RW-5 canonical helper/Team-revision/writer retrofit have landed with PostgreSQL lock proof, then separately authorize the creator. The two stages are serial and must not be collapsed. |
| **RW4-1 — persistence** | D3 lifecycle semantics are accepted. Before implementation, D5 disposition vocabulary/reference matrix and uniqueness scope are accepted; the physical constraints and cross-record integrity design must be reviewed and proven; the persistence design must integrate deferred disposition writes into the existing TaskRuntime-owned terminal transaction (same Session/commit as Task Outcome/status/Event), with rollback proof and no independent disposition commit. No matching algorithm, D6 reactivation, receipt, or Context decision is required for this persistence-only slice. |
| **RW4-3 — matching and commit** | Accepted D4.1/D4.1a/D4.2/D4.3 rules plus the canonical Team/hash persistence design, measured fixture thresholds/margin/score serialization/bounds/query cost and actual D4b pins; C1 receipt/recovery contract; accepted D5 reference matrix; and stale-pin TaskRuntime supersession/no-retry proof. No automatic Thread creation, noise, near-duplicate classification, or dormant reactivation in the initial slice. D6 is accepted; dormant reactivation is confined to RW4-5 and requires its separate authorization and proof. |
| **RW4-4 — Context** | Named later Task consumer, existing assembler, eligible records, provenance, bounds, overflow, snapshot/manifest and replay contract accepted; Experiment A result or explicit Operator disposition recorded before representation freeze. |
| **RW4-5 — integration** | RW4-1 through RW4-4 accepted as applicable, RW-5 decay implementation available, and the accepted D6 contract implemented under separate RW4-5 authorization, with integrated race/recovery/post-decay retrieval proof completed. |

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

RW-5 first release changes confidence only. It does not transition Threads to dormant. Dormancy is prohibited until a durable RW-4 reactivation/recovery path is implemented and separately authorized. D6 decisions are accepted but do not authorize a dormancy writer. `last_touched_at` is not historical authority and decay never changes it. RW5-P remains a separate host integration and must be accepted before foundation exit/R8 can claim autonomous periodic decay. TaskRuntime remains the sole lifecycle/recovery authority.

### Experiment A

Preparation and offline protocol work may proceed independently. Its scope is limited to informing RW4-4 representation. The merged canonical fixture package is not an executed experiment. Provider/model execution requires separate explicit authorization. Before RW4-4 representation freeze, record either the accepted experiment result or an explicit Operator rationale and residual uncertainty. Before foundation exit/R8, retain an accepted report or explicit inconclusive/not-required disposition with limitations.

### RWN-01

RWN-01 is the separate newsroom value-harness scenario. Freeze publisher PDF and Supplementary Material review, corpus manifest, task brief, answer key, independent outcome set, scoring examples, reviewer calibration, and execution configuration before scored runs. It is not a prerequisite to starting RW-4 and is not a substitute for matching fixtures or Experiment A.

## 5. RW-4 implementation sequence

Each stage has its own reviewed scope, acceptance evidence, and explicit authorization.

### RW4-2 — Triage Task boundary (two-stage delivery)

**Stage A — design and decisions (first):** D1 and all six D2 decisions are accepted; D1 ten-writer delegation and D2 migration `0020_rw4_task_identity.py` are implemented and merged. Stage A closure freezes/reviews the exact request Event v1 schema/fingerprint, creator lock/retry contract, and requirement-to-proof status in [the Stage A closure record](rw4-2-stage-a-contract-closure.md). Historical migration preflight is delivered by PR #203; creator runtime validation and creator-specific race/replay proofs remain Stage B obligations. Actual matching-pin values remain for D4b. This stage creates no production creator code.

**Stage B — creator implementation (deferred):** only after RW4-1 persistence and the separately authorized RW-5 canonical lock-helper/Team-revision/writer retrofit have landed with real PostgreSQL lock proofs. Implement the host-invoked creator and TaskRuntime-owned boundary: atomic Task/request Event, canonical helper paths, database/race behavior, fingerprint/replay/conflict rules, exact Task envelope, admission/failure/recovery. Obtain separate explicit implementation authorization.

Keep TaskDispatcher unchanged. Do not add automatic post-ingestion enqueueing.

### RW4-1 — SignalDisposition persistence

**RW4-1A — current-source and persistence audit: complete.** The read-only audit and F1–F3 corrections are recorded in [RW4-1A audit](rw4-1a-current-source-and-persistence-audit.md). It covers the three existing-Signal reuse paths (ordinary fetch_no_change, ON CONFLICT winner, and prior_outcome replay), distinguishes intake provenance from D4.1a canonical Team/hash identity, and separates the stable disposition reason code from the human explanation and complete Task-attributed Outcome evidence. No code, schema, migration, test, or database change was made; no implementation is authorized.

**RW4-1B — physical persistence design: OPEN Full Design work; deferred from R8-ready Path A.** Issue [#199](https://github.com/abtn/Watch-Architecture-Rev2/issues/199) remains the design/decision tracker, following merge of PR [#198](https://github.com/abtn/Watch-Architecture-Rev2/pull/198) at `72dc899d5983fd5176fff25be220f0fd1b417844`. Resume this work when Full Design sequencing reaches the RW4-1B dependency or when an explicitly approved scope change proves SignalDisposition necessary for an R8-ready scenario. The Operator accepted the Thread status/domain separation on 2026-11-26: status is checked at matched commit and may later transition without invalidating the disposition; domain is immutable after a matched reference and requires a database guard; no status/domain snapshot columns are added to SignalDisposition. See [RW4-1B design proposal](rw4-1b-physical-schema-and-integrity-design.md). The second review found that the earlier prose corrections were not checked against the exact source lock modes or the full relational/serialization requirements. Corrections now: use Task → Team → Signal trigger locks with `FOR SHARE` (matching existing ingestion Task `FOR UPDATE` and Team `FOR SHARE`; no Team lock upgrade); bind each disposition to the exact D2 triage Task/Team/Signal/identity-version tuple through a composite FK and D2 migration support key, with the D2 task-type/identity-field CHECK and a no-INSERT-grant boundary until the FK is installed; protect referenced Signal deletion and trigger bypass paths; revoke runtime TRUNCATE privileges and reject TRUNCATE/CASCADE on protected Events, Signals, dispositions, Tasks, and Teams; freeze the exact `TerminalObservation.signal_triage` JSON schema, task_completed payload, and replay checks including `Task.completed_at`; and specify `LOCK TABLE tasks, teams, signals, events, threads IN ACCESS EXCLUSIVE MODE NOWAIT` for the RW4-1 cutover because it adds an Event column and installs DDL protections; migration-first blocks access, while any reader/writer-first lock causes a clean immediate abort/retry rather than a lock-upgrade deadlock. The latest review also identified that row-level DELETE triggers do not stop PostgreSQL TRUNCATE. The proposal now requires effective runtime-role TRUNCATE revocation, statement-level rejection triggers on protected history/identity tables, a restricted audited migration/owner boundary, and direct/CASCADE/partition PostgreSQL proofs. The merged proposal is the baseline, not an accepted physical design. Operator decisions now accepted: minimal SignalDisposition row shape (Option A); conditional Option A Event witness subject to a proven runtime/migration-owner role boundary; and a forward-only DB-attested cutover. Legacy intake Events remain unmarked and ineligible; only post-cutover Events stamped by the validating database trigger may establish provenance. The independent physical-design review findings F1–F4 are now specified as executable correction requirements in §10.1 of the design: target runtime/migration-owner roles and effective grants; the checked-in development writer/credential inventory reconciled with the actual local environment, with explicit confirmation that no production deployment exists; the exact domain-guard trigger and both PostgreSQL race orders; ORM locked-row refresh; exact replay after later status transitions; and an expanded proof matrix. F2 remains OPEN/BLOCKING: Watch has no production deployment, so no production writer inventory currently exists to attest. The checked-in development/bootstrap/CI/migration/test/Thread-writer inventory is recorded, but the actual local environment still requires reconciliation for untracked processes, manually provisioned roles, and out-of-repository/direct-SQL writers; effective role enforcement and PostgreSQL proofs also remain outstanding. F1/F3/F4 remain unproven pending disposable-PostgreSQL and SQLAlchemy evidence. No implementation is authorized. Issue #199 sequences the seven Operator decisions, source/role/lock audit, the merged D2 identity schema and pending disposition-to-Task composite-FK dependency, TaskRuntime contract, rollout gates, PostgreSQL proof subset, cross-document review, and explicit acceptance. No implementation is authorized. A bounded audit of `core/models.py`, `core/operator_application.py`, `core/update_thread_context.py`, `core/world_memory.py`, and migration `0019_rw1_world_memory.py` found no checked-in production Python Thread create/insert path and no production `Thread.status`/`Thread.domain` writer. The Operator confirmed there is no production deployment, so no production/deployment writer owner exists to identify at this stage. Before matched writes are enabled, reconcile the actual development environment for untracked processes, manually provisioned roles, seed/bootstrap/import/admin scripts, and external/direct-SQL writers; unsupported writers must be excluded from the runtime credential or separately isolated. Decision 3 is accepted: duplicate disposition writes remain disabled until D4.1a canonical Team/hash arbitration is separately implemented and proven by real two-session PostgreSQL tests covering same-Team/same-hash arrivals with different origins, first-successful-commit winner, rollback, stable association, and Team isolation. No winner may be inferred from origin, fetched_at, application Event.created_at, UUID order, or query order. Decision 7 is accepted: matched, duplicate, and deferred must be enabled together at one write-enable point. Prerequisites may land separately, but no disposition writes or successful triage finalization are enabled until the D1 Control Room creator/caller-authorization boundary and D2 Task identity/FK are proven; RW-5 Task → Team → sorted Thread → sorted Hypothesis serialization, Team revision, and all `update_thread`/`operator_update`/`apply_decay` and any Thread status/domain writer retrofits pass real PostgreSQL interleavings; D4.1a canonical arbitration and D4.2 matcher evidence and durable-receipt closure/D4b actual pins, including receipt schema/uniqueness/payload bounds, the separate durable receipt transaction, Team-revision/candidate-profile fence, KnowledgeIndexService Signal-lock, KnowledgeChunk DML guard/no-TRUNCATE, stable chunk/vector-fingerprint, and finalizer revalidation proof, and accepted `assessment_receipt_stale` TaskRuntime terminal-failure/permanent-v1-identity-occupancy mapping and its implementation/replay proof; the later business-finalization bundle remains atomic pass; RW4-1 physical provenance/role/immutability proof passes; D3/D5 TaskRuntime atomicity/exact replay passes; and integrated exact-SHA PostgreSQL proof, independent review, and separate implementation authorization are complete. Production host authentication remains mandatory before production use. No partial rollout or implementation is authorized. Decision 4 is accepted and its D2 schema prerequisite is delivered: PR #203 merged migration `0020_rw4_task_identity`, including Task identity columns, CHECK/unique keys, canonical request/UUID preflight, Team-lock insert trigger, and identity immutability. No triage Task creator is authorized by that merge. D2 columns/indexes stay out of the RW4-1 initial migration; the later four-column composite FK requires the locked `tasks, events, signal_dispositions` preflight specified in the RW4-1B design, and runtime disposition INSERT remains withheld until that FK is installed and verified. No caller/Event-only transitional substitute.

**Implementation gate:** closed. Do not implement ORM, SQL, migration, TaskRuntime, ingestion, or tests until RW4-1B receives design review and explicit acceptance, and RW4-1 implementation receives separate explicit authorization. The merged D2 Task identity schema is not to be reimplemented; the later disposition-to-Task composite-FK migration, D4.1a canonical Team/hash arbitration, and RW-5 lock/revision changes remain separately scoped. No D4.1a winner algorithm, RW-5 helper/revision, matcher, Task creator/dispatcher path, or dormant reactivation is included here.

### RW4-3 — Deterministic triage and commit

Implement only the evidence-approved duplicate/matching rules: bounded candidate/evidence retrieval; same-Team ingestion and Snapshot provenance; deterministic result/reason; canonical durable assessment receipt; separate receipt transaction; Kernel-authorized business commit; and atomic disposition/Event commit. Matched active-Thread handling may proceed under the accepted D4/C1/D5 contracts. D6.1–D6.6 are accepted, but dormant-Thread matched outcomes remain excluded from RW4-3: a dormant candidate may be evaluated only to determine whether it would otherwise win; it must not be reactivated or receive a `matched` disposition in this slice. If a dormant candidate would otherwise win and no active candidate wins, resolve it through terminal `deferred` with `dormant_thread_requires_reactivation`. Do not change Thread status/timestamps or emit a reactivation Event in RW4-3. Dormant matching/reactivation belongs to the separately authorized RW4-5 slice.

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
4. **Continue the serial implementation order:** after RW4-2 Stage A's full creator specification, migration/preflight design, existing-writer compatibility, lock-path contract, and proof subset are frozen and reviewed (the D1/D2 decisions themselves are already accepted), RW4-1 may begin when the RW4-1 physical design, reviewed proof subset, and explicit authorization are satisfied; D3 is accepted and reconciled. After RW4-1, separately authorize and implement the RW-5 canonical lock helper/Team revision/writer retrofit, including real PostgreSQL lock proof. Only then separately authorize RW4-2 Stage B creator implementation. RW4-3 follows after the creator/helper are reviewed/closed and D4/C1/accepted D5 are in place. RW-5 decay follows RW4-3. RW4-0 remains open unless separately closed.
5. **Close umbrella RW4-0:** reconcile and explicitly accept all D1–D6 and cross-cutting contracts, including matching evidence/query cost, receipt/recovery, and Context representation. This is a separate design-closure milestone; it does not retroactively authorize implementation.
6. **Implement RW4-3 and RW4-4 when their own gates are met:** RW4-3 matching/commit without reactivation requires D4, C1, and D5; dormant reactivation is a separately gated addition requiring D6. RW4-4 requires its named Context consumer/contracts and an accepted Experiment A result or explicit Operator disposition before representation freeze.
7. **Integrate and accept:** complete RW4-5 with RW-5 race and post-decay retrieval proofs; decide RW4-KU; complete foundation-exit evidence and explicit acceptance.

## 8. Readiness checklist

- [x] RW3.4 sequencing exception recorded with all seven PARTIAL qualifications retained; formal acceptance remains deferred.
- [x] D1 trusted invocation/authority accepted before RW4-2.
- [x] All six D2 decisions accepted: canonical UUIDv5 identity; Task-schema logical-pair uniqueness; partial unique request-Event index with atomic creation/replay validation; replay/provenance/re-triage rules; immutable first-writer watermarks; code-owned v1 matching pins (actual values deferred to D4b).
- [x] D3-A/B/C lifecycle and terminal-deferred semantics accepted and reconciled; deferred is immutable/terminal and TaskRuntime completes the Task as `done`; technical failure remains distinct; no Signal lifecycle column is added.
- [x] D4.1 exact same-Team hash duplicate rule, D4.1a first-committed canonical winner rule, D4.2 existing-Thread matcher shape, and D4.3 no automatic Thread creation accepted.
- [ ] D4 evidence/design closure before RW4-3: Team/hash persistence and concurrent-winner proof; independent labeled fixtures; measured threshold/margin, score serialization, candidate/evidence bounds, actual D4b pin values, and disposable-PostgreSQL query-plan/cost evidence.
- [x] D5.1–D5.4 disposition vocabulary/reference matrix, deferred reason vocabulary, and Task-attributed terminal Event semantics accepted; `new_thread` and `noise` excluded.
- [ ] RW4-1 physical persistence design, cross-record integrity enforcement, migration/constraint/rollback proof subset, and explicit implementation authorization.
- [x] D6.1–D6.6 dormant-reactivation decisions accepted: preserve Thread timestamps; use the canonical RW-5 timestamp/revision/lock protocol; increment Team revision; commit atomically; enforce replay/recovery.
- [ ] RW4-5 implementation closure: exact Event identity/DB uniqueness, cross-record integrity, stale-receipt fencing, affected lock rows, decay-first and triage-first disposable-PostgreSQL race proofs, rollback/lost-response/replay/recovery proofs, independent proof review, and separate explicit implementation authorization.
- [ ] Assessment receipt transaction/recovery accepted before RW4-3; later Task Context consumer/bounds accepted before RW4-4.
- [ ] Architecture lifecycle and Task/write-scope matrix reconciled.
- [ ] Requirement-to-test matrix independently reviewed.
- [ ] Slice-specific prerequisite checklist and proof-matrix subset reviewed before each implementation PR.
- [ ] First bounded implementation PR explicitly authorized after its own gate and reviewed proof subset.

No R8 date is assigned here. R8 remains TBD until RW-0 through RW-5 and the formal foundation exit gate are complete and accepted.


## RW4-1B accepted Thread lifecycle refinements (2026-11-26)

The Operator accepted the second architecture investigation recommendations and the resolution design. Reconcile the RW4-1B design and dependent documents around these frozen points:

1. Thread resolution is an exclusive resolve_thread operation mode within the existing operator_update Task. Do not add a new Task type, TaskRuntime, dispatcher path, or worker allowed_writes. It reuses the existing Operator update business-commit marker/recovery boundary.
2. The resolution business transaction updates Thread.status (active/dormant → resolved only), increments Team revision once, and appends exactly one immutable Task-attributed thread_resolved Event. TaskRuntime terminalizes/replays the Task separately; do not claim both transactions are atomic together.
3. activate_team is the canonical intended creator for Operator-approved starter Threads. Host authentication and delegation are external integration requirements; the host does not write Thread rows.
4. Correct D1/F2 trust language: PostgreSQL cannot distinguish Control Room code from arbitrary SQL using the same runtime credential. Keep owner/migrator separate from the non-owner runtime credential, and operationally exclude unsupported writers from the runtime credential. A stronger same-credential adversary model needs a separate capability/credential design.
5. The canonical RW-5 Team revision helper covers Thread creation, actual status transitions, and permitted pre-match domain changes: one bump per accepted transaction; no bump on replay/no-op/rejection/rollback.
6. The Operator has confirmed no production deployment and the checked-in inventory is complete; F2 remains OPEN/BLOCKING pending local process/credential reconciliation and implementation/proof of the accepted database privilege and physical-guard boundary.

The refinement is design/documentation only. RW4-1B remains not implementation-authorized; D2, D4.1a, RW-5 helper/revision retrofit, TaskRuntime triage seam, and PostgreSQL proofs remain separately gated. Decision 7's all-three-outcomes-together write-enable rule is unchanged.


## RW4-2 Stage A implementation-status reconciliation (2026-11-27)

D1 existing-writer centralization (ten producers) is implemented and merged in PR #207/#208. D2 canonical Task identity schema and locked zero-history migration preflight are implemented and merged in PR #203 (`0020_rw4_task_identity.py`). The triage creator is not implemented. Its request Event v1 schema/fingerprint, semantic replay-equivalence, lock paths, and outer transaction-owner retry contract are frozen for independent review in [RW4-2 Stage A contract closure](rw4-2-stage-a-contract-closure.md). RW4-2 Stage B remains behind RW4-1 and the separately authorized RW-5 canonical helper/Team-revision/writer retrofit with real PostgreSQL lock proofs, plus its own explicit authorization.
