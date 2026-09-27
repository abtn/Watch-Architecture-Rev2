# ADR-0025 — Plan Is Derived Execution State

## Status

Proposed

## Context

The Control layer introduces Plan.

There is a risk that Plan becomes a second form of memory containing all strategic reasoning.

## Decision

A Plan is a bounded execution artifact.

It is derived from a durable Objective, the selected StateAssessment, StrategyProposal, and TeamPolicy. The exact assessment basis is preserved as reconstructable decision provenance (references, hash, creation timestamp, and an immutable Snapshot when necessary). This provenance is not a second authoritative state store; current world state remains distinct from historical decision context.

It is auditable and durable enough to resume execution, but it is not Team memory and it is not authoritative reality.

Actual execution is represented by Tasks, Events, and Outcomes. A Plan may be partially completed, abandoned, invalidated, or superseded without corrupting the execution record.

Budget hierarchy is `TeamPolicy ceiling > Plan envelope > Task budget`: the Plan cannot exceed the applicable TeamPolicy ceiling, the total allocated/remaining Task budgets cannot exceed the Plan envelope, and each Task's budget remains authoritative for its individual execution.

When circumstances change substantially, create a new Plan rather than silently rewriting the old one. Plan materialization simply creates ordinary Tasks that then use the existing reactive execution path (ADR-0026).

## Consequence

Adaptation becomes visible:

```text
P1 → outcome/failure → assessment → P2
```

rather than:

```text
P1 silently changes meaning
```
