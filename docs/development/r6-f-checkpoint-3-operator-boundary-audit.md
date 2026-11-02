# R6-F Checkpoint 3 — Operator Task and Trusted Identity Boundary Audit

**Audit status:** design audit complete; the host-invoked application adapter is now an explicit Checkpoint 3 deliverable.
**Audit snapshot:** Checkpoint 2 merge `61be8db75b6bd4e23fcc91ef00f1a8f0a833dde0`; pre-audit branch head `cc87ada69e30e9ce1cfa66d6ca39d3f400d1d06b`.
**Audit date:** 2026-11-01.
**Implementation status (updated 2026-11-02):** the host adapter, pending request Task/Event creation, approval-specific no-deadline admission, create-only canonical LearningChange decision service, typed TaskRuntime accepted/rejected terminalization, synchronous adapter orchestration, completed-decision replay, and committed-decision interrupted recovery are implemented on draft PR #31. Operator-local disposable-PostgreSQL verification passed on exact code head `581ad1853a81d77b2a4fc41abe349ccc53dbe6d2`: fresh migration and one Alembic head at `0012_learning_foundation`, 83 focused tests, Ruff, mypy (27 source files), 577 full-suite tests, `git diff --check`, clean worktree, disposable container removal, and database environment restoration. Hosted CI run `41458560005` passed the same code head with 577 tests and the same migration/static checks. No schema migration was added. D10 is resolved below: Checkpoint 3 is create-only, and revise/retire proposal production and commitment are deferred as later knowledge-lifecycle work. PR #31 remains open/draft/unmerged pending documentation CI, review, and merge.

## 1. Decision and executive findings

The operator clarified that there is no separate deployed Watch API/CLI with authentication. Checkpoint 3 must include a thin in-repository application adapter that receives an authenticated Operator identity from its host.

**Decision:** include that adapter. The host application owns authentication and authorization and invokes the adapter in-process with a trusted, typed principal context. Watch does not add a deployed API, CLI, login/session/token subsystem, or authentication middleware.

`Host authentication + Team/action authorization → in-repository Operator adapter → pending approve_learning_change Task + request Event → TaskRuntime.admit → LearningChange commit service → atomic canonical decision + decision Event → TaskRuntime.finalize → host response`

| Area | Finding | Checkpoint 3 disposition |
|---|---|---|
| Host boundary | No deployed Watch API/CLI or authentication subsystem exists here. | Host supplies authenticated principal and has authorized Team/action. |
| Application adapter | The in-repository approval Task creator is now implemented. | `core/operator_application.py` accepts a typed host principal and atomically creates/replays the pending Task plus request Event. |
| Task creation | PlanService is the only production Task-row creation path found; it creates Plan-linked ingestion Tasks. | Adapter creates only a pending ordinary approval Task and request Event, atomically. |
| Task lifecycle | `TaskRuntime` owns admission, retry/recovery, and atomic terminal Outcome finalization. | Approval-specific no-deadline admission and typed accepted/rejected finalization are implemented. Finalization verifies the committed LearningChange, actor, decision Event, same Team, and current attempt before writing the ordinary `task_execution` Outcome/Snapshot/completion Event. |
| Approval execution | `TaskDispatcher` intentionally supports only `ingest_source`. | Run synchronously via adapter; do not extend dispatcher. |
| Trusted identity | Existing `operator_id` strings are attribution fields, not authenticated principals. | Accept typed host principal; persist stable issuer/subject, never request/model strings. |
| Target and replay | Task has no `input_refs` or request-key column; Event's `(task_id,type)` index is non-unique. | Host idempotency UUID resolves the same Task; request Event stores a fingerprint. Add schema only if tests prove a gap. |
| Recovery | Every stale running Task is considered interrupted after 60 seconds. | An uncommitted approval Task follows ordinary retry/exhaustion. A stale Task whose LearningChange decision is already committed is finalized from that durable decision before retry/exhaustion. Other Task types retain generic 60-second behavior. |
| Budget | Generic Tasks require positive `deadline_seconds`; approval Task intentionally has no model/tool deadline. | Implemented no-deadline allowance only for a structurally valid `approve_learning_change` Task. Generic deadline checks, daily quota, and 60-second stale recovery remain unchanged. |

## 2. Existing repository facts

