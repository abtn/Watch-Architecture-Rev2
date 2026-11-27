# R8-ready C-01 — Intake-to-Operator-Update Preparation

**Status:** source-audited preparation only; no C-01 implementation authorization is implied.
**Development state:** Pre-R8-ready. CG-01 is a bounded test-only technical baseline, not a complete C-01 run, treatment condition, or R8-ready acceptance.
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

## 5. Sequenced preparation and implementation gate

### Step 0 — Close the CG-01 evidence follow-up — COMPLETE

1. Added the no-`TeamExperienceChunk` assertion after the exact replay checks in the existing baseline test.
2. The exact test is included in the full hosted test job on the disposable PostgreSQL environment.
3. The focused WorldMemory/Operator/Control Room/TaskRuntime checks are covered by the exact-head full test suite; no separate local-shell run is claimed.
4. Exact-head CI #2338 passed PostgreSQL provisioning, migrations/current-head verification, Ruff, Mypy, patch whitespace, and the full test job.
5. The foundation record now records the tested PR head, merge commit, and CI run.

**Exit:** satisfied. The no-experience invariant is explicitly checked before, after first execution, and after replay. No production code/schema changes. Post-merge `main` CI remains to be verified separately.

### Step 1 — Freeze one-source C-01 scenario — COMPLETE

The scenario definition and proof boundary are frozen in [the one-source C-01 scenario freeze](r8-ready-c01-one-source-scenario-freeze.md).

The freeze specifies one active Team and pinned TeamPolicy source, one PlanService/Control Room-materialized PlanAction-backed ingestion Task, deterministic `FakeFetcher` bytes, one immutable Signal/Snapshot and TaskRuntime terminal evidence, and one authenticated Operator update citing that exact ingested evidence on a pre-existing active same-Team Thread. It also records the expected durable evidence, safe-failure matrix, existing evaluation follow-on constraint, and exclusions.

**Exit:** satisfied for scenario preparation. This is not implementation authorization; Step 2 and later implementation work remain gated by a separate explicit authorization.

### Step 2 — Build the integrated fixture by composition

1. Reuse the existing Plan/Objective fixtures and PlanService materialization flow. Do not hand-insert the source Task for the integrated proof.
2. Reuse the `dispatch_fixture` / `FakeFetcher` pattern from `tests/test_r6b_dispatcher.py`, adapting only what is needed to start from a real PlanService-created PlanAction.
3. Reuse `world_memory_context` setup only where appropriate for the active Thread and Operator target; do not create a generic C-01 harness package.
4. Ensure the source Task's policy pin and PlanAction identity are exactly those accepted by PlanService.
5. Run TaskDispatcher and wait for its TaskRuntime terminal result before submitting the Operator update.
6. Use the actual ingested Signal/Snapshot identifiers and bytes to build the exact-quote Operator proposal.
7. Preserve disposable PostgreSQL and fixture cleanup, including any existing evaluation follow-on request created by TaskRuntime.

**Exit:** one deterministic integration test exercises PlanService → TaskDispatcher → IngestionService → TaskRuntime → OperatorApplicationAdapter → Control Room/WorldMemoryCommitService → TaskRuntime.

### Step 3 — Prove boundaries without duplicating component suites

- Assert configured-source Task creation is PlanAction-backed and Control Room-owned.
- Assert the fetcher receives exactly the PlanAction URL/source type and is never called for an unconfigured source.
- Assert the committed Signal points to the exact immutable Snapshot bytes/hash and is attributed to the source Task.
- Assert source Task terminal Outcome/status/Event and any existing evaluation follow-on are valid and correctly attributed.
- Assert the Operator update uses the same Team/domain and exact ingested Signal/Snapshot quote and offsets.
- Assert no business writes occur for invalid grants, cross-Team references, malformed quotes, or conflicting replay.
- Assert exact replay creates no duplicate Signal, EvidenceLink, or Hypothesis.
- Use existing injected-failure tests for component rollback; add an integrated rollback test only if it reveals a boundary not already proven.
- Assert no Team Experience is supplied, retrieved, or created by this direct Operator update path. Do not add a fake empty Context.

**Exit:** each claim maps to an existing or new exact test; PostgreSQL evidence supports database guarantees.

### Step 4 — Verification and independent review

1. Run the new integrated C-01 test first.
2. Run focused PlanService, dispatcher, ingestion, TaskRuntime/evaluation-follow-on, Operator application, and WorldMemory suites.
3. Run Ruff, Mypy, migration current/head checks, whitespace, and full test suite.
4. Review the diff for direct Task writes, Task lifecycle bypass, policy-pin drift, source-identity substitution, live network use, transaction ownership changes, hidden experience inputs, and unrelated refactors.
5. Verify the exact tested PR head, CI conclusion, merge base, and disposable database cleanup.
6. Record any missing proof or environment limitation without treating Unknown as Pass.

**Exit:** exact-head hosted CI is green; no unresolved P1/P2 finding; all exercised boundaries have source-backed evidence.

### Step 5 — Return for explicit scope/implementation authorization

After the preparation and review are accepted, submit a separate authorization request naming the exact files, behavior, test cases, database impact (expected none), rollback, and verification. Do not begin C-01 implementation merely because this preparation document is merged.

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

**Current project state remains Pre-R8-ready.** CG-01 is a technical baseline only. C-01 remains a candidate pending scenario freeze, resolution of the stated proof questions, and separate explicit authorization. Formal/scored R8, RWN-01, treatment comparison, and R8-ready transition remain blocked by their existing gates.
