# R8-ready C-01 — One-source scenario freeze

**Status:** scenario definition was frozen before implementation; the test-only integration and its evidence follow-ups are now merged and reconciled in §9. This document does not authorize production implementation or expand the tested scenario.
**Development state:** Pre-R8-ready. CG-01 is the completed test-only baseline; C-01 is implemented and merged as a deterministic test-only integration. Neither is a production experiment, treatment condition, or R8-ready acceptance.
**Baseline:** `main` at `c1008b20eda49b53a1f44256c7d14de8065ed4db`.
**Authority:** `PLAN.md`, [R8 development states](r8-development-states.md), [R8-ready Path A scope matrix](r8-ready-scope-and-capability-matrix.md), [Control-Group foundation plan](r8-ready-internal-test-foundation-plan.md), and [C-01 source-audit preparation](r8-ready-c01-intake-to-operator-update-preparation.md).

## 1. Frozen question and scope

**Question:** Can one active Team, with one explicitly configured and policy-pinned source, materialize an ordinary source-ingestion Task through the existing PlanService/Control Room path; fetch deterministic synthetic bytes through the existing injected fetcher seam; commit the immutable Signal/Snapshot and source-attributed intake evidence through IngestionService and TaskRuntime; and then let an authenticated Operator cite that exact ingested evidence in a low-confidence Hypothesis on a pre-existing active Thread in the same Team/domain?

The proof is about a traceable, governed technical path. It does not prove that the source is true, relevant, representative, or causally responsible for a later outcome.

**Frozen cardinality:** one Team, one TeamPolicy version, one configured HTTPS origin, one Objective, one accepted Strategy proposal, one Plan, one PlanAction, one materialized `ingest_source` Task, one ingested Signal/Snapshot, one pre-existing active Thread, and one Operator update request.

## 2. Scenario inputs

| Input | Frozen definition |
|---|---|
| Team | Fresh, active test Team; one stable test domain shared by the source Signal and target Thread |
| TeamPolicy | One explicit policy version pinned by the Plan/Task; `rules.sources` contains exactly the one configured `origin_url` + `source_type` pair |
| Source URL | A unique HTTPS test URL under `news.example.test`, generated per test; never contacted over the network |
| Source type | `rss`, matching the existing dispatcher fixture convention |
| Objective | One active Objective describing collection of the configured source |
| Strategy | One accepted nested Vision → Workstream → Action proposal; exactly one `ingest_source` action, one configured URL/type pair, no prerequisites, `max_tasks=1`, completion condition `configured_source_ingested` |
| Thread | One pre-existing active Thread, fixture-seeded on the same Team/domain; Thread creation is not part of C-01 |
| Fetch result | Fixed synthetic RSS-like bytes returned by the existing `FakeFetcher`; fixed content and hash expectations; no live fetcher/provider |
| Operator | One authenticated test principal with the exact Team-level `operator_update` grant |
| Operator evidence | Exact quote and offsets computed from the bytes of the Snapshot produced by this same scenario |

The exact source URL and fixture UUIDs are generated per test. The response bytes, source type, quote, and expected hash are deterministic. Do not use real publisher content or a real external URL.

## 3. Required execution path

