# R8-ready Path A — Scope and Capability Matrix

**Status:** planning record opened by Operator decision on 2026-11-27. Path A is selected; candidate scenarios and capability classifications are not yet frozen.
**Current state:** Pre-R8-ready. This document does not authorize implementation, internal testing, database operations, or a state transition.
**Status authority:** [`PLAN.md`](../../PLAN.md).
**State/behavior authority:** [R8 development states](r8-development-states.md) and [R8 delivery plan](r8-delivery-plan.md).

## 1. Selected planning decision

Path A is selected for the initial R8-ready effort:

- Defer SignalDisposition and the complete `triage_signal` workflow from R8-ready.
- Prefer existing, already-authorized governed operations for the candidate internal scenarios.
- Do not introduce a caller/Event-only substitute, an ad-hoc disposition write, a second Task lifecycle authority, or a partial triage rollout.
- Preserve all accepted integrity, provenance, authorization, Team/domain isolation, transaction, replay, and concurrency guarantees for every capability actually exercised.

This is a scope direction, not a verified feasibility claim. The actual scenarios have not yet been frozen, and no existing path is presumed suitable until its exact entrypoint, contract, implementation, and proofs are inspected.

If a candidate scenario requires SignalDisposition or any other gated capability, stop that scenario and return with the concrete dependency and evidence. Do not silently change Path A or weaken a gate. Reopening the scope requires an explicit Operator decision.

## 2. Ordered planning work

1. **Select candidate scenarios.** Describe observable Watch behavior, input, expected durable effects, expected safe failure/abstention, and the question the test should answer.
2. **Trace each scenario end to end.** Identify the exact public/application entrypoint, Task creator, Kernel/Control boundary, TaskRuntime finalizer, persistence path, and any retrieval/Context consumer.
3. **Map required capabilities to authority.** Link each operation to its accepted contract/decision record, implementation source, migration/schema dependency, and owner.
4. **Audit the relied-upon invariants.** Check Team/domain isolation, source provenance, authorization, write scope, atomicity, rollback, replay, and concurrency. Use real PostgreSQL evidence for database guarantees.
5. **Classify every capability.** Use only `Required`, `Not required`, `Unknown`, or `Blocked`. `Unknown` is not a pass and cannot be treated as deferred.
6. **Freeze the bounded scope and deferment register.** Record limitations, proof subset, exact source baseline, fixtures, and the trigger/owner for reconsidering each deferment.
7. **Submit the implementation authorization request.** Only after the scope is reviewed; name exact files/paths, behavior, tests, database changes, rollback, and verification.
8. **Complete R8-ready entry review.** Require exact-SHA evidence, disposable PostgreSQL where applicable, repeatable fixtures, logs/baseline, cleanup, limitations, and explicit authorization in `PLAN.md`.

### 2.1 Initial source-audit result (2026-11-27)

**Audited source baseline:** `main` at `d671d066940d0dc06b1198c5ed474dc66653cccb`, the base of the Path A documentation PR. Source-file blob SHAs are recorded in the candidate rows below. This was a GitHub source inspection, not a local checkout, test execution, migration run, or live database inspection.

**Blocking architecture finding — accepted D1 is not yet implemented in source.**

