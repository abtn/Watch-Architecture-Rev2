# Watch — Session Context

Watch is a persistent, evidence-oriented team system. **Model intelligence is temporary; team experience is persistent.**

## Core architecture

**Worker → Proposal → application validation → Kernel/application commit → durable state.** Model output is never the authority for durable state.

Reactive and deliberative work converge on the same ordinary Task runtime. Tasks, Events, and committed records describe what actually happened; Plans describe intended work.

## Current milestone snapshot (phase status in PLAN.md)

R6 is complete through R6-G. The R6-G implementation and formal closeout are merged to main; R6 verification and limitations are recorded in PLAN.md and docs/testing.md. R7-0 documentation is complete. ADR-0032 was accepted on 2026-11-04 and R7-A alone is authorized. The accepted INV-12 amendment is active in docs/invariants.md. The R7 Task/write-scope matrix documents the future contracts but does not register runtime Tasks or grant writes; R7-A will activate only its exact assessment Task through implementation. R7-B/C remain unauthorized. The R6-G approval did not authorize R7.

## Open the smallest relevant set of documents

1. [`PLAN.md`](PLAN.md) — the only source for current milestone status, gates, and next action.
2. [`docs/development/r7-entry-gate.md`](docs/development/r7-entry-gate.md), [`ADR-0032`](docs/decisions/ADR-0032-knowledge-quality-evaluation-and-lifecycle.md), [`docs/development/r7-a-implementation-plan.md`](docs/development/r7-a-implementation-plan.md), and the non-active R7 matrix in [`docs/tasks.md`](docs/tasks.md) — accepted architecture, R7-A contract, and separate phase gates.
3. [`AGENTS.md`](AGENTS.md) — repository operating rules and stop conditions.
4. [`CHANGE_MAP.md`](CHANGE_MAP.md) — where each concept is authoritatively specified.
5. [`docs/control-model.md`](docs/control-model.md) — the Revision 2 Control model.
6. Read only the specific supporting source needed for the task:
   - [`docs/invariants.md`](docs/invariants.md) — non-negotiable rules.
   - [`docs/tasks.md`](docs/tasks.md) — Task types, write scopes, and budgets.
   - [`docs/architecture.md`](docs/architecture.md) — the original/general architecture for concepts not replaced by Revision 2.
   - [`docs/glossary.md`](docs/glossary.md) and [`docs/domains.md`](docs/domains.md) — terms and domain-pack boundaries.
   - [`docs/decisions.md`](docs/decisions.md) — ADR index; open the linked ADR when its decision matters.
   - [`docs/testing.md`](docs/testing.md) — verification requirements.

Do **not** read every document at session start. Use the authority map, then follow references relevant to the requested change.

## Authority rules

- `PLAN.md` owns current milestone status; do not copy status claims into other documents.
- `CHANGE_MAP.md` names the authority for revised concepts.
- ADRs record decisions; an ADR marked `Proposed` is not an accepted decision.
- Code presence is not proof that a milestone is authorized or formally closed. Test evidence is not a substitute for a phase gate.
- If authoritative sources conflict or a required gate is unclear, stop and report the exact conflict instead of silently reconciling it.

## Durable boundaries

- Workers propose; application code validates and commits.
- `StateAssessment` is derived, read-only, and non-authoritative.
- A Plan is immutable intended execution structure, not execution truth.
- A Task may be reactive or Plan-linked; both use the same runtime and commit gates.
- Domain packs cannot extend or bypass the Kernel.
