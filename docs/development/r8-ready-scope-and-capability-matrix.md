# R8-ready Path A — Scope and Capability Matrix

**Status:** Path A remains selected. The initial technical internal-test scope (CG-01 + C-01) and its current-source capability/proof reconciliation are recorded in [the internal-test scope and proof freeze](r8-ready-internal-test-scope-and-proof-freeze.md). This is not R8-ready entry or scored-execution authorization.
**Current state:** Pre-R8-ready. The bounded test-only Control Group baseline and its technical verification are authorized as recorded in `PLAN.md`; this does not authorize R8-ready entry, scored execution, production use, or a state transition.
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

**Historical blocking architecture finding at the audited `d671d066...` baseline — accepted D1 was not implemented in source.**

- The accepted D1 contract makes the application Control Room the sole logical authority for all supported Task creation. It explicitly says the Control Room is a logical boundary, not a claim that a dedicated implementation already exists.
- The accepted writer audit now inventories ten production Task producers and requires all of them to delegate to named Control Room-owned operations, without direct-persistence fallback. The inventory includes `update_thread`, `operator_update`, `ingest_source` Plan materialization, TaskRuntime follow-ons, and the KnowledgeRevalidation producer.
- At the audited `d671d066...` baseline, source contained direct Task persistence in all nine originally inventoried producer paths. A current-source check of the actual insert sites confirms the audit inventory:
  
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
  | 10 | KnowledgeLifecycleAssessmentService producer | `core/knowledge_lifecycle.py:1731` (`Task(...)`) | `58dc94bdbcd89b57b55f1aa5bdb59c02571c1032` |