- The accepted D1 contract makes the application Control Room the sole logical authority for all supported Task creation. It explicitly says the Control Room is a logical boundary, not a claim that a dedicated implementation already exists.
- The accepted writer audit inventories nine production Task producers and requires all of them to delegate to named Control Room-owned operations, without direct-persistence fallback. The inventory includes `update_thread`, `operator_update`, `ingest_source` Plan materialization, TaskRuntime follow-ons, and the KnowledgeRevalidation producer.
- The current source still contains direct Task persistence in all nine inventoried producer paths. A current-source check of the actual insert sites confirms the audit inventory:
  
  | # | Producer / operation | Current direct insert site | Source blob SHA |
  |---:|---|---|---|
  | 1 | OperatorApplicationAdapter `create_update_thread_task` | `core/operator_application.py:294` (`pg_insert(Task)`) | `0cdd5275fc5d33a0633b721a0e91840f0c0988cf` |
  | 2 | LearningChange decision request | `core/operator_application.py:618` (`pg_insert(Task)`) | `0cdd5275fc5d33a0633b721a0e91840f0c0988cf` |
  | 3 | Operator update request | `core/operator_application.py:809` (`Task(...)`) | `0cdd5275fc5d33a0633b721a0e91840f0c0988cf` |
  | 4 | Plan materialization of `ingest_source` | `core/plans.py:239` (`Task(...)`) | `ef63fb9f8f540892a2e90643b7d9812e0fe37b2c` |
  | 5 | TaskRuntime Knowledge Quality follow-on | `core/task_runtime.py:3283` (`Task(...)`) | `c19c1d6e87137441306cdb454f7ca304297d75d3` |
  | 6 | TaskRuntime Knowledge Revalidation follow-on | `core/task_runtime.py:3355` (`Task(...)`) | `c19c1d6e87137441306cdb454f7ca304297d75d3` |
  | 7 | TaskRuntime Knowledge Lifecycle follow-on | `core/task_runtime.py:3423` (`Task(...)`) | `c19c1d6e87137441306cdb454f7ca304297d75d3` |
  | 8 | TaskRuntime follow-on Evaluation | `core/task_runtime.py:3732` (`Task(...)`) | `c19c1d6e87137441306cdb454f7ca304297d75d3` |
  | 9 | KnowledgeRevalidationAssessmentService producer | `core/knowledge_revalidation.py:1095` (`Task(...)`) | `38ee4e77ba8dff77f0a1cf174f4321df4cbbb7f2` |

- Current source search did not find a Control Room implementation or the named `create_operator_update_task` / `create_update_thread_task` Control Room operations. The exact nine-site inventory agrees with the accepted [RW4-2 writer compatibility audit](rw4-2-migration-and-writer-compatibility-audit.md) §4.
- The accepted audit requires all nine producers to conform; implementing a new facade for only one selected scenario would not satisfy D1. The Control Room conformance work is not authorized by this matrix or PR #206.

**Consequence:** candidate scenarios that create Tasks through these existing adapters are currently **Blocked** pending separately authorized D1 conformance (or an explicit Operator decision that changes the accepted boundary). A pre-seeded Task fixture would not prove the real user-facing Task-creation path and must not be presented as end-to-end scenario evidence.

**Other source findings:**

- `TaskRuntime` remains the implemented lifecycle authority for admission, attempts, terminalization, replay, and interrupted recovery. Its terminal finalization commits the Outcome, terminal Task status, completion timestamp, and terminal Events in one transaction. This does not cure the separate Task-creation-authority gap.
- The configured-source `ingest_source` dispatcher is narrow. `IngestionService` validates the attributed Task/Team/policy and content hash, persists Signal/Snapshot/Event, and supports same-Task replay. Its existing duplicate lookup is by `origin_url + content_hash`; it is not the accepted Team-wide cross-origin canonical Signal arbitration designed for RW4-3.
- The `update_thread` worker is deliberately restricted to the deterministic test provider. Live-provider use remains separately unauthorized. Its Context tests explicitly establish that the worker does not invoke Team Experience retrieval; it therefore cannot by itself prove retained Team Experience retrieval/use.
- The existing `operator_update` path can create a low-confidence Hypothesis and verified EvidenceLinks from currently supported Signal/Outcome sources, with Team/action grants and TaskRuntime finalization. Its Task creator still has the D1 conformance gap.
- `activate_team` is documented as the intended starter-Thread creator but is not implemented in the current task-status summary. Candidate scenarios therefore assume an already-existing active Thread; they must not assume a supported Thread-creation journey.

**Source references and governing evidence:**

