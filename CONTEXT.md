# Watch — Session Context

Watch is a persistent, evidence-oriented team system. **Model intelligence is temporary; team experience is persistent.**

## Core architecture

**Worker → Proposal → application validation → Kernel/application commit → durable state.** Model output is never the authority for durable state.

Reactive and deliberative work converge on the same ordinary Task runtime. Tasks, Events, and committed records describe what actually happened; Plans describe intended work.

## Current R6 design direction (architectural principles accepted; implementation gated)

R6-G0 remains in progress; implementation has not started. The accepted architectural target is a knowledge-grounded loop: use RAG to retrieve source-traceable context from logically distinct Domain Knowledge and Team Experience cores, execute work through the ordinary Task runtime, record durable Outcomes, use LLMs to distill evidence-linked reusable abstractions through the authorized learning path, and retrieve accepted knowledge for later tasks. RAG indexes are projections, not authorities. ADR-0028 and ADR-0029 are accepted at principle level; their implementation choices remain in R6-G0.

For these decisions, read:
- [R6 entry gate](docs/development/r6-entry-gate.md) — unresolved G0 decisions and the future R6-A through R6-G sequence.
- [R6-G0 Decision Proposals](docs/development/r6-g0-decision-proposals.md) — recommended defaults for each unresolved design choice; recommendations only, not accepted decisions.
- [ADR-0028](docs/decisions/ADR-0028-rag-backed-knowledge-cores.md) — accepted RAG and Knowledge Core principles; implementation remains gated.
- [ADR-0029](docs/decisions/ADR-0029-llm-assisted-experience-distillation.md) — accepted distillation principles; implementation remains gated.

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
