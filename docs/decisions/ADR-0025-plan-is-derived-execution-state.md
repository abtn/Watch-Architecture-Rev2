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

### R5 semantic closure (subsequent decision)

A Plan belongs to exactly one Objective and is durable bounded intent, not execution history, Strategy memory, StateAssessment, a workflow engine, or a second runtime. Its selected proposal and assessment provenance, intended action definitions/identities, dependencies, budget envelope, completion/stop conditions are immutable after creation. Replanning creates a new Plan; supersession references and stops the old Plan without rewriting its intent.

Plan creation, all initial ordinary Tasks, and the attributable creation Event commit atomically. Each immutable action maps to at most one Task and, once materialized, exactly one. Nullable `Task.plan_id` and `Task.plan_action_id` provide this mapping; action identity is stable and unique within the Plan. No PlanAction entity is required.

The creating Task's existing `policy_version` records which policy was considered at creation; there is no separate Plan policy pin. Later operations use their applicable policy version. Policy changes do not rewrite Plan intent or existing Task policy semantics.

Dependencies are explicit acyclic prerequisites between actions in the same Plan. The existing Task admission/claim path prevents a dependent Task from starting before prerequisite Tasks are `done`; failed prerequisites keep dependents ineligible until the Plan is stopped or replanned. This adds no Task state, separate scheduler, or runtime.

Lifecycle is `active → completed | stopped`; terminal Plans cannot reopen. `stopped_reason` is `abandoned`, `invalidated`, or `superseded`. Progress is derived from Tasks. Completion requires each intended action to have exactly one linked Task in `done` status and the declared completion condition to be satisfied by durable records. Lifecycle transitions are explicit and application-controlled.

The narrow `create_plan` operation follows worker proposal → application validation → Kernel/application commit. It verifies the accepted proposal Event/hash, Objective/Team ownership, supported actions, dependencies, applicable policy constraints, budgets, and idempotency. It may create only the Plan, its initial ordinary Tasks, and explicitly scoped audit Events; it cannot change TeamPolicy or memory or create Strategy/StateAssessment entities.

### Subsequent R4 semantic closure — accepted Strategy source

R4 was reopened after the initial R4 implementation. The approved semantic closure establishes that one accepted StrategyProposal contains the complete coordinated strategic decision for one Objective and a historical StateAssessment basis. It may include multiple concurrent Visions, Workstreams, Actions, and explicit Action-to-Action prerequisites, including cross-Workstream/Vision prerequisites. The existing one-action R4 code is an implementation limitation, not this semantic contract.

Initially one Objective has one active accepted Strategy and one accepted Strategy produces one Plan. Plan intent preserves the accepted structure; R5 must not invent, omit, partition, or reinterpret it without explicit authority. A Vision is a bounded perspective; a Workstream groups coherent Actions for human comprehension but is not a dependency or execution boundary; an Action is purposeful intent, not conceptually a Task. Stable identities/provenance are required, but separate Strategy/Vision/Workstream/Action entities are not implied.

The accepted canonical proposal and hash, Task attribution, and exact historical assessment provenance remain recoverable without a transcript. Future Vision-level Evaluation may gather contextual evidence about usefulness; it must not equate correlation with causation or compute unsupported automatic scores. Team/capability changes remain separate proposals requiring human review before durable change.

## Consequence

Adaptation becomes visible:

```text
P1 → outcome/failure → assessment → P2
```

rather than:

```text
P1 silently changes meaning
```
