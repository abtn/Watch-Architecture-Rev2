# RW-4 / RW-5 Sequencing Decision

**Decision date:** 2026-11-24
**Decision authority:** Operator
**Status:** Approved sequencing exception; individual implementation slices remain separately gated.

## 1. Decision

RW3.4 remains implementation-complete and merged, but formal acceptance remains deferred. Its seven PARTIAL qualifications remain open exactly as recorded in the RW3.4 evidence ledger. The Operator grants a sequencing exception so RW-5 and subsequent RW-4 slices can advance under their own staged prerequisites without waiting for formal RW3.4 acceptance. Production implementation remains one serial stream.

This is a sequencing decision, not a retrospective RW3.4 acceptance and not blanket authorization for every RW-4 or RW-5 implementation slice. Each production slice still requires:
- its own accepted design and dependency gates;
- an independently reviewed requirement-to-test subset;
- explicit Operator authorization for that slice;
- exact-head CI and the required local/disposable-database verification before merge.

RW4-0 umbrella closure is not a universal prerequisite for independently gated slices.

## 2. RW4-2-first serial delivery order

The Operator's updated order is serial: RW4-2 design/implementation → RW4-1 persistence → RW-5 canonical lock-helper/Team-revision/writer retrofit → RW4-3 matching/commit → RW-5 decay implementation → RW4-4 Context retrieval → D6/RW4-5. This supersedes the RW-5-first implementation order recorded in the earlier 2026-11-24 sequencing decision. Only one production implementation stream may be active at a time.

1. **RW4-2 — trusted Task boundary and canonical identity.** Start with the lowest-risk vertical slice; expected to require no migration if D2 uses the deterministic canonical Task primary key as its database uniqueness boundary. Confirm this against the actual Task schema before freezing the slice spec. D1 and D2 are not yet accepted: freeze the host-invoked principal/grant contract, canonical Task identity, request fingerprint, atomic Task/request-Event creation, replay, and conflicting-request behavior first. No implementation until those decisions, the slice proof subset, and explicit Operator authorization are recorded.
2. **RW4-1 — SignalDisposition persistence.** Follow RW4-2 to keep the implementation stream serial and Alembic history linear. D3 and D5 remain prerequisites: reconcile terminal deferred lifecycle and Task write scopes, then freeze the disposition/reference combinations, uniqueness, attribution, and Event semantics. Treat a migration as expected; confirm exact schema impact in the slice spec.
3. **RW-5 shared lock helper, Team revision, and writer compatibility retrofit.** Implement the canonical Task → Team → sorted Thread → sorted Hypothesis lock helper, Team revision allocation, and the authorized WorldMemoryCommitService/Operator writer retrofit. This touches an accepted RW3.4 path and requires its own explicit implementation and migration authorization, writer inventory, and real-entrypoint tests. Standardize existing Operator lock modes in this same compatibility scope. This step must land before RW4-3.
4. **RW4-3 — deterministic matching and commit.** Requires accepted D4, C1, and D5, plus the shared helper from step 3. Keep first-release exclusions: no dormant-Thread reactivation, no new Thread creation, no automatic noise classification, and no near-duplicate classification.
5. **RW-5 decay implementation.** After RW4-3, implement the frozen decay Task/TaskRuntime/Kernel path against the helper and writer retrofit. Periodic scheduler/host invocation remains a separate RW5-P integration gate.
6. **RW4-4 — bounded Context retrieval.** Proceed only under its own accepted Context-consumer contract and after the Experiment A dependency is resolved by its result or an explicit Operator-approved rationale with residual uncertainty.
7. **D6 / RW4-5 — dormant reactivation and integrated proof.** Keep reactivation disabled until D6 is explicitly accepted; then prove the decay/triage race and integrated behavior.

The order is a review-load and migration-linearity constraint, not a claim that every slice is technically dependent on every predecessor. Preparation and non-production design work may continue independently. No production slice starts without its own reviewed spec, explicit authorization, exact-head CI, and Programmer-local disposable-database verification.

**Decision prerequisites at this baseline:** D1/D2 are open for RW4-2; D3/D5 are open for RW4-1; D4/C1/D5 are open for RW4-3; D6 is open for reactivation/RW4-5. The RW-5 shared contract itself is frozen, but the helper/Team revision retrofit and decay implementation remain separately unauthorized.

## 3. RW3.4 residual handling

The seven RW3.4 PARTIAL rows remain PARTIAL:
- `RW-REQ-01`: production host authentication/composition boundary;
- `RW-POL-01`: production TeamPolicy publisher/lock-serialization boundary;
- `RW-CTX-06`: broader Context tuple/state coverage;
- `RW-REPLAY-01`: duplicate write outcomes across replay states;
- `RW-RT-02`: 45-second Task deadline versus strictly-greater-than-60-second recovery threshold and related residuals;
- `RW-REC-01`: full locked Session/Task/attempt matrix;
- `RW-RP-01`: repeated recovery across all duplicate Event/write outcomes.

Do not relabel any row PASS or claim formal RW3.4 acceptance. Do not fabricate the external host-authentication or TeamPolicy-publisher integrations. Carry a residual into an RW-4/RW-5 PR when that PR changes or relies on the same contract; add only the directly relevant regression proof. Unrelated residuals remain in the RW3.4 ledger for separate disposition and do not become an automatic blocker for unrelated slices.

Preserve the fail-closed terminal-marker behavior: ambiguous duplicate/future terminal markers do not produce a terminal Outcome/Event. Do not weaken integrity guards to make recovery appear complete.

## 4. Boundaries

This decision does not authorize:
- all RW-4 or RW-5 production changes as one undivided implementation;
- RW4-0 umbrella closure by implication;
- dormant-Thread reactivation before D6;
- a new Task runtime, scheduler, or triage-triggered `update_thread` Task creator;
- live provider calls or a change to the closed provider-authorization gate;
- persistent-database operations, R7-C implementation, or R8.

`PLAN.md` remains the sole current milestone-status and authorization authority. The RW-4 readiness plan owns its staged gates; the RW implementation plan owns the overall slice sequence and proof matrix; `docs/tasks.md` owns Task shape and write scope; `docs/testing.md` owns exact verification evidence.
