# D1 Existing-Writer Control Room Conformance — Implementation Plan

**Status:** implementation authorized by the Operator on 2026-11-27 as a narrowly scoped sequencing exception.
**Implementation baseline:** Path A merge commit `194e60379a0d1ee1bfd57520391a786edf1c178a`.
**Scope:** migrate the ten existing supported Task producers to the accepted Control Room-owned operations. This is not RW4-2 Stage B and does not implement a triage Task creator.

## 1. Authorization and sequencing exception

The accepted Full Design sequence remains RW4-1 → RW-5 helper/Team revision/writer retrofit → RW4-2 Stage B triage creator. The Operator has separately authorized the existing-writer D1 conformance refactor to proceed before RW4-1, as an isolated implementation slice.

This exception applies only to the ten existing producers listed below. It does not reorder or authorize:
- SignalDisposition schema, persistence, writes, or replay;
- a `triage_signal` Task creator or triage request Event;
- RW-5 lock helper, Team revision, decay, or writer retrofit;
- RW4-2 Stage B creator/replay implementation;
- RW4-3 matching/commit, RW4-4 Context retrieval, or RW4-5 reactivation.

## 2. Frozen authority boundary

The Control Room is the sole logical application authority that constructs and persists supported Tasks. It is a small in-process module/facade, not a new service, framework, queue, scheduler, or generic Task factory.

Each named Control Room operation:
- receives the caller's already-active SQLAlchemy `Session`;
- constructs and persists the Task (and its request Event where the existing workflow requires one);
- flushes only as needed;
- never creates a Session or begins, commits, or rolls back a transaction;
- preserves the caller's existing authorization, identity, idempotency, policy pin, and replay checks.

The caller remains responsible for its existing business workflow and outer transaction. TaskRuntime remains the sole authority for admission, attempts, retries, interruption, recovery, terminalization, and finalization. The Control Room must not mutate Task lifecycle state.

## 3. Ten producer migrations

| # | Existing producer | Required Control Room operation | Caller-side behavior that must remain |
|---:|---|---|---|
| 1 | `OperatorApplicationAdapter` update_thread host entrypoint | `create_update_thread_task` | Host principal/grant validation, Thread-derived Team, policy pin, idempotency/replay/conflict, existing request Event shape |
| 2 | LearningChange decision request in `OperatorApplication` | `create_approve_learning_change_task` | Operator authorization, approval binding, request fingerprint, pinned policy, idempotency/replay/conflict |
| 3 | Operator update request in `OperatorApplication` | `create_operator_update_task` | Existing host authorization, request fingerprint, request Event, replay, and TaskRuntime invocation |
| 4 | Plan materialization in `PlanService` | `create_ingest_source_task` | One child Task per accepted PlanAction, same policy pin and parent Plan transaction |
| 5 | TaskRuntime Knowledge Quality follow-on | `create_assess_knowledge_quality_task` | Existing validation and same TaskRuntime Session/terminal transaction |
| 6 | TaskRuntime Knowledge Revalidation follow-on | `create_assess_knowledge_revalidation_task` | Existing validation and same TaskRuntime Session/terminal transaction |
| 7 | TaskRuntime Knowledge Lifecycle follow-on | `create_assess_knowledge_lifecycle_task` | Existing validation and same TaskRuntime Session/terminal transaction |
| 8 | TaskRuntime follow-on Evaluation | `create_evaluate_outcome_task` | Existing source-terminal evidence validation and same TaskRuntime Session/terminal transaction |
| 9 | `KnowledgeRevalidationService` producer | `create_assess_knowledge_revalidation_task` | Its distinct workflow-specific validation/replay remains separate; it converges only at Task persistence |
| 10 | `KnowledgeLifecycleAssessmentService.create_task` | `create_assess_knowledge_lifecycle_task` | Its LearningChange row lock, deterministic Task ID, existing-task validation/replay, and service-owned transaction remain unchanged; only new Task/Event persistence delegates |

