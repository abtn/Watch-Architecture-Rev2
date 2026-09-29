# Watch — Architecture Revision 2

K0 tooling and the baseline are implemented; K1 has not begun. This repository contains Watch's architecture specifications and the initial project tooling.

## Purpose

This repository contains Watch's Revision 2 architecture and implementation plan.

Original Watch documents remain authoritative for concepts Revision 2 has not explicitly revised. Revision 2 documents are authoritative only for concepts explicitly revised and mapped in `CHANGE_MAP.md`. Codex must not silently resolve conflicting specifications; when authority is unclear, stop and report the ambiguity.

The original design already establishes a strong Kernel:

- durable records instead of shared conversation
- agents/workers propose; application code commits
- immutable snapshots and evidence validation
- explicit competing Hypotheses
- controlled Team memory
- auditable Events
- deterministic commit-time validation
- replaceable Workers

The main architectural change proposed here is to add an explicit **Control layer** as an additive, higher-level decision layer above the existing Task system. Revision 2 defines Objective as one durable entity with an explicit lifecycle; Tasks may reference it, with no ephemeral task-scoped Objective abstraction.

The central idea is:

> Watch should be a persistent adaptive software system that uses LLM workers as bounded cognitive components, rather than an agent swarm whose behavior is primarily encoded in prompts and agent personalities.

## The new model: dual-entry execution

The revised architecture keeps the original reactive execution path and adds a deliberative Control path that converges into it.

### Reactive execution path

For deterministic or routine work where the response is already known:

```text
Signal / Trigger / Scheduler / Operator
→ Task
→ Worker
→ Proposal
→ Kernel validation
→ Commit
```

Examples: `ingest_source`, `apply_decay`, routine triage, `record_outcome`, operator actions, deterministic maintenance.

This path remains valid and is not removed.

### Deliberative control path

For work where the Team must decide what to attempt next, starting from one durable Objective:

```text
Objective
→ deterministic StateAssessment
→ StrategyProposal
→ Plan
→ Task materialization
→ existing Task execution path
```

The Control layer produces ordinary Tasks. Once materialized, those Tasks use the same state machine, write scopes, budgets, validation, atomic commit, Events, and idempotency as any reactive Task. Plan membership is optional provenance metadata.

Budget ceilings are nested: TeamPolicy budget > Plan budget > Task budget. A Plan may not exceed the applicable TeamPolicy ceiling, and the allocated/remaining budgets of its materialized Tasks may not exceed the Plan envelope. Each Task's own budget remains authoritative for that Task's execution.

### Layer stack

```text
┌─────────────────────────────────────────────┐
│  LEARNING                                   │
│  Outcomes → Evaluations → LearningChanges  │
├─────────────────────────────────────────────┤
│  CONTROL (deliberative path, additive)      │
│  Objective → StateAssessment → Strategy    │
│  → Plan → Task materialization              │
├─────────────────────────────────────────────┤
│  INTELLIGENCE / WORKERS                     │
│  LLM Workers / deterministic Workers        │
├─────────────────────────────────────────────┤
│  STATE                                      │
│  World Memory / Team Memory / Provenance    │
├─────────────────────────────────────────────┤
│  INTEGRITY KERNEL                           │
│  validation / scope / atomic commit / audit │
└─────────────────────────────────────────────┘
```

The existing Kernel remains the foundation. The Control layer is one of two valid entry points, not a replacement.

## Why this change

The original plan is very good at:

> Given a Task, execute it safely.

It is less explicit about:

> Given the current state, mission, policy, constraints, and open questions, why should the system do this Task next?

Without that abstraction, Watch risks becoming a sophisticated workflow engine with LLM workers.

The Control layer makes the missing distinction explicit:

- **State** = what we currently know.
- **Policy** = how this Team is allowed/preferred to operate.
- **Strategy** = how the Team intends to approach its current situation.
- **Plan** = the bounded execution structure chosen from that strategy.
- **Task** = one executable unit.
- **Worker** = the temporary performer of that Task.

## Important scope rule

This is a **design revision workspace**, not a replacement of the current repository documents yet.

Do not edit the original Watch repository according to this folder automatically.

First use the documents here to:

1. agree on the revised abstraction,
2. write ADRs for changes that are truly architectural,
3. amend the original specifications,
4. then start implementation.

Implementation order: tooling → smallest Kernel commit path → tests → Objective → Control layer.

## Source-of-truth precedence

Original Watch documents remain authoritative for concepts Revision 2 has not explicitly revised. Revision 2 documents are authoritative only for concepts explicitly revised and mapped in `CHANGE_MAP.md`. Codex must never silently choose between conflicting specifications; if the map does not make authority clear, stop and report the ambiguity.

## What stays unchanged

The following original principles remain foundational unless a later ADR explicitly changes them:

- durable records, not shared conversation
- agents propose, code commits
- immutable Snapshots
- deterministic quote/hash validation
- no unexplained ConfidenceChange
- competing Hypotheses
- conservative scheduled Decay
- explicit SignalDisposition
- projections are never authoritative
- controlled Team memory (INV-12)
- atomic revalidation and idempotency
- human input passes through the same validation gates
- Domain packs cannot bypass the Kernel
- Triggers, scheduler, API, and task chaining remain valid Task entry points
- existing Task state machine and write scopes remain unchanged

## Documents

| Document | Purpose |
|---|---|
| `docs/01-architecture-revision.md` | Revised architecture and boundaries, including dual-entry model |
| `docs/02-control-layer.md` | Objective → assessment → strategy → plan design; validation can/cannot |
| `docs/03-runtime-model.md` | Runtime lifecycle and execution semantics for both paths |
| `docs/04-data-model-changes.md` | Proposed entities/fields and what should remain unchanged |
| `docs/05-implementation-plan.md` | Revised implementation sequence; Kernel-first |
| `docs/06-codex-vscode-workflow.md` | How to use Codex in VS Code without losing architectural control |
| `docs/07-codex-task-templates.md` | Reusable prompts/task packets for Codex |
| `docs/08-first-coding-session.md` | Exact starting sequence for the first coding sessions |
| `docs/09-migration-from-original-design.md` | How to reconcile this revision with the existing docs |
| `docs/10-test-strategy.md` | Tests that prove the architecture rather than just line coverage |
| `docs/decisions/ADR-0023-control-layer.md` | Add an explicit Control layer |
| `docs/decisions/ADR-0024-strategy-is-not-team-policy.md` | Boundary between Strategy and TeamPolicy |
| `docs/decisions/ADR-0025-plan-is-derived-execution-state.md` | Why Plan should not become another memory layer |
| `docs/decisions/ADR-0026-dual-entry-execution-model.md` | The two-path execution model |
| `AGENTS.md` | Codex/AI working contract for this revision workspace |
| `PLAN.md` | Entry point for implementation work |
