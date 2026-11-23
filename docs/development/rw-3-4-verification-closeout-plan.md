# RW3.4 — Integrated Verification and Closeout Plan

**Status:** RW3.4 implementation, deadline/cost behavior, recovery corrections, and proof follow-ups are merged through PR #169. PR #169 merge commit: `2190c6362b4884286d55d1d24d94c3e176969d72`; exact tested head: `02154e8a7070981ebd39efc7eb1fb3e40e18cbf6`. The 35-row ledger is **28 PASS / 7 PARTIAL / 0 OPEN** after closing `RW-WK-01` by bounded source audit. Formal RW3.4 Operator acceptance remains pending; live provider authorization remains closed.

**Planning baseline:** `main` at `2190c6362b4884286d55d1d24d94c3e176969d72` (2026-11-23), after merged PR #169.

**Milestone authority:** `PLAN.md` owns current status and authorization. This plan owns the RW3.4 closeout sequence and evidence checklist. The [RW-3 design and acceptance plan](rw-3-design-and-acceptance.md) remains normative for protocol and recovery semantics; [the implementation plan and proof matrix](rw-implementation-plan.md) remains normative for proof IDs; [Task specifications](../tasks.md) remain normative for Task shape, write scope, and budget; [testing records](../testing.md) own exact verification results.

## PR #169 — bounded recovery-proof follow-up (merged 2026-11-23)

