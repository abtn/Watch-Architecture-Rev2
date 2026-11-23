# RW-4 — Signal Triage and World-Memory Retrieval Design

**Status:** documentation/design proposal only; RW-4 implementation is not authorized.
**Planning baseline:** main after PR #172, merge commit `5e8a8bfa1dd0bbda37d0eab77c301b5713f2bffa` (2026-11-23).
**Authority:** PLAN.md owns current milestone status and authorization. Accepted RW decisions and the Task/write-scope matrix remain binding.

## 1. Purpose

RW-4 connects an ingested canonical Signal to a Team-specific world-memory Thread through deterministic triage, then makes accepted active Hypotheses and verified evidence available to a later Task through the existing bounded Context path.

The intended path is:

Signal → Team-scoped triage_signal disposition → existing or newly created/reactivated Thread → later Task Context containing eligible active Hypotheses and verified EvidenceLinks.

Triage is deterministic application behavior. It is not model reasoning, and a similarity score is not authority to create a Thread by itself. A new_thread decision requires the accepted strong-match rule. Ambiguous or failed matching remains explicit as deferred; a Signal must never disappear silently.

## 2. Accepted constraints and dependencies

The following are existing constraints, not new decisions in this document:

- RW-D16: triage_signal is the only canonical Thread-creation path in the first newsroom slice, with scoped new_thread permission. update_thread and operator_update refine existing Threads only.
- RW-D21: preserve the shared EvidenceLink model and existing Evaluation/distillation behavior. Do not add automatic Hypothesis-to-Evaluation linkage or new distillation behavior without a demonstrated scenario requirement.
- RW-D134: every implementation slice needs an explicit requirement-to-test proof matrix, exact-head verification, and disposable-PostgreSQL evidence where applicable.
- RW-D135: documentation closeout and decision approval do not authorize implementation or scored execution.
- RW-5 decay is an independently implementable slice: its design, implementation, and unit-level decay proofs do not wait for RW-4 triage or Experiment A. The integration boundary is narrower: the combined RW-4/RW-5 proof must exercise a deterministically matched Signal reactivating the selected dormant Thread and then verify decay behavior and retrieval against the resulting post-decay state. RW-4 must define and prove the reactivation transition and freeze its matching conditions before RW-4 coding; that freeze is not a prerequisite for independent RW-5 implementation. Experiment A informs RW4-4 representation only and does not block RW-5 planning or implementation.
- The RW-3 update_thread Task creator remains the host-authorized Operator operation. Triage must not create or enqueue update_thread Tasks. Any future application-authored follow-up creator requires a separate actor, authorization, attribution, request-Event, idempotency, and replay design and explicit approval.
- The existing TaskRuntime remains the sole Task lifecycle authority. The current TaskDispatcher remains limited to configured-source ingest_source work unless a separate dispatcher change is designed and authorized.

RW3.4 implementation is merged, but its formal acceptance was explicitly deferred by the Operator and recorded in PR #171. RW-4 documentation planning may proceed. Before RW-4 implementation begins, the Operator must either resolve the bounded RW3.4 acceptance work and accept RW3.4, or explicitly approve a sequencing exception while retaining the deferred disposition. This document does neither.

## 3. Current source audit

This is a read-only source/spec inspection against the planning baseline above. No tests, migrations, database queries, or provider calls were run for this audit.

| Concern | Current implementation evidence | RW-4 consequence |
|---|---|---|
| Signal | core/models.py stores domain, source type, origin URL, fetch time, content hash, and Snapshot reference. core/ingestion.py implements ingestion only. | Signal ingestion is a usable predecessor, not triage. The Task-name entry in the Event allow-list is not an implementation. |
| Signal embeddings | Embeddings and their model/configuration identity are stored on KnowledgeChunk projections in core/models.py / core/knowledge_index.py; Signal has no direct embedding field. | The documented “Signal embedding” must be reconciled with the existing chunk projection and its provenance/rebuild rules. |
| Thread | The current ORM model stores Team, domain, title, status, and timestamps. It has no embedding or summary projection. | The documented “Thread embeddings” and summary are not available as current implementation. Do not assume they exist or add projections without a demonstrated need and accepted design. |
| Domain and matching configuration | The current Team model contains domain and status. No Domain ORM/configuration model or implemented match_heuristics / dedup_policy source was found in the inspected paths. | The owner, schema, versioning, and validation of matching/dedup configuration are unresolved. Do not invent a new Domain subsystem or silently overload TeamPolicy. |
| SignalDisposition | Specified in docs/architecture.md and docs/tasks.md; no ORM model, migration, triage service, or commit path exists. | Physical representation, uniqueness, transition semantics, and Task attribution must be frozen before implementation. |
| Task execution | core/dispatcher.py supports only ingest_source. triage_signal is present in the Event-scope allow-list but has no creator or execution adapter. | The trigger, Task creator, immutable request, Team selection, admission, retry, and replay contract must be designed. Do not infer automatic follow-up creation from ingestion. |
| Existing Context | core/context_assembly.py assembles Objective-scoped Strategy Task Context using Domain Knowledge and Team Experience retrieval. core/update_thread_context.py assembles the separate RW-3 target-Thread Context with active same-Thread Hypotheses and accepted EvidenceLinks. | RW-4 must identify the later Task consumer and extend the appropriate existing Context path. Do not create a parallel Context subsystem or weaken RW-3's target-Thread contract. |

