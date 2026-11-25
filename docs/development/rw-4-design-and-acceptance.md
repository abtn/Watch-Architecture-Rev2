# RW-4 — Signal Triage and World-Memory Retrieval Design

**Status:** documentation/design proposal only; RW-4 implementation is not authorized.
**Planning baseline:** main after PR #173, merge commit `126063199c919a9576e20f4909781f0776d1ca87` (2026-11-23).
**Authority:** PLAN.md owns current milestone status and authorization. Accepted RW decisions and the Task/write-scope matrix remain binding.

> **Reconciliation note (2026-11-25):** This document is the earlier broad RW-4 design proposal and is historical wherever it conflicts with later accepted decisions. D1/D2, D3-A/B/C, D4.1/D4.1a/D4.2/D4.3, D5.1–D5.4, and D6.1–D6.6 are accepted and reconciled in the [RW4-2 Stage A specification](rw-4-2-decision-and-specification-draft.md), [bounded decision record](rw-4-0-bounded-decision-record.md), and [Readiness and Delivery Plan](rw-4-readiness-and-delivery-plan.md). In particular, automatic Thread creation is disabled in v1; valid non-match or ambiguous/insufficient evidence is terminal deferred; corrupt or inconsistent provenance is an integrity failure, not a deferred business result; duplicate identity is exact raw hash within a Team with first-committed canonical association; and the accepted existing-Thread matcher shape is evidence-based but its thresholds, bounds, pin values, and query-cost proof remain open. D6 permits dormant-Thread matching only through the atomic reactivation contract, which remains unavailable until separately authorized and proven RW4-5 implementation. The broad `new_thread`, noise, and deferred-refinement target language below is superseded. This document does not authorize implementation.

## 1. Purpose

RW-4 connects an ingested canonical Signal to a Team-specific world-memory Thread through deterministic triage, then makes accepted active Hypotheses and verified evidence available to a later Task through the existing bounded Context path.

The intended path is:

Signal → Team-scoped triage_signal disposition → qualifying existing Thread or terminal deferred/duplicate outcome → later Task Context containing eligible active Hypotheses and verified EvidenceLinks. Automatic Thread creation is excluded from v1; D6 reactivation semantics are accepted, but implementation remains separately gated as RW4-5.

Triage is deterministic application behavior. It is not model reasoning, and a similarity score is not authority to create a Thread by itself. A non-match does not create a Thread. Ambiguous or failed matching remains explicit as terminal deferred; a Signal must never disappear silently.

## 2. Accepted constraints and dependencies

The following are existing constraints, not new decisions in this document:

- Historical RW-D16 proposal: triage_signal was previously described as the canonical Thread-creation path with scoped new_thread permission. This is superseded for v1 by accepted D4.3: automatic Thread creation is disabled. update_thread and operator_update refine existing Threads only.
- RW-D21: preserve the shared EvidenceLink model and existing Evaluation/distillation behavior. Do not add automatic Hypothesis-to-Evaluation linkage or new distillation behavior without a demonstrated scenario requirement.
- RW-D134: every implementation slice needs an explicit requirement-to-test proof matrix, exact-head verification, and disposable-PostgreSQL evidence where applicable.
- RW-D135: documentation closeout and decision approval do not authorize implementation or scored execution.
- RW-5 decay is an independently implementable slice: its design, implementation, and unit-level decay proofs do not wait for RW-4 triage or Experiment A. The integration boundary is narrower: the combined RW-4/RW-5 proof must exercise a deterministically matched Signal reactivating the selected dormant Thread and then verify decay behavior and retrieval against the resulting post-decay state. D6.1–D6.6 define and accept the reactivation transition; RW4-5 still requires a separately reviewed proof subset and explicit implementation authorization before reactivation coding. Experiment A informs RW4-4 representation only and does not block RW-5 planning or implementation.
- The RW-3 update_thread Task creator remains the host-authorized Operator operation. Triage must not create or enqueue update_thread Tasks. Any future application-authored follow-up creator requires a separate actor, authorization, attribution, request-Event, idempotency, and replay design and explicit approval.
- The existing TaskRuntime remains the sole Task lifecycle authority. The current TaskDispatcher remains limited to configured-source ingest_source work unless a separate dispatcher change is designed and authorized.

