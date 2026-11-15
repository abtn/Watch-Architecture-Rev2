# Watch — Session Context

Watch is a persistent, evidence-oriented team system. **Model intelligence is temporary; team experience is persistent.**

## Core architecture

**Worker → Proposal → application validation → Kernel/application commit → durable state.** Model output is never authority for a durable write.

Reactive and deliberative work converge on the same ordinary Task runtime. Tasks, Events, and committed records describe what happened; Plans describe intended work.

## Current status

[PLAN.md](PLAN.md) is the only authority for current milestone status, gates, and next actions.

The current path is B6 legacy-lifecycle hardening (baseline verification and read-only audit first), then the RW world-memory reasoning foundation, then R8. B5.4 is complete and closed. R8 is planned to start on November 23, 2026; that is not its completion deadline. R8 cannot start until all required foundational layers have passed their exit gate.

See the [B6 delivery plan](docs/development/r7-b-b6-legacy-lifecycle-hardening-plan.md) and [R8 delivery plan](docs/development/r8-delivery-plan.md). A roadmap entry does not itself authorize implementation.

The first RW value-harness domain is newsroom. Its proposed decision record, implementation/proof plan, and measurement contract are [RW-0](docs/development/rw-0-decision-record.md), [RW implementation plan](docs/development/rw-implementation-plan.md), and [newsroom value harness](docs/development/rw-value-harness.md). These are planning documents; RW-0 follows B6 and implementation remains separately gated.

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