- D1 nine-writer inventory and delegation contract: [RW4-2 writer compatibility audit](rw4-2-migration-and-writer-compatibility-audit.md), especially §§4 and 4.2.
- Task/operation implementation status: [Task specifications](../tasks.md).
- Current-source and persistence limitations: [RW4-1A audit](rw4-1a-current-source-and-persistence-audit.md).
- R8-ready state and authorization: [`PLAN.md`](../../PLAN.md).

## 3. Candidate scenario register (not accepted/frozen)

These are source-backed candidates for Operator selection, not approved test scope. The D1 blocker applies to each Task-creating path.

| ID | Candidate behavior | Input and expected durable effect | Safe failure / abstention | Candidate entrypoint and source | Status |
|---|---|---|---|---|---|
| C-01 | Configured-source intake followed by an Operator recording an evidence-backed Hypothesis on an existing active Thread | A configured source is ingested through an ordinary `ingest_source` Task; an authorized Operator then proposes a low-confidence Hypothesis and exact-quote EvidenceLink(s) using a same-Team Signal or Outcome Snapshot. Durable effects are the existing Signal/Snapshot/intake Event and the ordinary `operator_update` Task/business Events/Hypothesis/EvidenceLinks. | Unconfigured source, invalid Task/Team/policy, invalid grant, cross-Team source, invalid quote/offset, stale target, conflicting request, or database failure must fail/reject without partial business writes; exact replay must not duplicate business writes. | `PlanService` → `TaskDispatcher` → `IngestionService`; then `OperatorApplicationAdapter.operator_update` → `WorldMemoryCommitService.commit` → `TaskRuntime`. See source SHAs in §4. | **Blocked** — both Task-creation paths must conform to D1; Thread must already exist. |
| C-02 | Model proposes bounded updates to an existing active Thread from its verified Context | An authorized Operator requests `update_thread`; the worker assembles bounded Context and a deterministic test provider returns typed proposals. Durable effects are the existing request/attempt/receipt/proposal/commit/terminal records and any accepted Hypothesis/EvidenceLink/ConfidenceChange updates. | Invalid principal/grant/target, malformed provider output, stale/invalid Context, timeout/cost failure, invalid evidence, or commit conflict must fail closed; no provider-supplied authority and no partial proposal writes. | `OperatorApplicationAdapter.create_update_thread_task` → `UpdateThreadWorker.run` → `WorldMemoryCommitService.commit_model` → `TaskRuntime`. See source SHAs in §4. | **Blocked** — D1 conformance is missing; live provider is unauthorized; seven RW3.4 qualifications remain PARTIAL. Deterministic-fake-only testing is a possible narrower candidate, subject to Operator selection. |
| C-03 | Configured-source Signal intake only (supporting setup, not a complete R8 reasoning scenario) | An already-created configured-source Task is dispatched; the worker stores an immutable Signal Snapshot and Task-attributed intake Event, or records no-change/replay. | Invalid/unconfigured source, hash mismatch, Task/Team/policy mismatch, snapshot integrity failure, or DB failure must not publish partial Signal state. | `PlanService` → `TaskDispatcher.dispatch` → `IngestionService.ingest`. See source SHAs in §4. | **Blocked** as an end-to-end candidate by D1 Task creation; **Not sufficient alone** for Signal interpretation, Thread/Hypothesis reasoning, or retained-experience claims. |

No candidate currently qualifies as a frozen R8-ready scenario. Do not convert a candidate into an accepted scenario without Operator selection and closure of its capability blockers.

## 4. Provisional capability-to-candidate matrix

Classifications below are provisional source-audit results, not an accepted scope. The SHA column records the exact blob SHA for each source file at the audited `d671d066...` baseline. Test names are references to existing test code; their presence is not a claim that tests were rerun during this audit.

