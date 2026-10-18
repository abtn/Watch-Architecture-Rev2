# Watch — Authority Map

This file identifies the active source for each concern. It is an index, not a second specification. Read only the rows relevant to the task.

| Concern | Authoritative source | Boundary |
|---|---|---|
| Current milestone, phase gate, next action | [`PLAN.md`](PLAN.md) | The only source of current status. Code presence or a test result does not close a phase. |
| Agent workflow, preflight, stop/report rules | [`AGENTS.md`](AGENTS.md) | Process only; it does not independently authorize architecture changes. |
| Unchanged/original domain architecture | [`docs/architecture.md`](docs/architecture.md) | Applies where the Revision 2 map below has not superseded it. |
| Revision 2 Control layer and dual-entry model | [`docs/control-model.md`](docs/control-model.md), ADR-0023–ADR-0026 | Reactive and deliberative work converge on ordinary Tasks. |
| Objective lifecycle | `docs/control-model.md`, `core/objectives.py`, tests, relevant ADRs | The spec defines behavior; code/tests establish current implementation. |
| StateAssessment | `docs/control-model.md`, `core/state_assessment.py`, tests | Derived, read-only, deterministic, non-authoritative; preserve decision-basis provenance. |
| StrategyProposal, Vision, Workstream, Action | `docs/control-model.md`, ADR-0023/0024, `docs/tasks.md` | Acceptance means deterministic legality, not strategic wisdom. Exact accepted structure/provenance must be reconstructable. |
| Plan and Action prerequisites | `docs/control-model.md`, ADR-0025/0026, `docs/tasks.md`, `core/plans.py`, `core/task_runtime.py`, tests | Plan is immutable intended work; Tasks/Events record execution. Dependencies are enforced by existing admission. |
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

## Known authority issue — do not silently resolve

`docs/tasks.md` contains a normative-looking **TeamPolicy daily Task-start quota** contract, but ADR-0027 is marked **Proposed** and `PLAN.md` records R5 as paused pending its phase gate. The intended quota semantics are documented, but their acceptance/implementation authorization is not established by those facts alone. Before implementing or declaring the quota accepted, obtain an explicit decision and satisfy the milestone gate. Do not interpret this documentation refactor as authorization to proceed with R5 or R6.

## Conflict rule

When two relevant sources disagree, stop before the disputed change. Report the paths and statements in conflict and request the smallest explicit decision. Do not use an archived source, a generated text dump, or code presence to silently override an active authority.
