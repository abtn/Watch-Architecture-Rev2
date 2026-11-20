# RW3.4 — Integrated Verification and Closeout Plan

**Status:** Working on RW3.4. This document defines the integrated verification and acceptance sequence for the already-merged RW3.1–RW3.3 implementation. The current PR is documentation-only. It does not authorize implementation changes, live provider calls, schema changes, persistent-database access, or later RW milestones.

**Planning baseline:** `main` at `c6febd883cb1d7390f44cf6aef09e3a8dbd5ba48` (2026-11-20).

**Milestone authority:** `PLAN.md` owns current status and authorization. This plan owns the RW3.4 closeout sequence and evidence checklist. The [RW-3 design and acceptance plan](rw-3-design-and-acceptance.md) remains normative for protocol and recovery semantics; [the implementation plan and proof matrix](rw-implementation-plan.md) remains normative for proof IDs; [Task specifications](../tasks.md) remain normative for Task shape, write scope, and budget; [testing records](../testing.md) own exact verification results.

## 1. Purpose and closeout boundary

RW3.4 is the integrated verification and closeout slice. Its job is to establish, on one exact repository tree, that the accepted RW3.1, RW3.2, and RW3.3 behavior composes correctly and preserves the already-accepted RW-2 Operator path.

The central invariant is continuity of one immutable Context identity across all durable stages:

`(context_event_id, context_snapshot_ref, context_content_hash)`

The tuple must identify the same verified Context Event and content-addressed Snapshot through:

1. RW3.1 Context assembly and immutable Task-attempt Event/Snapshot.
2. RW3.2 provider input, generation receipt, validated proposal Event, and proposal fingerprint.
3. RW3.3 typed commit envelope, accepted/rejected disposition Events, terminal marker, and TaskRuntime recovery.

A green test suite for each slice in isolation is not enough. RW3.4 must prove the integrated chain and its failure behavior on the same tested source SHA.

**RW3.4 is not a new worker or feature slice.** If verification exposes a production-code defect, stop and record it. Do not silently expand this documentation-only closeout into code changes. A corrective implementation requires a separately scoped and explicitly authorized PR; RW3.4 then verifies the corrected exact head.

## 2. Accepted predecessor baseline

