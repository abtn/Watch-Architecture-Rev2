# R8-ready Internal Test Foundation — Control-Group Baseline

**Status:** bounded implementation plan; Operator authorization recorded in `PLAN.md` on 2026-11-27.
**Development state:** Pre-R8-ready preparation. This plan authorizes only the minimum test-only baseline foundation and its technical verification; it does not authorize scored newsroom runs, formal R8, production use, or a state transition to R8-ready.
**Planning baseline:** PR #207 D1 merged to `main` at `d03297c2b4e3522b0dc59ce001955cda130fd14f`; tested PR head `8532f573170b23b95bd98ccd56b3d8ea8d36cea8` passed hosted CI run #2326.
**Authority:** `PLAN.md`, [R8 development states](r8-development-states.md), [R8-ready Path A scope matrix](r8-ready-scope-and-capability-matrix.md), and accepted RW-0 decisions.

## 1. Purpose

Create the smallest repeatable internal-test baseline that can exercise a real, already-governed Watch vertical slice. The first Control Group is a **test-harness condition**, not a new production Watch entity or a second execution system.

The baseline must be useful before a treatment implementation exists. It establishes a controlled, experience-free starting state and records what the current governed application path does. Later treatment work can be compared against that baseline only after its own retrieval/Context contract and authorization are satisfied.

## 2. Terminology and hard boundaries

The names are deliberately distinct:

- **Control Room** is the in-process application authority for Task creation. D1 centralizes supported Task producers there; TaskRuntime remains the sole Task lifecycle authority.
- **Control Group** is the experiment/test condition that receives the common test inputs without retained Watch experience. It is not Control Room and does not create, authorize, admit, execute, or finalize Tasks.
- **Baseline fixture** is the test-only data and setup used to instantiate one isolated Control Group case.

The Control Group foundation belongs in test/harness code. It must not add:
- a production `Experiment`, `ExperimentGroup`, `ControlGroup`, cohort, assignment, or run model/table;
- a new Task type, Task lifecycle, Event family, Control Room operation, or write authority;
- production retrieval/Context behavior or a substitute for RW4-4;
- SignalDisposition, `triage_signal`, RW-5 decay, TaskKnowledgeReference, or KnowledgeUseAssessment;
- a generic experiment runner, scheduler, provider framework, or scoring subsystem.

The accepted RW-D09 decision places retrieval-quality evaluation and small-sample reporting in harness tooling, not a permanent Watch subsystem. RW-D10 defines the eventual control/treatment comparison: both receive the same brief and source material; only treatment receives retained experience through normal retrieval/Context. This foundation implements neither the treatment path nor the scored comparison.

## 3. Initial bounded vertical slice

Use Path A and the smallest governed portion of candidate C-01: an authenticated Operator evidence update against a pre-existing, same-Team source. This deliberately does **not** exercise the full C-01 configured-source intake sequence.

1. Start from an isolated Team with an already-existing active Thread. The fixture may seed this Thread because `activate_team` is not implemented; do not imply that Thread creation is part of this test.
2. Seed one immutable same-Team Signal/Snapshot as prerequisite evidence, using the existing `world_memory_context` test fixture pattern. The source-attribution Task is fixture state, not the Task-creation path under test.
3. Use the authenticated Operator application entrypoint to submit a bounded `operator_update` request for the seeded active Thread, adding a low-confidence Hypothesis and a verified EvidenceLink to that Signal/Snapshot. The request Task must be created through the D1 Control Room operation.
4. Let TaskRuntime own admission and terminalization. Verify durable state only through ordinary read-side inspection.
5. Assert that the Team has no retained `TeamExperienceChunk` available to this baseline and that no retrieval/Context path is invoked.

The first Control Group condition has **no retained Team Experience supplied to the Task** and makes **no retrieval or claim-level knowledge-use assertion**. It is a technical baseline for the governed Operator update path, not the full C-01 intake journey, not a treatment comparison, and not evidence of product-value improvement. Existing ingestion and PlanService tests remain separate proofs of those components.