- Six empty-result Context-tuple corruption cases cover `context_event_id`, `context_snapshot_ref`, and `context_content_hash` independently in the generation receipt and empty proposal Event.
- Four duplicate/future-attempt cases cover generation receipt and proposal Events.
- The full `TaskRuntime.recover_interrupted()` path is exercised; tests assert fail-closed terminalization, one terminal Outcome/Event, no business writes, no provider reinvocation, and repeated-recovery no-op.
- A bounded source audit closes `RW-WK-01` for the inspected tree: one TaskRuntime lifecycle authority, narrow adapters delegating to it, and TaskDispatcher limited to `ingest_source`.
- Hosted CI run [#45171335421](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/45171335421) passed on exact head `02154e8a7070981ebd39efc7eb1fb3e40e18cbf6` with 1,296 tests, fresh PostgreSQL migration/head checks, Ruff, Mypy, and patch-whitespace validation.
- Programmer-local Windows verification on that exact head passed Ruff, Mypy (42 files), 163 focused tests, 1,296 full-suite tests, and two independent disposable PostgreSQL migration/test phases. Both containers were removed; branch/HEAD and clean worktree checks passed. The script's final environment-restoration assertion failed. The original process-variable states were not captured independently, so exact restoration is not claimed.
- Residuals remain: full Context tuple/state cross-product, duplicate/future commit/rejection marker coverage, mismatched in-session attempts, and the external host-authentication/TeamPolicy-publisher boundaries. Ledger: **28 PASS / 7 PARTIAL / 0 OPEN**. This merge does not constitute formal RW3.4 Operator acceptance.

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

The ledger below contains 35 RW-3 proof rows. The merged #165/#167 evidence baseline had **27 PASS, 8 PARTIAL, and 0 OPEN**. This follow-up closes `RW-WK-01` by bounded source audit, yielding **28 PASS, 7 PARTIAL, and 0 OPEN**; it also adds six Context-tuple plus four duplicate/future receipt/proposal cases without claiming to close `RW-CTX-06`. Exact follow-up test SHA and hosted verification are recorded in `docs/testing.md`. PASS/PARTIAL are evidence classifications only; they do not replace the explicit Operator acceptance gate.

For each row, record the exact test node(s), exact tested SHA, and outcome. A row with only design text, a generic unit test, or an earlier-slice CI result is not closed evidence.


### 4.5 Integrated proof ledger — evidence mapping against the verified tree

**Ledger baseline:** current `main` is `2190c6362b4884286d55d1d24d94c3e176969d72` (PR #169 merge). The integrated implementation baseline is PR #163 merge `6cbef27cd4fb39b1d1c860de8bf419046f35d5ae`; supplemental test-only PR #165 and committed-recovery correction PR #167 remain part of the predecessor evidence. PR #169 exact head `02154e8a7070981ebd39efc7eb1fb3e40e18cbf6` passed hosted CI #45171335421 with 1,296 tests and Programmer-local verification (163 focused; 1,296 full; Ruff; Mypy; disposable PostgreSQL). The local environment-restoration assertion failed, so exact restoration is not claimed. The earlier 1,213-test result remains tied to `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` and is not substituted for later evidence. Each row retains the exact SHA for the tests/source evidence it cites.

- Tests: `tests/test_update_thread.py` (`d9b6027ec097adcf0a5937fd9df065cc65026bcc`), `tests/test_task_runtime.py` (`f5a5302038d6254360cb39f66fb80196ddec09ed`), `tests/test_generation.py` (`0887687414372ca322128960b1954e05667229b6`), `tests/test_generation_cost.py` (`c76e2f2b830a58583ffefaa1cc60640f6b20b9ca`), `tests/test_world_memory.py` (`cf1478df54019cbe3cf84ef216d04074470fe780`), `tests/test_operator_application.py` (`f5003f00212feb78ff5c60f9ec8e7f09a07e1fa7`), and `tests/test_r6b_dispatcher.py` (`40b693843c75cf68d9ad8096079b7432401d988d`).
- Relevant implementation: `core/update_thread.py` (`9958bdf6dbb68cd1c378ab440545326c487b1706`), `core/update_thread_context.py` (`30075dba186b3cab2a412713b30641249b389438`), `core/update_thread_worker.py` (`e24b58959c9e93155a05d19e45aafcc6ffd539b0`), and `core/task_runtime.py` (`c19c1d6e87137441306cdb454f7ca304297d75d3`).

Each row records the exact tree on which its cited test evidence was verified. The original integrated implementation baseline `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` was locally verified with 155 focused tests and 1,213 full-suite tests. The supplemental test-only evidence uses PR #155 tested head `fe757872774191af0f171656acceb945fafc0ee9` and its hosted 1,246-test CI run. A listed test node is evidence that the named test passed as part of that full-suite run; it is not a claim that the test alone proves every clause in a compound proof ID.

**Status meanings:** **PASS** means the identified tests directly exercise the stated obligation at the verified SHA. **PARTIAL** means some clauses are demonstrated but at least one clause lacks direct test evidence or is an explicitly absent integration. **OPEN** means no adequate test node was identified. **NOT IMPLEMENTED** is reserved for an intentionally absent integration, not an accidental test omission. These are evidence statuses, not formal RW3.4 acceptance. Within each table row, subsequent unqualified `test_...` names refer to the same test file as the most recently named fully qualified path; a new `tests/...` path starts a new file context. This shorthand does not change the exact pytest node identity.

| Proof ID | Exact test nodes / source evidence | Tested SHA | Status | Remaining qualification or missing proof |
|---|---|---|---|---|
| `RW-REQ-01` | `tests/test_update_thread.py::test_host_creator_pins_policy_and_replays_without_execution`; `test_creator_rejects_wrong_action_without_task_or_event`; `test_creator_rejects_missing_or_malformed_principal_without_task_or_event`; `test_creator_rejects_wrong_team_grant_without_task_or_event`; `test_creator_rejects_cross_team_thread_without_task_or_event`; `test_creator_rejects_inactive_team_without_task_or_event`; `test_creator_rejects_resolved_thread_without_task_or_event`; `test_same_key_replay_by_another_operator_conflicts`; `test_request_identity_and_fingerprint_golden_vector`; `test_concurrent_same_key_creation_writes_one_request_event` | `fe757872774191af0f171656acceb945fafc0ee9` | **PARTIAL** | Watch-side Task creation now has direct negative coverage for principal shape, Team grant, cross-Team Thread, inactive Team, and resolved Thread. Production host authentication remains **NOT IMPLEMENTED / NOT PROVEN** because no production composition root exists. |
| `RW-CT-01` | `tests/test_update_thread.py::test_context_is_deterministic_bounded_and_replayable`; `test_context_fails_closed_when_active_hypothesis_bound_is_exceeded`; `test_context_fails_closed_when_evidence_link_bound_is_exceeded`; `test_context_fails_closed_when_evidence_character_bound_is_exceeded`; `test_context_rejects_quote_offsets_outside_source_snapshot`; `test_context_rejects_evidence_signal_from_another_team_domain` | `a256a7da8682747581e44cc9381bba4646c822da` | **PASS** | The Context assembler rejects a linked Signal whose domain differs from the target Team before a Context Event is persisted. |
| `RW-CT-02` | `tests/test_update_thread.py::test_context_is_deterministic_bounded_and_replayable`; `test_context_replay_rejects_boolean_substitution_for_integer_fields`; `test_context_fails_closed_when_active_hypothesis_bound_is_exceeded`; `test_context_fails_closed_when_evidence_link_bound_is_exceeded`; `test_context_fails_closed_when_evidence_character_bound_is_exceeded` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | Equal-time ordering, deterministic replay, integer-type tampering, and the configured Context bounds are directly exercised. |
| `RW-CT-03` | `tests/test_update_thread.py::test_update_thread_context_schema_excludes_team_experience_projection`; `test_update_thread_worker_never_invokes_team_experience_retrieval` | `a256a7da8682747581e44cc9381bba4646c822da` | **PASS** | The `update_thread` worker test traps any `HybridKnowledgeRetriever.retrieve` call, asserts zero calls, and checks that the persisted Context Snapshot contains no Team Experience passage fields. This PASS is scoped to the RW-3 worker path. |
| `RW-CTX-04` | `tests/test_update_thread.py::test_context_is_deterministic_bounded_and_replayable`; `test_host_creator_pins_policy_and_replays_without_execution`; `test_replay_keeps_original_policy_after_policy_advancement`; `test_context_uses_task_pinned_policy_after_policy_advancement` | `a3e1d15b4ea4a7954e3b3b01d2852af80351eb45` | **PASS** | Context assembly is directly shown to use the Task-pinned policy v1 after TeamPolicy v2 exists, while preserving the expected target-Thread active Hypothesis and EvidenceLink membership. Publisher selection/lock-order integration is a separate `RW-POL-01` qualification.
| `RW-CTX-05` | `tests/test_update_thread.py::test_context_is_reloaded_from_its_verified_snapshot_before_provider_use`; `test_update_thread_worker_never_calls_provider_for_boolean_context_fields`; `test_update_thread_worker_never_calls_provider_for_invalid_context`; `test_task_runtime_admission_rejects_tampered_update_thread_request` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | The invalid-context parametrization includes Boolean manifest tampering, Snapshot hash mismatch, duplicate Context Events, and future-attempt substitution; provider call count is asserted zero. |
| `RW-CTX-06` | `tests/test_update_thread.py::test_update_thread_worker_records_context_identity_and_empty_proposal_set`; `test_committed_marker_context_substitution_fails_closed_without_reapplying`; `test_empty_proposal_recovery_finalizes_success_no_change`; `test_empty_proposal_recovery_context_substitution_fails_closed` (six receipt/proposal-event tuple substitutions) | Follow-up PR head (see `docs/testing.md`) | **PARTIAL** | PR #167 covers all three tuple fields on the committed-marker path. This follow-up adds all three tuple-field substitutions in both the generation receipt and empty proposal Event (six cases) through full `TaskRuntime.recover_interrupted()`. Each case proves fail-closed terminalization, one Outcome/Event, no business writes, no provider reinvocation, and repeated-recovery no-op. The broader tuple/state cross-product remains intentionally unenumerated. |
| `RW-REPLAY-01` | `tests/test_update_thread.py::test_update_thread_worker_receipt_and_charge_reconciliation_are_atomic`; `test_interrupted_provider_call_marks_reserved_charge_unknown_before_retry`; `test_transient_model_commit_failure_rolls_back_and_recovers_same_proposals`; `test_marker_recovery_reconstructs_terminal_result_without_reapplying`; `test_empty_proposal_recovery_finalizes_success_no_change`; `test_empty_proposal_recovery_context_substitution_fails_closed`; `test_empty_result_recovery_rejects_duplicate_or_future_attempt_evidence` (duplicate/current and future-attempt receipt/proposal Events) | Follow-up PR head (see `docs/testing.md`) | **PARTIAL** | Receipt/charge atomicity, no-receipt, transient, marker-present, empty-result, Context-tuple corruption, duplicate current-attempt receipt/proposal Event, and future-attempt receipt/proposal Event paths have direct coverage. Duplicate/future commit/rejection markers, all crash windows, and duplicate write outcomes are not exhaustively enumerated; this residual is retained rather than expanding to a Cartesian matrix. |
| `RW-SER-01` | `tests/test_update_thread.py::test_model_proposal_fingerprint_has_canonical_golden_vector`; `test_model_proposal_fingerprint_preserves_proposal_array_order`; source validation in `core/update_thread_worker.py` and `core/task_runtime.py` | `fe757872774191af0f171656acceb945fafc0ee9` | **PASS** | The proposal fingerprint now has a fixed canonical SHA-256 golden vector and an explicit array-order preservation test. This is distinct from the pre-existing request-fingerprint vector. |
| `RW-LC-01` | `tests/test_task_runtime.py::test_admission_captures_monotonic_timestamp_used_by_worker`; `test_daily_quota_query_preserves_paired_admission_deadline`; `test_retry_requires_runtime_redelivery_not_second_claim`; `tests/test_update_thread.py::test_task_runtime_admission_rejects_tampered_update_thread_request`; `test_retryable_provider_interruption_schedules_task_retry`; `test_update_thread_worker_never_calls_provider_for_invalid_context` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | Admission ownership, monotonic anchor, admission-before-worker validation, and retry ownership have direct test coverage. |
| `RW-RT-01` | `tests/test_update_thread.py::test_update_thread_worker_records_context_identity_and_empty_proposal_set`; `test_update_thread_worker_commits_typed_proposal_with_model_actor`; `test_update_thread_committed_result_is_rejected_for_other_task_types` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | Both accepted success categories and rejection of the committed category for other Task types are exercised. |
| `RW-RT-02` | `tests/test_update_thread.py::test_update_thread_worker_records_context_identity_and_empty_proposal_set`; `test_empty_proposal_recovery_finalizes_success_no_change`; `test_update_thread_model_commit_partitions_proposals_exhaustively`; `test_interrupted_provider_call_marks_reserved_charge_unknown_before_retry`; `test_transient_model_commit_failure_rolls_back_and_recovers_same_proposals`; `test_marker_recovery_reconstructs_terminal_result_without_reapplying`; `test_committed_marker_context_substitution_fails_closed_without_reapplying`; `test_empty_proposal_recovery_context_substitution_fails_closed`; `test_empty_result_recovery_rejects_duplicate_or_future_attempt_evidence`; `test_update_thread_worker_does_not_materialize_receipt_only_recovery_after_deadline`; `test_proposal_only_recovery_fails_closed_without_business_writes`; `test_malformed_receipt_without_inconsistency_marker_blocks_finalization` | Follow-up PR head (see `docs/testing.md`) | **PARTIAL** | Empty, no-receipt/interrupted, committed, all-invalid, proposal-only, marker-present, receipt-only-after-deadline, Context-tuple corruption, duplicate receipt/proposal Event, and future-attempt receipt/proposal Event outcomes have direct coverage. Duplicate/future commit/rejection marker and full locked Session/Task/attempt variants remain residual. |
| `RW-REC-01` | `tests/test_update_thread.py::test_transient_model_commit_failure_rolls_back_and_recovers_same_proposals`; `test_marker_recovery_reconstructs_terminal_result_without_reapplying`; `test_committed_marker_context_substitution_fails_closed_without_reapplying`; `test_permanent_provenance_conflict_records_inconsistent_without_writes`; `test_missing_request_provenance_terminalizes_as_recovery_inconsistent`; `test_empty_proposal_recovery_finalizes_success_no_change`; `test_empty_proposal_recovery_context_substitution_fails_closed`; `test_empty_result_recovery_rejects_duplicate_or_future_attempt_evidence`; `test_interrupted_provider_call_marks_reserved_charge_unknown_before_retry`; `test_update_thread_worker_does_not_materialize_receipt_only_recovery_after_deadline`; `test_proposal_only_recovery_fails_closed_without_business_writes`; `test_malformed_receipt_without_inconsistency_marker_blocks_finalization` | Follow-up PR head (see `docs/testing.md`) | **PARTIAL** | Empty, no-receipt, transient, marker-present, marker-tampered, proposal-only, receipt-only-after-deadline, malformed-receipt, duplicate receipt/proposal Event, and future-attempt receipt/proposal Event paths have direct coverage. The full locked Session/Task/attempt matrix and duplicate/future marker variants remain incomplete. |
| `RW-CF-01` | `tests/test_update_thread.py::test_transient_model_commit_failure_rolls_back_and_recovers_same_proposals`; `test_update_thread_model_commit_partitions_proposals_exhaustively`; `test_permanent_provenance_conflict_records_inconsistent_without_writes`; `test_model_commit_savepoint_rolls_back_staged_writes_before_inconsistent_marker` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | Same-proposal transient recovery, exhaustive accepted/rejected partitioning, and rollback-before-inconsistent-marker behavior are directly exercised. |
| `RW-ACT-01` | `tests/test_update_thread.py::test_model_output_cannot_supply_actor_identity`; `test_update_thread_worker_commits_typed_proposal_with_model_actor`; `tests/test_world_memory.py::test_host_grant_is_team_and_action_scoped`; `tests/test_operator_application.py::test_host_grant_must_match_the_proposal_team_and_exact_action` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | Model actor attribution and rejection of model-supplied actor identity are tested alongside the unchanged Operator grant path. |
| `RW-ACT-02` | `tests/test_update_thread.py::test_update_thread_worker_commits_typed_proposal_with_model_actor`; `test_model_proposal_disposition_event_rejects_boolean_integer_substitution`; `test_update_thread_committed_result_is_rejected_for_other_task_types`; `test_model_marker_validator_rejects_operator_event_family`; `tests/test_world_memory.py::test_operator_terminal_validator_rejects_model_event_family`; Operator regression nodes in `tests/test_world_memory.py` and `tests/test_operator_application.py` | `a256a7da8682747581e44cc9381bba4646c822da` | **PASS** | Both directions are now directly proven: model terminal validation rejects Operator marker Events, and Operator terminal validation rejects model marker Events. |
| `RW-AT-01` | `tests/test_update_thread.py::test_update_thread_model_commit_partitions_proposals_exhaustively`; `test_model_commit_savepoint_rolls_back_staged_writes_before_inconsistent_marker`; `tests/test_world_memory.py::test_database_failure_rolls_back_the_entire_valid_proposal_set`; `test_all_invalid_proposals_fail_task_and_write_no_business_state` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | Mixed/all-invalid model batches and rollback of staged writes are directly covered; the accepted Operator path retains its atomicity regression proof. |
| `RW-RP-01` | `tests/test_update_thread.py::test_marker_recovery_reconstructs_terminal_result_without_reapplying`; `test_transient_model_commit_failure_rolls_back_and_recovers_same_proposals` (repeated recovery assertion); `test_empty_proposal_recovery_finalizes_success_no_change` (second recovery no-op); `test_empty_proposal_recovery_context_substitution_fails_closed`; `test_empty_result_recovery_rejects_duplicate_or_future_attempt_evidence`; `tests/test_world_memory.py::test_reusing_idempotency_key_with_different_request_is_rejected`; `test_committed_operator_update_is_recovered_without_replaying_writes` | Follow-up PR head (see `docs/testing.md`) | **PARTIAL** | Repeated recovery, Context corruption, duplicate current-attempt receipt/proposal Events, and future-attempt receipt/proposal Events are directly tested without reapplying business writes. Duplicate/future marker variants and duplicate write outcomes across every replay state remain unenumerated. |
| `RW-RC-01` | `tests/test_world_memory.py::test_concurrent_operator_updates_serialize_competing_transitions`; `tests/test_update_thread.py::test_concurrent_same_key_creation_writes_one_request_event`; `test_model_workers_serialize_concurrent_commits_for_same_thread` | `fe757872774191af0f171656acceb945fafc0ee9` | **PASS** | The model-worker-specific same-Thread concurrency gap is now directly exercised: two workers are forced to the commit boundary concurrently and both independent commits must survive. |
| `RW-LT-01` | `tests/test_world_memory.py::test_operator_update_creates_low_hypothesis_and_verified_evidence`; `test_mentions_rejections_and_replay_do_not_touch_hypothesis`; `test_accepted_evidence_touches_preexisting_hypothesis_at_commit_time`; `tests/test_update_thread.py::test_model_worker_accepted_evidence_touches_preexisting_hypothesis_at_commit_time`; shared `touched_hypothesis_ids` update in `core/world_memory.py` | `a256a7da8682747581e44cc9381bba4646c822da` | **PASS** | Both the Operator and model-worker commit paths directly prove that accepted evidence advances a pre-existing Hypothesis to the commit marker timestamp. The existing rejected/mention/replay non-touch regression is directly mapped to the Operator path; #163 does not add separate model-worker non-touch variants. |
| `RW-TS-02` | `tests/test_update_thread.py::test_host_creator_pins_policy_and_replays_without_execution`; `test_task_request_rejects_budget_integer_type_substitution`; `test_update_thread_task_contract_keeps_two_cent_budget_and_three_starts`; `test_task_runtime_admission_rejects_tampered_update_thread_request` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | Task creation, immutable shape, exact budget, attempt limits, write scope and tampered-request admission are covered by the named tests. |
| `RW-POL-01` | `tests/test_update_thread.py::test_host_creator_pins_policy_and_replays_without_execution`; `test_replay_keeps_original_policy_after_policy_advancement`; `test_concurrent_same_key_creation_writes_one_request_event` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PARTIAL** | Creator-side selection, pinning, replay and Task-creation arbitration are covered. The production publisher and both real Task-creation/publisher lock orders remain unproven because no publisher exists. |
| `RW-GC-01` | `tests/test_generation_cost.py::test_reservation_is_persisted_before_reconciliation_and_settled_from_usage`; `test_budget_exhaustion_writes_no_charge_or_reservation_event`; `test_concurrent_same_attempt_reservations_commit_exactly_once`; `tests/test_update_thread.py::test_update_thread_worker_counts_reconciled_and_unknown_charges_before_next_call` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | The integrated `update_thread` worker test exhausts cumulative Task budget on its third start: the third reservation raises `task_generation_budget_exhausted`, `provider.calls` remains exactly 2, and no third provider invocation or business write occurs. This directly proves reservation denial precedes provider invocation for the operation. The cost-service tests additionally cover durable reservation, denial without charge/Event, and same-attempt reservation arbitration. |
| `RW-GC-02` | `tests/test_generation_cost.py::test_unknown_usage_keeps_full_reservation_and_blocks_same_attempt_replay`; `test_usage_above_reserved_bounds_is_recorded_as_an_overrun`; `test_generation_charge_is_reconciled_idempotently`; `test_reconciliation_event_failure_keeps_reservation_and_can_be_marked_unknown`; `tests/test_update_thread.py::test_update_thread_worker_persists_valid_usage_before_parser_failure`; `test_update_thread_worker_receipt_and_charge_reconciliation_are_atomic` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | Unknown, overrun, idempotent reconciliation, reconciliation failure, usage-before-parser-failure and receipt/charge atomicity have direct test coverage. |
| `RW-GC-03` | `tests/test_generation.py::test_three_maximum_update_thread_reservations_fit_task_cost_ceiling`; `tests/test_update_thread.py::test_update_thread_task_contract_keeps_two_cent_budget_and_three_starts`; `test_update_thread_worker_counts_reconciled_and_unknown_charges_before_next_call`; `test_update_thread_worker_terminalizes_generation_cost_overrun_without_writes` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | Production three-start/$0.02 arithmetic, cumulative reconciled-plus-unknown exposure, and terminal overrun without business writes are covered. The smaller exhaustion budget is explicitly test-only. |
| `RW-GN-01` | `tests/test_generation.py::test_generation_posts_once_and_returns_validated_json_and_usage`; `test_generation_fails_when_usage_is_missing`; `test_generation_fails_closed_when_provider_returns_a_different_model`; `test_configuration_rejects_non_cloudflare_or_unsafe_base_urls`; `test_configuration_rejects_output_limit_above_initial_cap`; `test_initial_provider_rejects_a_model_without_a_pinned_price_card`; `tests/test_generation_cost.py::test_untrusted_quote_cannot_lower_the_selected_model_price_card`; `test_generation_operations_reject_task_type_and_write_scope_mismatches` (seven mismatch cases) | `a256a7da8682747581e44cc9381bba4646c822da` | **PASS** | Provider/model/rate-card/usage rules and direct negative operation-to-Task-type/write-scope mismatch coverage are mapped for strategy, distillation, and update-thread operations. |
| `RW-GN-02` | `tests/test_update_thread.py::test_update_thread_worker_rejects_live_provider_until_separately_authorized`; deterministic fake-provider use across the RW-3 worker tests | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | The live-provider gate is directly tested; the recorded verification used deterministic fakes only. |
| `RW-DL-01` | `tests/test_task_runtime.py::test_admission_captures_monotonic_timestamp_used_by_worker`; `test_daily_quota_query_preserves_paired_admission_deadline`; `tests/test_generation.py::test_absolute_generation_deadline_bounds_slow_dns_resolution`; `test_repeated_stalled_dns_resolution_is_process_bounded`; `test_absolute_generation_deadline_interrupts_tcp_and_tls`; `test_absolute_deadline_rejects_send_after_expiry`; `test_absolute_deadline_closes_socket_during_response_read`; `test_provider_uses_earliest_absolute_or_relative_deadline`; `tests/test_update_thread.py::test_provider_timeout_at_task_deadline_is_terminal_and_keeps_charge_unknown`; `test_update_thread_worker_caps_provider_timeout_at_thirty_seconds`; `test_update_thread_worker_provider_timeout_is_capped_by_remaining_deadline`; `test_update_thread_worker_does_not_invoke_provider_after_deadline`; `test_update_thread_worker_discards_provider_result_returned_after_deadline`; `test_update_thread_worker_checks_deadline_after_parsing`; `test_update_thread_worker_rechecks_deadline_after_commit_lock`; `test_update_thread_worker_rechecks_deadline_during_proposal_persistence`; `test_update_thread_recovery_rejects_proposal_event_persisted_at_or_after_deadline` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | Admission anchoring, DNS/socket deadline enforcement, 30-second and remaining-time caps, late provider results, pre-commit checks and recovery expiry are directly exercised. The existing 60-second recovery threshold remains unchanged. |
| `RW-PR-01` | `tests/test_generation.py::test_generation_rejects_non_json_completion`; `tests/test_update_thread.py::test_model_response_rejects_duplicate_json_object_keys`; `test_model_response_rejects_nonstandard_json_constants`; `test_model_response_rejects_unknown_top_level_fields`; `test_model_proposal_rejects_forged_authority_fields`; `test_model_response_rejects_unsupported_shapes_and_invalid_references`; `test_update_thread_worker_persists_valid_usage_before_parser_failure` (expanded worker-to-TaskRuntime matrix); `test_model_proposal_count_accepts_eight_and_rejects_nine`; `test_update_thread_worker_terminalizes_generation_cost_overrun_without_writes`; `test_update_thread_model_commit_partitions_proposals_exhaustively` | `a3e1d15b4ea4a7954e3b3b01d2852af80351eb45` | **PASS** | The integration matrix exercises malformed/duplicate/non-standard JSON, unknown and forged fields, invalid UUID/source reference, unsupported proposal kind, and excessive proposal count through worker/TaskRuntime with no proposal or business writes. The existing 8/9 boundary and 129/128-token overrun test establish the configured bounds. The required error categories are directly covered; exhaustive cross-combinations are not a requirement.
| `RW-PV-01` | `tests/test_update_thread.py::test_retryable_provider_interruption_schedules_task_retry`; `test_interrupted_provider_call_marks_reserved_charge_unknown_before_retry`; `test_provider_timeout_at_task_deadline_is_terminal_and_keeps_charge_unknown`; `tests/test_generation.py::test_incomplete_http_response_is_a_retryable_provider_failure`; `test_http_errors_are_categorized_without_retrying` | `20cfc252d21bdecc6153c1d8daa8369e1f331ff2` | **PASS** | Retry ownership, interruption, unknown charge, terminal deadline timeout, incomplete transport and no adapter-level HTTP retry are covered. |
| `RW-PR-02` | `tests/test_update_thread.py::test_model_proposal_count_accepts_eight_and_rejects_nine`; `test_operator_update_proposal_count_remains_sixty_four`; parser contract in `core/update_thread_worker.py` | `fe757872774191af0f171656acceb945fafc0ee9` | **PASS** | The model parser now has explicit 8-accepted/9-rejected boundary coverage, and the independent Operator 64-proposal contract is preserved by its own test. |
| `RW-NO-01` | `tests/test_update_thread.py::test_update_thread_worker_records_context_identity_and_empty_proposal_set`; `test_empty_proposal_recovery_finalizes_success_no_change` | `a3e1d15b4ea4a7954e3b3b01d2852af80351eb45` | **PASS** | Empty proposal sets are persisted and reconciled, then recovered as `success_no_change` with one receipt Event, one proposal Event, no commit/business writes, one provider invocation, and a second recovery no-op.
| `RW-PF-01` | `tests/test_update_thread.py::test_update_thread_worker_persists_valid_usage_before_parser_failure` (expanded parser-error integration matrix); `test_model_response_rejects_duplicate_json_object_keys`; `test_model_response_rejects_nonstandard_json_constants`; `test_model_response_rejects_unknown_top_level_fields`; `test_model_proposal_rejects_forged_authority_fields`; `test_model_response_rejects_unsupported_shapes_and_invalid_references`; `test_update_thread_model_commit_partitions_proposals_exhaustively`; `tests/test_generation.py::test_generation_rejects_non_json_completion` | `a3e1d15b4ea4a7954e3b3b01d2852af80351eb45` | **PASS** | Parser errors now terminalize through the worker/TaskRuntime path with a reconciled charge and no per-proposal accepted/rejected or business Events. The typed proposal partition test separately proves that domain-invalid proposals receive proposal rejection dispositions, including all-invalid and mixed batches.
| `RW-ID-01` | `tests/test_update_thread.py::test_model_output_cannot_supply_actor_identity`; `test_model_proposal_rejects_forged_authority_fields` (parameterized forged actor, Task, Team, Thread, policy, budget, charge, write-scope, and authority fields); `test_update_thread_worker_commits_typed_proposal_with_model_actor` | `fe757872774191af0f171656acceb945fafc0ee9` | **PASS** | The strict model proposal boundary now has direct negative coverage for the enumerated forged authority and identity fields, alongside application-attributed model commit Events. |
| `RW-WK-01` | Source audit of `core/task_runtime.py`, `core/dispatcher.py`, `core/update_thread_worker.py`, `core/evaluation_tasks.py`, `core/knowledge_quality_tasks.py`, `core/knowledge_lifecycle_tasks.py`, `core/knowledge_revalidation_tasks.py`, and `core/operator_application.py` | `b00c6df93f224bca03168b7894ec3e154b2293ec` | **PASS** | One `TaskRuntime` implementation owns lifecycle status/attempt transitions, admission, finalization, failure reporting, and interrupted recovery. The listed workers/adapters delegate lifecycle operations to it; `TaskDispatcher` dispatches only `ingest_source`. No second scheduler or lifecycle implementation was found in the inspected repository source. This is a bounded current-tree source audit, not a guarantee against future additions. |

### 4.6 Consolidated gaps requiring disposition

The merged #165/#167 evidence baseline had eight PARTIAL rows. This follow-up closes `RW-WK-01` by source audit and adds six Context-tuple plus four duplicate/future receipt/proposal cases; seven PARTIAL rows remain. The remaining qualifications are intentionally not conflated.

1. **RESOLVED — `RW-CT-01`:** #163 adds a Context-assembler test for a linked Signal whose domain differs from the target Team. The assembler fails before writing a Context Event.
2. **RESOLVED — `RW-CT-03`:** #163 traps `HybridKnowledgeRetriever.retrieve` and proves the `update_thread` worker never calls it; the persisted Context Snapshot also contains no Team Experience passage fields. This is scoped to the RW-3 worker path.
3. **RESOLVED — `RW-ACT-02`:** #163 adds both directions of marker-family isolation: the model validator rejects an Operator marker and the Operator validator rejects a model marker.
4. **RESOLVED — `RW-LT-01`:** #163 adds a model-worker end-to-end accepted-EvidenceLink case proving a pre-existing Hypothesis is touched at the commit marker timestamp. The Operator route and negative non-touch cases remain covered.
5. **RESOLVED — `RW-GN-01`:** #163 adds seven generation-cost mismatch cases covering operation/Task-type and write-scope violations across strategy, distillation, and update-thread operations.
6. **RESOLVED — `RW-CTX-04`:** #165 adds `test_context_uses_task_pinned_policy_after_policy_advancement`. It creates a Task pinned to policy v1, adds policy v2, and assembles Context. The persisted Context still contains policy v1 and the target Thread's expected active Hypothesis/EvidenceLink membership. Publisher concurrency remains separately qualified under `RW-POL-01`.
7. **RESOLVED — `RW-PR-01`:** #165 extends the worker-to-TaskRuntime parser-failure test over malformed JSON, duplicate keys, NaN, unknown/forged fields, invalid UUID/source reference, unsupported proposal kind, and nine proposals. It asserts terminal parser failure, reconciled charge, and no proposal/disposition/business writes. Existing tests cover the eight-proposal boundary and output-token overrun (129 observed against the 128-token cap).
8. **RESOLVED — `RW-PF-01`:** The same integration matrix proves parser errors do not produce per-proposal rejection Events. `test_update_thread_model_commit_partitions_proposals_exhaustively` separately proves typed domain-invalid proposals do produce rejection dispositions, including all-invalid and mixed outcomes.
9. **PARTIAL — `RW-CTX-06`:** PR #167 covers all three Context tuple fields on the committed-marker path. This follow-up adds `test_empty_proposal_recovery_context_substitution_fails_closed`, parameterized across all three tuple fields in both the generation receipt and empty proposal Event (six cases). Each case drives full `TaskRuntime.recover_interrupted()` and proves fail-closed terminalization, one Outcome/Event, no business writes, no provider reinvocation, and repeated-recovery no-op. The broader tuple/state cross-product across commit/rejection/other recovery states remains intentionally unenumerated.
10. **PARTIAL — `RW-REPLAY-01` / `RW-RP-01`:** Existing tests cover receipt/charge atomicity, no-receipt interruption, transient commit recovery, marker-present recovery, and empty-result recovery. PR #167 proves committed-marker Context corruption through TaskRuntime finalization without replay; this follow-up strengthens empty-result Context integrity. Duplicate/future-attempt Event evidence and every replay/crash-state combination are not exhaustively enumerated; that residual qualification remains explicit rather than prompting a Cartesian test matrix.
11. **PARTIAL — `RW-RT-02` / `RW-REC-01`:** Existing coverage includes no-receipt interruption, receipt-only after deadline, proposal-only, marker-present, transient commit, empty-result, malformed-receipt failure, and #167 full TaskRuntime committed-marker recovery. The `update_thread` operation deadline is 45 seconds while normal `TaskRuntime.recover_interrupted()` considers a running Task stale only after more than 60 seconds. Receipt-only-before-deadline is therefore unreachable through normal recovery; the tested after-deadline behavior correctly fails terminally without materializing proposals. Earlier recovery would require a new safe lease/ownership synchronization mechanism, not a test-only seam. Duplicate/cross-attempt evidence and the full locked Session/Task/attempt matrix remain residual qualifications.
12. **RESOLVED — `RW-WK-01`:** The bounded source audit records one lifecycle authority (`TaskRuntime`) and distinguishes it from multiple narrow adapters. `TaskDispatcher` supports only configured-source `ingest_source`; the update-thread worker, evaluation runner, knowledge-quality/lifecycle/revalidation runners, and Operator adapter delegate lifecycle operations to `TaskRuntime`. No second scheduler or lifecycle implementation was found in the inspected source tree. This is a current-tree source-inspection result, not a promise about future code.
13. **UNIMPLEMENTED INTEGRATION BOUNDARIES — `RW-REQ-01` / `RW-POL-01`:** Production host composition-root authentication and the production TeamPolicy publisher/lock-order serialization remain absent. Watch-side principal/grant tests and Context policy-pin tests do not prove these integrations. Do not fabricate production integrations or relabel these qualifications as test gaps.

The ledger records the production recovery corrections in #163 and #167 and the test-only follow-up in #165. No additional production-code defect is asserted by the remaining proof qualifications. Formal RW3.4 Operator acceptance remains pending.

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
| 0. Freeze baseline | Start from `main` at `2190c6362b4884286d55d1d24d94c3e176969d72` (PR #169 merge). Record repo, branch, HEAD, clean worktree, origin, Python/uv versions, and current Alembic head. No reset/stash or destructive cleanup. | Current exact merge baseline and evidence-tree SHAs are recorded in this plan and `docs/testing.md`. |
| 1. Build the evidence ledger | Map all RW3.1–RW3.4 proof rows to exact current test nodes, source locations, and exact tested SHAs. Separate source inspection, focused tests, local full verification, and hosted CI evidence. | The 35-row ledger is 28 PASS, 7 PARTIAL, 0 OPEN after the bounded source audit; six Context-tuple plus four duplicate/future receipt/proposal cases strengthen `RW-CTX-06` without closing it. Remaining qualifications are itemized in §4.6; formal Operator acceptance remains pending. |
| 2. Audit integration seams | Inspect the Task creator → TaskRuntime admission → Context verifier → cost reservation → generation adapter → receipt/proposal persistence → shared commit core → TaskRuntime finalization/recovery path. Check the exact Context tuple at every handoff. Recheck RW-2 Operator compatibility. | Reviewed sequence diagram or concise call-path record; no guessed identity substitution or parallel authority path. |
| 3. Resolve blockers | PR #152 delivered deadline/recovery, bounded DNS resolver, timeout, and cumulative-cost corrections. PR #163 added recovery-finalization ordering correction and proof packets from #157–#162. PR #167 corrected post-commit inconsistent-recovery finalization and expanded its regression through TaskRuntime recovery. | All implementation corrections are merged; source PRs #157–#162 are closed as superseded with branches preserved. No further production-code scope is inferred. |
| 4. Run focused integrated proofs | The pre-#163 integrated implementation had 155 focused tests on `20cfc252d21bdecc6153c1d8daa8369e1f331ff2`. #165 added parser/recovery/Context proofs; #167 expanded committed-marker Context corruption through full TaskRuntime recovery. | Exact #167 head `d2139c41ec3450f7198e61bdd1169edbeff13e01` and its hosted/local evidence are recorded in `docs/testing.md`. |
| 5. Run full verification | Hosted CI on #163 exact head `a256a7da8682747581e44cc9381bba4646c822da` passed 1,274 tests. PR #167 exact head `d2139c41ec3450f7198e61bdd1169edbeff13e01` passed 1,286 tests, fresh PostgreSQL migration/head checks, Ruff, Mypy, and `git diff --check`. | Programmer-local Windows verification on the exact #167 head passed 153 focused tests, 1,286 full-suite tests, disposable PostgreSQL migration/current/single-head checks, Ruff, Mypy, and `git diff --check`; see `docs/testing.md`. |
| 6. Hosted verification and review | Hosted CI [run #45147241723](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/45147241723) passed on #167 PR head `d2139c41ec3450f7198e61bdd1169edbeff13e01`; the earlier #163 and #165 exact-head runs remain historical evidence. | The final exact-head CI evidence is recorded in `docs/testing.md`; formal Operator disposition remains pending. |
| 7. Reconcile and accept | The bounded test/source-audit follow-up updates proof mapping and testing evidence against main baseline `2190c6362b4884286d55d1d24d94c3e176969d72`. | PR #169 is merged after exact-head CI passed. Formal RW3.4 acceptance remains a separate explicit Operator decision and is not performed by this PR. |

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

Final Programmer-local verification passed on exact PR #167 head `d2139c41ec3450f7198e61bdd1169edbeff13e01`: 153 focused tests, 1,286 full-suite tests, Ruff, Mypy (42 source files), disposable PostgreSQL migration/current/single-head checks at `0019_rw1_world_memory`, `git diff --check`, cleanup, and clean-worktree checks. Hosted CI passed on the same exact PR head in run #45147241723. The earlier #152 local result remains historical evidence only. See `docs/testing.md`. If code changes, rerun this contract against the new exact head; do not transfer prior results.

## 7. Documentation authority and deliverables

- `PLAN.md`: sole current status and authorization. It records #163/#165/#167 as merged, the current main baseline, the 28 PASS / 7 PARTIAL / 0 OPEN ledger, and keeps formal RW3.4 acceptance pending until explicit Operator disposition.
- This document: detailed RW3.4 execution sequence, reconciled 35-row proof ledger, testable evidence gaps, explicit integration boundaries, and the formal acceptance checklist.
- `docs/development/rw-implementation-plan.md`: slice order and proof IDs; link to this plan and map RW3.4 rows to their final test nodes.
- `docs/development/rw-3-design-and-acceptance.md`: normative protocol and failure semantics; do not duplicate mutable milestone status beyond a pointer to PLAN.
- `docs/tasks.md`: normative Task shape/write scope/budget; current implementation status only as a pointer.
- `docs/architecture.md`: concise implemented boundary and known host/provider limitations.
- `docs/testing.md`: exact #152/#155 historical evidence, #163 and #165 evidence, and final #167 exact PR head/hosted CI/local verification, recovery correction, migration boundary, and runtime-version qualification.
- `CHANGE_MAP.md`: links the RW3.4 plan and points current status to PLAN.

This documentation reconciliation records the merged #152 implementation stack, #163 recovery/evidence integration, #165 test-only follow-up, and #167 committed-recovery finalization correction against main at `36da6a6f838d48b8709b5dcab252e35028c61899`, and preserves the formal acceptance checklist

## 8. RW3.4 acceptance checklist

- [x] All RW3.1 request, Task-shape, policy-pin, Context, Snapshot, and replay proofs are mapped to current test nodes.
- [x] All RW3.2 admission/provider/receipt/charge/proposal/failure proofs are mapped to current test nodes.
- [x] All RW3.3 shared-commit/actor/marker/atomicity/recovery proofs are mapped to current test nodes.
- [ ] The Context identity tuple is independently checked at every durable boundary and in every recovery state.
- [x] RW-2 Operator behavior is unchanged and its regression proofs pass.
- [x] `RW-GC-01` and `RW-GC-03` cumulative Task-budget proofs are complete.
- [x] `RW-DL-01` deadline and provider-timeout proof is complete or an explicit Operator-approved contract adjustment is recorded.
- [x] Host composition-root and TeamPolicy publisher limitations are stated accurately and not misrepresented as tested integrations.
- [x] Live provider authorization remains closed; fake-provider gate is proven.
- [x] Hosted #167 CI passed fresh disposable PostgreSQL migration/current/single-head checks at `0019_rw1_world_memory`; no persistent database is used.
- [x] Ruff, Mypy, focused tests, full suite, patch-whitespace checks, disposable-DB cleanup, and clean-worktree checks pass on exact PR #167 head `d2139c41ec3450f7198e61bdd1169edbeff13e01` (153 focused; 1,286 full-suite tests; see `docs/testing.md`).
- [ ] Exact pre-run and post-run database URL environment-variable values are explicitly compared in the captured #167 local verification record.
- [x] Hosted CI passes on the exact tested #167 PR head `d2139c41ec3450f7198e61bdd1169edbeff13e01`; source SHA and merge commit are recorded.
- [x] Independent review of the #163 integrated head and #167 recovery correction found no unresolved blocking correctness issue.
- [x] `PLAN.md`, proof matrix, `docs/testing.md`, Task/architecture docs, and CHANGE_MAP agree on the merged implementation baseline, exact #167 evidence, six Context-tuple plus four duplicate/future receipt/proposal cases, 28 PASS / 7 PARTIAL / 0 OPEN ledger, and pending formal Operator acceptance.
- [ ] Explicit Operator acceptance is recorded before RW3.4 is marked complete.

## 9. Non-authorizations

Completing this plan or merging its documentation-only PR does not authorize:

- any production-code change in the deadline/cost/provider paths;
- any Cloudflare/live provider call;
- production host authentication composition or TeamPolicy publishing;
- schema/migration/index/constraint changes or persistent database access;
- RW-4, RW-5, R7-C, RW-4-KU, R8, or scored newsroom execution.

Those require their own scope, review, and explicit authorization.