| Slice | Accepted merge | Tested implementation evidence | Contract now inherited by RW3.4 |
|---|---|---|---|
| RW3.1 | PR [#136](https://github.com/abtn/Watch-Architecture-Rev2/pull/136), merge `6260921b451f99ab07756890045175ba9983c3ad` | Tested PR head `b59ecca786bf418456e0e687c3e77d632d1e4118`; hosted CI [#1492](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/44705109042); Programmer-local verification recorded in `docs/testing.md` | Host-authorized Task creation, Team-derived identity, deterministic Task/Event replay, pinned policy, bounded deterministic Context, exact Snapshot and quote validation. |
| RW3.2 | PR [#137](https://github.com/abtn/Watch-Architecture-Rev2/pull/137), merge `ee2f7002c8710e27589ab2a7f004bf3adb2c1dd7` | Hosted CI passed on `38181a8a46a17853db6ab0d9e7df0615752195d4`; exact local verification evidence is qualified in `docs/testing.md` and must not be inferred from the merge alone | TaskRuntime admission, verified Context before provider invocation, deterministic fake-provider boundary, usage reconciliation, atomic receipt/charge, strict proposal parsing, empty-set no-op, and durable Context provenance. |
| RW3.3 | PR [#138](https://github.com/abtn/Watch-Architecture-Rev2/pull/138), merge `8fff9fa9d515b46d446fdf46d076d2504e7f462f` | Corrected implementation head `86f603b019868a3bf49f43ca15a5285292aff7df`; hosted implementation CI [#1525](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/44784779816); final documentation-inclusive PR head `1893dcda27c962d1091cfd29b124f0b8e6e37ed8), CI [#1531](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/44789724923) | Shared RW-2 commit core, typed Operator/model-worker actor boundary, provenance-bound proposal dispositions, atomic commit/rejection markers, savepoint-protected permanent-integrity failure, and in-session TaskRuntime recovery. |

The current `main` baseline has no RW3.1–RW3.3 migration. Alembic remains at `0019_rw1_world_memory`. The accepted RW3.3 local and hosted full-suite result was **1,166 passed**, with 130 existing Alembic `path_separator` deprecation warnings in the local run. These are predecessor results, not a substitute for RW3.4 exact-head verification.

## 3. Scope

### Included

- Reconcile the three accepted slices against the current source, tests, Task contract, design plan, and proof matrix.
- Verify the Context identity tuple end to end, including negative tampering and crash-recovery paths.
- Verify that provider invocation cannot precede Task admission, Context integrity, and maximum cost reservation.
- Verify receipt/charge atomicity, strict proposal parsing, model/Operator actor separation, shared commit semantics, and TaskRuntime terminalization/recovery.
- Re-run the applicable RW-2 Operator regression suite and full repository suite.
- Re-run fresh disposable-PostgreSQL migration/current/single-head checks and all required static checks on one exact tested head.
- Reconcile documentation and record the exact tested SHA, test nodes, hosted CI run, local cleanup, known limitations, review disposition, and explicit Operator acceptance.

### Excluded

- No new Task type, worker, scheduler, TaskDispatcher expansion, runtime, authentication system, or follow-up Task creator.
- No live Cloudflare or other production-provider invocation. The existing worker is fake-provider-only; provider authorization remains a separate closed gate.
- No production host composition root or TeamPolicy publisher implementation.
- No SignalDisposition/triage, Thread creation/reactivation/projection, Team Experience retrieval, KnowledgeItem mutation, RW-4/RW-5, RW-4-KU, R7-C, or R8 work.
- No migration, schema, index, trigger, database constraint, or persistent-database operation.
- No newsroom scored run or value-harness result.

## 4. Cross-slice verification matrix

The following sequence maps the existing proof obligations to the accepted code and named tests. These names are an evidence index, not a claim that every obligation has already been closed by RW3.4.

### 4.1 RW3.1 — request, Task shape, policy pin, and Context

Verify the complete request boundary:

- `TrustedOperatorPrincipal` is required; the exact `request_update_thread` grant is checked against the Team derived from the locked Thread.
- New Task creation follows Team → Thread → TeamPolicy lock order; the newest supported policy is selected without fallback and pinned in both Task and request Event.
- UUIDv5 Task identity is Team-scoped. Same-Team/key reuse with another Thread or requester conflicts; same UUID in another Team is independent. Replay retains the original policy pin after policy advancement.
- Task and its single request Event are atomic; Task-PK conflict arbitration does not create duplicate request Events.
- Exact Task shape, write scope, and budget are preserved, including exact built-in integer types (booleans and floats are not accepted as integers).
- Context membership and ordering are deterministic and exhaustive for the bounded scope: target Thread, active same-Thread Hypotheses, all accepted EvidenceLinks for those Hypotheses, and verified source Snapshots. Overflow, invalid quotes, stale or cross-Team references, duplicate/mutated Context Events, and Snapshot hash mismatches fail closed.
- Same-attempt Context replay returns the same immutable Snapshot/Event. Team Experience and triage state remain excluded.

Primary test nodes in `tests/test_update_thread.py`:

- `test_host_creator_pins_policy_and_replays_without_execution`
- `test_task_request_rejects_budget_integer_type_substitution`
- `test_creator_rejects_wrong_action_without_task_or_event`
- `test_same_key_replay_by_another_operator_conflicts`
- `test_context_is_deterministic_bounded_and_replayable`
- `test_context_replay_rejects_boolean_substitution_for_integer_fields` (six parametrized cases)
- `test_request_identity_and_fingerprint_golden_vector`
- `test_request_task_identity_is_stable_and_team_scoped`
- `test_replay_keeps_original_policy_after_policy_advancement`
- `test_same_key_for_another_thread_conflicts`
- `test_concurrent_same_key_creation_writes_one_request_event`
- `test_context_fails_closed_when_evidence_link_bound_is_exceeded`
- `test_context_fails_closed_when_evidence_character_bound_is_exceeded`
- `test_context_rejects_quote_offsets_outside_source_snapshot`

Also verify the accepted RW-2 Team/Thread, quote/hash/offset, confidence-cause, low-initial-confidence, transition, replay, and concurrency proofs in `tests/test_world_memory.py`.

### 4.2 RW3.2 — admission, provider boundary, receipt, charge, and proposal Event

Verify ordering and durable provenance:

1. TaskRuntime validates and admits the immutable Task before attempt-specific Context work.
2. Context is reloaded from its content-addressed Snapshot and verified before the provider request is constructed or invoked.
3. Only the deterministic fake provider is accepted. Invalid Context causes zero provider calls and zero reservations.
4. The maximum exact-prompt cost is reserved before provider invocation.
5. Raw completion and validated model/usage metadata are reconciled and persisted with the charge in one transaction, even when completion text later fails strict parsing.
6. Receipt, proposal Event, and proposal fingerprint all preserve the exact Context identity tuple and bind Task, Team, Thread, attempt, policy, receipt, charge, and complete typed proposal list.
7. Empty proposal list is durable and completes only as `success_no_change`, after charge reconciliation and with no business write.
8. A non-empty proposal Event is durable input to RW3.3; it is not itself a business commit.
9. A provider return whose receipt transaction never commits leaves the reservation unknown and follows TaskRuntime's existing retry rules. Exactly-once remote provider invocation is not promised across that crash window.

Primary test nodes in `tests/test_update_thread.py`:

- `test_context_is_reloaded_from_its_verified_snapshot_before_provider_use`
- `test_task_runtime_admission_rejects_tampered_update_thread_request`
- `test_update_thread_worker_records_context_identity_and_empty_proposal_set`
- `test_update_thread_worker_persists_valid_usage_before_parser_failure`
- `test_interrupted_provider_call_marks_reserved_charge_unknown_before_retry`
- `test_model_output_cannot_supply_actor_identity`
- `test_update_thread_worker_never_calls_provider_for_invalid_context`
- `test_update_thread_worker_leaves_receipted_proposals_resumable_on_write_failure`
- `test_update_thread_worker_rejects_live_provider_until_separately_authorized`
- `test_update_thread_worker_receipt_and_charge_reconciliation_are_atomic`

Generation-adapter regression nodes in `tests/test_generation.py`:

- `test_generation_raw_returns_malformed_completion_with_validated_usage`
- `test_generation_posts_once_and_returns_validated_json_and_usage`
- `test_generation_fails_when_usage_is_missing`
- `test_http_errors_are_categorized_without_retrying`
- `test_generation_fails_when_provider_returns_a_different_model`

The exact node names must be checked against the current branch before the verification record is finalized; do not silently rename or infer test results.

### 4.3 RW3.3 — shared commit, actor separation, atomicity, and recovery

Verify that:

- Model proposals pass through the RW-2 validation/transaction core; no alternate business write path exists.
- The Operator actor and RW-2 Event/principal behavior remain unchanged. The model actor is application-created, Task-attributed, and cannot supply or inherit an Operator identity.
- Valid proposals commit as one atomic accepted set; invalid proposals receive attributable rejection Events; mixed sets commit only valid proposals; all-invalid sets have a durable rejection marker and terminal failure.
- The committed/rejected marker binds the exact receipt, charge, proposal Event/fingerprint, attempt, and Context identity.
- Recovery uses TaskRuntime's already-locked Session/Task/attempt and never reinvokes the provider or reapplies committed business writes.
- Receipt-only, proposal-only, marker-present, empty-set, interrupted-provider, transient-persistence, and permanent-integrity states are distinguished.
- Transient persistence failure leaves the same proposal set resumable. Permanent provenance/integrity failure rolls back staged business writes before the inconsistent marker is recorded.
- Overrun is a terminal failure and never authorizes business writes.
- Event integer fields reject Boolean substitutions.

Primary test nodes in `tests/test_update_thread.py`:

- `test_transient_model_commit_failure_rolls_back_and_recovers_same_proposals`
- `test_marker_recovery_reconstructs_terminal_result_without_reapplying`
- `test_permanent_provenance_conflict_records_inconsistent_without_writes`
- `test_missing_request_provenance_terminalizes_as_recovery_inconsistent`
- `test_update_thread_worker_commits_typed_proposal_with_model_actor`
- `test_update_thread_model_commit_partitions_proposals_exhaustively`
- `test_update_thread_worker_terminalizes_generation_cost_overrun_without_writes`
- `test_model_commit_savepoint_rolls_back_staged_writes_before_inconsistent_marker`
- `test_model_proposal_disposition_event_rejects_boolean_integer_substitution`
- `test_update_thread_committed_result_is_rejected_for_other_task_types`

### 4.4 Integrated invariants across all three slices

The closeout report must explicitly account for these proof rows from the implementation plan:

- Identity/provenance: `RW-REQ-01`, `RW-CTX-02`, `RW-CTX-04`, `RW-CTX-05`, `RW-CTX-06`, `RW-REPLAY-01`, `RW-SER-01`.
- Runtime and recovery: `RW-LC-01`, `RW-RT-01`, `RW-RT-02`, `RW-REC-01`, `RW-CF-01`.
- Actor and commit behavior: `RW-ACT-01`, `RW-ACT-02`, `RW-AT-01`, `RW-RP-01`, `RW-RC-01`, `RW-LT-01`.
- Scope and budget: `RW-TS-02`, `RW-POL-01`, `RW-GC-01`, `RW-GC-02`, `RW-GC-03`, `RW-GN-01`, `RW-GN-02`, `RW-DL-01`, `RW-PR-01`, `RW-PV-01`, `RW-PR-02`, `RW-NO-01`, `RW-PF-01`.

For each row, record the exact test node(s), exact tested SHA, and outcome. A row with only design text, a generic unit test, or an earlier-slice CI result is not closed evidence.

## 5. Cross-slice audit findings and unresolved proof gaps

This section records source-level observations from the RW3.4 planning audit. It distinguishes implemented behavior from what has not yet been demonstrated.

### 5.1 Deadline and provider-timeout mismatch — open closeout blocker

The normative Task/design contract requires a 45-second absolute deadline from TaskRuntime admission, covering Context assembly, quoting, provider execution, parsing, and pre-commit work; the provider timeout must be no more than 30 seconds and no greater than remaining Task time. The 60-second interrupted-recovery threshold must remain unchanged.

The current `UpdateThreadWorker.run` starts a monotonic timer after admission and calls `_check_deadline` at several stage boundaries. However, the current `GenerationProvider.generate_raw` protocol has no per-call timeout argument; the worker calls it without a deadline-derived timeout. `CloudflareWorkersAIConfig.timeout_seconds` defaults to 60 seconds and permits larger values. The worker cannot interrupt a blocking provider call at the Task deadline, and the inspected path does not check the deadline after parsing immediately before commit/finalization. The current `tests/test_update_thread.py` inventory has no dedicated 45-second deadline/30-second provider-timeout test node.

**Disposition:** do not claim `RW-DL-01` complete from the presence of `MAX_TASK_SECONDS` or boundary checks alone. RW3.4 must either:
- obtain separate authorization for a narrowly scoped corrective implementation and deterministic deadline/timeout regression tests, then rerun the integrated exact-head verification; or
- present the exact residual behavior and an explicit contract adjustment for Operator decision.

This documentation-only PR does not modify the provider protocol, timeout configuration, worker, or TaskRuntime.

### 5.2 Cumulative generation-cost proof — verify explicitly

The Task contract fixes a cumulative `$0.02` ceiling across at most three starts, one reservation per attempt, and full accounting for unknown reservations. The worker has an `update_thread` operation and the test suite covers receipt/charge atomicity and overrun terminalization. The inspected test-node inventory does not identify a dedicated proof of the exact `update_thread` operation mapping and cumulative three-start arithmetic.

**Disposition:** close `RW-GC-01` and `RW-GC-03` only after a test proves the Task-specific mapping, one reservation per attempt, aggregation of reconciled and unknown charges across all starts, budget exhaustion before provider invocation, and no business commit on overrun. Generic cost-service tests alone are insufficient unless the exact `update_thread` mapping is exercised.

### 5.3 Host authentication and TeamPolicy publication limitations

- The repository still has no production host composition root. RW3.1 tests prove Watch-side typed-principal/grant enforcement, not end-to-end host authentication. Record this as an integration limitation; do not describe it as proven.
- The repository still has no production TeamPolicy publishing service. RW3.1 proves creator-side Team lock/policy pin behavior, but cannot prove serialization against a production publisher that does not exist. Keep the Team-first lock contract documented for any future publisher; do not add a publisher, mutate policy, or invent a publication test fixture that claims production integration.

### 5.4 Provider authorization and migration boundary

- Live Cloudflare/provider invocation remains unauthorized. The deterministic fake-provider gate must remain active throughout RW3.4.
- No migration/schema change was made by RW3.1–RW3.3. Confirm fresh disposable PostgreSQL still reaches the single Alembic head `0019_rw1_world_memory`; do not use a persistent database.
- RW-4 triage does not create or enqueue `update_thread` Tasks. No RW-4/RW-5/R7-C/R8 or scored newsroom work is included.

## 6. Execution sequence

The order is deliberate. Do not skip ahead from green slice tests to acceptance.

| Step | Work | Required output / gate |
|---|---|---|
| 0. Freeze baseline | Start from the exact current `main` SHA. Record repo, branch, HEAD, clean worktree, origin, Python/uv versions, and current Alembic head. No reset/stash or destructive cleanup. | Exact baseline SHA and clean preflight record. |
| 1. Build the evidence ledger | Map every RW3.1–RW3.3 proof row to exact current test nodes, source locations, and prior verification SHA. Separate source inspection, focused tests, local full verification, and hosted CI evidence. | Completed proof ledger; all missing nodes explicitly marked open. |
| 2. Audit integration seams | Inspect the Task creator → TaskRuntime admission → Context verifier → cost reservation → generation adapter → receipt/proposal persistence → shared commit core → TaskRuntime finalization/recovery path. Check the exact Context tuple at every handoff. Recheck RW-2 Operator compatibility. | Reviewed sequence diagram or concise call-path record; no guessed identity substitution or parallel authority path. |
| 3. Resolve blockers | Present the deadline/timeout mismatch and cumulative-budget proof gap for explicit disposition. If code changes are needed, stop this docs-only stream and request separate implementation authorization. | Every P1/P2 finding resolved or explicitly left as a blocking acceptance item; no silent waiver. |
| 4. Run focused integrated proofs | Run the RW3.1–RW3.3 nodes in §§4.1–4.3 plus the applicable RW-2 Operator tests on the same source tree. Include PostgreSQL-backed concurrency, atomicity, replay, savepoint, and recovery proofs. | Exact command output and node counts tied to the tested SHA. |
| 5. Run full verification | On a fresh disposable PostgreSQL instance with a dynamically assigned host port: migrate to head; verify `alembic heads` and `alembic current`; run Ruff, Mypy, `git diff --check`, and full pytest. Preserve/restore `DATABASE_URL` and `TEST_DATABASE_URL`; remove only the disposable container/volume created for this run. | Complete local verification record, cleanup confirmation, exact branch/HEAD, and clean worktree. |
| 6. Hosted verification and independent review | Push the exact tested code/test tree and require hosted CI to pass on that exact SHA. If documentation-only commits follow, record their final PR head and hosted run separately. Independently review the final diff for correctness, scope, stale claims, and evidence traceability. | Passing hosted run(s), exact tested SHA versus final PR head, and review disposition. |
| 7. Reconcile and accept | Update `PLAN.md`, this plan, the RW implementation proof matrix, `docs/testing.md`, `docs/tasks.md`, `docs/architecture.md`, and `CHANGE_MAP.md` so the authority split remains singular. Record limitations and explicit Operator disposition. | RW3.4 may be marked accepted only after all mandatory evidence and explicit Operator acceptance are recorded. |

### 6.1 Programmer-local verification contract

Use the repository's current Windows PowerShell sync/test guide and exact-head preflight conventions. The verification script must:

- verify repository root, expected branch, expected SHA, clean worktree, and origin before changing anything;
- use a disposable PostgreSQL container only, with a dynamically assigned local port (never assume 5432);
- preserve and restore both database URL environment variables exactly;
- run Alembic migration/current/single-head checks, focused tests, Ruff, Mypy, full pytest, and `git diff --check`;
- check native-command exit codes explicitly;
- stop/remove only the disposable resources created by that script;
- report exact commands, counts, warnings, final HEAD, branch, worktree state, and cleanup result;
- refuse to continue on branch/HEAD/cleanliness mismatch; never stash, reset, or discard user work.

No local verification result is claimed by this plan. The results must be produced by running the approved script against the eventual exact RW3.4 tested head.

## 7. Documentation authority and deliverables

- `PLAN.md`: sole current status and authorization. During this slice it must say **working on RW3.4 integrated verification/closeout**, not accepted.
- This document: detailed RW3.4 execution sequence, proof ledger structure, audit findings, and closeout gate.
- `docs/development/rw-implementation-plan.md`: slice order and proof IDs; link to this plan and map RW3.4 rows to their final test nodes.
- `docs/development/rw-3-design-and-acceptance.md`: normative protocol and failure semantics; do not duplicate mutable milestone status beyond a pointer to PLAN.
- `docs/tasks.md`: normative Task shape/write scope/budget; current implementation status only as a pointer.
- `docs/architecture.md`: concise implemented boundary and known host/provider limitations.
- `docs/testing.md`: exact tested SHA, test nodes, commands, counts, Alembic result, CI runs, cleanup, and acceptance record.
- `CHANGE_MAP.md`: links the RW3.4 plan and points current status to PLAN.

The documentation-only planning PR is not RW3.4 acceptance. It moves the project state to **working on RW3.4** and establishes the evidence required for a later closeout decision.

## 8. RW3.4 acceptance checklist

- [ ] All RW3.1 request, Task-shape, policy-pin, Context, Snapshot, and replay proofs are mapped to current test nodes.
- [ ] All RW3.2 admission/provider/receipt/charge/proposal/failure proofs are mapped to current test nodes.
- [ ] All RW3.3 shared-commit/actor/marker/atomicity/recovery proofs are mapped to current test nodes.
- [ ] The Context identity tuple is independently checked at every durable boundary and in every recovery state.
- [ ] RW-2 Operator behavior is unchanged and its regression proofs pass.
- [ ] `RW-GC-01` and `RW-GC-03` cumulative Task-budget proofs are complete.
- [ ] `RW-DL-01` deadline and provider-timeout proof is complete or an explicit Operator-approved contract adjustment is recorded.
- [ ] Host composition-root and TeamPolicy publisher limitations are stated accurately and not misrepresented as tested integrations.
- [ ] Live provider authorization remains closed; fake-provider gate is proven.
- [ ] Fresh disposable PostgreSQL reaches exactly one head, `0019_rw1_world_memory`; no persistent database is used.
- [ ] Ruff, Mypy, focused tests, full suite, patch-whitespace checks, cleanup, and environment restoration pass on the exact tested SHA.
- [ ] Hosted CI passes on the exact tested SHA and final PR head; both SHAs are recorded if documentation-only commits follow.
- [ ] Independent review finds no unresolved blocking correctness issue.
- [ ] `PLAN.md`, proof matrix, `docs/testing.md`, Task/architecture docs, and CHANGE_MAP agree.
- [ ] Explicit Operator acceptance is recorded before RW3.4 is marked complete.

## 9. Non-authorizations

Completing this plan or merging its documentation-only PR does not authorize:

- any production-code change in the deadline/cost/provider paths;
- any Cloudflare/live provider call;
- production host authentication composition or TeamPolicy publishing;
- schema/migration/index/constraint changes or persistent database access;
- RW-4, RW-5, R7-C, RW-4-KU, R8, or scored newsroom execution.

Those require their own scope, review, and explicit authorization.
