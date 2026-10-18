# Watch — Architecture Revision 2

Watch is an evidence-oriented system for turning temporary model intelligence into persistent, auditable Team experience.

The central principle is:

> **Model-call intelligence is temporary. Team experience is persistent.**

A general-purpose AI worker can reason, investigate, write, compare, and propose. Watch provides the durable environment in which those temporary workers can observe the world, perform bounded work, produce outcomes, learn from experience, and improve future behavior.

## Current design direction

The approved R4 redesign supersedes the first implementation's one-action limit as the semantic definition. Its redesigned implementation is present and focused exit verification is recorded; R4 remains formally open pending the required phase-boundary merge. R5 remains paused and is not released.

A single Objective has one active accepted Strategy containing multiple concurrent perspectives and lines of work.

The emerging control model is:

~~~
Objective
   ↓
StateAssessment
   ↓
StrategyProposal
   ↓
multiple Visions
   ↓
Workstreams
   ↓
Actions
   ↓
Plan
   ↓
ordinary Tasks
   ↓
existing Task runtime
   ↓
Outcomes
   ↓
Evaluation
   ↓
Learning
   ↺
~~~

### Vision

A Vision is a bounded way of understanding part of an Objective. It defines a meaningful scope and perspective rather than acting as a simple label.

For a Python-development Objective, possible Visions include:

- Python ecosystem
- Python engineering
- computer science
- practical experimentation
- critical analysis

Different Visions may operate simultaneously.

### Workstream

A Workstream is a coherent body of related work inside a Vision.

It hides internal complexity and provides the main conceptual place for dependent Actions.

For example:

~~~
Vision: Python ecosystem

Workstream: Monitor Python changes
├── collect sources
├── compare findings
└── evaluate significance
~~~

The Workstream abstraction is intended to keep humans from having to reason about every low-level dependency.

### Action

An Action is a purposeful unit of work required by a Workstream.

Actions are intended work. Tasks are the executable runtime units created from that intent.

A single Strategy may therefore contain many Actions across many Visions.

## Concurrency and dependencies

Watch is intended to support parallel work across Visions:

~~~
Vision A ───────────┐
Vision B ───────────┼──→ same Objective
Vision C ───────────┘
~~~

Inside a Vision, Workstreams may contain Actions that depend on one another:

~~~
Action A
   ↓
Action B
   ↓
Action C
~~~

The execution runtime remains the existing Task runtime. The Control layer does not create a second scheduler or execution system.

The important separation is:

- Strategy decides which perspectives and purposeful work should be pursued.
- Vision defines scope and perspective.
- Workstream groups related work and its internal dependencies.
- Action expresses intended work.
- Plan records accepted durable execution intent.
- Task is the execution unit.
- Worker performs the Task.
- Outcome records what happened.
- Evaluation determines what was learned.

## Authority boundary

The core authority model remains unchanged:

~~~
Worker
   ↓
proposal
   ↓
application validation
   ↓
Kernel/application commit
   ↓
durable state
~~~

Workers do not directly write durable truth.

Plans are execution intent, not execution history. Tasks, Events, and Outcomes remain authoritative for what actually happened.

StateAssessment remains derived and non-authoritative.

Provenance must survive the Strategy → Vision → Workstream → Action → Plan → Task chain so later experience can be traced back to the decision that authorized it.

## Team adaptation

Watch is intended to eventually support proposals that change the Team's capabilities or structure.

For example:

~~~
Watch detects a capability gap
          ↓
Team / capability proposal
          ↓
human review
          ↓
approve / edit / reject
          ↓
Team change
~~~

The system should be able to become more capable without silently changing its own durable structure.

Structural Team changes are a separate control concern from ordinary Plan execution.

## Vision evaluation and learning

Each Vision should accumulate its own experience from the work performed through it:

~~~
Vision
   ↓
Work
   ↓
Outcomes
   ↓
Evaluation
   ↓
evidence about usefulness
   ↓
future Strategy
~~~

The intended model is cautious evaluation, not automatic causal scoring.

A successful result does not automatically prove that a Vision caused the success. Watch should accumulate evidence about what perspectives are useful under particular conditions and let future Strategy use that evidence.

## Current R4/R5 status

K0–R3 remain the completed foundation.

R4's redesigned nested Strategy implementation is present in commit `50e288a`. Its focused exit verification passed on the current R5 worktree: 44 Strategy tests, targeted Ruff, `mypy core`, `git diff --check`, and migrations to `0006_immutable_plan_actions` on a disposable PostgreSQL database. The full suite and R5 tests were not run.

R4 is not formally closed: the implementation commit is on R5 and has not crossed the documented phase-boundary merge into `main`. R5 Plan work remains **paused and not released** pending formal R4 closure and the R5 entry gate. R5 must preserve the accepted Strategy and may not invent or reinterpret its structure.

## Milestones

| Phase | Status | Purpose |
|---|---|---|
| K0 | Complete | Repository tooling and deterministic foundation |
| K1 | Complete | Smallest executable Kernel ingestion path |
| R0 | Complete | Revision 2 architecture freeze |
| R1 | Complete | Control-layer compatibility contract |
| R2 | Complete | Durable Objective model and lifecycle |
| R3 | Complete | Deterministic, read-only StateAssessment |
| R4 | Implemented; focused exit verification passed; formal closure pending | Redesigned Strategy around multiple Visions, Workstreams, and Actions |
| R5 | Paused | Durable Plan materialization after the R4 redesign |
| R6 | Later | First intelligent Control loop |
| R7 | Later | Evaluation and learning integration |
| R8 | Later | Multi-domain pressure test |
| R9 | Later | Codex-assisted production workflow |

## Technology

- Python 3.12+
- uv
- PostgreSQL 16 + pgvector
- SQLAlchemy
- Alembic
- pytest
- Ruff
- mypy

## Repository layout

~~~
core/                       Kernel and Control-layer implementation
migrations/                 Alembic migrations
tests/                      PostgreSQL integration tests
docs/                       Architecture, invariants, task specs, plans
PLAN.md                     Milestones and implementation order
CHANGE_MAP.md               Document authority mapping
Simple Explain.md           Human-readable architecture explanation
~~~

## Authority and development discipline

Original Watch documents remain authoritative for concepts that Revision 2 has not explicitly revised. Revision 2 documents govern the concepts mapped in CHANGE_MAP.md.

Do not silently reconcile conflicting specifications.

The implementation process is intentionally incremental:

1. inspect the current architecture and authoritative documents;
2. identify the smallest unresolved boundary;
3. design before implementing when authority is unclear;
4. implement the smallest reversible slice;
5. verify behavior, invariants, provenance, restartability, and concurrency;
6. only then advance to the next milestone.

The architecture should remain understandable at the conceptual level even when the implementation becomes sophisticated.
