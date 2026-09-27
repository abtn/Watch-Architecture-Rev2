# Revision 2 Change Map

This map identifies the concepts explicitly revised by Revision 2 and the authoritative Revision 2 source for each. Concepts not mapped here remain governed by the original Watch documents. If a concept's authority is unclear, Codex must stop and report the ambiguity; it must not silently select a specification. See `AGENTS.md` for the source-of-truth procedure.

| Revised concept | Revision 2 authority | Scope of revision |
|---|---|---|
| Authority precedence and conflict handling | `AGENTS.md` | Original Watch documents remain authoritative for unchanged concepts; Revision 2 documents govern only mapped revisions. Codex must stop on ambiguous authority. |
| Objective | `docs/01-architecture-revision.md`, `docs/02-control-layer.md`, `docs/04-data-model-changes.md`, `docs/glossary.md` | Objective is one durable entity with an explicit lifecycle. Tasks may reference it; there is no ephemeral task-scoped Objective abstraction. |
| StateAssessment provenance | `docs/01-architecture-revision.md`, `docs/02-control-layer.md`, `docs/03-runtime-model.md`, `docs/04-data-model-changes.md` | Assessment remains derived and non-authoritative; when selecting a Strategy/Plan, preserve the exact assessment basis reconstructably using references, hash, timestamp, and when needed an immutable Snapshot. |
| StrategyProposal | `docs/01-architecture-revision.md`, `docs/02-control-layer.md`, `docs/decisions/ADR-0023-control-layer.md`, `docs/decisions/ADR-0024-strategy-is-not-team-policy.md` | Temporary structured proposal, validated for deterministic constraints; semantic wisdom is evaluated through Outcome → Evaluation → Learning. It is not TeamPolicy or Team memory. |
| Plan | `docs/01-architecture-revision.md`, `docs/02-control-layer.md`, `docs/04-data-model-changes.md`, `docs/decisions/ADR-0025-plan-is-derived-execution-state.md` | Durable intended orchestration, not execution truth. Tasks, Events, and Outcomes represent actual execution. Plan budgets are bounded by TeamPolicy; Task allocation is bounded by the Plan envelope. |
| Optional Task provenance | `docs/04-data-model-changes.md`, `docs/03-runtime-model.md`, `docs/glossary.md` | Task may optionally reference an Objective and/or Plan. Existing Task state machine, write scopes, tools, budgets, validation, commit, Event, and idempotency behavior are unchanged. |
| Dual-entry execution | `docs/decisions/ADR-0026-dual-entry-execution-model.md`, `docs/01-architecture-revision.md`, `docs/03-runtime-model.md` | Reactive entry remains valid; deliberative Control materializes ordinary Tasks and converges into the existing Task execution path. |
| Trigger behavior | `docs/decisions/ADR-0026-dual-entry-execution-model.md`, `docs/01-architecture-revision.md`, `docs/02-control-layer.md`, `docs/03-runtime-model.md` | Trigger may create a Task directly for deterministic responses, or create/activate an Objective when deliberation is needed. Not every Trigger passes through Control. |
| Control budget hierarchy | `docs/01-architecture-revision.md`, `docs/02-control-layer.md`, `docs/04-data-model-changes.md`, `docs/decisions/ADR-0025-plan-is-derived-execution-state.md`, `docs/decisions/ADR-0026-dual-entry-execution-model.md` | TeamPolicy ceiling > Plan envelope > Task budget. Plan may not exceed TeamPolicy; materialized Task allocations may not exceed Plan envelope; each Task budget governs its individual execution. |
| Implementation order | `PLAN.md`, `docs/05-implementation-plan.md`, `docs/08-first-coding-session.md` | Tooling and smallest Kernel commit path are proven before any Control implementation. |

## Original documents still authoritative outside mapped revisions

- `docs/architecture.md`
- `docs/invariants.md`
- `docs/tasks.md`
- `docs/domains.md`
- `docs/walkthrough.md`
- original ADRs, unless a mapped Revision 2 concept explicitly revises them

This map does not implicitly revise any other original behavior or schema.