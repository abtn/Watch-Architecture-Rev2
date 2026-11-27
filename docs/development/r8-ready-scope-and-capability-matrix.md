# R8-ready Path A — Scope and Capability Matrix

**Status:** planning record opened by Operator decision on 2026-11-27. Path A is selected; candidate scenarios and capability classifications are not yet frozen.
**Current state:** Pre-R8-ready. This document does not authorize implementation, internal testing, database operations, or a state transition.
**Status authority:** [`PLAN.md`](../../PLAN.md).
**State/behavior authority:** [R8 development states](r8-development-states.md) and [R8 delivery plan](r8-delivery-plan.md).

## 1. Selected planning decision

Path A is selected for the initial R8-ready effort:

- Defer SignalDisposition and the complete `triage_signal` workflow from R8-ready.
- Prefer existing, already-authorized governed operations for the candidate internal scenarios.
- Do not introduce a caller/Event-only substitute, an ad-hoc disposition write, a second Task lifecycle authority, or a partial triage rollout.
- Preserve all accepted integrity, provenance, authorization, Team/domain isolation, transaction, replay, and concurrency guarantees for every capability actually exercised.

This is a scope direction, not a verified feasibility claim. The actual scenarios have not yet been frozen, and no existing path is presumed suitable until its exact entrypoint, contract, implementation, and proofs are inspected.

If a candidate scenario requires SignalDisposition or any other gated capability, stop that scenario and return with the concrete dependency and evidence. Do not silently change Path A or weaken a gate. Reopening the scope requires an explicit Operator decision.

## 2. Ordered planning work

1. **Select candidate scenarios.** Describe observable Watch behavior, input, expected durable effects, expected safe failure/abstention, and the question the test should answer.
2. **Trace each scenario end to end.** Identify the exact public/application entrypoint, Task creator, Kernel/Control boundary, TaskRuntime finalizer, persistence path, and any retrieval/Context consumer.
3. **Map required capabilities to authority.** Link each operation to its accepted contract/decision record, implementation source, migration/schema dependency, and owner.
4. **Audit the relied-upon invariants.** Check Team/domain isolation, source provenance, authorization, write scope, atomicity, rollback, replay, and concurrency. Use real PostgreSQL evidence for database guarantees.
5. **Classify every capability.** Use only `Required`, `Not required`, `Unknown`, or `Blocked`. `Unknown` is not a pass and cannot be treated as deferred.
6. **Freeze the bounded scope and deferment register.** Record limitations, proof subset, exact source baseline, fixtures, and the trigger/owner for reconsidering each deferment.
7. **Submit the implementation authorization request.** Only after the scope is reviewed; name exact files/paths, behavior, tests, database changes, rollback, and verification.
8. **Complete R8-ready entry review.** Require exact-SHA evidence, disposable PostgreSQL where applicable, repeatable fixtures, logs/baseline, cleanup, limitations, and explicit authorization in `PLAN.md`.

## 3. Scenario register

No scenario is preselected by this document. Add one row per candidate and freeze only after the Operator accepts the resulting bounded scope.

| ID | Scenario / user-visible behavior | Input and expected durable effect | Safe failure / abstention | Candidate entrypoint | Status |
|---|---|---|---|---|---|
| S-01 | TBD | TBD | TBD | TBD | Unknown |

## 4. Capability-to-scenario matrix

Record one row for each capability used or potentially needed by each scenario. Do not infer implementation from a design document or infer proof from a passing unit test.

| Scenario | Capability / operation | Classification | Exact entrypoint and source SHA | Governing contract / decision | Required invariants and proofs | Limitation / next action |
|---|---|---|---|---|---|---|
| S-01 | Shared Kernel/Control authority | Unknown | TBD | TBD | Authority, caller authorization, allowed writes, rejection/no partial writes | Trace exact path |
| S-01 | Task creation and TaskRuntime lifecycle | Unknown | TBD | TBD | Identity, single lifecycle authority, terminal atomicity, replay/recovery | Trace exact creator/finalizer |
| S-01 | Signal/source provenance and Team/domain isolation | Unknown | TBD | TBD | Source integrity, Team/domain scoping, invalid/cross-Team rejection | Trace exact persistence path |
| S-01 | Thread/Hypothesis/EvidenceLink operations | Unknown | TBD | TBD | Attribution, valid transitions, evidence integrity, confidence cause | Trace exact write path |
| S-01 | Context retrieval / retained experience | Unknown | TBD | TBD | Consumer contract, bounded retrieval, provenance, snapshot/replay; claim-use attribution only if asserted | Determine whether scenario needs retrieval |
| S-01 | SignalDisposition / `triage_signal` | Not required under selected Path A unless scenario evidence contradicts the scope | N/A | RW4-1B / RW4-2 accepted design records | No disposition write or partial triage rollout | Deferred Full Design work; reopen only by explicit scope decision |
| S-01 | PostgreSQL roles, migrations, disposable DB isolation | Unknown | TBD | RW4-1B role boundary and R8-ready entry criteria | Non-superuser runtime; separate migration authority; actual DB constraints/locks proven where relied upon | Inspect actual test/runtime path |

Replace the illustrative S-01 rows with the actual candidate scenarios and exact source evidence. Do not leave any `Unknown` classification in a frozen scope.

## 5. Path A deferment register

| Deferred capability | Why it is deferred | Reopen trigger | Preserved gate / owner |
|---|---|---|---|
| SignalDisposition persistence and `triage_signal` matched/duplicate/deferred outcomes | Not assumed necessary for the initial bounded R8-ready scenarios; Path A uses existing governed operations | A frozen scenario demonstrably requires this capability and no existing authorized path can satisfy it | RW4-1B through RW4-1F and RW4-2 Stage B/RW-5/RW4-3 prerequisites remain binding; issue #199 remains open |
| Dormant Thread reactivation and broader RW-5 behavior | Not required unless a selected scenario exercises it | Scenario needs the capability | Existing RW-5/RW4-5 contracts and separate gates |
| Claim-level knowledge-use attribution | Not asserted by retrieval/Context assembly alone | Scenario makes a claim-level use or outcome-attribution assertion | RW-D99/D133 mapped slice, authorization, and proofs |
| Formal/scored newsroom value-harness execution | Separate from exploratory internal testing | Full Design foundation exit and frozen corpus/scoring package | R8 delivery plan and RW-0 acceptance gates |

## 6. Non-negotiable stop conditions

Pause the affected scenario if:

- No existing governed entrypoint can perform the required operation.
- Caller authority, Task ownership, provenance, Team/domain isolation, or allowed-write scope is unclear.
- A required invariant depends only on an unproven design statement or an in-memory/SQLite substitute for PostgreSQL behavior.
- Atomicity, replay, or concurrency behavior is not established for the exercised path.
- A requested result would require partial SignalDisposition/triage enablement or a new unaccepted write path.
- The scenario depends on RW4-4 retrieval or RW-D99/D133 attribution without its own accepted consumer contract, gate, authorization, and proofs.

A stop is a scope/design finding, not permission to improvise a workaround.

## 7. Freeze record (complete only after review)

- Accepted scenario IDs: TBD
- Exact `main` baseline SHA: TBD
- Relevant Alembic head: TBD
- Existing governed entrypoints: TBD
- Required capability set: TBD
- Deferred capability set and reopen triggers: TBD
- Required PostgreSQL proof set: TBD
- Fixtures, baseline, and expected outputs: TBD
- Known limitations: TBD
- Implementation authorization: Not granted
- R8-ready internal-testing authorization: Not granted
