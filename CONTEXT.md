# Watch — Session Context

Watch is a persistent, evidence-oriented team system. **Model intelligence is temporary; team experience is persistent.**

## Core architecture

**Worker → Proposal → application validation → Kernel/application commit → durable state.** Model output is never the authority for durable state.

Reactive and deliberative work converge on the same ordinary Task runtime. Tasks, Events, and committed records describe what actually happened; Plans describe intended work.

## Current R6 design direction (architectural principles accepted; phase status in PLAN.md)

R6-G0 and R6-A through R6-E are complete. PR #28 merged on 2026-11-01; R6-E's three checkpoints — bounded Task Context assembly, Context-bound model-backed StrategyProposer, and Task-attributed generation cost reservation/reconciliation — are integrated and operator/hosted verified. Cloudflare Workers AI Llama 3.1 8B FP8 is authorized for R6-E only and remains outside automatic Task dispatch. R6-F is planned; Step 0 creates branch `r6f-experience-distillation` and the detailed [four-checkpoint implementation plan](docs/development/r6-f-implementation-plan.md). R6-F implementation has not started, and its open design decisions must be resolved before the first migration/provider call. R6-G remains the integrated exit gate. ADR-0027 remains Proposed. See [`PLAN.md`](PLAN.md) for the authoritative current status.

For these decisions, read:
- [R6 entry gate](docs/development/r6-entry-gate.md) — accepted G0 decisions and scoped R6-A through R6-G acceptance criteria.
- [R6-F implementation plan](docs/development/r6-f-implementation-plan.md) — four technical checkpoints, open design decisions, and verification gates.
- [R6-G0 Decision Record](docs/development/r6-g0-decision-proposals.md) — accepted G0 defaults and deliberately staged provider choices.
- [ADR-0028](docs/decisions/ADR-0028-rag-backed-knowledge-cores.md) — accepted RAG and Knowledge Core principles; implementation remains gated.
- [ADR-0029](docs/decisions/ADR-0029-llm-assisted-experience-distillation.md) — accepted distillation contract; implementation remains gated.
- [ADR-0030](docs/decisions/ADR-0030-r6-bounded-execution-source-safety-outcome.md) — accepted Task lifecycle, source-fetch safety, and terminal Outcome contract.

## Open the smallest relevant set of documents

1. [`PLAN.md`](PLAN.md) — the only source for current milestone status, gates, and next action.
2. [`AGENTS.md`](AGENTS.md) — repository operating rules and stop conditions.
3. [`CHANGE_MAP.md`](CHANGE_MAP.md) — where each concept is authoritatively specified.
4. [`docs/control-model.md`](docs/control-model.md) — the Revision 2 Control model.
5. Read only the specific supporting source needed for the task:
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