| Candidate | Capability / operation | Classification | Exact entrypoint, source SHA, and existing proof references | Governing contract / required invariants | Limitation / next action |
|---|---|---|---|---|---|
| C-01 | Task creation authority / Control Room | **Blocked** | `core/operator_application.py` `0cdd5275fc5d33a0633b721a0e91840f0c0988cf`; `core/plans.py` `ef63fb9f8f540892a2e90643b7d9812e0fe37b2c`. Current operator adapter and PlanService paths persist Tasks directly. | Accepted D1: all nine producers delegate to named Control Room operations, session-bound, with caller-owned transaction and no direct-persistence fallback. | Requires separately authorized, reviewed D1 implementation and proof across all nine producers—not a scenario-specific shim. |
| C-01 | Task lifecycle, terminal atomicity, replay/recovery | **Required** | `core/task_runtime.py` `c19c1d6e87137441306cdb454f7ca304297d75d3`; `core/operator_application.py` `0cdd5275fc5d33a0633b721a0e91840f0c0988cf`. Existing proofs include `tests/test_world_memory.py::test_committed_operator_update_is_recovered_without_replaying_writes` and `tests/test_operator_application.py::test_concurrent_identical_requests_create_one_task_and_request_event`. | One Task lifecycle authority; attempt fencing; atomic terminal Outcome/Task/Event; exact replay and interrupted recovery. | Preserve existing TaskRuntime path when D1 is implemented; rerun focused and integrated PostgreSQL tests on exact head. |
| C-01 | Signal/source provenance and Team/domain isolation | **Required** | `core/ingestion.py` `aa7178fc95ad6df42ec100f992ff26abc9b3ed44`; `core/world_memory.py` `527b190cfbf36cf73e65ecc6b5cdad62025df085`. Existing proofs include `tests/test_ingestion.py::test_successful_ingestion_commits_signal_event_and_snapshot`, `test_same_task_retry_reuses_existing_outcome`, and `tests/test_world_memory.py::test_cross_team_hypothesis_signal_and_snapshot_references_fail_closed`. | Task attribution, source allowlist, immutable Snapshot/hash, same-Team source validation, exact quote/offset verification, no cross-Team evidence. | Audit actual candidate fixture and ensure it uses a same-Team source; do not claim Team-wide cross-origin canonical Signal identity (RW4-3 remains gated). |
| C-01 | Thread/Hypothesis/EvidenceLink operations | **Required** | `core/world_memory.py` `527b190cfbf36cf73e65ecc6b5cdad62025df085`; `core/operator_application.py` `0cdd5275fc5d33a0633b721a0e91840f0c0988cf`. Existing proofs include `test_operator_update_creates_low_hypothesis_and_verified_evidence`, `test_concurrent_operator_updates_serialize_competing_transitions`, `test_database_failure_rolls_back_the_entire_valid_proposal_set`, and `test_later_confidence_change_uses_one_valid_evidence_cause` in `tests/test_world_memory.py`. | Typed proposals; same-Team/Thread ownership; exact quote/hash/offset; confidence cause; canonical locks; atomic business commit; replay. | Confirm exact proof subset and residual qualifications; no new writer or alternate commit path. |
| C-01 | Context retrieval / retained experience | **Not required** | No Context assembler is called by the direct Operator proposal path. | Do not claim retrieval or retained-experience use when the scenario only supplies explicit source evidence. | Keep retrieval claims out of C-01; any retrieval scenario needs its own accepted consumer contract and gate. |
| C-01 | SignalDisposition / `triage_signal` | **Not required** | No disposition write is part of the candidate. `core/ingestion.py` `aa7178fc95ad6df42ec100f992ff26abc9b3ed44` only implements ingestion. | Path A explicitly defers disposition and complete triage. | No caller/Event substitute, ad-hoc disposition, or partial triage. |
| C-01 | PostgreSQL roles, migrations, disposable DB isolation | **Unknown** | Migration source head is `0020_rw4_task_identity` (`migrations/versions/0020_rw4_task_identity.py`, blob `855ac3b06b8b523aab507737cd2fc9cc2fe5d954`). No disposable DB or live role inspection was run in this audit. | Runtime must not be superuser/owner; migration authority separated; relevant constraints, transactions, locks, and concurrency must be proven on PostgreSQL. | Verify actual Alembic current/head on disposable PostgreSQL and prove the exact runtime/migrator role behavior before freeze. |
| C-02 | Task creation authority / Control Room | **Blocked** | `core/operator_application.py` `0cdd5275fc5d33a0633b721a0e91840f0c0988cf`; `core/update_thread.py` `9958bdf6dbb68cd1c378ab440545326c487b1706`. | Same accepted D1 nine-producer conformance gate as C-01. | No separate adapter-owned Task writer. |
| C-02 | Task lifecycle and model-commit replay | **Required** | `core/task_runtime.py` `c19c1d6e87137441306cdb454f7ca304297d75d3`; `core/world_memory.py` `527b190cfbf36cf73e65ecc6b5cdad62025df085`. Existing proofs include `tests/test_update_thread.py::test_transient_model_commit_failure_rolls_back_and_recovers_same_proposals`, `test_marker_recovery_reconstructs_terminal_result_without_reapplying`, and `test_model_workers_serialize_concurrent_commits_for_same_thread`. | Single TaskRuntime lifecycle; durable generation receipt; attempt/Context binding; rollback/recovery; no duplicate business commit. | RW3.4 remains 28 PASS / 7 PARTIAL / 0 OPEN and formal acceptance is deferred; preserve the seven PARTIAL qualifications in any scope. |
| C-02 | Context assembly and evidence provenance | **Required** | `core/update_thread_context.py` `30075dba186b3cab2a412713b30641249b389438`; `core/update_thread_worker.py` `e24b58959c9e93155a05d19e45aafcc6ffd539b0`. Existing proofs include `test_context_is_deterministic_bounded_and_replayable`, `test_context_uses_task_pinned_policy_after_policy_advancement`, and `test_context_rejects_evidence_signal_from_another_team_domain`. | Task-pinned policy, bounded Context, immutable Snapshot/manifest, source quote verification, replay and Team/domain isolation. | Worker explicitly does not invoke Team Experience retrieval (`test_update_thread_worker_never_invokes_team_experience_retrieval`); it cannot satisfy a retained-experience retrieval claim. |
| C-02 | Provider authorization | **Blocked** for live-provider scenario | `core/update_thread_worker.py` `e24b58959c9e93155a05d19e45aafcc6ffd539b0`; `tests/test_update_thread.py::test_update_thread_worker_rejects_live_provider_until_separately_authorized`. | Only the deterministic test provider is accepted by the current worker. | A deterministic-fake-only candidate may be considered; live-provider execution remains separately gated. |
| C-02 | SignalDisposition / `triage_signal` | **Not required** | No disposition write is part of the existing update_thread path. | Path A defers disposition and triage. | No partial triage. |
| C-03 | Task creation authority / Control Room | **Blocked** | `core/plans.py` `ef63fb9f8f540892a2e90643b7d9812e0fe37b2c`; `core/dispatcher.py` `2c29d869982ceee37fb6ed36caf3b58b72f36f1a`. | Accepted D1: PlanService delegates Task persistence to named Control Room operation. | Same nine-producer D1 gate; no PlanService direct-persistence fallback. |
| C-03 | Signal ingestion, Snapshot, Event, same-Task replay | **Required** | `core/ingestion.py` `aa7178fc95ad6df42ec100f992ff26abc9b3ed44`; `core/dispatcher.py` `2c29d869982ceee37fb6ed36caf3b58b72f36f1a`. Existing proofs include `tests/test_ingestion.py::test_database_failure_rolls_back_signal_and_success_event`, `test_concurrent_identical_ingestion_converges_on_one_signal`, and `test_same_task_conflict_is_rejected_without_overwriting_outcome`. | Configured source, content hash, Task/Team/policy provenance, immutable Snapshot, transactional Event, replay and concurrency. | Existing duplicate key is origin URL + hash, not accepted Team/hash cross-origin canonical arbitration. C-03 alone is not a reasoning scenario. |
| C-03 | Thread/Hypothesis/Context retrieval | **Not required** | The ingestion dispatcher path does not create Thread/Hypothesis or assemble reasoning Context. | Do not infer triage or interpretation from an ingestion Event or allow-list entry. | Must be followed by a separately authorized governed operation if selected. |
| C-03 | SignalDisposition / `triage_signal` | **Not required** | No disposition write is part of ingestion. | Path A defers disposition and triage. | No caller/Event-only substitute. |
| C-03 | PostgreSQL roles and disposable DB | **Unknown** | No disposable DB or live role inspection was run in this audit. | Prove actual role boundary, migration head, rollback, and concurrency behavior. | Required before a frozen scenario relies on these DB guarantees. |