1. **Prepare the governed Plan input.** Reuse the existing `plan_request` setup pattern from `tests/test_plans.py`: active Team and Objective, pinned TeamPolicy, and the ordinary proposal/Plan-creation prerequisite Tasks. Configure the single source in the policy before the assessment/proposal is accepted.
2. **Accept one Strategy proposal.** Reuse `FakeStrategyWorker` / `StrategyService.submit` and the existing nested Strategy proposal contract. Verify the accepted proposal action carries the exact configured URL and source type.
3. **Materialize through PlanService.** Call `PlanService.create`; do not insert the source Task or PlanAction directly. The resulting PlanAction and `ingest_source` Task must be materialized by the existing PlanService → Control Room operation. Verify the Task's `plan_id`, `plan_action_id`, Team, Objective, and policy-version pin.
4. **Complete the Plan-creation Task through TaskRuntime.** Reuse the existing terminalization pattern in `tests/test_plans.py`; do not directly set Task status or fabricate a terminal Outcome.
5. **Dispatch the source Task.** Reuse the existing `FakeFetcher` pattern from `tests/test_r6b_dispatcher.py`. Invoke `TaskDispatcher.dispatch` for the Plan-materialized Task. Assert exactly one fetch request with the PlanAction's URL and source type.
6. **Verify ingestion and lifecycle.** Confirm the committed Signal and immutable Snapshot match the exact Team/domain, origin URL, source type, content bytes/hash, and source Task attribution. Confirm TaskRuntime's terminal Task/Outcome/Event evidence through read-side queries. Inspect and account for the existing evaluation follow-on behavior; do not delete, suppress, or reclassify it to simplify the test.
7. **Submit the authenticated Operator update.** Build the evidence quote and offsets from the actual ingested Snapshot bytes. Call `OperatorApplicationAdapter.operator_update` with the pre-existing active Thread and exact same-Team Signal/Snapshot. Do not insert the Operator request Task directly; the application path must create it through Control Room and let TaskRuntime own its lifecycle.
8. **Verify replay and baseline boundary.** Verify the exact Signal/Snapshot reference, Hypothesis, EvidenceLink, quote/offset/hash, request/commit Events, terminal Outcome, and replay identity/no duplicate writes. Assert no `TeamExperienceChunk` is supplied, retrieved, or created for the Team; do not create a fake empty Context.

## 4. Expected durable evidence

### Plan and source intake

- One accepted Strategy proposal bound to the active Objective and pinned TeamPolicy version.
- One Plan and one immutable PlanAction containing the exact source identity.
- One Plan-materialized `ingest_source` Task created through Control Room.
- One successful source fetch through the injected fake only.
- One immutable Signal referencing the exact Snapshot bytes/hash and source origin/type.
- One source-attributed intake Event and the TaskRuntime terminal evidence for the source Task.
- Any existing TaskRuntime evaluation follow-on remains visible and is checked against its established contract.

### Operator update

- One ordinary `operator_update` request Task created through Control Room.
- One low-confidence Hypothesis on the pre-existing active Thread.
- One EvidenceLink to the exact Signal/Snapshot created by this source-intake path.
- Exact quote, offsets, and content hash validated against immutable Snapshot bytes.
- The existing commit/rejection Event and terminal Outcome evidence.
- Exact request replay preserves Task/Outcome identity and creates no duplicate Signal, Hypothesis, or EvidenceLink.

Do not assert undocumented Event payload fields or assume the exact evaluation follow-on count without first matching the current TaskRuntime implementation and its existing tests.

## 5. Safe-failure proof matrix

| Boundary | Required failure proof | Expected safety property |
|---|---|---|
| Policy allowlist | Proposed source not in the pinned TeamPolicy | Plan materialization is rejected; no source Task is materialized |
| Durable source identity | Missing/malformed PlanAction or unsupported Task source identity | Dispatcher rejects before admission; fetcher is not called and no attempt is consumed |
| Fetch | Deterministic fetch failure | Existing TaskRuntime retry/failure contract is followed; no fabricated Signal/Snapshot success |
| Content integrity | Ingestion hash mismatch | Ingestion rejects; no mismatched Signal/Snapshot or success Event is committed |
| Team/domain provenance | Cross-Team or wrong-domain Signal/Thread reference | Operator update fails closed; no partial business writes |
| Authorization | Missing or wrong Team/action grant | No Operator request/business mutation is created |
| Quote integrity | Quote/offset mismatch against immutable Snapshot | Evidence proposal is rejected; no invalid EvidenceLink is committed |
| Idempotency | Exact replay and conflicting key reuse | Exact replay is idempotent; conflicting reuse fails closed |
| Database atomicity | Injected persistence failure at an already-uncovered integrated boundary | No partial business proposal or false terminal success; reuse existing rollback proofs where they already cover the boundary |

Do not duplicate the restricted-fetcher URL/DNS/redirect/size suite, component ingestion rollback tests, Operator authorization/quote tests, or TaskRuntime lifecycle suite. Add an integrated failure test only when source inspection shows a boundary that the existing proofs do not cover.

## 6. Explicit exclusions

