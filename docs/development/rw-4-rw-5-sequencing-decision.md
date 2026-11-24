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

## 2. RW-5-first dependency order

The production implementation order is serial: RW-5 implementation/proof → RW4-1 → RW4-2 → RW4-3 → RW4-4 under its own gates → D6 reactivation and RW4-5 integrated proof. Preparation/design work may continue independently, but no second production implementation stream starts while the current one remains open.

1. **RW-5 shared contract freeze — complete in PR #182.** The bounded regression review found no blocker and exact-head CI passed. The frozen contract resolves raw PostgreSQL `as_of`, commit-only epoch high-water mark and named Operator-authorized rebase, terminal supersession of stale Tasks, audit-only observed high-water metadata, Team revision watermark, explicit revision-0 legacy-row treatment, immutable cutover baselines, pinned bounded active-Hypothesis manifests, history reconstruction, confidence-window semantics, and one canonical Task → Team → sorted Thread → sorted Hypothesis lock helper. No clock-health monitor, singleton, incident latch, or separate catch-up cap is part of the first-release contract. Existing Operator lock-mode standardization is part of the separately authorized compatibility retrofit.
2. **RW-5 implementation and proof.** Separately authorize the migration and RW3.4-adjacent WorldMemoryCommitService writer compatibility change, including existing Operator lock-mode standardization, then the deterministic decay Task boundary and TaskRuntime/Kernel execution. The migration is required; it is not included or authorized by the documentation proposal. Periodic scheduler/host invocation remains a separate RW5-P integration gate.
3. **RW4-1 SignalDisposition persistence.** Begin only after RW-5 implementation/proof is reviewed and closed and RW4-1's D3/D5 gates, proof subset, and explicit authorization are satisfied.
4. **RW4-2 triage Task boundary.** Follow RW4-1 as the next single implementation stream, with D1/D2 gates, proof subset, and explicit authorization.
5. **RW4-3 without reactivation.** Matching/commit may proceed only after its own D4/C1/D5 gates; dormant candidates remain deferred until D6 is accepted.
6. **RW4-4 and integrated proof.** Context retrieval remains separately gated; later integrate authorized reactivation, decay, post-decay retrieval, RW4-KU, Experiment A, RWN-01, and formal acceptance before R8.

RW4-1 and RW4-2 do not run in parallel with each other or with RW-5 implementation. This serial order is the Operator's review-load constraint, not a claim that every slice is technically dependent on the previous one. No implementation slice starts without its own explicit authorization.

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