The current source therefore does not yet support the complete matching inputs described in the Task specification. The mismatch is a design task, not permission to build every previously described projection.

## 4. Design decisions required before implementation

The following decisions are open. The architecture/Task documents provide target behavior, but they do not settle every physical and runtime detail exposed by the current source audit.

### 4.1 Triage Task identity and invocation

Freeze:

- Who or what creates a triage_signal Task, and under what trusted authority.
- Whether triage is explicitly requested, scheduled, or initiated by a separately authorized application operation after ingestion. No automatic ingest_source → triage_signal Task creation is assumed.
- How the Team is selected for a Signal. Signals are not Team-owned; one Signal may have a separate disposition for each Team.
- The immutable request identity and idempotency scope. The candidate identity is a Signal/Team pair, but the exact request fields, key ownership, fingerprint, replay, and conflict behavior must be approved.
- Admission, attempt, failure, retry, and recovery behavior through TaskRuntime. No adapter may write Task lifecycle state directly.

### 4.2 SignalDisposition contract

The architecture describes one disposition per (signal_id, team_id), with a disposition from matched, new_thread, noise, duplicate, or deferred; optional Thread and duplicate-Signal references; a reason; and Task attribution.

Before schema work, freeze:

- Exact columns, keys, foreign keys, uniqueness, checks, indexes, nullability, and timestamp behavior.
- Whether a disposition is immutable with append-only refinement Events or is a mutable current-state row with a fully auditable transition history.
- The exact meaning and allowed references for thread_id and duplicate_of_signal_id, including Team/domain isolation.
- The legal transition out of deferred, who may perform it, and which Task/write scope owns it.

There is a contract gap to resolve: the architecture lifecycle table describes deferred refinement by update_thread or operator_update, while the accepted RW-2/RW-3 commit implementation does not currently write SignalDisposition and RW-3 explicitly excludes its creation/refinement. Do not widen either accepted write scope implicitly. Decide whether RW-4 owns a narrowly scoped refinement operation or whether deferred is terminal for the first RW release.

### 4.3 Matching, deduplication, and Thread creation

Freeze the smallest deterministic algorithm that satisfies the selected newsroom scenario:

- The authoritative source and version of domain-specific matching and deduplication rules.
- Whether matching reuses Signal-derived KnowledgeChunk embeddings, introduces a derived Thread representation, or uses a smaller deterministic non-vector rule. Any projection must be regenerable and non-authoritative.
- Embedding-space identity, compatibility checks, candidate scope, similarity thresholds, tie-breaking, ordering, candidate limits, and behavior at threshold boundaries.
- The time window and same-Team/domain rules for near-duplicate Signals, and the exact meaning of duplicate_of_signal_id.
- The deterministic source for a new Thread title and domain. Do not generate titles with a model in this slice unless separately approved.
- The strong-match condition required for new_thread; weak or ambiguous matches must remain deferred.
- The exact condition under which a matched Signal reactivates a dormant Thread. Noise, duplicate, deferred, and unrelated matches must not reactivate it.

Do not introduce general-purpose domain-pack machinery merely to host these rules. Reuse an existing configuration boundary only if its current schema and semantics actually support the required rules.

### 4.4 Later Task Context read path

Freeze the exact consumer Task type(s) and Context entry point before implementation. The proposed behavior is:

- Include only active Hypotheses belonging to the current Task's Team and eligible Thread scope.
- Include only accepted EvidenceLinks attached to those Hypotheses.
- Revalidate canonical Team/Thread/Hypothesis ownership, source identity, immutable Snapshot hash, and exact quote/offset correspondence before model exposure.
- Use deterministic ordering and explicit count/character/token bounds. Do not silently rank away canonical active Hypotheses, truncate evidence, or replace invalid references with mutable source text.
- Preserve immutable Context Snapshot and manifest Event identity, replay, and schema-version behavior.
- Keep this read path distinct from the already implemented RW-3 target-Thread Context. The RW-3 Context is not to be broadened to other Threads.
- Do not assume RW-3's 8-Hypothesis / 8-EvidenceLink / 8-Snapshot / 8,000-character bounds automatically apply to another Task Context. Select and justify the bound for the actual consumer.