RW3.4 implementation is merged, but its formal acceptance remains deferred with all seven PARTIAL qualifications preserved. The Operator approved a sequencing exception on 2026-11-24 so individually gated RW-4/RW-5 slices may advance without formal RW3.4 acceptance. This does not authorize any implementation slice; each still requires its own accepted prerequisites, reviewed proof subset, and explicit authorization.

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

### 4.2 SignalDisposition contract — accepted D3 and D5 semantics; RW4-1 physical persistence remains gated

The current canonical SignalDisposition representation is still conceptual and not implemented. D3-A/B/C were accepted on 2026-11-25 and supersede the earlier deferred-refinement proposal:

- One immutable v1 disposition per Team/Signal pair; an existing disposition excludes a second first-release decision.
- A valid deferred business outcome is terminal and immutable. The triage Task completes successfully as done, not failed.
- Disposition, Task attribution/reason, TaskRuntime task_execution Outcome, terminal Task status, and task_completed Event commit or roll back together in one TaskRuntime-owned transaction. The Kernel persistence operation uses the active Session and does not commit independently.
- update_thread, operator_update, and background processing cannot refine or reopen a deferred disposition.
- Technical execution failures remain distinct and follow TaskRuntime retry/recovery.
- Missing, duplicate, malformed, or inconsistent canonical Task/request-Event history fails closed without repair, replacement, or disposition mutation.

D5.1–D5.4 are accepted. RW4-1 still requires a reviewed physical persistence design, cross-record integrity strategy, proof subset, and separate implementation authorization. This document does not freeze physical columns, constraints, or migration details and authorizes no persistence implementation.

### 4.3 Duplicate detection and existing-Thread matching — accepted D4 shape; evidence gates remain

D4.1/D4.1a/D4.2/D4.3 were accepted by the Operator on 2026-11-25. The accepted rules are recorded normatively in the [RW4-2 Stage A specification](rw-4-2-decision-and-specification-draft.md) §7.6 and the [bounded decision record](rw-4-0-bounded-decision-record.md) D4. This older proposal is subordinate to those accepted decisions:

- Exact raw content-hash equality within one Team's intake history is a duplicate regardless of origin; equal hashes across Teams are not duplicates. Near-duplicate and semantic duplicate detection are excluded.
- The first successfully committed Signal for a Team + exact content hash is canonical. PostgreSQL must arbitrate concurrent first arrivals and preserve the association. The current origin-scoped uniqueness does not implement this Team-wide rule; a reviewed persistence design and two-session PostgreSQL proof remain required.
- Derive existing-Thread evidence profiles at read time through Team-scoped EvidenceLink → Hypothesis → Thread. Candidate scope is same-Team/same-Domain active or dormant Threads; resolved is excluded. Only supports/challenges EvidenceLinks count; mentions alone is insufficient.
- Validate same-Team ingestion provenance and exact Signal/Snapshot/hash and EvidenceLink Snapshot/hash associations. Absent legacy provenance is excluded; partial, mismatched, or corrupt provenance fails closed.
- Use only compatible existing KnowledgeChunk projections under immutable embedding-space/chunking pins. No Thread embeddings, model calls, re-embedding, summary/alias subsystem, or recency bonus.
- Maximum pairwise chunk cosine similarity is an experimental baseline only. Its outlier sensitivity and evidence-profile-size bias require independent labeled fixtures. Threshold, runner-up margin, score serialization, candidate/evidence bounds, actual v1 pin values, false-positive tolerance, query plan, and cost remain open.
- Ties or ambiguous winners, insufficient eligible evidence, absence of evidence compatible with the accepted embedding/chunking pins, or scan-bound overflow produce a terminal `deferred` business outcome with the applicable accepted D5 reason code. No UUID or incidental-order tie-break is allowed.
- A queued Task whose immutable matcher pins are no longer supported is not a deferred business outcome. RW4-3 must terminally supersede it through TaskRuntime's existing non-success path (`failed`, `terminal_failure`, reason `matching_pins_superseded`) and prove no retry or replacement before triage execution is enabled.
- Missing, partial, mismatched, or corrupt canonical provenance is an integrity failure, not a deferred disposition; fail closed through TaskRuntime technical-failure/recovery handling. This rule concerns provenance integrity and does not classify projection availability/staleness when immutable pins remain supported. For that distinct post-admission projection-loss condition, do not commit a disposition or substitute/rebuild/recompute from another projection; its TaskRuntime outcome/recovery mapping remains unresolved and must be accepted before RW4-3 implementation.
- A dormant Thread may be considered as a candidate. Under accepted D6, it may be matched only when the same TaskRuntime-owned transaction reactivates it and records one immutable Task-attributed `thread_reactivated` Event. Until RW4-5 is separately authorized and proven, a dormant would-be match resolves to terminal deferred with `dormant_thread_requires_reactivation`.
- Automatic Thread creation is disabled in v1. No qualifying existing match, ambiguous/insufficient eligible candidate evidence, or a dormant would-be winner before RW4-5 availability resolves to terminal deferred with the applicable accepted reason. Missing, partial, mismatched, or corrupt provenance is a technical/integrity failure as stated above, not deferred. Post-admission projection loss while pins remain supported has no accepted outcome mapping yet and must not be assigned one implicitly. No URL-derived or model-generated title fallback. Any future automatic Thread creation requires a separate source-backed design and Operator decision.

