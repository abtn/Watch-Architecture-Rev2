# Watch — Authority Map

This file identifies the active source for each concern. It is an index, not a second specification. Read only the rows relevant to the task.

| Concern | Authoritative source | Boundary |
|---|---|---|
| Current milestone, phase gate, next action | [`PLAN.md`](PLAN.md) | The only source of current status. Code presence or a test result does not close a phase. |
| R5-A materialization/recovery and R5-B lifecycle sequencing | [`PLAN.md`](PLAN.md), `docs/tasks.md`, `docs/testing.md` | R5-A and R5-B are recorded READY; overall R5 was formally closed by operator decision on 2026-10-24. R5 closure is not ADR-0027 acceptance or authorization to start R6. Replanning remains later work. |
| Agent workflow, preflight, stop/report rules | [`AGENTS.md`](AGENTS.md) | Process only; it does not independently authorize architecture changes. |
| Unchanged/original domain architecture | [`docs/architecture.md`](docs/architecture.md) | Applies where the Revision 2 map below has not superseded it. |
| Revision 2 Control layer and dual-entry model | [`docs/control-model.md`](docs/control-model.md), ADR-0023–ADR-0026 | Reactive and deliberative work converge on ordinary Tasks. |
| Objective lifecycle | `docs/control-model.md`, `core/objectives.py`, tests, relevant ADRs | The spec defines behavior; code/tests establish current implementation. |
| StateAssessment | `docs/control-model.md`, `core/state_assessment.py`, tests | Derived, read-only, deterministic, non-authoritative; preserve decision-basis provenance. |
| StrategyProposal, Vision, Workstream, Action | `docs/control-model.md`, ADR-0023/0024, `docs/tasks.md` | Acceptance means deterministic legality, not strategic wisdom. Exact accepted structure/provenance must be reconstructable. |
| Plan, lifecycle, and Action prerequisites | `docs/control-model.md`, ADR-0025/0026, `docs/tasks.md`, `core/plans.py`, `core/task_runtime.py`, `migrations/versions/0007_plan_lifecycle.py`, `migrations/versions/0008_plan_lifecycle_state.py`, tests | Plan intent is immutable; R5-B lifecycle changes use the scoped `transition_plan` Task operation; Events record each transition. Dependencies are enforced by existing admission. |
| R6 knowledge-grounded loop and entry gate | [`PLAN.md`](PLAN.md), [`docs/development/r6-entry-gate.md`](docs/development/r6-entry-gate.md), ADR-0025/0026/0028/0029/0030, `docs/tasks.md` | R6-G0 is **COMPLETE (2026-10-25)** and **R6-A is COMPLETE — merged to `main` by PR #12** (merge commit `ebbc48d`). ADR-0027 remains Proposed. Preserve one runtime and all R5 safeguards. ADR-0030 §5 governs R6-A/R6-C sequencing only: R6-A owns atomic terminal Outcome persistence; R6-C consumes it for reassessment. |
| R6-A Task lifecycle and Outcome persistence | `migrations/versions/0009_task_lifecycle_outcome.py`, `core/models.py`, `core/plans.py`, `core/task_runtime.py`, `tests/test_task_lifecycle_schema.py`, `tests/test_task_lifecycle_finalize.py`, `tests/test_task_lifecycle_retry.py`, `tests/test_task_lifecycle_recovery.py` | **COMPLETE — merged to `main` by PR #12** (merge commit `ebbc48d`). Step 1 schema at `42257ad` (Task `created_at`/`completed_at`/`max_attempts` backfilled from the earliest `task_started` Event, `uq_tasks_id_team`, the `outcomes` table with its eight named constraints, the `Outcome` ORM mapping, and `max_attempts=3` pinning in `PlanService._create`); Checkpoint 2A terminal finalization at `c3e9428`; Checkpoint 2B retry scheduling and attempt exhaustion at `e05a8a4`; Checkpoint 2C interrupted-task recovery at `da47694` in `TaskRuntime.recover_interrupted()`, which reuses the Checkpoint 2B retry disposition and the Checkpoint 2A terminal finalizer. R6-B dispatch wiring remains separate. |
| R6-G0 decision record | [`docs/development/r6-g0-decision-proposals.md`](docs/development/r6-g0-decision-proposals.md), [`docs/development/r6-entry-gate.md`](docs/development/r6-entry-gate.md), ADR-0025/0026/0028/0029/0030 | Record of the accepted G0 design defaults and staged provider choices. Not implementation authorization. R6-G0 is complete; R6-A was authorized separately by the operator and is now complete. |
| Knowledge Cores and RAG retrieval | [ADR-0028](docs/decisions/ADR-0028-rag-backed-knowledge-cores.md) | Initial canonical inputs, PostgreSQL hybrid retrieval, Team/source scope, Context Snapshot/manifest, bounds, freshness and rebuild contract are recorded; embedding provider/model selection is staged until immediately before R6-D. |
| LLM-assisted experience distillation | [ADR-0029](docs/decisions/ADR-0029-llm-assisted-experience-distillation.md), INV-12 | Typed evidence-linked proposals, evidence rule, explicit operator review/commit, version lifecycle, and retrieval publication rules are recorded. |
| Task types, write scopes, commit rules, budgets | [`docs/tasks.md`](docs/tasks.md) | The Task matrix is the operative scope contract; do not infer extra scope from prose. |
| Architectural invariants | [`docs/invariants.md`](docs/invariants.md) | Normative constraints; use PLAN, code, and tests to determine which are implemented in the current phase. |
| Domain-pack boundary | [`docs/domains.md`](docs/domains.md), ADR-0016 | Packs cannot extend the Kernel. |
| Terms | [`docs/glossary.md`](docs/glossary.md) | Terminology reference; it does not override a spec or ADR. |
| Testing | [`docs/testing.md`](docs/testing.md), `pyproject.toml`, test fixtures | Verify only the stated command/environment and report skipped checks. |
| Reasons behind decisions | [`docs/decisions.md`](docs/decisions.md), full ADRs in `docs/decisions/` | A `Proposed` ADR is not an accepted decision. |
| Workflow-validation evidence | `docs/development/workflow-validation.md` | Append-only history, read only when validating the development process or when a task requires its evidence. |

