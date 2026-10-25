# Revision 2 — Control Model

This is the compact active reference for concepts revised by Revision 2. Use `docs/architecture.md` for the original architecture where this document does not explicitly replace it, and use the linked ADRs for decision rationale. This document describes the intended model; `PLAN.md`, code, migrations, and tests determine current implementation status.

## 1. Central rule

**Workers propose → application validates → Kernel/application commits → durable state.** No model, worker, graph, transcript, or derived assessment is authority for a durable write.

The Control layer decides *what intended work should be materialized*. It does not execute work itself or become a second runtime.

## 2. Two entry paths, one execution path

```text
Reactive Trigger / Scheduler / Operator
                 │
                 ▼
          ordinary Task ─────────────────┐
                                         │
Objective → StateAssessment → StrategyProposal → Plan → ordinary Tasks
                                         │
                                         ▼
                              existing Task runtime
                                         ▼
                              Worker → Proposal
                                         ▼
                       application validation/commit
                                         ▼
                           durable records + Events
```

- Reactive work may create a Task directly and need not create an Objective or Plan.
- Deliberative work starts from an Objective and can materialize a Plan.
- Both paths use the same Task admission, worker authority, write scopes, commit validation, Event attribution, and persistence rules.
- Triggers may use a direct Task for deterministic response or initiate/activate an Objective when deliberation is required. Do not force every Trigger through Control.

## 3. Objective

An Objective is one durable, team-owned operational goal. It is not a Thread, a Strategy, or an ephemeral per-Task abstraction.

Lifecycle:

```text
draft → active | cancelled
active → paused | blocked | completed | cancelled
paused → active | cancelled
blocked → active | cancelled
completed and cancelled are terminal
```

Every lifecycle mutation is application-controlled, validated against current state, and auditable. See `core/objectives.py`, its tests, and the relevant Objective scope in `docs/tasks.md`.

## 4. StateAssessment

StateAssessment is derived from authoritative durable records. For identical inputs, its normalized output/basis must be deterministic. It is read-only, non-authoritative, and must not mutate world/team memory.

When a Strategy/Plan uses an assessment, preserve the historical decision basis: references, hash, creation timestamp, and the exact immutable payload when references/hash alone cannot reconstruct it. A later assessment of current state must not rewrite the earlier decision basis.

## 5. StrategyProposal and nested intent

One accepted StrategyProposal is one coordinated strategic decision for one Objective and one historical StateAssessment basis.

```text
StrategyProposal
  └─ one or more Visions (bounded perspectives)
       └─ one or more Workstreams (human-facing grouping)
            └─ Actions (intended work)
                 └─ explicit Action prerequisites
```

The nesting is a presentation/grouping model, not a dependency restriction: an Action prerequisite may cross Workstream or Vision boundaries. Validation must establish target identity, ownership/scope, supported capabilities/types, policy/budget limits, and an acyclic dependency graph; reject invalid references, self-dependencies, and cycles.

- **Vision:** a bounded strategic perspective.
- **Workstream:** a coherent grouping for human comprehension; not a scheduler or dependency boundary.
- **Action:** intended work; not a Task and not execution history.
- **Acceptance:** deterministic legality and authorization for later Plan materialization, not a claim that the Strategy is wise or effective.
- **Provenance:** the accepted structure, hash, and historical assessment basis must be reconstructable from durable Task-attributed Event data without depending on a model transcript or regeneration.
- **Persistence:** these concepts do not automatically require separate durable entity tables.

The worker can propose only within the defined contract. It cannot mutate TeamPolicy/Team structure, create arbitrary rows, invent entity writes, self-authorize tools, bypass Task scope, raise its own budget, or commit durable state.

## 6. Plan

A Plan is durable, immutable intended work derived from one accepted Strategy for one Objective. It is not execution truth, a transcript, a Strategy store, a StateAssessment, workflow engine, or second runtime.