The existing Strategy Task Context already contains Signal retrieval and Team Experience. The design must state how world-memory records coexist with those inputs, and must preserve the current retrieval and provenance guarantees.

### 4.5 Minimum claim-level attribution (RW-4-KU)

RW-D133 maps only the minimum D99 capabilities—immutable application-written TaskKnowledgeReference and typed application-validated KnowledgeUseAssessment—to the planned RW-4-KU sub-slice. The current proof matrix records proposed test modules and exact obligations.

Keep RW-4-KU separately named and separately gated. Before authorizing it, confirm its precise dependency on the core RW-4 retrieval path and the newsroom value-harness Gate 3. This is not authorization for the R7-C milestone, a broad retrieval benchmark, autonomous evaluation, or a learning loop.

### 4.6 Experiment A and R8

Experiment A's canonical fixtures are an offline research artifact, not an executed experiment. Its model execution remains a distinct planned work item and requires the separate authorization defined in the [Experiment A execution plan](experiment-a-execution-plan.md).

The Operator has accepted the following dependency rule:

- Experiment A informs the RW4-4 model-facing evidence-representation decision. Its result should inform the choice before that representation is frozen.
- RW4-4 may proceed without a usable Experiment A result only if the selected representation, rationale, and residual uncertainty are explicitly recorded as an Operator disposition before the representation is frozen.
- Experiment A does not block RW4-0 through RW4-3, and does not block RW-5 planning or implementation.
- Experiment A does not prove multi-Thread retrieval, RW-4 Context safety, RW-5 decay, or the integrated RW-4/RW-5 behavior. Those retain separate proof obligations.
- Before foundation exit/R8, the Experiment A result must have an accepted report and limitations, or an explicit Operator disposition that the result is inconclusive or not required for the selected RW4-4 representation, with residual uncertainty carried forward.
- RWN-01 remains a separate newsroom retained-experience experiment.

This dependency decision does not authorize Experiment A provider execution, RW-4/RW-5 implementation, or R8.

R8 remains unscheduled. Its start date is TBD until RW-4/RW-5 estimates, the Experiment A disposition, newsroom package readiness, and the foundation exit forecast are evidence-based and accepted.

## 5. Proposed implementation sequence

These are planning stages, not approved code changes. Each implementation stage requires its own reviewed scope and explicit Operator authorization.

| Stage | Work | Exit evidence |
|---|---|---|
| RW4-0 — design freeze | Resolve §4 decisions; reconcile architecture, Task/write-scope matrix, data ownership, Task invocation, and Context consumer. Obtain independent review. | Accepted design, explicit open-risk disposition, frozen requirement-to-test matrix, and exact file/test scope. No code or migration. |
| RW4-1 — disposition persistence | Prepare the physical SignalDisposition schema and migration only after the representation and transition contract are accepted. Preserve existing Signals, Threads, and EvidenceLinks. | Disposable-PostgreSQL migration/constraint/rollback proofs, uniqueness and Team-isolation proofs, and populated-state compatibility evidence where applicable. |
| RW4-2 — Task boundary | Implement the approved immutable triage request/creator and TaskRuntime-owned execution/admission boundary. Keep TaskDispatcher unchanged unless its expansion is separately designed and authorized. | Creator authorization, Team derivation, exact Task/write scope, idempotency/replay/conflict, lifecycle/recovery, and no direct Task-state mutation proofs. |
| RW4-3 — deterministic triage commit | Implement matching/dedup decisions, explicit deferred outcomes, atomic SignalDisposition + permitted Thread create/reactivation + Event commit, and the approved transition/refinement path. | All disposition branches, threshold/tie cases, duplicate/replay/concurrency, atomic rollback, Task attribution, and no unapproved follow-up Task proofs. |
| RW4-4 — world-memory Context read path | Extend the selected existing Task Context path with bounded, same-Team active Hypotheses and verified EvidenceLinks. Preserve immutable Snapshot/manifest replay. | Freeze the model-facing evidence representation using the Experiment A result, or record an explicit Operator-approved rationale and residual uncertainty if no usable result is available. Then prove positive/negative scope, exact source/quote validation, deterministic ordering, bounds/overflow, stale-reference rejection, and replay integrity. |
| RW4-KU — claim-level attribution | Implement the D99/D133 minimum only after its dependency and exact scope are accepted. Keep it a separately gated sub-slice. | Exact KnowledgeItem/version/LearningChange/Team/Context binding, immutable references, typed assessment against the later Task Outcome, replay, and invalid/stale/forbidden-scope rejection. |
| RW4-5 — integrated closeout | Reconcile Task/architecture/CHANGE_MAP/PLAN, run exact-head local and hosted verification, and review the complete source-to-Context path. | Exact tested SHA, required CI and disposable-DB evidence, no live provider or persistent-DB use, residual ledger, and explicit Operator acceptance. |

