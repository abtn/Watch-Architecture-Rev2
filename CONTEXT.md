# Watch — Session Context

Watch is a persistent, evidence-oriented team system. **Model intelligence is temporary; team experience is persistent.**

## Core architecture

**Worker → Proposal → application validation → Kernel/application commit → durable state.** Model output is never authority for a durable write.

Reactive and deliberative work converge on the same ordinary Task runtime. Tasks, Events, and committed records describe what happened; Plans describe intended work.

## Current status

PLAN.md is the only authority for milestone status, gates, and next actions. Do not copy a second status tracker here.

As of 2026-11-13, R7-B B4.4 G1–G6 regression proofs are complete. G1–G5 are merged; G6 is implemented and verified in open PR [#113](https://github.com/abtn/Watch-Architecture-Rev2/pull/113). Its latest exact-head hosted CI passed on `44a31cb59588457cbaedc4863046795cea03ca3a` (run [#43394074207](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/43394074207)). B4.4 is not formally closed: documentation reconciliation and explicit Operator acceptance remain. B5, B6, and R7-C remain unauthorized. R8 remains entry-gated; its November 15 gate is not implementation authorization.

## Read the smallest relevant set

1. [PLAN.md](PLAN.md) — current milestone status, gates, and next action.
2. [CHANGE_MAP.md](CHANGE_MAP.md) — authoritative specification and implementation location for a concept.
3. [AGENTS.md](AGENTS.md) — repository operating rules and stop conditions.
4. [Documentation guide](docs/documentation-guide.md) — document roles and reading policy.
5. Read only the relevant canonical spec, ADR, Task contract, implementation plan, or test record for the requested change. Use [docs/testing.md](docs/testing.md) for verification requirements and evidence.

Do **not** read every document at session start. Historical plans and closeout records are opened only when their specific decision, invariant, or verification evidence is relevant.

## Authority rules

- PLAN.md owns current milestone status and authorization.
- CHANGE_MAP.md identifies the authority for each concept; the linked specification or accepted ADR owns the actual contract.
- ADRs record decisions, not current project status. A Proposed ADR is not accepted.
- Code presence, a passing test, or a merged implementation does not independently authorize a later phase or establish formal milestone closure.
- If authoritative sources conflict or a required gate is unclear, stop and report the exact conflict rather than silently reconciling it.

## Durable boundaries

- Workers propose; application code validates and commits.
- StateAssessment is derived, read-only, and non-authoritative.
- A Plan is immutable intended execution structure, not execution truth.
- A Task may be reactive or Plan-linked; both use the same runtime and commit gates.
- Domain packs cannot extend or bypass the Kernel.