Use synthetic, deterministic test inputs. Do not use the unfrozen RWN-01 newsroom corpus, publisher files, real scored briefs, reviewer materials, or the scored 20-run protocol for this internal technical baseline.

## 4. Control Group fixture contract

A baseline case must be isolated and reproducible:

- A fresh Team and policy state, with explicit domain and policy identity.
- One active Thread belonging to that Team and domain.
- One immutable same-Team Signal/Snapshot with exact content hash, seeded as historical prerequisite evidence.
- A fixture-seeded source-attribution Task only; the Task under test is the authenticated `operator_update` Task created through Control Room.
- One authenticated Operator principal and exact Team/action grant for the subsequent `operator_update`.
- No retained Team Experience chunks/snapshot supplied to the case; no hidden prompt/operator hint that acts as a substitute.
- A recorded fixture identity/version and the exact source/test-code revision. The fixture may use generated UUIDs, but all relationships and source bytes must be deterministic.
- Disposable PostgreSQL for database-backed integration assertions. No persistent local `watch` database and no production credentials.

The fixture should be a small pytest helper or fixture composed from existing test factories. Prefer reusing existing helpers and test setup over creating a new harness package. Do not introduce a general-purpose factory or runner until a second real test demonstrates the need.

The fixture is setup only. It must not bypass Control Room creation of the `operator_update` Task, TaskRuntime lifecycle, Operator authorization, WorldMemoryCommitService validation, or transaction boundaries. IngestionService/PlanService are outside this baseline's integrated path and retain their separate existing proofs.

## 5. Detailed implementation and verification sequence

### Phase 0 — D1 integration gate

1. Confirm PR #208 is merged into PR #207.
2. Wait for the complete CI run on PR #207's updated exact head.
3. If CI fails, retrieve logs, identify the root cause, fix the narrow defect, and rerun the affected/full required checks.
4. Independently review the complete PR diff and confirm all ten supported Task producers delegate to Control Room-owned operations.
5. Merge PR #207 into `main` only after all required checks are green and mergeability is current.
6. Verify the merged PR state, merge SHA, and `main` ancestry. Record the exact baseline SHA for the next work.

**Exit:** D1 is merged and its exact merged head has passing CI. No R8 scope claim is inferred from D1 closure.

### Phase 1 — Reconcile current R8-ready and Full Design states

1. Read `PLAN.md`, the R8 development-state document, R8 delivery plan, Path A matrix, RW-0 decisions, RW-4 readiness plan, Task specifications, and the relevant source/tests.
2. Reconcile historical statements in the matrix that describe the pre-D1 source baseline. Preserve their historical meaning, but add a current-source result at the post-D1 SHA.
3. Classify each capability used by the bounded `operator_update` subset as Required, Not required, Unknown, or Blocked. Unknown is not a pass.
4. Record the exact entrypoints, owner, persistence effect, current tests, missing proof, and any Full Design dependency.
5. Keep the distinction explicit: this plan's test-only baseline is not R8-ready entry, formal R8, or the RWN-01 scored value harness.

**Exit:** a current-source capability map exists with no stale D1 blocker and no unclassified dependency hidden as a deferment. D1 is already merged; the remaining classification is limited to the bounded `operator_update` baseline.

### Phase 2 — Freeze the minimum technical scenario

1. Confirm the bounded `operator_update` subset is the smallest meaningful existing governed vertical slice after D1; do not label it full C-01.
2. Freeze the observable question: can an authenticated Operator use an existing same-Team immutable Signal/Snapshot to record an evidence-backed low-confidence Hypothesis on an existing active Thread through the governed `operator_update` path, with safe rejection and no partial writes?
3. Freeze expected durable effects and safe-failure outcomes.
4. Explicitly exclude Thread creation, automatic triage, retained-experience retrieval, claim-level attribution, and treatment/control value claims.
5. Record all fixture identities as generated test data and preserve deterministic source bytes.
6. Map each relied-upon invariant to existing tests or a required new integrated proof.