## 5. Path A deferment register

| Deferred capability | Why it is deferred | Reopen trigger | Preserved gate / owner |
|---|---|---|---|
| SignalDisposition persistence and `triage_signal` matched/duplicate/deferred outcomes | Not assumed necessary for the initial bounded R8-ready scenarios; Path A uses existing governed operations | A frozen scenario demonstrably requires this capability and no existing authorized path can satisfy it | RW4-1B through RW4-1F and RW4-2 Stage B/RW-5/RW4-3 prerequisites remain binding; issue #199 remains open |
| Dormant Thread reactivation and broader RW-5 behavior | Not required unless a selected scenario exercises it | Scenario needs the capability | Existing RW-5/RW4-5 contracts and separate gates |
| Claim-level knowledge-use attribution | Not asserted by retrieval/Context assembly alone | Scenario makes a claim-level use or outcome-attribution assertion | RW-D99/RW-D133 mapped slice, authorization, and proofs |
| Formal/scored newsroom value-harness execution | Separate from exploratory internal testing | Full Design foundation exit and frozen corpus/scoring package | R8 delivery plan and RW-0 acceptance gates |
| Live model-provider execution for `update_thread` | Current worker explicitly accepts only the deterministic test provider | Separate provider authorization and any required operational/security review | Existing provider gate and RW3 evidence ledger |