### 2.1 No deployed authentication surface

The repository contains the domain core and tests, not a running Watch API/CLI host. ADR-0011's earlier "created by the API" wording describes intended integration, not an existing deployed component.

Do not add FastAPI routes, command-line authentication, credentials, sessions, token verification, user tables, or a standalone service merely for Checkpoint 3. The host is the authentication root.

### 2.2 Task creation and lifecycle

- The only production Task-row construction path found is Plan materialization in `core/plans.py`. It creates pending Plan-linked Tasks with `allowed_writes=["Signal"]`; it is not an Operator Task factory.
- `TaskRuntime.admit(task_id)` locks and admits a pre-existing pending Task, validates active Team, pinned TeamPolicy version, budget shape, attempt limit, prerequisites, and daily quota, then increments the attempt and emits `task_started`.
- Admission is generic. It does not prove that `task_type` and `allowed_writes` agree. Adapter and decision service must enforce exact approval type and grants.
- `TaskRuntime.finalize` owns terminal Task status, terminal Events, and terminal `task_execution` Outcome. Current typed success categories include proposal and Evaluation results, not accepted/rejected LearningChange decisions.
- `TaskDispatcher` supports only `ingest_source`; its recovery entrypoint calls the existing runtime. Do not turn it into an Operator dispatcher.

### 2.3 Persistence

Migration `0012_learning_foundation` stores LearningChange operation/target, proposal state, evidence basis/hash, disposition, previous/committed state, rejection reason, operator ID, committing Task ID, and timestamps. KnowledgeItem is canonical/versioned; composite foreign keys enforce same-Team proposing/committing Task references.

It does **not** add Task `input_refs`, approval-target or generic request-key columns, unique request Event constraint, Operator table/issuer foreign key, or database proof that `committed_by_task_id` is an admitted approval Task with exact scope. Application code owns those semantic checks.

## 3. Trusted host principal contract (D8)

**Host application:** authenticate the Operator; authorize the principal for target Team and exact `approve_learning_change` action; pass a typed in-process principal containing stable issuer/subject and Team/action authorization context; invoke the adapter only from a host-controlled call path. Never construct principal context from request-body fields, model output, or client-controlled `operator_id`.

**Watch adapter:** accept typed context, not a bare actor string; validate non-empty stable issuer/subject and persisted length without truncation; require exact Team/action authorization; canonicalize namespaced issuer + subject and persist it in `LearningChange.operator_id` and decision Event.

A small frozen `TrustedOperatorPrincipal` with issuer/subject plus host authorization context is sufficient. A Python dataclass/protocol is **not** a cryptographic credential or unforgeable within a process. Trust comes from host-controlled call site/composition root. Do not expose the adapter directly to untrusted network input. Fake principal/authorizer tests prove Watch's contract, not that a production host authenticated a person.

Use stable issuer + subject, not display name/email. `LearningChange.operator_id` is `String(255)`; reject overlong canonical identities rather than truncating/aliasing. Widen only if a real host identity requires it.

### 3.1 Existing raw-string methods are not trusted boundaries

`ObjectiveService.create` and `transition` accept `operator_id: str | None` and copy it into Event payloads. Test values such as `"operator-1"` prove attribution only, not authentication/authorization. Do not copy that signature into the approval adapter. This audit does not refactor unrelated Objective methods.

## 4. In-repository application adapter

Proposed module: `core/operator_application.py`. It is an in-process application integration seam, not deployed API/CLI.

Expose one narrow synchronous operation, conceptually:

`decide_learning_change(principal: TrustedOperatorPrincipal, request: LearningChangeDecisionRequest) -> LearningChangeDecisionResult`

Request carries the LearningChange ID, decision, rejection reason when rejecting, and host-generated idempotency UUID; the adapter derives Team from the locked LearningChange rather than trusting a caller-supplied Team. It does not carry authoritative actor identity.

The adapter validates principal/authorization; loads target and derives/validates its Team; resolves or atomically creates one pending approval Task + request Event; calls `TaskRuntime.admit`; invokes `LearningCommitService` with same Task/attempt/principal/target/decision; then calls `TaskRuntime.finalize` with typed result. Never insert a running Task or mutate Task lifecycle fields/events directly. No worker, model, dispatcher, or background queue. Authentication remains in host; commit validation remains in Watch.

