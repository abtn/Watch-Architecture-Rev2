# RW3.4 — Integrated Verification and Closeout Plan

**Status:** The RW3.4 implementation and integrated verification stack are merged. Consolidated PR [#152](https://github.com/abtn/Watch-Architecture-Rev2/pull/152) was merged to `main` at `77388707c82aa8dbcf4a37d3f44cb14a0b914f60`. Its implementation was locally verified on `20cfc252d21bdecc6153c1d8daa8369e1f331ff2`; hosted CI passed on final PR head `7c7aa3a3c5fc98c4ccfab21900f327b9323ee61d` (run [#45018330304](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/45018330304)). This document preserves the integrated proof matrix and records the remaining formal acceptance gate. **RW3.4 is not formally accepted by this merge or verification record.**

**Planning baseline:** `main` at `77388707c82aa8dbcf4a37d3f44cb14a0b914f60` (2026-11-22).

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
| RW3.3 | PR [#138](https://github.com/abtn/Watch-Architecture-Rev2/pull/138), merge `8fff9fa9d515b46d446fdf46d076d2504e7f462f` | Corrected implementation head `86f603b019868a3bf49f43ca15a5285292aff7df`; hosted implementation CI [#1525](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/44784779816); final documentation-inclusive PR head `1893dcda27c962d1091cfd29b124f0b8e6e37ed8`; CI [#1531](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/44789724923) | Shared RW-2 commit core, typed Operator/model-worker actor boundary, provenance-bound proposal dispositions, atomic commit/rejection markers, savepoint-protected permanent-integrity failure, and in-session TaskRuntime recovery. |

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

- Context selection and scope: `RW-CT-01`, `RW-CT-02`, `RW-CT-03`, `RW-CTX-04`, `RW-CTX-05`, `RW-CTX-06`.
- Identity and durable provenance: `RW-REQ-01`, `RW-ID-01`, `RW-REPLAY-01`, `RW-SER-01`.
- Runtime and recovery: `RW-LC-01`, `RW-RT-01`, `RW-RT-02`, `RW-REC-01`, `RW-CF-01`, `RW-WK-01`.
- Actor, commit, and retained state: `RW-ACT-01`, `RW-ACT-02`, `RW-AT-01`, `RW-RP-01`, `RW-RC-01`, `RW-LT-01`.
- Scope, provider, and budget: `RW-TS-02`, `RW-POL-01`, `RW-GC-01`, `RW-GC-02`, `RW-GC-03`, `RW-GN-01`, `RW-GN-02`, `RW-DL-01`, `RW-PR-01`, `RW-PV-01`, `RW-PR-02`, `RW-NO-01`, `RW-PF-01`.

The ledger below contains 35 RW-3 proof rows: **15 PASS, 19 PARTIAL, and 1 OPEN**. PASS/PARTIAL are evidence-coverage classifications only; they do not replace the explicit Operator acceptance gate.

For each row, record the exact test node(s), exact tested SHA, and outcome. A row with only design text, a generic unit test, or an earlier-slice CI result is not closed evidence.


### 4.5 Integrated proof ledger — evidence mapping against the verified tree

**Ledger baseline:** exact locally verified implementation/code-test SHA: `20cfc252d21bdecc6153c1d8daa8369e1f331ff2`. The local full suite passed **1,213 tests** on this SHA. The following test/source files were fetched at both this SHA and the current `main` commit `f6ca5bdcec0b2e0590c93d4228c3c9d9108de030`; their Git blob SHAs were identical, so the named nodes below are present unchanged in the locally verified tree:

- Tests: `tests/test_update_thread.py` (`bd129ae9b86b8317808f6149079512d2d5a6aaed`), `tests/test_task_runtime.py` (`f5a5302038d6254360cb39f66fb80196ddec09ed`), `tests/test_generation.py` (`0887687414372ca322128960b1954e05667229b6`), `tests/test_generation_cost.py` (`c76e2f2b830a58583ffefaa1cc60640f6b20b9ca`), `tests/test_world_memory.py` (`cf1478df54019cbe3cf84ef216d04074470fe780`), `tests/test_operator_application.py` (`f5003f00212feb78ff5c60f9ec8e7f09a07e1fa7`), and `tests/test_r6b_dispatcher.py` (`40b693843c75cf68d9ad8096079b7432401d988d`).
- Relevant implementation: `core/update_thread.py` (`9958bdf6dbb68cd1c378ab440545326c487b1706`), `core/update_thread_context.py` (`30075dba186b3cab2a412713b30641249b389438`), `core/update_thread_worker.py` (`e24b58959c9e93155a05d19e45aafcc6ffd539b0`), and `core/task_runtime.py` (`c19c1d6e87137441306cdb454f7ca304297d75d3`).

The exact SHA in every row is the tree against which the 155 focused tests and 1,213-test full suite were run. A listed test node is evidence that the named test passed as part of that full-suite run; it is not a claim that the test alone proves every clause in a compound proof ID.

**Status meanings:** **PASS** means the identified tests directly exercise the stated obligation at the verified SHA. **PARTIAL** means some clauses are demonstrated but at least one clause lacks direct test evidence or is an explicitly absent integration. **OPEN** means no adequate test node was identified. **NOT IMPLEMENTED** is reserved for an intentionally absent integration, not an accidental test omission. These are evidence statuses, not formal RW3.4 acceptance. Within each table row, subsequent unqualified `test_...` names refer to the same test file as the most recently named fully qualified path; a new `tests/...` path starts a new file context. This shorthand does not change the exact pytest node identity.

| Proof ID | Exact test nodes / source evidence | Tested SHA | Status | Remaining qualification or missing proof |
|---|---|---|---|---|
| `RW-REQ-01` | `tests/test_update_thread.py::test_host_creator_pins_policy_and_replays_without_execution`; `test_creator_rejects_wrong_action_without_task_or_event`; `test_same_key_replay_by_another_operator_conflicts`; `test_request_identity_and_fingerprint_golden_vector`; `test_request_task_identity_is_stable_and_team_scoped`; `test_replay_keeps_original_policy_after_policy_advancement`; `test_same_key_for_another_thread_conflicts`; `test_concurrent_same_key_creation_writes_one_request_event`; `test_creator_fails_closed_on_tampered_request_fingerprint` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PARTIAL** | Watch-side Task creation, exact-action rejection, identity binding and replay are tested. The test search found no direct creator-negative cases for missing/malformed principal, wrong-Team grant, cross-Team Thread, inactive Team, or resolved/unavailable Thread; source-level validation is not a substitute for those tests. Production host authentication is **NOT IMPLEMENTED / NOT PROVEN** because no production composition root exists. |
| `RW-CT-01` | `tests/test_update_thread.py::test_context_is_deterministic_bounded_and_replayable`; `test_context_fails_closed_when_active_hypothesis_bound_is_exceeded`; `test_context_fails_closed_when_evidence_link_bound_is_exceeded`; `test_context_fails_closed_when_evidence_character_bound_is_exceeded`; `test_context_rejects_quote_offsets_outside_source_snapshot` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PARTIAL** | Bounded target-Thread Context and quote/Snapshot checks are represented. A dedicated Context-level cross-Team reference proof is not explicitly mapped here; do not substitute an Operator commit test for that Context proof. |
| `RW-CT-02` | `tests/test_update_thread.py::test_context_is_deterministic_bounded_and_replayable`; `test_context_replay_rejects_boolean_substitution_for_integer_fields`; `test_context_fails_closed_when_active_hypothesis_bound_is_exceeded`; `test_context_fails_closed_when_evidence_link_bound_is_exceeded`; `test_context_fails_closed_when_evidence_character_bound_is_exceeded` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | Equal-time ordering, deterministic replay, integer-type tampering, and the configured Context bounds are directly exercised. |
| `RW-CT-03` | Source inspection: `core/update_thread_context.py` contains the RW-3 Context assembler; no Team Experience retrieval path is present in this module. No dedicated negative test node identified. | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PARTIAL** | Absence is currently a source-inspection finding, not an executable proof that no Team Experience retrieval call or passage can enter through composition. Add an instrumented negative test or keep this row qualified. |
| `RW-CTX-04` | `tests/test_update_thread.py::test_context_is_deterministic_bounded_and_replayable`; `test_host_creator_pins_policy_and_replays_without_execution`; `test_replay_keeps_original_policy_after_policy_advancement` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PARTIAL** | Context membership and historical policy pinning are represented. Production TeamPolicy publisher lock-order serialization remains **NOT IMPLEMENTED / NOT PROVEN**; creator-side tests cannot establish integration with a publisher that does not exist. |
| `RW-CTX-05` | `tests/test_update_thread.py::test_context_is_reloaded_from_its_verified_snapshot_before_provider_use`; `test_update_thread_worker_never_calls_provider_for_boolean_context_fields`; `test_update_thread_worker_never_calls_provider_for_invalid_context`; `test_task_runtime_admission_rejects_tampered_update_thread_request` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | The invalid-context parametrization includes Boolean manifest tampering, Snapshot hash mismatch, duplicate Context Events, and future-attempt substitution; provider call count is asserted zero. |
| `RW-CTX-06` | `tests/test_update_thread.py::test_update_thread_worker_records_context_identity_and_empty_proposal_set`; `test_update_thread_worker_commits_typed_proposal_with_model_actor`; `test_transient_model_commit_failure_rolls_back_and_recovers_same_proposals`; `test_marker_recovery_reconstructs_terminal_result_without_reapplying`; source validation in `core/task_runtime.py` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PARTIAL** | Receipt/proposal/marker persistence and recovery are exercised. The ledger does not yet enumerate a negative mutation test for every tuple boundary (receipt, proposal Event/fingerprint, typed envelope, marker, and each recovery branch). |
| `RW-REPLAY-01` | `tests/test_update_thread.py::test_update_thread_worker_receipt_and_charge_reconciliation_are_atomic`; `test_update_thread_worker_records_context_identity_and_empty_proposal_set`; `test_interrupted_provider_call_marks_reserved_charge_unknown_before_retry`; `test_transient_model_commit_failure_rolls_back_and_recovers_same_proposals`; `test_marker_recovery_reconstructs_terminal_result_without_reapplying`; `test_update_thread_receipt_history_validation_rejects_invalid_history` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PARTIAL** | Receipt/charge atomicity, unknown reservation after interruption, durable proposal recovery and marker replay are tested. The proof ledger still needs a sub-row map for every required tuple field and every receipt-only/proposal-only/marker crash window. Exactly-once remote provider invocation is not promised. |
| `RW-SER-01` | Source inspection: `core/update_thread_worker.py` constructs the versioned proposal fingerprint; `core/task_runtime.py` recomputes it using canonical JSON and rejects duplicate JSON object keys. Related tests: `test_update_thread_worker_records_context_identity_and_empty_proposal_set`; `test_transient_model_commit_failure_rolls_back_and_recovers_same_proposals`; `test_marker_recovery_reconstructs_terminal_result_without_reapplying`. | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PARTIAL** | Runtime verification of the fingerprint is present, but no dedicated golden-vector test was identified for proposal serialization across process restarts (UUID/enum encoding, preserved array order, exact canonical bytes, domain tag and digest). The existing request-fingerprint golden vector is a different contract. |
| `RW-LC-01` | `tests/test_task_runtime.py::test_admission_captures_monotonic_timestamp_used_by_worker`; `test_daily_quota_query_preserves_paired_admission_deadline`; `test_retry_requires_runtime_redelivery_not_second_claim`; `tests/test_update_thread.py::test_task_runtime_admission_rejects_tampered_update_thread_request`; `test_retryable_provider_interruption_schedules_task_retry`; `test_update_thread_worker_never_calls_provider_for_invalid_context` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | Admission ownership, monotonic anchor, admission-before-worker validation, and retry ownership have direct test coverage. |
| `RW-RT-01` | `tests/test_update_thread.py::test_update_thread_worker_records_context_identity_and_empty_proposal_set`; `test_update_thread_worker_commits_typed_proposal_with_model_actor`; `test_update_thread_committed_result_is_rejected_for_other_task_types` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | Both accepted success categories and rejection of the committed category for other Task types are exercised. |
| `RW-RT-02` | `tests/test_update_thread.py::test_update_thread_worker_records_context_identity_and_empty_proposal_set`; `test_update_thread_model_commit_partitions_proposals_exhaustively`; `test_transient_model_commit_failure_rolls_back_and_recovers_same_proposals`; `test_marker_recovery_reconstructs_terminal_result_without_reapplying`; `test_update_thread_worker_does_not_materialize_receipt_only_recovery_after_deadline` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PARTIAL** | Empty, committed, all-invalid, proposal-persistence and marker recovery are represented. A complete explicit receipt-only and proposal-only recovery-state matrix, including mismatch/duplicate/cross-attempt cases, is not yet mapped. |
| `RW-REC-01` | `tests/test_update_thread.py::test_transient_model_commit_failure_rolls_back_and_recovers_same_proposals`; `test_marker_recovery_reconstructs_terminal_result_without_reapplying`; `test_permanent_provenance_conflict_records_inconsistent_without_writes`; `test_missing_request_provenance_terminalizes_as_recovery_inconsistent`; `test_update_thread_worker_does_not_materialize_receipt_only_recovery_after_deadline` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PARTIAL** | Transient, marker-present, and permanent-inconsistency recovery are tested. The exact locked Session/Task/attempt contract and all Context tuple consistency checks across every recovery state need explicit sub-proof mapping. |
| `RW-CF-01` | `tests/test_update_thread.py::test_transient_model_commit_failure_rolls_back_and_recovers_same_proposals`; `test_update_thread_model_commit_partitions_proposals_exhaustively`; `test_permanent_provenance_conflict_records_inconsistent_without_writes`; `test_model_commit_savepoint_rolls_back_staged_writes_before_inconsistent_marker` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | Same-proposal transient recovery, exhaustive accepted/rejected partitioning, and rollback-before-inconsistent-marker behavior are directly exercised. |
| `RW-ACT-01` | `tests/test_update_thread.py::test_model_output_cannot_supply_actor_identity`; `test_update_thread_worker_commits_typed_proposal_with_model_actor`; `tests/test_world_memory.py::test_host_grant_is_team_and_action_scoped`; `tests/test_operator_application.py::test_host_grant_must_match_the_proposal_team_and_exact_action` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | Model actor attribution and rejection of model-supplied actor identity are tested alongside the unchanged Operator grant path. |
| `RW-ACT-02` | `tests/test_update_thread.py::test_update_thread_worker_commits_typed_proposal_with_model_actor`; `test_model_proposal_disposition_event_rejects_boolean_integer_substitution`; `test_update_thread_committed_result_is_rejected_for_other_task_types`; Operator regression nodes in `tests/test_world_memory.py` and `tests/test_operator_application.py` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PARTIAL** | Model Event attribution and Task-type terminal validation are exercised. The proof ledger does not yet identify a direct bidirectional test rejecting Operator Event substitution in the model family and model Event substitution in the Operator family. |
| `RW-AT-01` | `tests/test_update_thread.py::test_update_thread_model_commit_partitions_proposals_exhaustively`; `test_model_commit_savepoint_rolls_back_staged_writes_before_inconsistent_marker`; `tests/test_world_memory.py::test_database_failure_rolls_back_the_entire_valid_proposal_set`; `test_all_invalid_proposals_fail_task_and_write_no_business_state` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | Mixed/all-invalid model batches and rollback of staged writes are directly covered; the accepted Operator path retains its atomicity regression proof. |
| `RW-RP-01` | `tests/test_update_thread.py::test_marker_recovery_reconstructs_terminal_result_without_reapplying`; `test_transient_model_commit_failure_rolls_back_and_recovers_same_proposals`; `tests/test_update_thread.py::test_host_creator_pins_policy_and_replays_without_execution`; `tests/test_world_memory.py::test_reusing_idempotency_key_with_different_request_is_rejected`; `test_committed_operator_update_is_recovered_without_replaying_writes` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PARTIAL** | Operator request replay and model marker recovery are tested. A direct repeated model Task/proposal replay assertion covering every duplicate Event/write outcome is not separately identified. |
| `RW-RC-01` | `tests/test_world_memory.py::test_concurrent_operator_updates_serialize_competing_transitions`; `tests/test_update_thread.py::test_concurrent_same_key_creation_writes_one_request_event` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PARTIAL** | Operator-side concurrent transition serialization and Task-creation arbitration are tested. A direct concurrent model-worker commit race on one Thread is not identified. |
| `RW-LT-01` | `tests/test_world_memory.py::test_operator_update_creates_low_hypothesis_and_verified_evidence`; `test_mentions_rejections_and_replay_do_not_touch_hypothesis`; source inspection of the shared `touched_hypothesis_ids` update in `core/world_memory.py` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PARTIAL** | The creation test asserts a timestamp, but its Hypothesis is created in the same operation, so it does not isolate accepted evidence as the cause of the timestamp. The negative test proves mentions, rejection and replay do not change an existing Hypothesis. The shared commit core updates `touched_hypothesis_ids`, but no direct test was identified where accepted evidence is added to a pre-existing Hypothesis and advances its timestamp; this remains a real proof gap for both the Operator and model-worker routes. |
| `RW-TS-02` | `tests/test_update_thread.py::test_host_creator_pins_policy_and_replays_without_execution`; `test_task_request_rejects_budget_integer_type_substitution`; `test_update_thread_task_contract_keeps_two_cent_budget_and_three_starts`; `test_task_runtime_admission_rejects_tampered_update_thread_request` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | Task creation, immutable shape, exact budget, attempt limits, write scope and tampered-request admission are covered by the named tests. |
| `RW-POL-01` | `tests/test_update_thread.py::test_host_creator_pins_policy_and_replays_without_execution`; `test_replay_keeps_original_policy_after_policy_advancement`; `test_concurrent_same_key_creation_writes_one_request_event` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PARTIAL** | Creator-side selection, pinning, replay and Task-creation arbitration are covered. The production publisher and both real Task-creation/publisher lock orders remain unproven because no publisher exists. |
| `RW-GC-01` | `tests/test_generation_cost.py::test_reservation_is_persisted_before_reconciliation_and_settled_from_usage`; `test_budget_exhaustion_writes_no_charge_or_reservation_event`; `test_concurrent_same_attempt_reservations_commit_exactly_once`; `tests/test_update_thread.py::test_update_thread_worker_counts_reconciled_and_unknown_charges_before_next_call` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | The integrated `update_thread` worker test exhausts cumulative Task budget on its third start: the third reservation raises `task_generation_budget_exhausted`, `provider.calls` remains exactly 2, and no third provider invocation or business write occurs. This directly proves reservation denial precedes provider invocation for the operation. The cost-service tests additionally cover durable reservation, denial without charge/Event, and same-attempt reservation arbitration. |
| `RW-GC-02` | `tests/test_generation_cost.py::test_unknown_usage_keeps_full_reservation_and_blocks_same_attempt_replay`; `test_usage_above_reserved_bounds_is_recorded_as_an_overrun`; `test_generation_charge_is_reconciled_idempotently`; `test_reconciliation_event_failure_keeps_reservation_and_can_be_marked_unknown`; `tests/test_update_thread.py::test_update_thread_worker_persists_valid_usage_before_parser_failure`; `test_update_thread_worker_receipt_and_charge_reconciliation_are_atomic` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | Unknown, overrun, idempotent reconciliation, reconciliation failure, usage-before-parser-failure and receipt/charge atomicity have direct test coverage. |
| `RW-GC-03` | `tests/test_generation.py::test_three_maximum_update_thread_reservations_fit_task_cost_ceiling`; `tests/test_update_thread.py::test_update_thread_task_contract_keeps_two_cent_budget_and_three_starts`; `test_update_thread_worker_counts_reconciled_and_unknown_charges_before_next_call`; `test_update_thread_worker_terminalizes_generation_cost_overrun_without_writes` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | Production three-start/$0.02 arithmetic, cumulative reconciled-plus-unknown exposure, and terminal overrun without business writes are covered. The smaller exhaustion budget is explicitly test-only. |
| `RW-GN-01` | `tests/test_generation.py::test_generation_posts_once_and_returns_validated_json_and_usage`; `test_generation_fails_when_usage_is_missing`; `test_generation_fails_closed_when_provider_returns_a_different_model`; `test_configuration_rejects_non_cloudflare_or_unsafe_base_urls`; `test_configuration_rejects_output_limit_above_initial_cap`; `test_initial_provider_rejects_a_model_without_a_pinned_price_card`; `tests/test_generation_cost.py::test_untrusted_quote_cannot_lower_the_selected_model_price_card` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PARTIAL** | Provider configuration, model/rate-card validation and usage metadata are covered. A direct negative matrix for every operation-to-Task/write-scope mismatch is not identified. |
| `RW-GN-02` | `tests/test_update_thread.py::test_update_thread_worker_rejects_live_provider_until_separately_authorized`; deterministic fake-provider use across the RW-3 worker tests | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | The live-provider gate is directly tested; the recorded verification used deterministic fakes only. |
| `RW-DL-01` | `tests/test_task_runtime.py::test_admission_captures_monotonic_timestamp_used_by_worker`; `test_daily_quota_query_preserves_paired_admission_deadline`; `tests/test_generation.py::test_absolute_generation_deadline_bounds_slow_dns_resolution`; `test_repeated_stalled_dns_resolution_is_process_bounded`; `test_absolute_generation_deadline_interrupts_tcp_and_tls`; `test_absolute_deadline_rejects_send_after_expiry`; `test_absolute_deadline_closes_socket_during_response_read`; `test_provider_uses_earliest_absolute_or_relative_deadline`; `tests/test_update_thread.py::test_provider_timeout_at_task_deadline_is_terminal_and_keeps_charge_unknown`; `test_update_thread_worker_caps_provider_timeout_at_thirty_seconds`; `test_update_thread_worker_provider_timeout_is_capped_by_remaining_deadline`; `test_update_thread_worker_does_not_invoke_provider_after_deadline`; `test_update_thread_worker_discards_provider_result_returned_after_deadline`; `test_update_thread_worker_checks_deadline_after_parsing`; `test_update_thread_worker_rechecks_deadline_after_commit_lock`; `test_update_thread_worker_rechecks_deadline_during_proposal_persistence`; `test_update_thread_recovery_rejects_proposal_event_persisted_at_or_after_deadline` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | Admission anchoring, DNS/socket deadline enforcement, 30-second and remaining-time caps, late provider results, pre-commit checks and recovery expiry are directly exercised. The existing 60-second recovery threshold remains unchanged. |
| `RW-PR-01` | `tests/test_generation.py::test_generation_rejects_non_json_completion`; `test_generation_raw_returns_malformed_completion_with_validated_usage`; `tests/test_update_thread.py::test_update_thread_worker_persists_valid_usage_before_parser_failure`; `test_update_thread_model_commit_partitions_proposals_exhaustively`; `test_model_output_cannot_supply_actor_identity` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PARTIAL** | Malformed JSON, parser failure after charge reconciliation, typed domain rejection and actor-field forgery are covered. Explicit unknown-field, every unsupported proposal shape, forged reference and proposal-count-overflow cases are not all mapped. |
| `RW-PV-01` | `tests/test_update_thread.py::test_retryable_provider_interruption_schedules_task_retry`; `test_interrupted_provider_call_marks_reserved_charge_unknown_before_retry`; `test_provider_timeout_at_task_deadline_is_terminal_and_keeps_charge_unknown`; `tests/test_generation.py::test_incomplete_http_response_is_a_retryable_provider_failure`; `test_http_errors_are_categorized_without_retrying` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | Retry ownership, interruption, unknown charge, terminal deadline timeout, incomplete transport and no adapter-level HTTP retry are covered. |
| `RW-PR-02` | Source inspection in `core/update_thread_worker.py` confirms `MAX_MODEL_PROPOSALS = 8` and the typed proposal list has `Field(max_length=MAX_MODEL_PROPOSALS)`. No dedicated test node was identified for accepting exactly 8, rejecting 9, and preserving the Operator's 64-proposal limit. | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **OPEN** | This is a concrete test-coverage gap. Do not mark the model proposal bound proof complete based on a schema constant or unrelated batch tests. |
| `RW-NO-01` | `tests/test_update_thread.py::test_update_thread_worker_records_context_identity_and_empty_proposal_set` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | Empty proposal list is reconciled, persisted, finalized as `success_no_change`, and produces no business commit. |
| `RW-PF-01` | `tests/test_update_thread.py::test_update_thread_worker_persists_valid_usage_before_parser_failure`; `test_update_thread_model_commit_partitions_proposals_exhaustively`; `tests/test_generation.py::test_generation_rejects_non_json_completion` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PARTIAL** | Parser failure and typed proposal-level rejection are distinct in the tested paths. The full malformed/unknown/unsupported/forged/oversized parser matrix is not individually mapped. |
| `RW-ID-01` | `tests/test_update_thread.py::test_model_output_cannot_supply_actor_identity`; `test_update_thread_worker_commits_typed_proposal_with_model_actor`; strict typed parser/source inspection in `core/update_thread_worker.py` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PARTIAL** | The model-supplied actor field is rejected and committed Events are application-attributed. Direct negative cases for forged Task, Team, Thread, policy, principal, budget, and allowed-write fields are not individually identified. |
| `RW-WK-01` | `tests/test_update_thread.py::test_host_creator_pins_policy_and_replays_without_execution`; `test_update_thread_worker_records_context_identity_and_empty_proposal_set`; `test_update_thread_worker_commits_typed_proposal_with_model_actor`; `tests/test_r6b_dispatcher.py::test_find_eligible_task_ignores_unsupported_task_types`; `test_unsupported_task_type_is_rejected_before_admission`; `test_one_dispatch_call_makes_at_most_one_attempt`; admission tests in `tests/test_task_runtime.py` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PARTIAL** | Separate creator and existing-Task worker paths are exercised. The ledger does not yet identify a direct regression proving TaskDispatcher remains ingestion-only and no alternate scheduler/runtime path was introduced. |

### 4.6 Consolidated gaps requiring disposition

The mapping above identifies the following remaining evidence work. These are not reasons to discard the successful #152 verification; they are the specific obligations that must be resolved or explicitly accepted as qualifications before formal closeout.

1. **OPEN — `RW-PR-02`:** add or identify tests for the 8-proposal model limit, rejection of 9, and preservation of the Operator 64-proposal limit.
2. **PARTIAL — `RW-SER-01`:** add or identify a proposal-fingerprint golden vector covering canonical JSON bytes, UUID/enum serialization, array order, domain tag and SHA-256.
3. **PARTIAL — `RW-CTX-06` / `RW-REPLAY-01` / `RW-REC-01`:** complete the boundary-by-boundary Context identity and recovery-state map. Separate receipt-only, proposal-only, marker-present, empty, transient and permanent-integrity states.
4. **PARTIAL — `RW-ID-01` / `RW-PR-01` / `RW-PF-01`:** identify direct negative tests for forged authority fields, unknown fields, unsupported proposal shapes, invalid references and oversized proposal batches. Do not infer these from generic strict parsing.
6. **PARTIAL — `RW-RC-01`:** determine whether the accepted Operator concurrency test plus shared-core extraction is sufficient for the model-worker concurrency claim; otherwise keep the model-specific concurrency clause open.
7. **PARTIAL — `RW-LT-01`:** the positive accepted-evidence assertion is now identified in the Operator/shared-commit test. Keep the row qualified until a model-worker accepted-evidence integration case is identified or the shared-core evidence is explicitly accepted as sufficient.
8. **PARTIAL — `RW-CT-03` / `RW-WK-01`:** convert the source-inspection claims (no Team Experience retrieval; TaskDispatcher remains ingestion-only) into explicit tests if those claims are required as executable proofs.
9. **PARTIAL — `RW-REQ-01` / `RW-POL-01`:** retain host composition-root authentication and production TeamPolicy publisher serialization as explicitly unimplemented integration boundaries. Do not create fake production integrations to make the table green.

No production-code defect is asserted by this ledger. Any new test or implementation work must be separately scoped; this closeout remains documentation/evidence reconciliation unless an explicit corrective-test authorization is given. Formal Operator acceptance remains pending.

## 5. Cross-slice audit findings and unresolved proof gaps

This section records source-level observations from the RW3.4 planning audit. It distinguishes implemented behavior from what has not yet been demonstrated.

### 5.1 Deadline and provider-timeout proof — implemented and verified

The accepted contract remains a 45-second absolute deadline measured from successful TaskRuntime admission, covering Context assembly, quoting, provider execution, parsing, and pre-commit work. A provider request is capped at 30 seconds and may not exceed remaining Task time. The existing 60-second interrupted-recovery threshold is unchanged.

The corrective implementation from component PRs #140, #144, #145, and #146 is included in consolidated PR [#152](https://github.com/abtn/Watch-Architecture-Rev2/pull/152), merged at `77388707c82aa8dbcf4a37d3f44cb14a0b914f60`. The integrated implementation captures paired durable UTC and monotonic admission anchors, applies the absolute deadline to provider transport and worker stages, bounds process-wide DNS resolver concurrency to two active workers, classifies provider timeout at or beyond the Task deadline as terminal, and prevents receipt-only recovery from materializing a late proposal or reinvoking the provider. A durable proposal Event created strictly before expiry remains recoverable without provider reinvocation.

The implementation was locally verified on exact code/test head `20cfc252d21bdecc6153c1d8daa8369e1f331ff2`; hosted CI passed on final PR head `7c7aa3a3c5fc98c4ccfab21900f327b9323ee61d` (run [#45018330304](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/45018330304)). The detailed test and cleanup evidence is in [docs/testing.md](../testing.md). The prior deadline proof gap is no longer open. This evidence does not itself constitute formal RW3.4 acceptance.

### 5.2 Cumulative generation-cost proof — implemented and verified

The Task contract remains a cumulative `$0.02` ceiling across at most three starts. Reconciled charges are counted by accounted cost; unresolved reservations are counted by reserved exposure. The exact `update_thread` operation is covered by the integrated worker proof, including a reconciled charge plus an unknown reservation, cumulative aggregation before another provider call, and no further provider call or business commit after exhaustion.

The test-only cumulative-cost proof from component PR #142 is included in consolidated PR #152. No production accounting rewrite or schema/migration change was required. The test uses a smaller test-only budget to exercise the otherwise unreachable exhaustion branch under the production three-start/$0.02 envelope; it does not alter the production contract.

The integrated stack was locally verified on exact code/test head `20cfc252d21bdecc6153c1d8daa8369e1f331ff2`; hosted CI passed on final PR head `7c7aa3a3c5fc98c4ccfab21900f327b9323ee61d` (run [#45018330304](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/45018330304)). See [docs/testing.md](../testing.md) for exact commands and results. The prior cumulative-cost proof gap is no longer open. This evidence does not itself constitute formal RW3.4 acceptance.

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
| 3. Resolve blockers | Completed in consolidated PR #152: deadline/recovery corrections, bounded DNS resolver concurrency, timeout classification, and cumulative-cost proof. Component PRs #140/#142/#144/#145/#146 were closed unmerged after consolidation. | Both previously identified proof gaps have implementation and exact-head verification evidence recorded in `docs/testing.md`; formal RW3.4 acceptance remains a separate Operator decision. |
| 4. Run focused integrated proofs | Completed on implementation head `20cfc252d21bdecc6153c1d8daa8369e1f331ff2`; the focused generation/runtime/update-thread selection passed 155 tests. | Focused result and exact tested SHA recorded in `docs/testing.md`. |
| 5. Run full verification | Completed on the same implementation head under CPython 3.12.12 with disposable PostgreSQL on port 55468; Alembic current/head matched `0019_rw1_world_memory`, Ruff and Mypy passed, and the full suite passed 1,213 tests (130 existing Alembic deprecation warnings). | Cleanup, environment restoration, exact HEAD, and clean-worktree evidence are recorded in `docs/testing.md`. |
| 6. Hosted verification and review | Hosted CI passed on implementation head `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` (run #45014525692) and final PR head `7c7aa3a3c5fc98c4ccfab21900f327b9323ee61d` (run #45018330304). The integrated technical audit found no merge-blocking defect; formal Operator disposition remains pending. | Both exact SHAs and CI runs are recorded in `docs/testing.md`; do not equate this audit or CI with formal acceptance. |
| 7. Reconcile and accept | Documentation reconciliation is prepared in this PR from current `main`; it records merged implementation/verification evidence and preserves the host-authentication, TeamPolicy-publisher, and live-provider limitations. | Docs-only PR CI/review remains pending. RW3.4 acceptance remains a separate explicit Operator decision and is not performed by this PR. |

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

Local verification has already passed on exact implementation head `20cfc252d21bdecc6153c1d8daa8369e1f331ff2`: 155 focused tests, 1,213 full-suite tests, Ruff, Mypy (42 source files), disposable PostgreSQL migration/current/single-head checks at `0019_rw1_world_memory`, cleanup, environment restoration, exact HEAD, and clean worktree. Hosted CI passed on final PR head `7c7aa3a3c5fc98c4ccfab21900f327b9323ee61d`. See `docs/testing.md`. If the code changes, rerun this contract against the new exact head; do not transfer prior results.

## 7. Documentation authority and deliverables

- `PLAN.md`: sole current status and authorization. It must record PR #152 as merged and verified while keeping formal RW3.4 acceptance pending until explicit Operator disposition.
- This document: detailed RW3.4 execution sequence, proof ledger structure, audit findings, and closeout gate.
- `docs/development/rw-implementation-plan.md`: slice order and proof IDs; link to this plan and map RW3.4 rows to their final test nodes.
- `docs/development/rw-3-design-and-acceptance.md`: normative protocol and failure semantics; do not duplicate mutable milestone status beyond a pointer to PLAN.
- `docs/tasks.md`: normative Task shape/write scope/budget; current implementation status only as a pointer.
- `docs/architecture.md`: concise implemented boundary and known host/provider limitations.
- `docs/testing.md`: exact tested SHA, test nodes, commands, counts, Alembic result, CI runs, cleanup, and acceptance record.
- `CHANGE_MAP.md`: links the RW3.4 plan and points current status to PLAN.

This documentation reconciliation records the merged and verified RW3.4 implementation stack and preserves the acceptance checklist. It does not mark RW3.4 formally accepted, authorize live providers, or change any later milestone gate.

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