**Exit:** one bounded scenario and its proof subset are explicit. The fixture-seeded source Task is only historical provenance input; the `operator_update` Task itself must be created by the real application entrypoint through Control Room.

### Phase 3 — Implement the test-only Control Group baseline

1. Reuse the existing `world_memory_context` fixture in `tests/test_world_memory.py`; it already seeds an isolated Team, policy, source Task, immutable Signal/Snapshot, and active Thread.
2. Add only a named test fixture wrapper (or an equivalent explicit assertion in the existing test) that verifies the baseline Team has no `TeamExperienceChunk` rows. Do not duplicate the fixture's data model or build a general harness abstraction.
3. Run the existing authenticated `OperatorApplicationAdapter.operator_update` entrypoint. Its target Task must be created through the D1 Control Room operation; the fixture-seeded source Task is only historical provenance input.
4. Make the absence of retained experience explicit and testable. Do not add a fake retrieval result or invent an empty Context path.
5. Reuse the existing `test_operator_update_creates_low_hypothesis_and_verified_evidence` assertions for Task/Outcome/Event, Hypothesis, EvidenceLink, exact quote/Snapshot identity, and replay. Add only the missing explicit baseline assertion.
6. Avoid adding production files, models, migrations, runtime flags, Event types, or an experiment runner.

**Exit:** the existing fixture plus one explicit no-retained-experience assertion provides the smallest deterministic baseline. If this requires a new generic fixture abstraction, stop and reuse the existing fixture directly.

### Phase 4 — Prove the integrity boundary

Add or reuse focused tests to prove:

- Task creation delegates through Control Room; TaskRuntime alone admits and finalizes.
- The pre-seeded Signal/Snapshot is immutable, same-Team, and the exact evidence source referenced by the Operator update. (The ingestion write path is covered by its separate existing tests, not this baseline integration.)
- Operator principal and exact Team/action grant are required.
- The Thread, Signal, Snapshot, Task, and Hypothesis are same-Team and same-domain where required.
- Exact quote and offsets match immutable Snapshot bytes.
- Invalid, cross-Team, stale, or malformed proposals do not create partial business state.
- Exact request replay is idempotent; conflicting reuse fails closed.
- Database failure rolls back the complete business proposal set.
- The Control Group has no Team Experience projection rows and no retained-experience payload or retrieval result is supplied.
- Each case uses disposable PostgreSQL for the database claims; in-memory mocks may test pure validation only.

Do not duplicate already-adequate unit proofs merely to increase test count. The existing Operator update test plus the explicit no-retained-experience assertion is the focused integrated baseline proof; existing focused tests remain the detailed invariant proofs.

**Exit:** every exercised invariant maps to a passing exact test, with PostgreSQL evidence for database behavior.

### Phase 5 — Full verification and independent review

1. Run `tests/test_world_memory.py::test_operator_update_creates_low_hypothesis_and_verified_evidence` first.
2. Run focused existing Operator application, WorldMemory, TaskRuntime, and Control Room tests affected by the path. Ingestion and PlanService tests are supporting regression evidence, not required for this narrowed baseline.
3. Run Ruff, Mypy, patch whitespace checks, migration-head checks, and the full CI suite.
4. Review the diff for direct Task writes, transaction ownership changes, hidden experience inputs, new production authority, test fixture leakage, and unrelated refactors.
5. Review the documentation against actual source/test behavior and exact tested SHA.
6. Record any unrun checks and limitations; do not claim a green local run if only hosted CI was run.

**Exit:** all required checks pass on the exact final PR head; no unresolved P1/P2 finding remains; independent review confirms the scope boundary.

### Phase 6 — Results and next experiment decision

