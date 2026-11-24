# RW-4 / RW-5 Sequencing Decision

**Decision date:** 2026-11-24  
**Decision authority:** Operator  
**Status:** Approved sequencing exception; individual implementation slices remain separately gated.

## 1. Decision

RW3.4 remains implementation-complete and merged, but formal acceptance remains deferred. Its seven PARTIAL qualifications remain open exactly as recorded in the RW3.4 evidence ledger. The Operator grants a sequencing exception so that RW-4 and RW-5 can advance under their own staged prerequisites without waiting for formal RW3.4 acceptance.

This is a sequencing decision, not a retrospective RW3.4 acceptance and not blanket authorization for every RW-4 or RW-5 implementation slice. Each production slice still requires:
- its own accepted design and dependency gates;
- an independently reviewed requirement-to-test subset;
- explicit Operator authorization for that slice;
- exact-head CI and the required local/disposable-database verification before merge.

RW4-0 umbrella closure is not a universal prerequisite for independently gated slices.

## 2. RW-5-first dependency order

Start with the shared timestamp, decay, and concurrency contract needed by both workstreams. Do not wait for all of RW-5 to finish before starting independently ready RW-4 slices.

1. **RW-5 shared contract first.** Resolve and document the authoritative clock/as-of instant, UTC handling, decay-window boundary semantics, the meaning and permitted updates of `Hypothesis.last_touched_at`, the records locked by decay and triage, common lock order, under-lock revalidation, decay-first/triage-first race outcomes, replay/idempotency, and at-most-one lifecycle Event behavior. These are design decisions to be reviewed; this record does not silently choose unresolved values.
2. **RW4-1 and RW4-2 may progress independently** as soon as their own gates are met: D3/D5 for persistence and D1/D2 for the Task boundary/identity, with the Task/write-scope reconciliation and proof subsets reviewed. They do not wait for completion of RW-5.
3. **RW-5 implementation and proof** follow the accepted shared contract, using the existing TaskRuntime and existing commit path. No second runtime, scheduler, or lifecycle authority.
4. **RW4-3 may initially exclude dormant-Thread reactivation.** Matching/commit requires D4 evidence (or an explicitly accepted narrower deterministic subset), C1 receipt/recovery, and D5 disposition semantics. Until D6 is accepted, a dormant candidate must not be reactivated or receive a `matched` result that implies reactivation; use the accepted terminal `deferred` disposition and reason.
5. **RW4-4 remains separately gated** by its named Context consumer, provenance, bounds, overflow, snapshot/manifest and replay contract. Experiment A informs the representation choice: before freezing it, record either the accepted experiment result or an explicit Operator rationale with residual uncertainty.
6. **RW4 reactivation and RW4-5 integrated proof come after D6 and RW-5 behavior are available.** Prove both race orders, under-lock revalidation, at-most-one reactivation Event, and retrieval against canonical post-decay state.

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