## 5. Approval Task and idempotency (D12)

Create a pending Task with `task_type="approve_learning_change"`, target Team/current policy version, no Objective/Plan/Action links, exact `allowed_writes=["LearningChange", "KnowledgeItem"]`, zero tools/cost, and no Plan prerequisites. Event writes are exact application-managed effects, not worker grants. Creator inserts initial pending row only; TaskRuntime owns subsequent lifecycle.

The host supplies one opaque idempotency UUID per decision and reuses it for every retry. Derive deterministic Task UUID (UUIDv5, fixed application namespace) from Team + approval Task type + request UUID. Insert Task and one `operator_task_requested` Event in the same transaction. Event records target LearningChange ID, decision, canonical host identity, current policy version, and deterministic request fingerprint (including rejection reason); store hash of key/fingerprint.

On retry, same key maps to same Task primary key. Require exactly one matching request Event and identical Team/target/decision/actor/fingerprint. Same request replays; same key with changed content/identity conflicts. Different key may create another Task, but only one decision can win the locked LearningChange transition. Task primary-key uniqueness is the race boundary; Task/Event insert is atomic. PostgreSQL tests must cover duplicate creation and missing/multiple/corrupted request Events. Event index is not a uniqueness constraint.

This avoids premature generic Task schema changes. Add a minimal migration only if restart/concurrency tests demonstrate an integrity gap.

## 6. Canonical decision and TaskRuntime

Lock approval Task, LearningChange, and target KnowledgeItem deterministically. Recheck exact Task type/status/current attempt/same Team/current policy/no Plan links/scope; host authorization and canonical actor must match request Event. Revalidate proposed status, operation/target, full evidence hash, source/evaluator Tasks, Outcomes, Evaluations, EvidenceLinks, Snapshot hashes/quotes, Team ownership, and target version/status.

**Accept:** for the real Checkpoint 2 create proposal, atomically create KnowledgeItem and write LearningChange accepted state/history, operator ID, Task ID, timestamp, and one decision Event.

**Reject:** atomically write LearningChange rejected state, non-empty reason, operator ID, Task ID, timestamp, and one rejection Event; do not create or mutate KnowledgeItem.

No TeamPolicy writes. Model output cannot choose actor or disposition.

Add narrow typed accepted/rejected LearningChange terminal results. Include LearningChange ID, decision, canonical operator identity (or equivalent typed object); finalizer checks committed LearningChange and matching decision Event against same-Team approval Task/current attempt. Rejection is a **successful Operator decision**: Task ends `done`, LearningChange ends `rejected`; it is not a failed execution.

Business decision transaction and TaskRuntime finalization remain separate, as in existing business-commit/replay pattern. Decision Event is atomic with LearningChange/KnowledgeItem; TaskRuntime alone writes terminal Task Event, Outcome, status, and completed timestamp.

### 6.1 Crash/recovery and budget (D11)

The human decides before adapter invocation; a Task must never wait in `running` for a person. A crash after canonical decision but before TaskRuntime finalization must resolve the same Task from the same host key, replay the decision without another KnowledgeItem/version, and finish through TaskRuntime. If 60-second recovery returned Task to pending, re-admit same Task; attempt fencing rejects older in-flight attempts.

Keep generic `recover_interrupted()` unchanged unless tests prove a conflict. The approval-specific no-deadline exception is implemented in `TaskRuntime.admit` and is bound to the exact Task shape and durable request Event. Ordinary Task types continue to require positive `deadline_seconds`. Retain generic 60-second stale-running recovery; it is orphan recovery, not time for a human decision. Do not invent a fake deadline or weaken other Task types.

## 7. Reachability and remaining gates

Checkpoint 2 ExperienceDistiller emits only `operation="create"` proposals. Checkpoint 3's verified approval/rejection path consumes those real proposals. By explicit operator decision on 2026-11-02, D10 is resolved: Checkpoint 3's acceptance scope is create-only. Revise/retire proposal production and commitment are deferred beyond Checkpoint 3 until a separately authorized knowledge-lifecycle scope supplies a genuine proposal source and defines target-version pinning, history, concurrency, replay/recovery, and projection invalidation. The schema's revise/retire vocabulary does not authorize implementation or production support. Do not use `seed_knowledge`, ad-hoc endpoints, direct fixtures, direct database mutation, or other bypasses to claim reachability. Future revise/retire decisions must retain Operator approval and canonical learning-commit authority.

