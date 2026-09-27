# Migration from the Original Design

## 1. Keep the original Kernel

Do not rewrite the existing foundation merely because the Control layer is new.

The following concepts remain useful and should stay:

- Team
- TeamPolicy
- Signal
- SignalDisposition
- Thread
- Hypothesis
- EvidenceLink
- ConfidenceChange
- Outcome
- Evaluation
- LearningChange
- Task
- Event
- Artifact
- Consultation
- Trigger
- Projection

## 2. Keep the interpretation of Task

Original:

> Task is the main bounded unit of work.

Keep this exactly.

New, additive:

> A Task may optionally be created by a Control-layer Plan.

Plan membership is optional provenance metadata. The Task state machine, write scopes, budgets, validation, atomic commit, Event emission, and idempotency rules are unchanged.

## 3. Keep Trigger

Do not remove Triggers.

A Trigger may:

1. directly create a Task when the response is deterministic and already known;
2. create or activate an Objective when the situation requires deliberation.

For simple deterministic cases, direct Task creation remains valid.

A future policy may determine which mode is appropriate for a given Trigger condition.

## 4. Dual-entry execution model

The two paths converge:

### Reactive path (existing)

```text
Signal / Trigger / Scheduler / Operator
→ Task
→ Worker
→ Proposal
→ Kernel validation
→ Commit
```

### Deliberative Control path (new)

```text
Objective
→ StateAssessment
→ StrategyProposal
→ Plan
→ Task materialization
→ existing Task execution path
```

The Control layer does not create a second execution runtime.

## 5. Keep TeamPolicy separate

Do not store Strategy in TeamPolicy.

TeamPolicy answers:

> How may/should this Team generally operate?

Strategy answers:

> How are we going to approach this particular Objective now?

## 6. Keep Team memory separate

Do not store every successful Strategy as a KnowledgeItem.

Only learning that has survived the existing Outcome → Evaluation → LearningChange path should become Team memory.

Plan is execution intent, not Team memory.

## 7. Replace “workflow-first” thinking without removing workflows

Old mental model (still valid for deterministic work):

```text
Signal
 → known Task type
 → known graph
 → result
```

New mental model for adaptive work:

```text
State + Objective
 → Assessment
 → bounded StrategyProposal
 → Plan
 → Tasks
 → results
 → re-assessment
```

Known workflows remain useful for simple paths. They are components, not the complete architecture.

## 8. Do not add five tables immediately

The safest migration path is:

```text
Objective
Plan
Task (with optional Objective/Plan FKs)
```

first.

Treat:

```text
StateAssessment
Strategy
OpenQuestion
```

as derived/proposal concepts until runtime evidence shows they require independent durability.

## 9. Proposed original-plan changes

The implementation plan becomes:

```text
K0 Kernel baseline (tooling)
K1 Smallest Kernel commit path
R0 architecture freeze
R1 Control-layer compatibility design
R2 Objective
R3 deterministic StateAssessment
R4 Strategy proposal
R5 Plan materialization
R6 first intelligent control loop
R7 evaluation/learning integration
R8 second-domain pressure test
R9 Codex production workflow
```

Infrastructure should still be added only when a real milestone forces it.

## 10. What not to migrate

Do not migrate:

- persistent Agent identities
- shared transcripts
- unrestricted planners
- model-owned database writes
- free-form autonomous policy evolution
- a requirement that every Task belong to a Plan
- a second workflow engine
- persistent Strategy/OpenQuestion entities before they are justified