The two Knowledge Revalidation producers must remain separate workflows and use the same named persistence operation. Do not consolidate their business logic.

## 4. Implementation sequence

1. Add the smallest `core.control_room` module with the eight named operations. Keep Task envelope constants and Event types explicit in the owning operation; do not accept caller-constructed `Task` objects as a substitute for centralized construction.
2. Migrate the two OperatorApplication paths and the update_thread adapter, preserving their current transaction and replay behavior.
3. Migrate PlanService child Task materialization inside its existing transaction.
4. Migrate all four TaskRuntime follow-on producers using the existing Session and transaction. Do not introduce nested sessions or alter terminalization ordering.
5. Migrate KnowledgeRevalidationService to the shared revalidation persistence operation without merging its workflow with TaskRuntime's workflow.
6. Migrate `KnowledgeLifecycleAssessmentService.create_task` to the existing lifecycle persistence operation. Preserve its deterministic identity, `LearningChange` lock, validation/replay branches, and outer service transaction.
7. Add focused unit/integration regression coverage for every operation and caller, including negative/replay/conflict behavior and atomic rollback.
8. Search the complete production source tree for remaining direct Task construction/persistence. Classify every remaining occurrence as either a migrated Control Room operation or a non-creation lifecycle/load path; no supported producer may retain a direct-persistence fallback.
9. Run focused tests, the full test suite, Ruff, Mypy, and `git diff --check`; run PostgreSQL-backed tests on the configured disposable database. Do not use the persistent local `watch` database.
10. Independently review the complete diff against the ten-writer matrix and accepted D1 transaction/authority contract. Reconcile `PLAN.md`, `CHANGE_MAP.md`, the RW4-2 audit, and the Path A capability matrix with exact implementation evidence.
11. Submit a separate PR. Do not merge it or declare D1 closed until exact-head CI and independent review pass.

## 5. Required proof matrix

- **Authority:** all ten callers delegate; no caller constructs/persists a Task; no alternate factory or fallback remains.
- **Transaction:** each operation uses the supplied Session; no internal Session creation, begin, commit, or rollback; Task and required Event roll back together.
- **Authorization:** each caller's pre-existing principal/grant checks remain in force; payload fields cannot create or override authority.
- **Identity/replay:** existing deterministic IDs, request fingerprints, Event payloads, pinned policy versions, same-key replay, and conflicting-key behavior remain byte/semantically equivalent.
- **Plan materialization:** all child Tasks remain in the Plan transaction and the parent Event lists the same child IDs.
- **TaskRuntime atomicity:** each follow-on remains in the originating Task's existing terminal/follow-on transaction; rollback cannot leave a partial follow-on Task/Event.
- **Knowledge Revalidation:** both producer workflows remain distinct while using the same Control Room persistence operation.
- **Lifecycle ownership:** no Control Room code admits, retries, executes, recovers, or terminalizes a Task.
- **Repository-wide audit:** no supported direct Task writer remains outside `core.control_room`.

## 6. Explicit exclusions and stop conditions

Do not change Task schema, migrations, database roles, lock protocols, TaskDispatcher, provider behavior, worker write scopes, or Task lifecycle semantics in this slice. Do not implement the triage creator. Do not weaken existing validation to simplify delegation.

Stop and report if a producer cannot preserve its existing authorization or transaction boundary using the accepted session-bound operation contract. Any required change to an accepted request/Event schema, identity, lock order, or external behavior requires a separate decision rather than being smuggled into this refactor.

## 7. Verification reporting

Report exact branch/head, changed files, all ten producer outcomes, focused/full test results, Ruff/Mypy results, PostgreSQL test environment, exact-head CI, and unresolved limitations. A source search alone is not proof of transaction or replay equivalence. Do not call D1 implementation complete until the full proof matrix and independent review pass.
