# R8 initial internal-test scope and proof freeze

**Status:** selected and reconciled for bounded technical internal testing; exploratory execution protocol and any new test execution require their own review/authorization.
**Development state:** Pre-R8-ready. This document does not declare R8-ready entry, formal R8, scored RWN-01 execution, or production readiness.
**Decision:** initial scope is CG-01 + C-01. Model-assisted C-02 and retained-experience/retrieval tests are deferred.
**Source baseline:** main at c648892e4896113700c8103397be01c11c0d22ed (2026-11-27 merge of PR #221).
**Authority:** PLAN.md, [R8 development states](r8-development-states.md), [Path A scope and capability matrix](r8-ready-scope-and-capability-matrix.md), [CG-01 foundation plan](r8-ready-internal-test-foundation-plan.md), and [C-01 scenario freeze](r8-ready-c01-one-source-scenario-freeze.md).

## 1. Decision and interpretation

The initial internal technical-test scope contains exactly two scenarios:

1. **CG-01 — experience-free authenticated Operator update baseline.**
2. **C-01 — one configured source intake followed by an authenticated Operator update.**

CG-01 is the shorter baseline; C-01 composes the configured-source and Operator-update paths. These are technical correctness and controlled exploratory foundations, not a control/treatment value comparison. The phrase "Control Group" refers only to the test-harness condition; it is not a production model or experiment subsystem.

This selection does not freeze the entire R8-ready feature set or waive any predecessor gate. It does not authorize a new test execution campaign, production implementation, live provider, persistent database, formal/scored R8, or transition from Pre-R8-ready.

## 2. Frozen scenario boundaries

### 2.1 CG-01 — authenticated Operator update baseline

**Question:** Does the existing authenticated operator_update path create and finalize a low-confidence Hypothesis and exact Snapshot-backed EvidenceLink on a pre-existing active Thread, while preserving authorization, Team isolation, atomicity, replay, and no-retained-experience invariants?

**Setup and path:**
- Isolated Team and active pre-existing Thread.
- Immutable same-Team Signal/Snapshot and source-attribution Task are fixture-seeded prerequisites.
- Authenticated test principal has the exact Team-level operator_update grant.
- Operator request Task is created through Control Room.
- WorldMemory commit and Task lifecycle remain owned by their existing services, including TaskRuntime.
- No Team Experience is supplied or retrieved; no TeamExperienceChunk is created before, after first update, or after exact replay.

**Expected evidence:** one completed Operator Task, expected request/commit/completion Events, one low-confidence Hypothesis, one exact verified EvidenceLink, replay identity without duplicate writes, and no Team Experience creation.

**Limitations:** no configured-source intake; Signal/Snapshot are fixture prerequisites; no Thread creation; no retrieval/Context; no treatment comparison; no scoring or product-value claim.

**Implementation evidence:** PR #209 and assertion follow-up #211; closure record #212. Exact-head CI #2338 passed and post-merge main CI passed. The test is in tests/test_world_memory.py using r8_control_group and the existing world_memory_context fixture.

### 2.2 C-01 — one-source intake-to-Operator integration

**Question:** Can one active Team and one policy-pinned configured HTTPS source materialize an ordinary ingest_source Task through PlanService/Control Room, fetch deterministic synthetic bytes through the injected fake fetcher, persist immutable Signal/Snapshot and Task-attributed intake evidence, then allow an authenticated Operator to cite that exact evidence in a low-confidence Hypothesis on a pre-existing active same-Team/domain Thread?

**Frozen cardinality:** one Team, one TeamPolicy version, one configured origin, one Objective, one accepted Strategy proposal, one Plan, one PlanAction, one materialized ingest_source Task, one Signal/Snapshot, one pre-existing active Thread, and one Operator update request.

**Expected evidence:**
- Accepted Strategy and Plan/PlanAction with the exact configured source.
- Plan-materialized source Task with Team/Objective/policy pins.
- Exactly one fake fetch request; no live network.
- Signal/Snapshot bytes/hash/origin/source type and Task attribution.
- Source Task Outcome/terminal Task/completion Event and existing evaluation follow-on.
- Authenticated Operator Task, low-confidence Hypothesis, exact quote/offset/hash EvidenceLink.
- Request/commit/completion Event cardinality before and after exact replay.
- No duplicate business writes and no TeamExperienceChunk creation, including after replay.

**Limitations:** Thread is fixture-seeded; only one configured source; no cross-origin canonicalization; no retrieval/Context or retained-experience use; no triage/disposition; no live network/provider; no scoring or causal claim.

**Implementation evidence:** PR #215 and assertion completion PR #216; documentation reconciliation PRs #217/#218. Exact-head CI #2355 and #2357 passed; PR #217 post-merge main CI passed. Test: tests/test_c01_intake_to_operator_update.py::test_c01_configured_source_intake_then_operator_update.

## 3. Current capability-to-proof matrix

Classifications apply only to the two selected scenarios. "Required — satisfied" means there is a current implementation and identified test/CI evidence; it does not mean every conceivable failure combination is proven. "Unknown" remains a blocker if a scenario is later expanded to depend on it.

| Capability / invariant | CG-01 | C-01 | Current implementation / proof | Residual qualification |
|---|---|---|---|---|
| Task creation authority | Required — satisfied | Required — satisfied | D1 PR #207/#208; ten supported producers delegate to named Control Room operations; exact-head CI #2326 | External/out-of-repository writers are not covered by the ten-producer source audit |
| Task lifecycle / terminal atomicity | Required — satisfied for exercised path | Required — satisfied for exercised path | TaskRuntime; CG-01/C-01 terminal Outcome and completion Event assertions; C-01 PR #216 closes source/operator completion Event gap | Does not qualify every Task type or all recovery states |
| Operator authentication and action grant | Required — satisfied | Required — satisfied | Existing Operator application tests and integration path; exact Team/action grant used by both fixtures | No deployed host authentication/composition proof |
| Thread / Team ownership | Required — satisfied for existing Thread | Required — satisfied for existing Thread | WorldMemory same-Team validation and cross-Team failure tests; C-01 same-Team/domain fixture | Thread creation and domain mutation lifecycle are not exercised |
| Signal/Snapshot provenance and integrity | Required — satisfied for fixture source | Required — satisfied for intake-created source | Ingestion and WorldMemory tests; C-01 asserts immutable Snapshot bytes/hash, origin, type and source Task linkage | Does not prove RW4-3 Team-wide cross-origin canonical Signal arbitration |
| Evidence quote/hash/offset validation | Required — satisfied | Required — satisfied | WorldMemory exact quote/offset validation; C-01 derives quote/offset from ingested Snapshot | Not a claim about truth/relevance of the source |
| Hypothesis/EvidenceLink durable commit | Required — satisfied | Required — satisfied | WorldMemory Operator update, rollback, concurrency and confidence-cause tests; C-01 integrated assertions | No autonomous model interpretation claim |
| Idempotency and replay | Required — satisfied for exact replay | Required — satisfied for exact replay | Operator application concurrency/replay tests; CG-01 replay assertion; C-01 PR #216 post-replay Event counts | Conflicting-key and broader concurrent interleavings remain component-level proofs, not one exhaustive integrated matrix |
| Atomic rollback | Required — component proof | Required — component + integrated path proof | test_database_failure_rolls_back_the_entire_valid_proposal_set; ingestion rollback tests; TaskRuntime rollback tests | Not every possible failure injection is integrated end-to-end; do not duplicate existing coverage without a demonstrated gap |
| PostgreSQL constraints/transactions/locks | Required — relied-upon subset verified | Required — relied-upon subset verified | Hosted CI provisions disposable PostgreSQL, applies migrations and runs full suite; concurrency/locking tests use PostgreSQL fixtures | No production host runtime workflow proof |
| Migration identity and test DB role isolation | Required — test boundary verified | Required — test boundary verified | PR #221 Windows run (1,341 passed) and hosted CI #2376; role provisioning and migrator Alembic path | watch_runtime remains SELECT-only; this is not a deployable app identity or DML grant proof |
| No retained Team Experience input/output | Required — satisfied | Required — satisfied | CG-01 checks no chunks before/after/replay; C-01 checks no TeamExperienceChunk and no retrieval path | No retrieval capability is exercised or proven |
| Configured source / Plan / Dispatcher composition | Not required | Required — satisfied | C-01 test integrates StrategyService, PlanService, Control Room, TaskDispatcher, FakeFetcher, IngestionService and TaskRuntime | One source only; fake fetcher only |
| Evaluation follow-on behavior | Not required | Required — observed and asserted | C-01 verifies the existing evaluation request and its Task identity/type | Not a separate evaluation quality/value test |
| Context assembly / Team Experience retrieval | Not required | Not required | Neither scenario invokes retrieval/Context | RW4-4 contract/gate and Experiment A disposition remain required before a retrieval-dependent scenario |
| Claim-level knowledge-use attribution | Not required | Not required | No claim-level use assertion is made | RW-D99/D133 mapping, implementation authorization and proof remain separate |
| SignalDisposition / triage | Not required | Not required | Neither scenario creates a disposition | Path A deferral and RW4-1/RW4-2 Stage B/RW-5/RW4-3 gates remain binding |
| Thread creation / dormant reactivation | Not required | Not required | Both scenarios use fixture-seeded active Thread | activate_team/RW-5/RW4-5 remain outside scope |
| Live model provider | Not required | Not required | Neither scenario invokes a live provider | Live provider authorization remains closed |
| Production application host / runtime identity | Not required for in-process tests | Not required for in-process tests | Current repo has no production host/composition root; pytest composes services directly | If a future scenario requires a deployed interface/worker, define host and identity as a separate prerequisite; do not build speculatively |
| Scored newsroom corpus / Control-Treatment experiment | Not required | Not required | Synthetic deterministic fixtures only | RWN-01 and formal/scored R8 remain blocked |

## 4. Test-environment and evidence boundary

- Use the existing pytest integration path and disposable PostgreSQL; do not create a production host solely to run these in-process tests.
- The local disposable runner uses bootstrap authority only for container/database setup and role provisioning; Alembic runs as watch_migrator. Runtime role remains read-only. No test in this scope should quietly rely on a production-like DML runtime login.
- Preserve the exact fixture, source bytes, generated identities, test SHA, migration head, CI run, logs, and cleanup evidence when a new authorized test execution is undertaken.
- No persistent local watch database, production database, live source URL, live model provider, publisher corpus, or production credential.
- PR #222 is open/unmerged at this baseline; its additional has_any_column_privilege test hardening must not be treated as merged main evidence. Its exact-head CI passed, but the current baseline is still the PR #221 merge commit.

## 5. Explicitly deferred or blocked

| Capability | Classification for this scope | Reopen trigger | Preserved gate |
|---|---|---|---|
| C-02 deterministic model-assisted update_thread scenario | Deferred from initial scope; not rejected | Operator selects a distinct model-assisted question and RW3.4 PARTIAL qualifications are reviewed for the exact path | RW3.4 acceptance ledger; live-provider authorization remains closed |
| Team Experience retrieval/Context scenario | Blocked / deferred | A scenario explicitly requires retained-experience retrieval and a consumer contract is accepted | RW4-4 consumer contract, its own gate, and accepted Experiment A result or explicit Operator disposition before representation freeze |
| Claim-level knowledge-use/outcome attribution | Not required | Scenario asserts actual use or downstream outcome contribution | RW-D99/D133 mapping, authorization, and proofs |
| SignalDisposition / triage_signal | Not required | Selected scenario cannot be completed through existing authorized paths and demonstrably needs disposition | RW4-1B–F, RW4-2 Stage B, RW-5, RW4-3 and issue #199 |
| Thread creation/reactivation | Not required | Selected scenario requires a real lifecycle transition rather than fixture-seeded active Thread | Accepted Thread lifecycle owner and RW-5/RW4-5 gates |
| Production host and application DML identity | Not required for current in-process scenarios | A selected scenario needs an actual deployed API/CLI/worker or external authentication boundary | Separate host composition, transaction ownership, operational writer audit, exact grant design, and explicit implementation authorization |
| Scored newsroom value test | Blocked | Foundation exit, frozen corpus/brief/answer key/outcome reference/reviewer/configuration and explicit authorization | RW-0 and R8 delivery plan |

## 6. Stop conditions

Stop the affected scenario and return with evidence if:
- a required operation lacks an existing governed entrypoint;
- authority, Task ownership, Team/domain provenance, or allowed writes are unclear;
- a test relies on SQLite/in-memory behavior for a PostgreSQL guarantee;
- replay, rollback, or concurrency is not established for the exercised behavior;
- a proposed workaround introduces a second Task creator/lifecycle, caller/Event-only triage, hidden retained-experience input, or unaccepted write path;
- a result would require live network/provider access, production credentials, persistent database access, scoring, or a gated capability;
- a test asserts retrieval, retained-experience use, causal value, or treatment superiority without the required consumer/attribution contract and evidence.

A stop is a design/requirements finding, not permission to weaken the expected behavior.

## 7. Next steps and authorization boundary

This document closes the documentation reconciliation and scenario/proof freeze only. It does not authorize additional execution.

Recommended next sequence:
1. Review this scenario/proof freeze against current source and exact merged test heads.
2. Review the documentation-only draft [R8 internal technical-test result-recording protocol](r8-internal-test-result-recording-protocol.md), which defines scenario/run identity, fixture/source pinning, expected/actual observations, durable-state evidence, failure classification, logs/artifacts, cleanup, retries, and final dispositions. Acceptance of that protocol does not authorize execution.
3. Review any missing scenario-specific PostgreSQL proof without broadening production scope.
4. Submit a separate request before running a new exploratory campaign or adding tests.
5. Review R8-ready entry criteria and explicit authorization separately; passing existing CI is not the state transition.

**Current disposition:** initial internal-test scope selected and technically implemented (CG-01 + C-01); current state remains Pre-R8-ready.
