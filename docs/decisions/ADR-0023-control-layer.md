# ADR-0023 — Add an Explicit Control Layer

## Status

Proposed

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
→ StrategyProposal
→ Plan
→ Tasks
```

Objective has an explicit lifecycle; Tasks may reference it, but there is no task-scoped ephemeral Objective abstraction. StateAssessment remains derived and non-authoritative, while its exact basis is retained as reconstructable Plan/Strategy decision provenance.

The Control layer does not replace the Kernel. The Kernel remains the authority for durable state and commits. The Control layer is one of two valid execution entry points; the other is the existing reactive path (Triggers, scheduler, API, task chaining). See ADR-0026.

A Task produced by Plan materialization is an ordinary Task. Plan membership is optional provenance metadata; the Task state machine and commit path remain unchanged.

## Consequences

Positive:

- distinguishes strategy from execution
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