The D4 policy shape is accepted; the listed persistence and matcher evidence gates are not. D5 and D6 decisions are accepted, but that does not authorize RW4-1 persistence, RW4-3 implementation, or RW4-5 reactivation.

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
| RW4-2 Stage A — Task boundary design/decision | Freeze D1/D2, the immutable request/identity/replay contract, Task envelope, current TeamPolicy selection, lock-path contract, proof subset, and explicit database-enforcement choices. No production code or migration. | Accepted D1/D2 design decisions, exact golden identity vector, lock-order review, and explicit disposition of pair-level Task/Event uniqueness residuals. |
| RW4-1 — disposition persistence | Prepare the physical SignalDisposition schema and migration only after the representation and transition contract are accepted. Preserve existing Signals, Threads, and EvidenceLinks. | Disposable-PostgreSQL migration/constraint/rollback proofs, uniqueness and Team-isolation proofs, and populated-state compatibility evidence where applicable. |
| RW-5 helper/Team revision/writer retrofit | Implement the canonical lock helper and Team revision/writer compatibility only after separate authorization. This stage precedes the RW4-2 creator. | Real PostgreSQL lock-order/concurrency proof and supported-writer entrypoint coverage. |
| RW4-2 Stage B — creator implementation | Implement the approved immutable triage Task creator/replay path and TaskRuntime-owned boundary only after RW4-1 and the RW-5 helper/retrofit have landed. Keep TaskDispatcher unchanged unless expansion is separately designed and authorized. | Creator authorization, Team derivation, exact Task/write scope, atomic Task/Event, idempotency/replay/conflict, lifecycle/recovery, and no direct Task-state mutation proofs. |
| RW4-3 — deterministic triage commit | Implement only the evidence-closed D4 duplicate/existing-Thread rules and terminal deferred outcome; no automatic Thread creation, noise, near-duplicates, or dormant reactivation. Requires C1, D5, stale-pin supersession proof, canonical lock helper, and separate authorization. | Team/hash canonical-winner concurrency; threshold/tie/overflow and provenance fixtures; receipt recovery; duplicate/replay/concurrency; atomic rollback; Task attribution; no Thread creation/reactivation or unapproved follow-up Task. |
| RW4-4 — world-memory Context read path | Extend the selected existing Task Context path with bounded, same-Team active Hypotheses and verified EvidenceLinks. Preserve immutable Snapshot/manifest replay. | Freeze the model-facing evidence representation using the Experiment A result, or record an explicit Operator-approved rationale and residual uncertainty if no usable result is available. Then prove positive/negative scope, exact source/quote validation, deterministic ordering, bounds/overflow, stale-reference rejection, and replay integrity. |
| RW4-KU — claim-level attribution | Implement the D99/D133 minimum only after its dependency and exact scope are accepted. Keep it a separately gated sub-slice. | Exact KnowledgeItem/version/LearningChange/Team/Context binding, immutable references, typed assessment against the later Task Outcome, replay, and invalid/stale/forbidden-scope rejection. |
| RW4-5 — dormant reactivation and integrated proof | Implement the accepted D6 transition only after its separate authorization; integrate the matched disposition, TaskRuntime terminal evidence, canonical RW-5 locks, and decay/triage races. | Exact Event identity/DB uniqueness, same-transaction rollback/replay/recovery, Team revision and stale-receipt fencing, both disposable-PostgreSQL interleavings, exact-head hosted/local verification, independent review, and explicit Operator acceptance. |

