# ADR-0023 — Add an Explicit Control Layer

## Status

Accepted — explicit operator decision, 2026-10-20, as part of the R4 phase closure (see `PLAN.md`).

## Context

The existing Watch design is strong at durable state, deterministic validation, Task execution, and learning.

However, the architecture does not yet make the decision:

> given current state, Objective, TeamPolicy, uncertainty, and constraints, why is this Task the correct next step?

explicit enough.

Without a Control layer, increasing sophistication risks producing a large catalog of Task-specific workflows.

## Decision

Introduce an explicit Control layer as a deliberative path that converges into the existing Task system:

```text
Objective (one durable entity)
→ StateAssessment
→ accepted StrategyProposal
→ Plan
→ ordinary Tasks
```

### Subsequent R4 semantic closure — multi-perspective Strategy

The initial R4 implementation was deliberately narrower than the Control concept. Its single-action restriction is an implementation limitation, not the StrategyProposal architecture. One accepted StrategyProposal is one coordinated strategic decision for one Objective and a particular historical StateAssessment basis. It may contain multiple concurrent Visions, Workstreams, purposeful Actions, and explicit Action prerequisites.

A Vision is a bounded perspective with meaningful scope and boundaries. A Workstream groups coherent Actions for human comprehension and may summarize derived progress; it is not a scheduler, workflow engine, lifecycle, or dependency boundary. An Action is intended work, not a Task. Dependencies are Action-to-Action and may cross Workstreams or Visions. Stable identities and provenance are preserved in the accepted canonical proposal and later Plan; no standalone Strategy, Vision, Workstream, or Action entity is implied.

An Objective initially has one active accepted Strategy, and one such Strategy produces one Plan. Acceptance means deterministic legality and authorization for later Plan materialization, not strategic wisdom or effectiveness. R5 must not invent, omit, partition, or reinterpret the accepted structure without explicit authority. The accepted Event remains Task-attributed and preserves canonical content/hash and historical assessment provenance for transcript-free reconstruction. Vision usefulness may later be assessed from Outcomes and Evaluation as contextual evidence, not automatic scores or causal conclusions.

A Strategy may identify capability gaps, but Team/capability changes are separate proposals requiring human review before durable structural change; R4 does not mutate Team structure.

Objective has an explicit lifecycle; Tasks may reference it, but there is no task-scoped ephemeral Objective abstraction. StateAssessment remains derived and non-authoritative, while its exact basis is retained as reconstructable Plan/Strategy decision provenance.

The Control layer does not replace the Kernel. The Kernel remains the authority for durable state and commits. The Control layer is one of two valid execution entry points; the other is the existing reactive path (Triggers, scheduler, API, task chaining). See ADR-0026.

A Task produced by Plan materialization is an ordinary Task. Plan membership is optional provenance metadata; the Task state machine and commit path remain unchanged.

## Consequences

Positive:

- distinguishes strategy from execution
- permits one accepted strategic decision to preserve concurrent perspectives and their authorized work
- makes “why this task?” reconstructable
- supports replanning
- makes LLM planning bounded
- reduces pressure to create many persistent Agent identities

Costs:

- additional concepts
- Plan lifecycle must be defined
- Control-layer validation must be added
- dual-entry model must be kept coherent with existing Triggers and scheduler entry points (ADR-0026)

## Rejected alternatives

### Persistent Manager Agent

Rejected because durable reasoning would become entangled with a model identity and conversation state.

### Planner-only framework

Rejected because planning alone does not provide authoritative state, commit safety, or durable learning.

### Hardcoded workflow catalog

Rejected as the sole architecture because it encodes strategy in Task types instead of representing adaptive choice explicitly.