- Initially: one accepted Strategy → one Plan.
- Preserve accepted Vision/Workstream/Action structure, identities, prerequisites, assessment/proposal provenance, budget envelope, and completion/stop conditions. Do not invent, omit, split, or reinterpret accepted structure without explicit authority.
- Plan plus initial ordinary Tasks plus its creation Event commit atomically. Partial materialization is not a valid durable state.
- Each intended Action maps to exactly one ordinary Task once materialized.
- Task membership is optional overall: a reactive Task may have no Plan. If a Task is Plan-linked, `plan_id` and `plan_action_id` identify its Action under the specified ownership/uniqueness constraints.
- A Plan-linked Task cannot start until each prerequisite Task is `done`; this is enforced at existing Task admission. Do not add a separate scheduler or change Task states to enforce dependencies.
- Lifecycle transitions use the application-controlled `transition_plan` Task operation. Only lifecycle metadata changes; accepted proposal/assessment provenance, Action definitions, prerequisites, budget, and completion condition remain immutable.
- Lifecycle: `active → completed | stopped`; terminal states do not reopen. Stop reasons: `abandoned`, `invalidated`, `superseded`. Completion must be supported by durable Task/Event records for the declared completion condition.
- A stopped Plan with reason `superseded` references an already-existing active successor Plan for the same Objective. The transition does not create a replacement Plan; replanning remains later work.
- Progress is derived from Tasks. Replanning creates new immutable intent; prior Plans remain history.
- The creating `create_plan` Task's `policy_version` records the policy used to validate creation. Do not add an extra Plan policy pin without explicit authority.

## 7. Budget hierarchy and other policies

```text
TeamPolicy ceiling > Plan envelope > individual Task budget
```

A Plan must fit its applicable TeamPolicy ceiling. The materialized Task allocation must fit the Plan envelope. Every Task remains bounded by its own budget. Reactive Tasks without a Plan still obey Task-level and TeamPolicy constraints.

A Strategy-level Action count is not the same concept as a team-wide daily Task-start quota. See ADR-0027 and the open authority note in `PLAN.md` / `CHANGE_MAP.md`; do not infer approval or implementation authorization from a spec paragraph alone.

## 8. Architecture and implementation boundary

- `State` is observed authoritative world/team state; `TeamPolicy` is an operator-approved general constraint; `StrategyProposal` is contextual intended work; `Plan` is immutable orchestration intent; `Task` is the execution unit.
- Outcomes/Evaluations/learning are later feedback concepts; they must not be silently pulled into an earlier milestone.
- Human/operator actions pass the same applicable validation and commit gates as worker-generated proposals.
- If a Task can express the needed work, do not add a new runtime entity for convenience.
- Use `PLAN.md` to determine phase status and authorization. This model does not close a milestone by itself.

## 9. Proposed R6 direction: RAG-backed context and experience distillation

This is a **proposed design direction for R6-G0**, not a statement that the capability is implemented or that the related ADRs are accepted. See [ADR-0028](decisions/ADR-0028-rag-backed-knowledge-cores.md), [ADR-0029](decisions/ADR-0029-llm-assisted-experience-distillation.md), and the [R6 entry gate](development/r6-entry-gate.md).

Watch should distinguish three logical roles:

- **Domain Knowledge Core:** what the team knows about a subject, grounded in canonical source records, claims or hypotheses, evidence, provenance, uncertainty, and current status.
- **Team Experience Core:** what the team has learned from doing the work, represented by accepted, versioned practices, patterns, methods, and playbooks.
- **Task Context:** a bounded, derived assembly of relevant retrieved records, current authoritative state, objective, policy constraints, and source/version references for one task.

RAG retrieves candidate material from these logical cores. A retrieval index may share physical infrastructure across cores, but it must preserve Team/domain scope, permissions, record kind, acceptance/status, and provenance. Indexes, embeddings, summaries, and rankings are regenerable projections. A retrieval match cannot establish truth or authorize a write; the application resolves candidates to current canonical records and existing validation/commit rules still apply.

The proposed experience loop is:

**durable execution and evidence → Outcome/Evaluation → LLM-proposed abstraction → application validation and authorized learning commit → accepted canonical knowledge → retrieval for later work.**

Distillation means abstracting reusable experience—not saving transcripts or merely summarizing a run. Proposed abstractions must retain their evidence basis, scope/applicability, limitations, uncertainty, and counterexamples where available. A model cannot directly commit team knowledge or TeamPolicy. The R6 G0 gate must define the first bounded contract and recovery/approval behavior before implementation.

This direction does not change the Control/Task boundary: deliberative proposals still pass Strategy validation; accepted Plans still materialize ordinary Tasks; reactive work remains valid without a Plan; and both entry paths use one runtime.
