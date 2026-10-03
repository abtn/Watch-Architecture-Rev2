# R0 Freeze Contract

## 1. Purpose

This contract freezes the architectural relationships that future Watch work
must preserve while deliberately leaving implementation choices and empirical
questions open.

> R0 freezes the current architecture as a testable hypothesis; it does not
> claim that the hypothesis has been empirically validated.

The authority of a concept remains governed by `CHANGE_MAP.md`: original Watch
documents govern unmapped concepts, and Revision 2 documents govern only their
explicitly mapped revisions. This contract records the R0 boundary; it does not
silently replace those sources.

## 2. Architectural objective

> Watch is a persistent environment for developing domain expertise around
> general-purpose AI through durable experience, evaluation, and controlled
> learning.

This is a conceptual goal, not a proven capability. In particular, the
architecture does not yet demonstrate that accumulated experience improves
performance, generalizes, remains useful across models, or produces reliable
learning.

## 3. Frozen architectural model

The following is the stable high-level model. Its inclusion freezes the
relationships among these concepts, not the completion status of every
component.

```text
WORLD
Signals
Snapshots
Threads
Hypotheses
Evidence
Confidence
Outcomes

WORK
Objective
StateAssessment
StrategyProposal
Plan
Task
Worker

EXPERIENCE
Outcome
Evaluation
LearningChange
KnowledgeItem
TeamPolicy

GOVERNANCE
Proposal
Validation
Commit
Event
Kernel
```

The Kernel, Task boundary, immutable Snapshot handling, and a K1 ingestion
slice are implemented. Objective, StateAssessment, StrategyProposal, Plan,
and their runtime are specified architecture, not implemented Control-layer
behavior. The WORLD and EXPERIENCE names are conceptual layers: an Outcome can
be an observed world-facing result and is also the input to recorded Team
experience; this does not collapse the two memory layers.

## 4. Frozen architectural relationships

- **Worker → Proposal.** Workers propose changes. They do not directly commit
  durable state.
- **Proposal → Validation → Commit.** Application and Kernel code validate
  durable changes. The commit boundary is authoritative.
- **Task as execution unit.** Tasks remain the common execution unit for
  bounded work, including its write, tool, and budget scope.
- **Dual-entry execution.** Reactive and deliberative work both eventually
  become ordinary Tasks:

  ```text
  Reactive
  Signal / Trigger / Scheduler / Operator
  → Task

  Deliberative
  Objective
  → StateAssessment
  → StrategyProposal
  → Plan
  → Task
  ```

- **Single execution runtime.** Control materializes or manages Tasks but
  must not create a second execution system or commit kernel.
- **Plan semantics.** A Plan is execution intent. Tasks, Events, and Outcomes
  represent execution truth; changes to a Plan do not rewrite that history.
- **StateAssessment semantics.** A StateAssessment is derived and
  non-authoritative. Its decision basis is preserved reconstructably when a
  Strategy or Plan is selected, without making it a competing source of truth.
- **Strategy semantics.** Strategy is situational intent. Strategy is not
  TeamPolicy and is not Team memory.
- **World memory vs. Team learning.** World understanding and accumulated Team
  experience remain separate conceptual layers. Revisions to one must not be
  represented as an implicit revision to the other.
- **Learning path.** Learning proceeds through:

  ```text
  Outcome
  → Evaluation
  → LearningChange
  → KnowledgeItem / TeamPolicy
  ```

  This path provides controlled change; it does not automatically guarantee
  good learning.
- **Provenance.** Durable state remains attributable to Tasks and Events.
  Watch preserves provenance around outcomes and evaluations, but causal
  attribution remains a future epistemic problem. Provenance establishes who
  performed the Task, what was observed, what Outcome was recorded, and what
  Evaluation was produced; it does not establish what actually caused the
  Outcome.
- **Evidence.** Snapshot integrity is not quote verification; quote
  verification is not source reliability; source reliability is not claim
  truth. The architecture protects evidence provenance and integrity, not a
  universal truth oracle.
- **External content boundary.** External content enters as data, not
  automatically as authority. This architectural boundary is established;
  runtime resistance to hostile instructions embedded in that data, including
  prompt injection, remains to be tested.

## 5. Frozen invariants

R0 preserves the following existing invariants. The linked authority contains
their definitions and enforcement rules; this contract does not redefine them.

| R0 requirement | Authoritative repository document |
| --- | --- |
| Workers cannot bypass Kernel validation. | [`INV-02 — Agents propose, code commits`](../invariants.md) |
| Tasks remain within write/tool/budget scope. | [`INV-14 — Tasks stay in scope`](../invariants.md) and [`docs/tasks.md`](../tasks.md) |
| Commits are revalidated. | [`INV-13 — Commits revalidate`](../invariants.md) |
| Evidence references remain verifiable against immutable source material. | [`INV-03 — Sources are immutable`](../invariants.md) and [`INV-04 — Quotes are checked, not trusted`](../invariants.md) |
| Confidence changes require explicit causes. | [`INV-05 — No unexplained confidence change`](../invariants.md) |
| Competing hypotheses are retained. | [`INV-07 — Threads retain competing hypotheses`](../invariants.md) |
| World beliefs may decay according to explicit rules. | [`INV-08 — Decay is scheduled and conservative`](../invariants.md) |
| Team memory changes use the learning path. | [`INV-12 — Team memory changes only through the learning path`](../invariants.md) |
| Human contributions use the same validation boundary. | [`INV-15 — Human input enters through the same gates`](../invariants.md) |
| Projections are not authoritative. | [`INV-11 — Projections are not authority`](../invariants.md) |
| Plans do not rewrite execution history. | [`ADR-0025 — Plan is derived execution state`](../decisions/ADR-0025-plan-is-derived-execution-state.md) and [`docs/01-architecture-revision.md`](../01-architecture-revision.md) |

