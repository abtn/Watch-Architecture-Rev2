# Watch — Authority Map

This file identifies the active source for each concern. It is an index, not a second specification. Read only the rows relevant to the task.

| Concern | Authoritative source | Boundary |
|---|---|---|
| Current milestone, phase gate, next action | [`PLAN.md`](PLAN.md) | The only source of current status. Code presence or a test result does not close a phase. |
| R5-A materialization/recovery and R5-B lifecycle sequencing | [`PLAN.md`](PLAN.md), `docs/tasks.md`, `docs/testing.md` | Both slices are recorded READY; overall R5 remains IN PROGRESS pending the operator's formal exit-gate decision. Slice readiness is not formal closure or ADR acceptance. Replanning remains later work. |
| Agent workflow, preflight, stop/report rules | [`AGENTS.md`](AGENTS.md) | Process only; it does not independently authorize architecture changes. |
| Unchanged/original domain architecture | [`docs/architecture.md`](docs/architecture.md) | Applies where the Revision 2 map below has not superseded it. |
| Revision 2 Control layer and dual-entry model | [`docs/control-model.md`](docs/control-model.md), ADR-0023–ADR-0026 | Reactive and deliberative work converge on ordinary Tasks. |
| Objective lifecycle | `docs/control-model.md`, `core/objectives.py`, tests, relevant ADRs | The spec defines behavior; code/tests establish current implementation. |
| StateAssessment | `docs/control-model.md`, `core/state_assessment.py`, tests | Derived, read-only, deterministic, non-authoritative; preserve decision-basis provenance. |
| StrategyProposal, Vision, Workstream, Action | `docs/control-model.md`, ADR-0023/0024, `docs/tasks.md` | Acceptance means deterministic legality, not strategic wisdom. Exact accepted structure/provenance must be reconstructable. |
| Plan, lifecycle, and Action prerequisites | `docs/control-model.md`, ADR-0025/0026, `docs/tasks.md`, `core/plans.py`, `core/task_runtime.py`, `migrations/versions/0007_plan_lifecycle.py`, `migrations/versions/0008_plan_lifecycle_state.py`, tests | Plan intent is immutable; R5-B lifecycle changes use the scoped `transition_plan` Task operation; Events record each transition. Dependencies are enforced by existing admission. |
| Task types, write scopes, commit rules, budgets | [`docs/tasks.md`](docs/tasks.md) | The Task matrix is the operative scope contract; do not infer extra scope from prose. |
| Architectural invariants | [`docs/invariants.md`](docs/invariants.md) | Normative constraints; use PLAN, code, and tests to determine which are implemented in the current phase. |
| Domain-pack boundary | [`docs/domains.md`](docs/domains.md), ADR-0016 | Packs cannot extend the Kernel. |
| Terms | [`docs/glossary.md`](docs/glossary.md) | Terminology reference; it does not override a spec or ADR. |
| Testing | [`docs/testing.md`](docs/testing.md), `pyproject.toml`, test fixtures | Verify only the stated command/environment and report skipped checks. |
| Reasons behind decisions | [`docs/decisions.md`](docs/decisions.md), full ADRs in `docs/decisions/` | A `Proposed` ADR is not an accepted decision. |
| Workflow-validation evidence | `docs/development/workflow-validation.md` | Append-only history, read only when validating the development process or when a task requires its evidence. |

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

R5-A remains recorded READY in `PLAN.md`. R5-B's database-constraint correction is commit `95a1e8e`, integrated into `main` by PR #2 merge commit `435e88f`. Programmer-reported verification at branch HEAD `c99858f` passed the `0007 → 0008` disposable-PostgreSQL upgrade, 38 lifecycle tests, 147 focused R5-A/Strategy regressions, 260 full-suite tests, Ruff, mypy, and `git diff --check`. A fresh full-chain migration through `0008` was not rerun; a subsequent `0008 → 0007 → 0008` downgrade/upgrade round trip succeeded on the disposable database, but schema equivalence was not separately compared. The overall R5 gate remains IN PROGRESS pending the operator's formal decision. The missing Task-completion path remains a documented dependency and must be explicitly assessed at the gate. ADR-0027 remains Proposed; R6 is not authorized.

One dependency is recorded and unresolved: no component in the current codebase moves a Task to `done`, so the R5-B completion precondition is exercised against prepared durable state rather than an end-to-end executable path. `PLAN.md` records the effect of that dependency on the R5 gate.

## Conflict rule

When two relevant sources disagree, stop before the disputed change. Report the paths and statements in conflict and request the smallest explicit decision. Do not use an archived source, a generated text dump, or code presence to silently override an active authority.