1. Record the baseline behavior, fixture version, source/test SHA, test results, logs, and any observed failures.
2. Classify findings as implementation defects, missing requirements, design assumptions, unnecessary complexity, fixture defects, or environment limitations.
3. Propose the smallest correction for each finding and preserve the original baseline evidence.
4. Decide whether a treatment condition is now feasible. It requires the accepted retrieval/Context consumer contract and its own gate; do not claim retained knowledge was used merely because it was available.
5. Only after the technical baseline is understood, propose a bounded treatment fixture or a separate experiment protocol change.
6. Keep RWN-01 scored execution blocked until its corpus, assignment, answer key, outcome reference, reviewers, and execution configuration are frozen and explicitly accepted.

**Exit:** baseline findings are recorded and the next step is based on evidence rather than assumed architecture.

## 6. Existing proof inventory to reuse

The following existing tests are relevant starting points; their presence is not a claim that they were rerun by this planning change:

- `tests/test_ingestion.py::test_successful_ingestion_commits_signal_event_and_snapshot` (separate supporting proof; not part of the baseline vertical slice)
- `tests/test_ingestion.py::test_database_failure_rolls_back_signal_and_success_event` (separate supporting proof)
- `tests/test_ingestion.py::test_same_task_retry_reuses_existing_outcome` (separate supporting proof)
- `tests/test_plans.py::test_materialized_task_uses_existing_ingestion` (separate supporting proof)
- `tests/test_operator_application.py::test_request_creates_one_pending_task_and_one_attributed_event`
- `tests/test_operator_application.py::test_concurrent_identical_requests_create_one_task_and_request_event`
- `tests/test_world_memory.py::test_operator_update_creates_low_hypothesis_and_verified_evidence`
- `tests/test_world_memory.py::test_database_failure_rolls_back_the_entire_valid_proposal_set`
- `tests/test_world_memory.py::test_cross_team_hypothesis_signal_and_snapshot_references_fail_closed`
- `tests/test_world_memory.py::test_committed_operator_update_is_recovered_without_replaying_writes`
- `tests/test_task_runtime.py::test_transaction_failure_rolls_back_task_and_event`

These test names and their relevant fixtures/contracts were inspected at the post-D1 baseline. The existing Operator update test is extended with the explicit no-retained-experience assertion; do not add a duplicate integration test if this existing test already exercises the required path.

## 7. Explicit non-goals and stop conditions

- No SignalDisposition or triage implementation.
- No RW-5 decay or canonical lock retrofit.
- No RW4-4 retrieval/Context implementation under this plan.
- No live provider calls or production credentials.
- No persistent local database writes.
- No RWN-01 scored run, no reviewer scoring, and no causal or statistical superiority claim.
- No production ControlGroup/Experiment schema or subsystem.
- No R8-ready state transition or formal R8 acceptance.

Stop if the selected path requires a deferred capability, if the only way to test it is to bypass an authority boundary, if database isolation cannot be proven, or if the fixture would conceal an unimplemented user-facing entrypoint.


## 8. CG-01 evidence-closure record — 2026-11-27

The post-replay no-Team-Experience assertion follow-up is complete.

- Correction PR: [#211](https://github.com/abtn/Watch-Architecture-Rev2/pull/211).
- Tested PR head: `0bb41974976a8a9a1454cdddb264616848dd97ae`.
- Merge commit: `97732042fa746f6c60cb48335df244efea79588d`.
- Exact-head hosted CI: run #2338 (`45976581249`) passed. The run completed PostgreSQL container initialization and isolated role provisioning, migration application and head verification, Ruff, Mypy, patch whitespace, and the full test job.
- Change scope: one assertion in `tests/test_world_memory.py`; no production code, fixture, schema, migration, or runtime changes.
- The test now checks the no-`TeamExperienceChunk` invariant before the operation (fixture), after the first successful update, and after exact replay. Existing replay identity, single EvidenceLink, and no-ConfidenceChange assertions remain intact.

**Disposition:** CG-01's explicit no-retained-Team-Experience evidence gap is closed at the tested head above. This closes only the test-only baseline proof; it does not establish full C-01, retrieval/Context, treatment comparison, scored R8, or R8-ready status. Post-merge `main` CI remains a separate verification item.