## 6. Explicitly non-frozen implementation details

The following choices remain deliberately open: model provider; model
family/version; agent framework; retrieval algorithm; embedding
implementation; experience-ranking algorithm; storage optimization; queue
implementation; causal-attribution mechanism; evaluation implementation;
learning algorithm; KnowledgeItem serialization; number of retrieved memories;
autonomy level; human-review frequency; domain-specific heuristics; and
security implementation details.

> R0 freezes architectural relationships, not implementation details that can
> evolve behind those relationships.

## 7. Explicit open hypotheses

These hypotheses motivate the architecture; they are not claims established by
the freeze.

| Hypothesis | Status |
| --- | --- |
| **H1 — Persistent experience improves future performance.** Watch assumes accumulated experience can improve later domain work. | Not yet proven. |
| **H2 — Validated Team knowledge is useful.** KnowledgeItems and related Team memory should improve future work. | Not yet proven. |
| **H3 — Experience can generalize.** A learned lesson should sometimes help in a related but not identical situation. | Not yet proven. |
| **H4 — Evaluation can support useful learning.** Outcome → Evaluation → LearningChange should produce useful rather than harmful learning. | Not yet proven. |
| **H5 — Experience can remain useful across model changes.** Team experience is intended to remain separable from a model's weights. | Cross-model effectiveness is not yet proven. |
| **H6 — Bounded retrieval can provide sufficient context.** A Worker should not need the entire historical database. | The effectiveness of bounded selection remains an empirical question. |
| **H7 — Accumulated learning can be kept from becoming harmful self-reinforcement.** The Team should be able to challenge its own knowledge. | The mechanism remains future work. |

## 8. Explicit non-goals

R0 does not attempt to prove:

- that Watch creates true AGI;
- that Watch creates objectively truthful beliefs;
- that Watch performs perfect causal inference;
- that Watch guarantees model compliance;
- that Watch guarantees expert-level performance;
- that Watch makes every model equally effective;
- that Watch eliminates hallucination; or
- that Watch replaces domain experts.

These claims are not necessary for the architecture freeze.

## 9. Critical unresolved problems

The following problems are intentionally open. Their classification identifies
the next kind of work, not a conclusion that a new architectural layer is
required.

| Problem | Classification |
| --- | --- |
| Causal attribution | Future experiment |
| Evaluation reliability | Future experiment |
| Source reliability | Future experiment |
| Evidence independence | Future implementation |
| Experience retrieval | Future experiment |
| Conditional/contradictory knowledge | Future implementation |
| Generalization | Future experiment |
| Self-reinforcing beliefs | Future experiment |
| Behavior change from learned knowledge | Future experiment |
| Cross-model portability | Future experiment |
| Dynamic state reconstruction | Future implementation |
| Prompt injection | Future implementation |
| Scaling / knowledge entropy | Future architecture candidate |
| Measurement of expertise | Future experiment |

## 10. Redesign triggers

The current architecture should be reconsidered if any of the following occurs:

- a required state cannot be represented without violating invariants;
- Control cannot safely converge into Tasks;
- World memory and Team learning cannot remain separated;
- historical decision provenance cannot be reconstructed;
- the learning loop requires a second incompatible authority layer;
- a core architectural hypothesis is experimentally falsified and cannot be
  repaired locally; or
- a multi-domain test shows that the universal Kernel works only through
  duplicated domain-specific architecture.

> Difficult implementation does not by itself trigger redesign.

> An unresolved research question does not by itself trigger redesign.

> A structural contradiction or strong empirical falsification may trigger
> redesign.

## 11. R0 acceptance criteria

R0 is frozen when all of the following are true:

1. Major architectural concepts have one clear authority source.
2. Objective, StateAssessment, Strategy, Plan, Task, Worker, and Kernel have
   non-overlapping responsibilities.
3. Reactive and deliberative execution paths converge on Tasks.
4. Plan and StateAssessment do not become competing sources of truth.
5. World memory and Team learning remain conceptually distinct.
6. Durable state, execution provenance, and the validation/commit boundary
   remain attributable and reconstructable through the existing model.
7. The frozen invariants in this contract continue to govern future changes.
8. The listed implementation choices and empirical hypotheses remain open;
   none is represented as an R0 proof or mandatory implementation choice.
9. Causal attribution, evidence truth, and prompt-injection resistance are
   recorded with their stated limits rather than claimed as solved.
10. No fundamental contradiction has been identified in the frozen
    relationships, and the architecture can proceed as a testable hypothesis.