RW4-1 through RW4-4 may be split further if the frozen contracts require independent review. Do not combine unrelated schema, runtime, matching, and Context changes into one large implementation PR merely to reduce PR count.

## 6. Required proof obligations

The exact test nodes must be named before RW-4 implementation authorization under RW-D134. The following behaviors are the minimum proposed proof set; refine them only when the decisions in §4 are frozen.

### Triage and persistence

- One disposition per Signal/Team pair; the same Signal may be triaged independently by multiple eligible Teams.
- Cross-Team and cross-domain Signal, Thread, duplicate, and disposition references are rejected.
- Every disposition is Task-attributed and has a durable reason; no Signal is silently dropped.
- matched, new_thread, noise, duplicate, and deferred branches are deterministic and have explicit expected state changes.
- new_thread occurs only at the frozen strong-match boundary; ambiguous, missing, or failed heuristic inputs fail closed to the approved deferred behavior.
- Near-duplicate detection uses the frozen scope/time window and cannot cross the approved Team/domain boundary.
- A matched Signal reactivates only the deterministically selected dormant Thread. Other dispositions do not reactivate it.
- A disposition replay returns/reuses the canonical result without duplicate Thread, disposition, or Event writes. A changed request under the same idempotency identity conflicts without mutation.
- Thread creation/reactivation, disposition persistence, and the required Event are atomic. A failed commit leaves no partial state.
- Deferred refinement follows only the explicitly accepted owner/transition contract.
- Triage creates or enqueues no update_thread Task or any other unapproved follow-up Task.

### Context retrieval

- Only eligible active Hypotheses and accepted EvidenceLinks for the authorized Team/Thread scope are included.
- Rejected/superseded Hypotheses, unaccepted or stale EvidenceLinks, cross-Team references, missing Snapshots, hash mismatches, and altered quote offsets fail closed or are excluded exactly as the frozen contract specifies.
- Ordering and serialized Context are deterministic across repeated runs.
- Count/character/token limits are enforced without silent truncation or discretionary omission.
- Context Snapshot bytes, hash, manifest Event, Task identity, and replay are mutually consistent; prior immutable Context is not silently rebuilt under a new retrieval configuration.
- Existing Domain Knowledge and Team Experience behavior remains unchanged except for the explicitly approved addition of world-memory records.

### Integration and safety

- TaskRuntime remains the only lifecycle authority; no second scheduler/runtime or direct lifecycle writes.
- Business write scope is exactly the approved triage scope. Event and Outcome effects remain Kernel/TaskRuntime side effects.
- No model call is needed for deterministic triage. Ordinary CI uses deterministic fixtures; no live provider call is part of RW-4.
- Database-backed proofs use disposable PostgreSQL only. No persistent database operation or scored newsroom execution is authorized by this plan.

## 7. Exit criteria and non-authorizations

RW-4 may be requested for acceptance only when:

1. The frozen triage and Context contracts are implemented without widening accepted Task authority.
2. Every applicable proof obligation passes on the exact implementation head, with required race/mutation and disposable-PostgreSQL evidence.
3. The end-to-end path from canonical Signal to Team-scoped Thread/disposition and later Task Context is demonstrated.
4. Documentation and CHANGE_MAP match the verified implementation.
5. Hosted CI and Programmer-local verification are recorded against their exact SHAs.
6. Residual risks and any external integration limits are explicitly presented.
7. The Operator records formal RW-4 acceptance.

This design PR does not authorize RW-4 implementation, a migration, a test-only follow-up, dispatcher expansion, live provider calls, persistent-database access, R7-C as a separate milestone, scored RWN-01 execution, RW-5, or R8. Those remain separately gated.

## 8. Operator decisions still required

Before RW4-0 can close, review and decide:

1. The trusted creator/trigger and immutable request identity for triage_signal.
2. The source and versioning boundary for matching/dedup rules, including whether existing Signal chunk embeddings are sufficient and how candidate Threads are represented.
3. The disposition transition/refinement owner, especially the current deferred contract gap with RW-2/RW-3.
4. The exact new-Thread title/source rule and the dormant-Thread reactivation condition.
5. The later Task type(s), Context assembler, and justified bounds for world-memory retrieval.
6. Whether RW4-KU is an RW-4 acceptance prerequisite or a separately accepted sub-slice before the foundation exit gate.
7. The accepted Experiment A dependency rule is fixed as described in §4.6. Separately, approve the remaining Experiment A protocol decisions in its execution plan before EA-0 closes; those protocol decisions do not reopen the accepted RW4-4/RW-5 dependency mapping.
8. Whether RW-4 implementation waits for RW3.4 formal acceptance or proceeds only under an explicit sequencing exception.

No implementation stage should begin by treating an unresolved item above as an implicit default.
