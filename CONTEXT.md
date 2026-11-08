# Watch — Session Context

Watch is a persistent, evidence-oriented team system. **Model intelligence is temporary; team experience is persistent.**

## Core architecture

**Worker → Proposal → application validation → Kernel/application commit → durable state.** Model output is never the authority for durable state.

Reactive and deliberative work converge on the same ordinary Task runtime. Tasks, Events, and committed records describe what actually happened; Plans describe intended work.

## Current milestone snapshot (phase status in PLAN.md)

R6 is complete through R6-G. R7-0, R7-A, R7-B B0/B1, and B2 Steps 1–8 are accepted and merged. Step 8 PR #56 merged at `58d88bafdf33e8ce1af2f5a7ba9af11bfd84cb32`; PR #57 merged at `027b9f1cb0bbd5faaaf8d6d7cc44c8359af49b31`. The merged implementation commit `027b9f1cb0bbd5faaaf8d6d7cc44c8359af49b31` passed hosted run [42479112563](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42479112563) and Operator-local exact-SHA verification (fresh migration/single-head, Ruff, Mypy, 806 tests, 77 warnings). The local disposable container was confirmed absent. Focused-only test execution, `git diff --check`, complete final diff review and formal B2 exit acceptance remain open; see `docs/testing.md`. Local verification preceded merge of the Step 9 planning PR, a recorded sequence deviation. The active approval allowlist remains exactly `create`; B3–B6 and R7-C remain separately gated. PLAN.md is the sole current status authority.

## Open the smallest relevant set of documents

1. [`PLAN.md`](PLAN.md) — the only source for current milestone status, gates, and next action.
2. [`docs/development/r7-entry-gate.md`](docs/development/r7-entry-gate.md), [`ADR-0032`](docs/decisions/ADR-0032-knowledge-quality-evaluation-and-lifecycle.md), [`docs/development/r7-a-implementation-plan.md`](docs/development/r7-a-implementation-plan.md), [`docs/development/r7-b-implementation-plan.md`](docs/development/r7-b-implementation-plan.md), and [`docs/tasks.md`](docs/tasks.md) — accepted architecture, completed R7-A contract and non-authorizing R7-B preparation.
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