## 6. Non-negotiable stop conditions

Pause the affected scenario if:

- No existing governed entrypoint can perform the required operation.
- Caller authority, Task ownership, provenance, Team/domain isolation, or allowed-write scope is unclear.
- D1 Task-creation conformance is absent for a Task-creating path; do not substitute a pre-seeded Task fixture and call it end-to-end.
- A required invariant depends only on an unproven design statement or an in-memory/SQLite substitute for PostgreSQL behavior.
- Atomicity, replay, or concurrency behavior is not established for the exercised path.
- A requested result would require partial SignalDisposition/triage enablement or a new unaccepted write path.
- The scenario depends on RW4-4 retrieval or RW-D99/RW-D133 attribution without its own accepted consumer contract, gate, authorization, and proofs.
- A scenario claims retained-experience retrieval while using the current `update_thread` Context path, which explicitly does not invoke Team Experience retrieval.
- A scenario requires a live `update_thread` provider while provider authorization remains closed.

A stop is a scope/design finding, not permission to improvise a workaround.

## 7. Freeze record (complete only after review)

- Accepted scenario IDs: **None; C-01 to C-03 are candidates only**
- Exact `main` baseline SHA: `d671d066940d0dc06b1198c5ed474dc66653cccb` (source-audit baseline)
- Relevant Alembic source head: `0020_rw4_task_identity`; actual disposable DB current/head not verified in this audit
- Existing governed entrypoints: identified candidates in §3; D1 conformance is not implemented
- Required capability set: provisional only; see §4
- Deferred capability set and reopen triggers: see §5
- Required PostgreSQL proof set: not frozen; exact role/migration/concurrency proof remains outstanding
- Fixtures, baseline, and expected outputs: not frozen
- Known limitations: D1 nine-producer Control Room conformance gap; live update_thread provider unauthorized; RW3.4 seven PARTIAL qualifications; Team Experience not retrieved by update_thread; no triage/disposition; no disposable DB/role inspection in this audit
- Implementation authorization: Not granted
- R8-ready internal-testing authorization: Not granted