RW4-1 through RW4-4 may be split further if the frozen contracts require independent review. Do not combine unrelated schema, runtime, matching, and Context changes into one large implementation PR merely to reduce PR count.

## 6. Required proof obligations

The exact test nodes must be named before RW-4 implementation authorization under RW-D134. The following behaviors are the minimum proposed proof set; refine them only when the decisions in §4 are frozen.

### Triage and persistence

- One disposition per Signal/Team pair; the same Signal may be triaged independently by multiple eligible Teams.
- Cross-Team and cross-domain Signal, Thread, duplicate, and disposition references are rejected.
- Every disposition is Task-attributed and has a durable reason; no Signal is silently dropped.
- The accepted v1 decision surface is duplicate, matched to an eligible existing Thread, or terminal deferred. D5.1–D5.4 already freeze the disposition vocabulary, reference matrix, deferred reasons, and TaskRuntime-owned terminal Event semantics; RW4-1 physical persistence remains separately gated.
- Exact raw content-hash duplicate detection is Team-scoped and origin-independent; the first committed Team/hash association is canonical. Prove database arbitration and stability with two PostgreSQL sessions.
- No automatic Thread creation, automatic noise classification, or near-duplicate classification occurs in v1.
- Ties or ambiguous winners, insufficient eligible candidate evidence, absence of compatible candidate evidence, and candidate/evidence overflow defer; no semantic tie is broken by UUID or incidental order. Missing, partial, mismatched, or corrupt provenance is an integrity failure, not deferred. Post-admission projection loss while pins remain supported is unresolved: no disposition or projection substitution/rebuild/recomputation is permitted until its TaskRuntime outcome/recovery mapping is accepted. A queued Task whose immutable matching pins are no longer supported follows TaskRuntime's terminal supersession path (`failed`, `terminal_failure`, `matching_pins_superseded`), not deferred.
- D6.1–D6.6 are accepted. Until the separately authorized and proven RW4-5 implementation is available, a dormant would-be winner with no active winner resolves to terminal deferred with `dormant_thread_requires_reactivation`; RW4-3 may evaluate dormant candidates but must not commit a dormant `matched` disposition or reactivate a dormant Thread.
- A disposition replay returns/reuses the canonical result without duplicate Thread, disposition, or Event writes. A changed request under the same idempotency identity conflicts without mutation.
- Thread creation/reactivation, disposition persistence, and the required Event are atomic. A failed commit leaves no partial state.
- Deferred is terminal and immutable in v1; no ordinary Task or background process may refine it. TaskRuntime atomically commits the disposition and terminal Task evidence.
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

## 8. Remaining design and engineering closure gates

D1–D6 decisions are accepted and reconciled in the [RW4-0 bounded decision record](rw-4-0-bounded-decision-record.md) and the authoritative Stage A specification. That decision record remains design-only and does not authorize implementation.

The remaining cross-cutting design work includes freezing the later Task type(s), Context assembler, eligible world-memory records, and justified retrieval bounds; confirming the RW4-KU relationship to the foundation exit gate; and approving the remaining Experiment A protocol decisions before EA-0 closes. The accepted Experiment A dependency mapping in §4.6 is not reopened by those protocol decisions. D4 matching evidence closure and the individual RW4-1/RW4-3/RW4-5 engineering gates remain as described in the readiness plan; they are not pending Operator decisions to redefine D1–D6.

No implementation stage should begin by treating an unresolved design or proof item as an implicit default.
