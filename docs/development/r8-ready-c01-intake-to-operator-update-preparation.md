# R8-ready C-01 — Intake-to-Operator-Update Preparation

**Status:** C-01 one-source success-path integration implemented as test-only evidence; component-level failure proofs audited and recorded.
**Development state:** Pre-R8-ready. CG-01 remains a bounded test-only technical baseline. C-01 integration is not a treatment condition, scored run, or R8-ready acceptance.
**Audit baseline:** `main` at PR #209 merge commit `9702b941090b7c1cd49756d497f3d462c7b5e08e`. PR #209 exact head `7c0cafefad75264dc73e105c65cfb4259c3844e5` passed CI #2334; post-merge `main` CI #2335 (run ID `45958592015`) also passed the full PostgreSQL, migration, Ruff, Mypy, and test job.
**Authority:** `PLAN.md`, [R8 development states](r8-development-states.md), [R8-ready Path A matrix](r8-ready-scope-and-capability-matrix.md), and the [Control-Group foundation plan](r8-ready-internal-test-foundation-plan.md).

## 1. Review result — CG-01 foundation

PR [#209](https://github.com/abtn/Watch-Architecture-Rev2/pull/209) was reviewed against its stated scope and current source:

- The Control Group is test-harness-only. No production Experiment/ControlGroup model, schema, migration, runtime, or new Task authority was introduced.
- `r8_control_group` reuses `world_memory_context`; it checks that the fixture Team has no `TeamExperienceChunk` before the scenario.
- The integrated test invokes the real authenticated `OperatorApplicationAdapter.operator_update` entrypoint. That path creates its request Task through D1's Control Room operation and delegates lifecycle to TaskRuntime.
- The test verifies the low-confidence Hypothesis, exact Signal/Snapshot-backed EvidenceLink, terminal Outcome/commit Event, and replay identity/no duplicate EvidenceLink. It checks that no Team Experience chunk exists after the first successful update.
- The fixture-seeded `ingest_source` Task and Signal/Snapshot are historical prerequisite state. They are not produced by PlanService, TaskDispatcher, or IngestionService in CG-01.
- The scenario does not create a Thread, execute source intake, invoke retrieval/Context, or compare control and treatment outcomes. The matrix correctly keeps full C-01 separate.

**Review disposition:** no production-boundary or architecture blocker was found in the bounded CG-01 implementation. The evidence-completeness follow-up is now closed by [PR #211](https://github.com/abtn/Watch-Architecture-Rev2/pull/211), merged at `97732042fa746f6c60cb48335df244efea79588d`. The test now checks the no-Team-Experience invariant before the operation, after the first successful update, and after exact replay. Exact-head CI #2338 passed PostgreSQL provisioning, migrations/current-head verification, Ruff, Mypy, patch whitespace, and the full test job. The change is test-only; no production behavior was modified.

## 2. C-01 behavior to prepare

C-01 is the next candidate, not an accepted or frozen R8-ready scenario:

1. A source must be explicitly configured in the TeamPolicy version pinned to the Plan/Task.
2. An ordinary Plan-materialized `ingest_source` Task is created through the existing PlanService → Control Room path.
3. TaskDispatcher resolves the durable source identity from the Task's PlanAction and uses the existing restricted fetcher.
4. IngestionService validates the Task, pinned TeamPolicy source allowlist, fetched bytes/hash, and commits the immutable Signal/Snapshot plus Task-attributed intake Event.
5. TaskRuntime owns admission, attempts, terminalization, Outcome, and completion Event.
6. After successful ingestion, an authenticated Operator submits an `operator_update` against a pre-existing active Thread in the same Team/domain, citing the exact ingested Signal/Snapshot quote.
7. The Operator update is created through Control Room, committed through WorldMemoryCommitService, and finalized through TaskRuntime.
8. The end state proves a traceable source-intake-to-evidence-backed-Hypothesis path. It does not prove that the source is true, relevant, or causally responsible for a later outcome.

Use one synthetic configured source and deterministic bytes. Reuse the existing `FakeFetcher` pattern; do not make live network calls or use real publisher material.

## 3. Source-audit findings and limitations

### 3.1 Existing components that can be reused

| Component | Current owner/path | Existing evidence to reuse | C-01 preparation implication |
|---|---|---|---|
| Plan materialization | `PlanService.create` in `core/plans.py`; materialized `ingest_source` Task creation delegates to `create_ingest_source_task` in Control Room | `tests/test_plans.py`, `tests/test_task_lifecycle_finalize.py`, and the Plan materialization fixtures | Build the source Task from a real PlanAction; do not hand-insert the Task as the integrated proof. |
| Source dispatch | `TaskDispatcher` in `core/dispatcher.py`; source identity comes from the PlanAction | `tests/test_r6b_dispatcher.py`; deterministic `FakeFetcher` is already available | Reuse the fetcher seam and restricted-fetcher component tests. Do not duplicate URL/DNS/redirect/size tests. |
| Signal intake | `IngestionService.ingest` in `core/ingestion.py` | `tests/test_ingestion.py`, plus `tests/test_r6b_dispatcher.py` | Assert exact Team, origin URL, source type, content hash, Snapshot bytes/ref, and intake Event attribution. |
| Task lifecycle | `TaskRuntime` | Existing lifecycle, retry, recovery, and evaluation-task tests | Do not finalize Tasks directly in test code; verify terminal state through read-side queries. |
| Operator update | `OperatorApplicationAdapter.operator_update` → Control Room → WorldMemoryCommitService → TaskRuntime | `tests/test_world_memory.py`, `tests/test_operator_application.py` | Cite the newly ingested Signal/Snapshot and preserve the existing grant, quote, replay, and atomicity rules. |

### 3.2 Important limits that must remain explicit

- Ingestion's existing duplicate lookup is by `(origin_url, content_hash)`. It supports same-origin no-change/replay behavior; it is not RW4-3's Team-wide cross-origin canonical Signal arbitration. C-01 must not claim cross-origin canonicalization or near-duplicate handling.
- The integrated source Task must carry a PlanAction. TaskDispatcher rejects a Task without durable PlanAction source identity; a manually inserted Task/Signal pair is not proof of the configured-source intake path.
- `PlanService.create` validates that every proposed source is present in the TeamPolicy source allowlist. The pinned Task policy version must remain the policy used by dispatch and ingestion; no latest-policy substitution.
- `operator_update` is a direct authenticated evidence-proposal path. It does not invoke Team Experience retrieval. The C-01 result is evidence-backed, not retrieval-backed.
- A pre-existing active Thread is required. `activate_team` is not implemented as a supported Thread-creation journey in the current scope.
- TaskRuntime's existing `ingest_source` completion flow may create its existing evaluation follow-on request. The test must inspect and account for that established side effect rather than misclassifying it as a new C-01 writer or silently deleting it. Reuse the existing evaluation-task proofs; do not add another evaluation subsystem.
- RW4-3's cross-origin canonical Signal arbitration, RW4-4 retrieval/Context, RW-5, SignalDisposition/triage, and RWN-01 scoring remain outside this slice.

## 4. Proposed capability classification for C-01

| Capability | Provisional classification | Required proof / condition |
|---|---|---|
| Control Room Task creation authority | Required — D1 satisfied for the ten inventoried repository producers | PlanService materialization and Operator update both use their existing Control Room operations; no direct Task insert in the integrated path. |
| Plan/PlanAction source identity and policy allowlist | Required | PlanService rejects unconfigured source and binds source identity to immutable PlanAction and pinned policy. |
| Restricted source dispatch | Required | TaskDispatcher fetches only the PlanAction source through injected deterministic fake; component safety tests remain supporting evidence. |
| Signal/Snapshot/Event provenance | Required | Real IngestionService commit; immutable Snapshot bytes/hash and same-Team Task/Event attribution; exact replay/no-change semantics. |
| TaskRuntime admission and terminalization | Required | One lifecycle authority; terminal Outcome/status/Event atomicity and recovery/replay. |
| Operator grant and evidence update | Required | Existing authenticated application path, exact Team/action grant, exact quote/offset/hash validation, no cross-Team evidence. |
| Database atomicity and rollback | Required | Disposable PostgreSQL integrated test and existing injected-failure proofs; no persistent local or production DB. |
| Team Experience retrieval/Context | Not required | No retrieval or knowledge-use claim; explicitly absent from this candidate. |
| SignalDisposition/triage and Thread creation | Not required | Existing active Thread only; Path A defers disposition and triage. |
| Team-wide cross-origin canonical Signal arbitration | Blocked / out of scope | Do not claim it; revisit only if the scenario requires multiple origins or RW4-3's accepted contract demands it. |
| Production experiment assignment/scoring | Not required | Test-only deterministic scenario; no Experiment model, treatment group, RWN-01, or scored run. |

These classifications are a preparation aid, not the final accepted matrix. Any newly discovered Unknown or Blocked capability must be surfaced before scope freeze.

## 5. Implementation and verification record

### Step 0 — Close the CG-01 evidence follow-up — COMPLETE

1. Added the no-`TeamExperienceChunk` assertion after exact replay in the existing baseline test.
2. Exact-head CI #2338 passed PostgreSQL provisioning, migrations/current-head verification, Ruff, Mypy, patch whitespace, and the full test job.
3. Post-merge `main` CI run ID `45979010439` passed.
4. The test checks the no-experience invariant before the operation, after first execution, and after replay. No production code/schema changes.

### Step 1 — Freeze one-source C-01 scenario — COMPLETE

The scenario definition and proof boundary are frozen in [the one-source C-01 scenario freeze](r8-ready-c01-one-source-scenario-freeze.md). It specifies one configured RSS source, PlanAction-backed PlanService materialization, deterministic fake fetching, one immutable Signal/Snapshot, TaskRuntime terminal evidence, and one authenticated Operator update citing that exact evidence on a pre-existing active same-Team Thread. It also records the safe-failure matrix, evaluation follow-on constraint, and exclusions.

### Step 2 — Build the integrated fixture by composition — COMPLETE

Implemented in [PR #215](https://github.com/abtn/Watch-Architecture-Rev2/pull/215), merged at `e83101cfffa51897327a3651087f2ec464329115`. Exact tested PR head: `b34f48545325b6f34fd73a30dd78c660a91340b0`; exact-head CI #2355 passed PostgreSQL provisioning, migrations/current-head verification, Ruff, Mypy, patch whitespace, and the full test job.

The test-only integration lives in `tests/test_c01_intake_to_operator_update.py`. It composes Strategy acceptance, PlanService/Control Room PlanAction-backed source Task materialization, deterministic fake dispatch and ingestion, TaskRuntime terminalization and its existing evaluation follow-on, and an authenticated Operator update against a pre-existing active Thread using the ingested Snapshot evidence. It verifies low-confidence Hypothesis/EvidenceLink provenance, exact replay identity, and no Team Experience creation. No production code, schema, migration, or runtime behavior was changed.

PR #215 review identified two assertion gaps; these were corrected in [PR #216](https://github.com/abtn/Watch-Architecture-Rev2/pull/216), merged at `ffa3703be22a7e8e8078582f287e8acb46031241`. PR #216 exact head `d787d2142645520ac2773326c2f32e20dec460a5` passed CI #2357, including the full PostgreSQL, migration, Ruff, Mypy, whitespace, and test job. The follow-up asserts exactly one `task_completed` Event for each of the source and Operator Tasks, then re-queries after exact replay to assert exactly one each of `operator_update_requested`, `operator_update_committed`, and `task_completed` Events.

The initial PR #215 integration fixture had a CI failure caused by dependent Task rows being flushed before their TeamPolicy parent under a composite foreign key. The fixture ordering was corrected before the final exact-head green run; this was a test-fixture ordering issue, not a production behavior change.

### Step 3 — Prove boundaries without duplicating component suites — COMPLETE WITH QUALIFICATIONS

The integrated success-path test proves the intended one-source composition. The targeted component-test audit maps the principal safe-failure contracts to existing tests; it does not claim that every failure has been injected at every point in the combined journey.

| Boundary / failure | Existing component proof | Evidence assessment |
|---|---|---|
| Missing PlanAction / unconfigured source | `test_task_without_durable_source_configuration_is_rejected_before_admission`; `test_task_whose_source_is_not_configured_is_rejected_before_admission` (`tests/test_r6b_dispatcher.py`) | Covered at dispatcher admission |
| Restricted source URL, DNS, redirect, media type, encoding and response validation | RestrictedFetcher safety tests (`tests/test_r6b_dispatcher.py`) | Covered at fetch boundary |
| Fetch failure, retry and recovery | R6-B dispatcher and TaskRuntime retry/recovery suites | Covered at component/lifecycle boundaries |
| Ingestion hash mismatch | `test_invalid_hash_records_rejection_without_publishing_snapshot` (`tests/test_ingestion.py`) | Covered |
| Ingestion database failure | `test_database_failure_rolls_back_signal_and_success_event` (`tests/test_ingestion.py`) | Covered |
| Same-Task ingestion replay | `test_same_task_retry_reuses_existing_outcome` (`tests/test_ingestion.py`) | Covered |
| Wrong or overbroad grant | `test_host_grant_is_team_and_action_scoped` (`tests/test_world_memory.py`); `test_host_grant_must_match_the_proposal_team_and_exact_action` (`tests/test_operator_application.py`) | Covered |
| Conflicting Operator idempotency reuse | `test_reusing_idempotency_key_with_different_request_is_rejected`, plus changed-proposal/changed-Operator cases (`tests/test_operator_application.py`) | Covered |
| Cross-Team / wrong-domain evidence | `test_cross_team_hypothesis_signal_and_snapshot_references_fail_closed` (`tests/test_world_memory.py`) | Covered |
| Cross-Team Thread admission | `test_cross_team_thread_reference_is_rejected_at_task_admission` | Covered |
| Invalid quote / wrong offsets | `test_invalid_quote_is_rejected_without_discarding_valid_proposal`; `test_exact_quote_with_wrong_offsets_is_rejected` (`tests/test_operator_application.py`) | Covered |
| Operator commit database failure | `test_database_failure_rolls_back_the_entire_valid_proposal_set` (`tests/test_world_memory.py`) | Covered |
| Operator update interruption/recovery | `test_committed_operator_update_is_recovered_without_replaying_writes`; `test_exhausted_interrupted_operator_update_fails_with_attributed_rejections` (`tests/test_operator_application.py`) | Covered |
| Plan provenance, incomplete state, changed identity and concurrency | `test_durable_provenance_rejection`, `test_unsupported_candidate_rejected`, `test_current_authority_revalidated`, `test_missing_task_cannot_create`, `test_identical_retry_and_concurrency`, `test_conflicting_creation_identity`, `test_changed_same_task_request_rejects`, `test_incomplete_plan_state_is_rejected_not_repaired`, `test_tampered_accepted_provenance_is_rejected`, `test_retry_does_not_repair_incomplete_plan_state` (`tests/test_plans.py`) | Covered |

**Evidence boundary:** component tests establish individual rejection, rollback, and recovery contracts. The C-01 integration test establishes the successful composition and replay invariants. Neither should be overstated as a full cross-product of injected failures across the integrated workflow. No additional integrated failure harness was justified by this audit: it would duplicate established component guarantees without identifying a specific uncovered contract. If a future change alters one of these boundaries, reassess whether an integrated failure test is then necessary.

### Step 4 — Verification and independent review — COMPLETE FOR THE TEST-ONLY SLICE

1. The integrated test was added and verified in PR #215; exact-head CI #2355 passed the full hosted PostgreSQL/static/test job.
2. The two missing terminal/replay assertions were added in PR #216; exact-head CI #2357 passed the full hosted PostgreSQL/static/test job.
3. The diffs were constrained to `tests/test_c01_intake_to_operator_update.py`; no production code, schema, migration, runtime, or application behavior changed.
4. Review checked the PlanAction-backed Task path, Control Room authority, TaskRuntime lifecycle, policy/source identity, fake-only fetch, existing evaluation follow-on, evidence provenance, replay behavior, and no-Team-Experience invariant.
5. The safe-failure matrix above was mapped to existing component tests. It remains component-level evidence rather than integrated failure injection.

**Exit:** the authorized test-only C-01 success-path slice and the identified assertion corrections are implemented and exact-head CI verified. This does not certify untested cross-component failure combinations or authorize production changes.

### Step 5 — Scope boundary after implementation

The explicit authorization for the bounded test-only Step 2 work was granted and consumed by PR #215. It does not authorize production implementation, new persistence/runtime behavior, retrieval/Context, cross-origin arbitration, scoring, or formal R8. Any expansion beyond the merged test-only slice requires a new scoped proposal and explicit authorization.

## 6. Stop conditions

Stop and return for a design decision if any of the following is found:

- PlanService cannot create a valid PlanAction-backed source Task without a new production Task writer or an unapproved authority.
- The accepted pinned TeamPolicy/source identity cannot be preserved end to end.
- TaskRuntime's existing evaluation follow-on creates an unaccounted lifecycle or transaction dependency.
- Ingestion needs RW4-3 cross-origin arbitration for the intended scenario.
- The Operator update cannot cite the exact ingested Snapshot without weakening provenance or Team/domain checks.
- The integrated path requires SignalDisposition, triage, Thread creation, RW4-4 retrieval/Context, RW-5, live providers, or persistent database access.
- Any proposed change requires a production schema/model/migration or a new Experiment/ControlGroup runtime.

A stop condition is a finding, not permission to weaken the architecture or silently expand scope.

## 7. Expected outcome and current state

The expected outcome of this preparation is a reviewable, one-source, deterministic C-01 implementation packet. It is not evidence that C-01 has been implemented or that R8-ready entry criteria are met.

**Current project state remains Pre-R8-ready.** CG-01 remains a technical baseline. The C-01 one-source success-path integration is implemented as test-only evidence, with terminal/replay assertions completed and existing component-level failure proofs mapped. This does not establish a treatment comparison, retrieval/Context capability, cross-origin canonicalization, production Experiment/ControlGroup behavior, RWN-01 scoring, formal R8, or R8-ready transition. Those remain blocked by their existing gates.