- A follow-up complete producer-path review found a tenth supported writer: `KnowledgeLifecycleAssessmentService.create_task`. It was not included in the original nine-site baseline table and is now included in the D1 conformance inventory. The implementation delegates its Task/Event persistence to the existing `create_assess_knowledge_lifecycle_task` operation while preserving the service's own workflow and transaction. The historical source blob SHA and line above refer to the baseline before D1 implementation.
- At the audited baseline, source search did not find a Control Room implementation or the named `create_operator_update_task` / `create_update_thread_task` Control Room operations. The original nine-site inventory was later expanded with a tenth supported producer in the accepted [RW4-2 writer compatibility audit](rw4-2-migration-and-writer-compatibility-audit.md) §4.
- The accepted audit required all ten producers to conform. That requirement is now implemented by PR [#207](https://github.com/abtn/Watch-Architecture-Rev2/pull/207), merged to `main` at `d03297c2b4e3522b0dc59ce001955cda130fd14f`; the correction in PR #208 is included. Hosted CI run [#2326](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/45955503881) passed on exact PR head `8532f573170b23b95bd98ccd56b3d8ea8d36cea8`, including disposable PostgreSQL setup/migrations, Ruff, Mypy, whitespace, and the full test suite.

**Historical consequence:** Task-creating candidates were blocked at the audited baseline. D1 no longer blocks them at the current source baseline. This does not freeze C-01/C-02/C-03, prove their complete end-to-end feasibility, or satisfy R8-ready entry.

### 2.2 Current-source update after D1 merge (2026-11-27)

**Current source baseline:** `main` at merge commit `d03297c2b4e3522b0dc59ce001955cda130fd14f` (D1 PR #207); tested PR head `8532f573170b23b95bd98ccd56b3d8ea8d36cea8`.

- All ten supported Task producers now delegate to eight named operations in `core/control_room.py`.
- The Control Room uses the caller's existing SQLAlchemy Session and does not create sessions or own commit/rollback. Existing caller authorization, policy pins, idempotency/replay, and business workflow remain with their current owners.
- TaskRuntime remains the sole Task lifecycle authority.
- The D1 correction in PR #208 validates paired request-Event arguments before mutating the caller Session; the regression test checks both invalid combinations leave the Session untouched.
- Hosted CI run #2326 passed on the exact PR head: disposable PostgreSQL initialization and role provisioning, migrations/current-head verification, Ruff, Mypy, patch whitespace, and the full test suite.
- This is a bounded repository source/CI proof. It does not prove external or out-of-repository writers, production deployment credentials, or R8-ready scenario feasibility.

**D1 status:** satisfied for the ten inventoried supported repository producers. The original source-audit table and its historical blob SHAs remain historical evidence; they must not be read as current direct-write locations.

**Other source findings:**

- `TaskRuntime` remains the implemented lifecycle authority for admission, attempts, terminalization, replay, and interrupted recovery. Its terminal finalization commits the Outcome, terminal Task status, completion timestamp, and terminal Events in one transaction. Task creation is separately centralized by the D1 Control Room boundary.
- The configured-source `ingest_source` dispatcher is narrow. `IngestionService` validates the attributed Task/Team/policy and content hash, persists Signal/Snapshot/Event, and supports same-Task replay. Its existing duplicate lookup is by `origin_url + content_hash`; it is not the accepted Team-wide cross-origin canonical Signal arbitration designed for RW4-3.
- The `update_thread` worker is deliberately restricted to the deterministic test provider. Live-provider use remains separately unauthorized. Its Context tests explicitly establish that the worker does not invoke Team Experience retrieval; it therefore cannot by itself prove retained Team Experience retrieval/use.
- The existing `operator_update` path can create a low-confidence Hypothesis and verified EvidenceLinks from currently supported Signal/Outcome sources, with Team/action grants and TaskRuntime finalization. Its Task creator now delegates to the Control Room-owned `create_operator_update_task` operation. The direct Operator proposal path does not invoke Team Experience retrieval.
- `activate_team` is documented as the intended starter-Thread creator but is not implemented in the current task-status summary. Candidate scenarios therefore assume an already-existing active Thread; they must not assume a supported Thread-creation journey.

**Source references and governing evidence:**

- D1 ten-writer inventory and delegation contract: [RW4-2 writer compatibility audit](rw4-2-migration-and-writer-compatibility-audit.md), especially §§4 and 4.2.
- Task/operation implementation status: [Task specifications](../tasks.md).
- Current-source and persistence limitations: [RW4-1A audit](rw4-1a-current-source-and-persistence-audit.md).
- R8-ready state and authorization: [`PLAN.md`](../../PLAN.md).

## 3. Candidate scenario register (not accepted/frozen)

CG-01 and C-01 are selected for the initial bounded technical internal-test scope only. C-02 and C-03 remain unselected supporting/future candidates. The selection does not freeze the broader R8-ready scope or authorize a state transition.

| ID | Candidate behavior | Input and expected durable effect | Safe failure / abstention | Candidate entrypoint and source | Status |
|---|---|---|---|---|---|
| C-01 | Configured-source intake followed by an Operator recording an evidence-backed Hypothesis on an existing active Thread | A configured source is ingested through an ordinary `ingest_source` Task; an authorized Operator then proposes a low-confidence Hypothesis and exact-quote EvidenceLink(s) using a same-Team Signal or Outcome Snapshot. Durable effects are the existing Signal/Snapshot/intake Event and the ordinary `operator_update` Task/business Events/Hypothesis/EvidenceLinks. | Unconfigured source, invalid Task/Team/policy, invalid grant, cross-Team source, invalid quote/offset, stale target, conflicting request, or database failure must fail/reject without partial business writes; exact replay must not duplicate business writes. | `PlanService` → `TaskDispatcher` → `IngestionService`; then `OperatorApplicationAdapter.operator_update` → `WorldMemoryCommitService.commit` → `TaskRuntime`. See source SHAs in §4. | **Selected; implemented and merged as a test-only integration.** Exact proof and limitation record is in the current internal-test scope freeze. Thread must already exist. |
| CG-01 | Test-only Control Group baseline for an authenticated Operator evidence update | Isolated Team, active pre-existing Thread, immutable same-Team Signal/Snapshot, and authenticated Operator request; the `operator_update` Task is created through Control Room and finalized by TaskRuntime. No retained Team Experience is present or supplied. | Invalid grant, cross-Team Thread/source/Snapshot, malformed proposal, quote/hash/offset mismatch, conflicting replay, or database failure must fail closed without partial business writes. | Existing `tests/test_world_memory.py::world_memory_context` plus `r8_control_group` fixture; `OperatorApplicationAdapter.operator_update` → Control Room `create_operator_update_task` → WorldMemoryCommitService → TaskRuntime. | **Selected and authorized for bounded technical internal testing only.** Not a frozen R8-ready scenario, not full C-01 intake, and not a control/treatment value comparison. |
| C-02 | Model proposes bounded updates to an existing active Thread from its verified Context | An authorized Operator requests `update_thread`; the worker assembles bounded Context and a deterministic test provider returns typed proposals. Durable effects are the existing request/attempt/receipt/proposal/commit/terminal records and any accepted Hypothesis/EvidenceLink/ConfidenceChange updates. | Invalid principal/grant/target, malformed provider output, stale/invalid Context, timeout/cost failure, invalid evidence, or commit conflict must fail closed; no provider-supplied authority and no partial proposal writes. | `OperatorApplicationAdapter.create_update_thread_task` → `UpdateThreadWorker.run` → `WorldMemoryCommitService.commit_model` → `TaskRuntime`. See source SHAs in §4. | **Blocked** — live provider is unauthorized and seven RW3.4 qualifications remain PARTIAL. Deterministic-fake-only testing remains a possible narrower candidate, subject to Operator selection. |
| C-03 | Configured-source Signal intake only (supporting setup, not a complete R8 reasoning scenario) | An already-created configured-source Task is dispatched; the worker stores an immutable Signal Snapshot and Task-attributed intake Event, or records no-change/replay. | Invalid/unconfigured source, hash mismatch, Task/Team/policy mismatch, snapshot integrity failure, or DB failure must not publish partial Signal state. | `PlanService` → `TaskDispatcher.dispatch` → `IngestionService.ingest`. See source SHAs in §4. | **Candidate — D1 cleared; standalone intake still does not prove Signal interpretation, Thread/Hypothesis reasoning, or retained-experience claims.** |

CG-01 and C-01 are selected as the initial technical internal-test scenarios. They are not, by this selection, accepted R8-ready entry scenarios, scored experiments, or evidence of retained-experience value. Broader R8-ready scope remains subject to its own entry gate.

## 4. Provisional capability-to-candidate matrix

Classifications below are provisional source-audit results, not an accepted scope. The SHA column records the exact blob SHA for each source file at the audited `d671d066...` baseline. Test names are references to existing test code; their presence is not a claim that tests were rerun during this audit.

| Candidate | Capability / operation | Classification | Exact entrypoint, source SHA, and existing proof references | Governing contract / required invariants | Limitation / next action |
|---|---|---|---|---|---|
| C-01 | Task creation authority / Control Room | **Required — satisfied by D1** | `core/control_room.py` and the ten-producer mapping in `docs/development/d1-control-room-writer-conformance-implementation.md`; merged PR #207 at `d03297c2b4e3522b0dc59ce001955cda130fd14f`, exact tested PR head `8532f573170b23b95bd98ccd56b3d8ea8d36cea8`. | All ten supported producers delegate to named Control Room operations; caller-owned Session/transaction; no direct-persistence fallback. | Preserve the boundary; investigate any newly discovered production writer rather than adding a parallel creator. |
| C-01 | Task lifecycle, terminal atomicity, replay/recovery | **Required** | `core/task_runtime.py` `37938270bed0679a1170f6b340ee6f0032d48906`; `core/operator_application.py` `b6666b4ada72626a75c2d8985b5bfc15b1a73067`; `core/control_room.py` `7b9add5d59271b317631784aebebe31723b645c3`. Existing proofs include `tests/test_world_memory.py::test_committed_operator_update_is_recovered_without_replaying_writes` and `tests/test_operator_application.py::test_concurrent_identical_requests_create_one_task_and_request_event`. | One Task lifecycle authority; attempt fencing; atomic terminal Outcome/Task/Event; exact replay and interrupted recovery. | Preserve the existing TaskRuntime lifecycle path; rerun the bounded scenario proofs on the exact tested head. |
| C-01 | Signal/source provenance and Team/domain isolation | **Required** | `core/ingestion.py` `aa7178fc95ad6df42ec100f992ff26abc9b3ed44`; `core/world_memory.py` `527b190cfbf36cf73e65ecc6b5cdad62025df085`. Existing proofs include `tests/test_ingestion.py::test_successful_ingestion_commits_signal_event_and_snapshot`, `test_same_task_retry_reuses_existing_outcome`, and `tests/test_world_memory.py::test_cross_team_hypothesis_signal_and_snapshot_references_fail_closed`. | Task attribution, source allowlist, immutable Snapshot/hash, same-Team source validation, exact quote/offset verification, no cross-Team evidence. | Audit actual candidate fixture and ensure it uses a same-Team source; do not claim Team-wide cross-origin canonical Signal identity (RW4-3 remains gated). |
| C-01 | Thread/Hypothesis/EvidenceLink operations | **Required** | `core/world_memory.py` `527b190cfbf36cf73e65ecc6b5cdad62025df085`; `core/operator_application.py` `0cdd5275fc5d33a0633b721a0e91840f0c0988cf`. Existing proofs include `test_operator_update_creates_low_hypothesis_and_verified_evidence`, `test_concurrent_operator_updates_serialize_competing_transitions`, `test_database_failure_rolls_back_the_entire_valid_proposal_set`, and `test_later_confidence_change_uses_one_valid_evidence_cause` in `tests/test_world_memory.py`. | Typed proposals; same-Team/Thread ownership; exact quote/hash/offset; confidence cause; canonical locks; atomic business commit; replay. | Confirm exact proof subset and residual qualifications; no new writer or alternate commit path. |
| C-01 | Context retrieval / retained experience | **Not required** | No Context assembler is called by the direct Operator proposal path. | Do not claim retrieval or retained-experience use when the scenario only supplies explicit source evidence. | Keep retrieval claims out of C-01; any retrieval scenario needs its own accepted consumer contract and gate. |
| C-01 | SignalDisposition / `triage_signal` | **Not required** | No disposition write is part of the candidate. `core/ingestion.py` `aa7178fc95ad6df42ec100f992ff26abc9b3ed44` only implements ingestion. | Path A explicitly defers disposition and complete triage. | No caller/Event substitute, ad-hoc disposition, or partial triage. |
| C-01 | PostgreSQL roles, migrations, disposable DB isolation | **Unknown** | Migration source head is `0020_rw4_task_identity` (`migrations/versions/0020_rw4_task_identity.py`, blob `855ac3b06b8b523aab507737cd2fc9cc2fe5d954`). No disposable DB or live role inspection was run in this audit. | Runtime must not be superuser/owner; migration authority separated; relevant constraints, transactions, locks, and concurrency must be proven on PostgreSQL. | Verify actual Alembic current/head on disposable PostgreSQL and prove the exact runtime/migrator role behavior before freeze. |
| C-02 | Task creation authority / Control Room | **Required — satisfied by D1** | `core/control_room.py` and `docs/development/d1-control-room-writer-conformance-implementation.md`; merged PR #207 at `d03297c2b4e3522b0dc59ce001955cda130fd14f`. | Same session-bound ten-producer Control Room boundary as C-01. | No separate adapter-owned Task writer. |
| C-02 | Task lifecycle and model-commit replay | **Required** | `core/task_runtime.py` `c19c1d6e87137441306cdb454f7ca304297d75d3`; `core/world_memory.py` `527b190cfbf36cf73e65ecc6b5cdad62025df085`. Existing proofs include `tests/test_update_thread.py::test_transient_model_commit_failure_rolls_back_and_recovers_same_proposals`, `test_marker_recovery_reconstructs_terminal_result_without_reapplying`, and `test_model_workers_serialize_concurrent_commits_for_same_thread`. | Single TaskRuntime lifecycle; durable generation receipt; attempt/Context binding; rollback/recovery; no duplicate business commit. | RW3.4 remains 28 PASS / 7 PARTIAL / 0 OPEN and formal acceptance is deferred; preserve the seven PARTIAL qualifications in any scope. |
| C-02 | Context assembly and evidence provenance | **Required** | `core/update_thread_context.py` `30075dba186b3cab2a412713b30641249b389438`; `core/update_thread_worker.py` `e24b58959c9e93155a05d19e45aafcc6ffd539b0`. Existing proofs include `test_context_is_deterministic_bounded_and_replayable`, `test_context_uses_task_pinned_policy_after_policy_advancement`, and `test_context_rejects_evidence_signal_from_another_team_domain`. | Task-pinned policy, bounded Context, immutable Snapshot/manifest, source quote verification, replay and Team/domain isolation. | Worker explicitly does not invoke Team Experience retrieval (`test_update_thread_worker_never_invokes_team_experience_retrieval`); it cannot satisfy a retained-experience retrieval claim. |
| C-02 | Provider authorization | **Blocked** for live-provider scenario | `core/update_thread_worker.py` `e24b58959c9e93155a05d19e45aafcc6ffd539b0`; `tests/test_update_thread.py::test_update_thread_worker_rejects_live_provider_until_separately_authorized`. | Only the deterministic test provider is accepted by the current worker. | A deterministic-fake-only candidate may be considered; live-provider execution remains separately gated. |
| C-02 | SignalDisposition / `triage_signal` | **Not required** | No disposition write is part of the existing update_thread path. | Path A defers disposition and triage. | No partial triage. |
| C-03 | Task creation authority / Control Room | **Required — satisfied by D1** | `core/control_room.py` and `docs/development/d1-control-room-writer-conformance-implementation.md`; merged PR #207 at `d03297c2b4e3522b0dc59ce001955cda130fd14f`. | PlanService delegates Task persistence to the named Control Room operation. | No PlanService direct-persistence fallback. |
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
- A supported Task-creating path outside the ten-producer D1 inventory is discovered, or any of the ten paths is shown to bypass Control Room; pause and audit before proceeding.
- A required invariant depends only on an unproven design statement or an in-memory/SQLite substitute for PostgreSQL behavior.
- Atomicity, replay, or concurrency behavior is not established for the exercised path.
- A requested result would require partial SignalDisposition/triage enablement or a new unaccepted write path.
- The scenario depends on RW4-4 retrieval or RW-D99/RW-D133 attribution without its own accepted consumer contract, gate, authorization, and proofs.
- A scenario claims retained-experience retrieval while using the current `update_thread` Context path, which explicitly does not invoke Team Experience retrieval.
- A scenario requires a live `update_thread` provider while provider authorization remains closed.

A stop is a scope/design finding, not permission to improvise a workaround.

## 7. Freeze record (complete only after review)

- Selected initial technical internal-test scenarios: **CG-01 and C-01**. This is not R8-ready entry acceptance; C-02/C-03 remain unselected.
- Selected technical test baseline: **CG-01**, test-only Control Group fixture for `operator_update`; authorized for internal technical verification, not R8-ready entry or scored execution
- Historical source-audit baseline SHA: `d671d066940d0dc06b1198c5ed474dc66653cccb`
- Current source baseline SHA for this reconciliation: `c648892e4896113700c8103397be01c11c0d22ed`
- Relevant Alembic source head: `0020_rw4_task_identity`; disposable PostgreSQL migration/current-head and role provisioning are covered by PR #221 local evidence and hosted CI; PR #222 role-test hardening also passed exact-head CI but remains unmerged.
- Existing governed entrypoints: D1 ten-producer conformance merged and CI-verified; CG-01 uses the existing authenticated Operator update path
- Required capability/proof set for CG-01 and C-01: reconciled in `r8-ready-internal-test-scope-and-proof-freeze.md`; the older §4 remains the historical candidate audit.
- Deferred capability set and reopen triggers: see §5
- Required PostgreSQL proof set: scenario-specific requirements are frozen in `r8-ready-internal-test-scope-and-proof-freeze.md`; production application-host identity proof remains out of scope and open.
- Fixtures and expected technical outcomes: CG-01 and C-01 are documented in their respective scenario records; exploratory result protocol remains the next planning step.
- Known limitations: neither scenario creates a Thread, invokes Team Experience retrieval, demonstrates treatment, or proves claim-level knowledge use; C-01 uses one source and does not prove cross-origin canonicalization; C-02/live provider remain gated; RW3.4 retains seven PARTIAL qualifications; no triage/disposition; no production host identity is established by these tests.
- D1 existing-writer implementation: merged by PR #207 at `d03297c2b4e3522b0dc59ce001955cda130fd14f`; hosted CI #2326 passed on exact PR head
- R8-ready internal technical-test foundation authorization: granted for CG-01 only on 2026-11-26; R8-ready state transition and scored RWN-01 execution remain unauthorized


## 8. Current-source internal-test reconciliation (2026-11-28)

The current implementation and evidence status supersede the historical candidate wording and baseline notes above. Historical source-audit tables remain preserved as historical evidence.

- **CG-01:** test-only baseline implementation and post-replay no-Team-Experience assertion are merged (PRs #209, #211, #212). Exact-head PostgreSQL/static/full-suite verification passed on PR #211; post-merge main CI passed. CG-01 remains a bounded operator_update technical baseline with fixture-seeded Signal/Snapshot and pre-existing active Thread.
- **C-01:** one-source configured-intake-to-Operator-update test is merged (PR #215); missing terminal/replay Event assertions were added in PR #216; documentation evidence was reconciled in PRs #217 and #218. Exact-head CI for #215 and #216 passed; #217 post-merge main CI passed. The integrated test includes Strategy acceptance, Plan materialization, deterministic FakeFetcher dispatch, Signal/Snapshot ingestion, TaskRuntime terminalization and evaluation follow-on, authenticated Operator update, exact evidence linkage, replay, and no-Team-Experience assertions.
- **D1:** all ten inventoried Task producers delegate through Control Room (PR #207/#208), and TaskRuntime remains lifecycle authority.
- **Disposable PostgreSQL and roles:** PR #221 merged after Windows full-suite verification (1,341 passed) and hosted exact-head CI. Its runner provisions watch_owner, watch_migrator, and read-only watch_runtime, uses the migrator for Alembic, and restores environment variables. PR #222 adds column-level privilege-test hardening and its exact head passed CI, but PR #222 is still open/unmerged; do not count its changes as part of main.
- **Current source baseline:** `c648892e4896113700c8103397be01c11c0d22ed`.

The detailed scenario boundary, capability classifications, proof references, and unresolved limitations are in [the internal-test scope and proof freeze](r8-ready-internal-test-scope-and-proof-freeze.md). This reconciliation is documentation only; it does not authorize a test run, production capability, R8-ready transition, or scored execution.