- Multiple sources, multiple origins, cross-origin canonicalization, or near-duplicate arbitration.
- RW4-3 Team-wide canonical Signal arbitration.
- RW4-4 retrieval/Context, retained-experience use, or claim-level knowledge-use assertions.
- SignalDisposition, triage, Thread creation, RW-5 decay, or new Task authority.
- Live network, publisher material, production credentials, or persistent local/production database writes.
- Experiment/ControlGroup production models, treatment assignment, scoring, RWN-01, formal R8, or R8-ready transition.

The one-origin ingestion deduplication behavior must not be represented as Team-wide canonicalization.

## 7. Implementation and verification sequence (historical plan; completed by PRs #215/#216)

1. Reconfirm current `main` and the exact preparation baseline before opening an implementation branch.
2. Inspect the current `plan_request`, Strategy proposal, PlanService, TaskDispatcher, IngestionService, TaskRuntime evaluation follow-on, and Operator application contracts; resolve any drift from this freeze.
3. Compose one disposable-PostgreSQL integration test from existing fixtures and fakes. Avoid a general-purpose C-01 harness or new production abstractions.
4. Run the new integration test first, then focused PlanService, dispatcher, ingestion, TaskRuntime/evaluation, Operator application, and WorldMemory suites.
5. Run Ruff, Mypy, migration-head verification, whitespace, and the full exact-head hosted CI suite.
6. Independently review for direct Task writes, Task lifecycle bypass, policy-pin drift, source-identity substitution, live network use, transaction ownership changes, hidden experience inputs, and unrelated refactors.
7. Record exact tested SHA, database/test evidence, and any unproven boundary. Stop on any scope or architecture condition in the C-01 preparation document.

**Historical exit:** the one-source scenario and proof boundary were frozen for a separate implementation proposal. The implementation was later authorized separately and completed as recorded in §9.

## 8. Historical implementation authorization gate (satisfied before PR #215)

Before implementation, return with a separate, explicit authorization request that names:

- exact files to change;
- the one integrated scenario and failure cases to implement;
- expected database impact (expected none: tests only, disposable PostgreSQL);
- rollback approach;
- exact local/hosted verification commands and acceptance criteria;
- all known limitations and any unresolved Unknown/Blocked classification.

The separate implementation authorization was granted before PR #215. This historical gate is closed for the bounded test-only implementation recorded in §9; it does not authorize any expansion or production implementation.


## 9. Implementation and verification reconciliation (2026-11-28)

The frozen scenario was implemented as a test-only integration and merged:

- Implementation: PR [#215](https://github.com/abtn/Watch-Architecture-Rev2/pull/215), exact tested head `b34f48545325b6f34fd73a30dd78c660a91340b0`, merge commit `e83101cfffa51897327a3651087f2ec464329115`. Exact-head CI #2355 passed PostgreSQL setup/role provisioning, migrations, Ruff, Mypy, whitespace, and the full test suite.
- Evidence correction: PR [#216](https://github.com/abtn/Watch-Architecture-Rev2/pull/216), exact tested head `d787d2142645520ac2773326c2f32e20dec460a5`, merge commit `ffa3703be22a7e8e8078582f287e8acb46031241`. It asserts exactly one task_completed Event for both source and Operator Tasks and rechecks request/commit/completion Event counts after replay. Exact-head CI #2357 passed.
- Documentation reconciliation: PRs [#217](https://github.com/abtn/Watch-Architecture-Rev2/pull/217) and [#218](https://github.com/abtn/Watch-Architecture-Rev2/pull/218) record the integrated success-path proof, mapped component failure proofs, and corrected current outcome wording. PR #217 post-merge main CI passed.
- Current main baseline for this reconciliation: `c648892e4896113700c8103397be01c11c0d22ed`.

**Current disposition:** C-01 is implemented and technically verified as a one-source test-only integration. Its frozen limitations remain: pre-existing active Thread, one configured source, deterministic fake fetcher, no live network/provider, no retrieval/Context, no retained-experience use, no cross-origin canonicalization, no triage/disposition, no scoring, and no R8-ready transition. This implementation record does not expand the original scenario or authorize new production behavior.