D7 (`review_after`) was resolved on 2026-11-02: the optional interval is TeamPolicy-controlled and pinned to the approval Task's policy version; timestamps and due checks use UTC; NULL and due items are ineligible for retrieval; only a deterministic `review_knowledge` Task moves `active → needs_review`. Checkpoint 3 still writes NULL dates and does not implement this policy. Date assignment, review Task execution, and retrieval enforcement remain gated Checkpoint 4 work; D7 does not authorize that checkpoint.

## 8. Implementation and verification sequence

1. **Implemented:** add host principal/authorization contract and `OperatorApplicationAdapter`; no routes, CLI, login, token verifier, user table, or deployed service.
2. **Implemented:** atomic pending Task + request Event creation, deterministic request mapping, same-request replay/conflict.
3. **Implemented and locally verified:** TaskRuntime approval-only admission guard, exact Task shape and request Event/fingerprint/target validation, and no-deadline budget exception. Generic Task deadline validation, daily quota, and 60-second interrupted recovery are unchanged.
4. **Implemented on current draft PR #31 head; local verification pending:** create-only `LearningCommitService`, provider-free canonical evidence-pack reconstruction, atomic accept/reject and Task-attributed decision Event, plus exact replay checks for Event payload/timestamp, attempt-start history, and full committed KnowledgeItem state.
5. **Remaining TaskRuntime/orchestration work:** typed accepted/rejected terminal results and validation of committed decision/Event against the approval Task and current attempt; wire the host adapter synchronously through admit → decide → finalize.
6. Test host context provenance, raw/model identity rejection, wrong Team/action, exact scope, same-key duplicate/concurrency, changed payload conflict, accept/reject, evidence tampering, stale target, and rollback.
7. Test rejection-as-done, result/task mismatch, stale attempts, crash after decision commit, recovery to pending, same-Task replay/finalize, and stale-attempt fencing.
8. Verify whether a migration is necessary; preferred design adds none unless tests prove an integrity gap.
9. Run focused tests, Ruff, mypy, full suite, disposable PostgreSQL locking/rollback/recovery tests, and `git diff --check`. No live R6-F provider.

## 9. Decision register

| Decision | Audit outcome |
|---|---|
| D8 — trusted Operator boundary | **Direction resolved by operator instruction:** host authenticates/authorizes and calls thin in-repository adapter with typed principal context. No separate Watch API/CLI or auth subsystem. Real host integration still required before claiming a deployed authenticated flow. |
| D11 — deadline/recovery | **Recommended implementation contract:** synchronous post-decision Task, no human wait, no-deadline budget for this Task type only, generic 60-second stale recovery preserved, same-Task replay mandatory. Validate this narrowly in TaskRuntime and PostgreSQL tests; it is not a new global recovery policy. |
| D12 — target/idempotency | **Preferred implementation design:** host idempotency UUID → deterministic approval Task UUID; atomic request Event stores target/fingerprint. Revisit schema only if PostgreSQL tests expose an integrity gap. |
| D10 — revise/retire reachability | **Resolved 2026-11-02 by explicit operator decision:** Checkpoint 3 is create-only. Revise/retire production and commitment are deferred to a separately authorized knowledge-lifecycle scope with a genuine proposal source and explicit version/history/concurrency/recovery/projection semantics. No seed or bypass. |
| D7 — review date | **Open:** no review interval or retrieval eligibility semantics. |

**Audit conclusion (updated 2026-11-02):** the external API/CLI blocker is removed and the create-only Operator approval lifecycle is implemented and verified both locally and in hosted CI on code head `581ad185` (83 focused and 577 full-suite local tests; 577 hosted tests). D10 is resolved: revise/retire proposal production and commitment are deferred beyond Checkpoint 3 under a separately authorized knowledge-lifecycle scope. No seed/bypass path, new provider, Dispatcher expansion, TeamPolicy grant, schema migration, Checkpoint 4 work, or R6-G work is included. Checkpoint 3 formal closeout now depends on PR #31's documentation CI, review, and merge; D7 remains a separate prerequisite to resolving retrieval eligibility for Checkpoint 4.
