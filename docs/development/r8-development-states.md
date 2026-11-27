# R8 Development States — R8-ready and Full Design

**Status:** accepted development-control model; PR [#205](https://github.com/abtn/Watch-Architecture-Rev2/pull/205) merged on 2026-11-27.
**Current project state:** pre-R8-ready; preparing the minimum working system for internal testing.
**Status authority:** `PLAN.md`. This document defines the meaning and rules of the two states; it does not independently change milestone authorization.

## 1. Purpose

Watch must reach a useful internal-testing system before every part of the long-term architecture is implemented. R8 testing is expected to reveal missing requirements, incorrect assumptions, unnecessary abstractions, and simpler ways to achieve the required behavior.

The project therefore uses two explicit development states:

1. **R8-ready** — a minimum working system that is safe, coherent, and sufficiently complete for controlled internal testing.
2. **Full Design** — the complete intended architecture and the full set of accepted contracts, implementation slices, and proofs currently planned for the R8 foundation and formal acceptance.

These are different completion bars. R8-ready is not Full Design, and neither code presence nor an internal test run proves Full Design completion.

The state model is intended to reduce premature implementation, not lower the integrity bar. A capability may be deferred; an invariant required by a capability that is actually exercised may not be bypassed.

## 2. State 1 — R8-ready (minimum working system)

### 2.1 Objective

Enable controlled internal tests of real end-to-end Watch behavior using the smallest implementation that can produce meaningful, reproducible evidence.

R8-ready is an internal development/testing state. It is not production-ready, a security certification, or formal completion of the full RW foundation.

### 2.2 Minimum capability bar

The R8-ready scope must identify and demonstrate a coherent vertical slice that includes, as applicable to the frozen internal scenarios:

- One shared Kernel/Control authority path for validating and committing durable changes. No parallel or model-authoritative write path.
- A usable Task execution path with explicit ownership of lifecycle, terminal outcomes, and supported replay/recovery behavior.
- Persistent world-memory records sufficient for the selected scenarios: Signals/source references, Threads, competing Hypotheses, EvidenceLinks, and attributable confidence changes.
- Source and Team/domain provenance sufficient to reject invalid, cross-Team, or cross-domain writes and transfers.
- A bounded way to retrieve relevant retained experience into a later Task, where the selected scenario needs retrieval, and an observable test of retrieval/Context assembly. Record what was retrieved and what the controlled Task did; retrieval alone does not demonstrate that a claim used the material or that it caused an outcome change. Do not claim claim-level knowledge use or downstream attribution without the accepted attribution mechanism and its proofs.
- Safe behavior for insufficient, irrelevant, contradictory, stale, and invalid evidence: abstain or reject rather than manufacture authority or partial writes.
- Reproducible internal fixtures, deterministic test doubles where needed, observable outcomes, and a recorded baseline for comparison.
- An isolated development/test environment using disposable databases and non-production credentials. No scored or persistent-data experiment may silently target the persistent local `watch` database.

The exact vertical slice and selected scenarios must be frozen in a short R8-ready scope record before implementation. Reuse existing code and contracts where they work. Do not build a feature solely because it appears in the Full Design target.

### 2.3 Required integrity boundary

R8-ready does not permit weakened invariants on exercised paths. At minimum:

- Model/worker output remains a proposal, never authority for durable state.
- All durable writes use the existing governed application/Kernel path.
- Task, Team, domain, provenance, and write-scope checks are applied on every relevant read/write boundary.
- Rejected operations leave no partial canonical state, duplicate terminal evidence, or corrupted history.
- Replay and concurrency are proven for the paths that the internal scenarios exercise.
- Real PostgreSQL is required for claims about PostgreSQL constraints, privileges, triggers, locking, and concurrency. SQLite or in-memory substitutes do not establish those properties.
- Runtime credentials used in tests must not be superusers. Migration/bootstrap/test-maintenance authority must be separate from the application runtime where the tested boundary depends on that separation.
- No untrusted or unsupported process may share a credential whose authority is being treated as a trusted application boundary.

If a selected scenario requires SignalDisposition or another gated RW4/RW5 capability, every accepted prerequisite, implementation authorization, and proof for that capability remains mandatory. A scenario-specific proof subset narrows which behaviors are exercised; it does not replace or relax the entry gates of a dependency. A capability may be deferred only when the scenario avoids it and uses an already-authorized governed path; record that limitation. Do not partially enable a gated feature or substitute an unaccepted write path. This R8-ready rule does not authorize implementation of RW4-4 Context retrieval: where a scenario depends on that path, its named consumer contract, own gate, and accepted Experiment A result or explicit Operator disposition before representation freeze remain required. Likewise, RW-D99/D133 attribution capabilities remain mapped to their named RW slice/proofs and separately authorized.

### 2.4 Explicitly deferrable from R8-ready

Unless the frozen scenarios demonstrate a real dependency, R8-ready may defer:

- Full SignalDisposition/matched-duplicate-deferred rollout and its complete dependency chain.
- Automatic Thread creation and dormant Thread reactivation.
- Full RW-5 decay behavior and broader lifecycle machinery.
- Production host authentication, production deployment composition, and operational hardening.
- Broad/general-purpose abstractions, schedulers, plugin systems, and domain-pack machinery not needed by the selected tests.
- Unneeded schema generalization, speculative extension points, and performance optimization beyond measured internal-test needs.
- Full scored newsroom value-harness execution until its source corpus, brief, answer key, independent outcome reference, reviewer calibration, and execution configuration are frozen.

Deferral is not deletion or rejection. Record each deferred capability, its reason, the scenario or evidence that would make it necessary, and the owner/next gate. Do not describe a deferred capability as implemented or tested.

### 2.4.1 Selected R8-ready planning direction — Path A

**Operator decision (2026-11-27): Path A is selected.** The R8-ready planning path will defer SignalDisposition and the full `triage_signal` workflow. The initial R8-ready scenarios should use existing, authorized, governed operations; no new disposition write path, caller/Event-only substitute, or partial triage rollout is permitted.

This is a planning direction, not proof that a suitable existing path already satisfies the eventual scenarios. The scenario and capability matrix in [R8-ready scope and capability matrix](r8-ready-scope-and-capability-matrix.md) must identify the exact existing entrypoints, governing contracts, and proofs. Unknown or unproven paths are blockers, not assumed capabilities. If a necessary scenario cannot be completed through an already-authorized governed path, pause and return to the Operator with the evidence; do not silently reclassify SignalDisposition as unnecessary or invent a transitional implementation.

For Path A, RW4-1B through RW4-1F and the SignalDisposition/triage dependency chain remain Full Design work. Their accepted decisions and design records are preserved; their implementation gates are neither closed nor waived. Reopen this selection only through an explicit scope decision supported by the frozen scenario and capability evidence.

### 2.5 R8-ready entry and exit

**Entry to internal testing requires:**

The scenario scope may narrow the exercised feature set, but cannot waive a predecessor gate for any capability it uses. Retrieval/Context assembly may be observed without asserting claim-level knowledge use. Any claim that retained experience was used in a claim or contributed to an outcome requires the accepted RW-D99/D133 attribution mechanism, its named RW-slice mapping, authorization, and proofs.

1. A frozen, bounded R8-ready scope and explicit authorization for the implementation/test slice.
2. A runnable end-to-end path through the shared authority boundary.
3. Passing focused tests and real-PostgreSQL proofs for the invariants relied upon by that path.
4. Verified Team/domain isolation, source provenance, safe rejection/abstention, and atomicity/replay for the exercised operations.
5. Reproducible fixtures, baseline, logs/results, exact tested SHA, and verified disposable-database cleanup.
6. A documented list of unimplemented Full Design requirements and known test limitations.

**R8-ready testing exit** is not a claim that every scenario passed. It means the system can be tested reproducibly and the findings are recorded. A scenario may fail; the failure is the purpose of testing, not grounds to weaken its expected result.

## 3. State 2 — Full Design

### 3.1 Objective

Complete and verify the full accepted architecture currently intended for the RW foundation and formal R8 acceptance, including the requirements intentionally excluded from the R8-ready minimum.

Full Design includes, as applicable to accepted decisions and the final R8 scope:

- Complete RW-0 through RW-5 contracts, implementations, integration, and formal foundation exit evidence.
- The accepted RW-4 SignalDisposition persistence, provenance, canonical duplicate arbitration, matching, durable assessment receipt, TaskRuntime atomic finalization, and all-or-nothing outcome enablement gates.
- The RW-5 shared lock helper, Team revision protocol, writer compatibility retrofit, decay behavior, and required PostgreSQL race/recovery proofs.
- RW4-4 bounded Context retrieval and RW4-5 dormant reactivation where required by accepted scope.
- The minimum accepted knowledge-use attribution needed for claims about retained experience, mapped to named implementation slices.
- The complete three-domain R8 scenarios, cross-domain isolation, failure behavior, replay/concurrency/atomicity proofs, and frozen value-harness reporting.
- Exact-head local/hosted verification, reconciled documentation, independent review, and explicit Operator acceptance.

The canonical R8 delivery plan, RW implementation/readiness plans, accepted decision records, and `PLAN.md` continue to define the detailed contracts and current status. This summary does not supersede them.

### 3.2 Full Design is a target, not a reason to overbuild

Full Design is the current architectural target, not a mandate to implement every specified future feature before R8-ready internal testing. Every Full Design requirement must still have a clear purpose, owner, dependency, and proof obligation.

A requirement that does not support an accepted invariant, user-visible behavior, or measured R8 objective should be challenged rather than implemented automatically.

## 4. How R8 testing may change the design

R8 is an architecture pressure test. Findings may justify changing an accepted design, replacing a complicated implementation with a simpler one, deferring a capability, or removing an unnecessary abstraction.

Use this controlled loop:

1. **Observe:** record the scenario, exact input/fixture, expected behavior, actual behavior, exact SHA, logs, and reproducibility.
2. **Classify:** distinguish implementation defect, missing requirement, incorrect design assumption, excessive complexity, test-fixture problem, and environment limitation.
3. **Assess impact:** identify affected invariants, persisted data, migrations, public/internal interfaces, accepted decisions, and other scenarios.
4. **Propose the smallest correction:** prefer deleting or simplifying code over adding abstractions. Preserve behavior and invariants that remain necessary.
5. **Record the decision:** update the governing spec/ADR and decision history when a contract changes. Mark superseded decisions as superseded; do not silently rewrite historical acceptance.
6. **Authorize and implement:** use a bounded implementation slice, tests first, exact scope, and separate authorization where required.
7. **Re-verify:** rerun the failed scenario and all affected regression, PostgreSQL, migration, replay, and concurrency proofs. Rebaseline only with an explicit reason and preserved comparison data.

A fundamental defect pauses the affected test path until it is understood and corrected. Do not continue scoring against a known-invalid architecture, and do not patch architecture ad hoc during a scored run.

A simpler design is preferred when it satisfies the same required behavior, authority boundaries, durability, provenance, failure semantics, and test evidence. Simpler does not mean weaker integrity.

## 5. Instructions for developers and coding agents

At the start of every R8-related task:

1. Read `PLAN.md` and this document. `PLAN.md` identifies the current state and authorization; this document explains the state boundary.
2. Confirm whether the task is **R8-ready** or **Full Design**. If not explicit, use the current state in `PLAN.md` and stop if the requested scope conflicts with it.
3. Implement only the smallest capability needed for the current state and authorized scenario.
4. Do not implement Full Design-only features merely because they are specified, accepted, or listed in a future plan.
5. Do not bypass an invariant to make a minimum slice work. If the invariant makes the slice materially larger, report the dependency and propose a smaller valid scenario or a revised design.
6. Treat accepted architecture decisions as authoritative until changed through the documented decision process; test evidence may initiate that change but does not silently amend the contract.
7. Keep implementation truth, test evidence, deferred requirements, and design proposals distinct.
8. Report what is deliberately absent, what was actually tested, what remains unproven, and what evidence would trigger the next capability.
9. Do not call R8-ready production-ready or Full Design complete. Do not claim formal R8 acceptance until the canonical R8 criteria and explicit Operator gate are satisfied.

## 6. State transitions and authority

The intended progression is:

`Pre-R8 preparation → R8-ready internal testing → Full Design completion and formal R8 acceptance`

The project may return from testing to design/implementation when evidence requires it. That is a controlled feedback loop, not a failure of the state model.

- `PLAN.md` is the sole source of current state, milestone status, and authorization.
- This document owns the definitions and agent behavior for the two states.
- `CHANGE_MAP.md` points to the authoritative documents for each concern.
- `docs/development/r8-delivery-plan.md` owns R8 scenario scope and formal acceptance criteria.
- `docs/development/rw-implementation-plan.md` and `docs/development/rw-4-readiness-and-delivery-plan.md` own their respective RW slice sequencing and proof obligations.
- Accepted ADRs/decision records own their contracts until amended through the decision process.
- Code, migrations, tests, exact Git state, and verified CI establish what is actually implemented.

No state transition, architecture change, production deployment, persistent-database operation, or implementation authorization is implied merely by this document or by a passing internal test.