## R6 knowledge direction (accepted principles; implementation gated)

- **RAG-backed Knowledge Cores:** ADR-0028 (Accepted for architectural principles) governs the design for Domain Knowledge Core, Team Experience Core, derived Task Context, traceable retrieval, access/status filtering, and regenerable indexes. Canonical records—not retrieval rank or embeddings—remain authoritative.
- **LLM-assisted experience distillation:** ADR-0029 (Accepted for architectural principles) governs the design for turning durable experience into evidence-linked reusable abstractions through controlled validation and the authorized learning commit path.
- The R6 entry gate in `docs/development/r6-entry-gate.md` records the accepted G0 decisions and the documented local preflight; R6-G0 is COMPLETE. That record did not itself authorize implementation; R6-A was authorized separately by the operator and is now COMPLETE, merged to `main` by PR #12 (merge commit `ebbc48d`). The staged R6 slices continue with R6-B.

## Revision 2 concepts

- **Objective:** one durable operational goal with an explicit lifecycle; no ephemeral task-scoped Objective.
- **StateAssessment:** reproducible derived snapshot of authoritative state, not a write authority.
- **Strategy:** one coordinated accepted decision for an Objective and a historical assessment basis; it may contain multiple Visions, Workstreams, Actions, and Action prerequisites.
- **Plan:** one accepted Strategy becomes one durable Plan; accepted structure is preserved as immutable intent. Plan progress is derived from ordinary Task state.
- **Execution:** reactive Tasks remain valid without an Objective/Plan; deliberative Tasks use the same Task runtime, state machine, and commit gates.
- **Budget hierarchy:** TeamPolicy ceiling → Plan envelope → individual Task budget.

## R5 scope and quota decision authority

`PLAN.md` owns the R5-A / R5-B boundaries, current status, and exit criteria. `docs/tasks.md` owns the Task and daily quota behavior; `docs/testing.md` owns the required verification evidence.

ADR-0027 remains `Proposed`. The operator's R5-A instructions dated 2026-10-21 explicitly direct verification and correction of the existing daily Task-start quota path against the documented semantics, including durable `task_started` Event accounting, concurrency, retries, UTC day boundaries, configuration validation, and failed-operation consistency. This task direction does not silently accept ADR-0027 or change its status. Keep Task-count accounting separate from monetary/token-cost accounting.

R5-A remains recorded READY in `PLAN.md`. R5-B's database-constraint correction is commit `95a1e8e`, integrated into `main` by PR #2 merge commit `435e88f`; the operator formally closed R5 on 2026-10-24, as recorded in `PLAN.md`. Programmer-reported verification at branch HEAD `c99858f` passed the `0007 → 0008` disposable-PostgreSQL upgrade, 38 lifecycle tests, 147 focused R5-A/Strategy regressions, 260 full-suite tests, Ruff, mypy, and `git diff --check`. A fresh full-chain migration through `0008` was not rerun; a subsequent `0008 → 0007 → 0008` downgrade/upgrade round trip succeeded on the disposable database, but schema equivalence was not separately compared. The Task-completion path remains assigned to R6; R5's completion preconditions remain mandatory. ADR-0027 remains Proposed; R5 closure does not authorize R6.

One dependency is recorded and unresolved: no component in the current codebase moves a Task to `done`, so the R5-B completion precondition is exercised against prepared durable state rather than an end-to-end executable path. The formal R5 closure record in `PLAN.md` retains this as R6 work without claiming end-to-end Task execution is delivered.

## Conflict rule

When two relevant sources disagree, stop before the disputed change. Report the paths and statements in conflict and request the smallest explicit decision. Do not use an archived source, a generated text dump, or code presence to silently override an active authority.
