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
| R6 knowledge-grounded loop and entry gate | [PLAN.md](PLAN.md), [docs/development/r6-entry-gate.md](docs/development/r6-entry-gate.md), ADR-0025/0026/0028/0029/0030, docs/tasks.md | PLAN.md is the sole source of current milestone status. Preserve one runtime and all R5 safeguards. ADR-0030 §5 fixes sequencing: R6-A owns atomic terminal Outcome persistence; R6-C consumes it for deterministic reassessment. External-provider decisions remain gated by explicit sign-off at the applicable milestone. |
| R6-A Task lifecycle and Outcome persistence | migrations/versions/0009_task_lifecycle_outcome.py, core/models.py, core/plans.py, core/task_runtime.py, lifecycle schema/finalize/retry/recovery tests | Canonical Task lifecycle and terminal Outcome write path, schema, retry/recovery behavior, and replay invariants. TaskRuntime remains the sole lifecycle authority; see PLAN.md for current milestone status. |
| R6-B configured-source execution path | core/dispatcher.py, core/source_fetch.py, tests/test_r6b_dispatcher.py, ADR-0030 §2–§3, docs/tasks.md | TaskDispatcher runs startup recovery and dispatches one configured-source ingest_source Task through RestrictedFetcher, IngestionService, and TaskRuntime. Durable source identity is the Task's PlanAction, authorized by TeamPolicy.rules['sources']. No second runtime or scheduler; see PLAN.md for status. |
| R6-G0 decision record | docs/development/r6-g0-decision-proposals.md, docs/development/r6-entry-gate.md, ADR-0025/0026/0028/0029/0030 | Record of accepted G0 design defaults and staged provider choices. Status and implementation authorization are tracked in PLAN.md; this record does not independently authorize provider selection. |
| Outcome-backed deterministic execution reassessment | core/execution_assessment.py, tests/test_execution_assessment.py, ADR-0030 §5 | Read-only, repeatable-read derived view over immutable Plan intent, Task attempts, Events, Outcomes, and Snapshots; validates canonical hashes and exposes a deterministic assessment hash. It never writes lifecycle records; see PLAN.md for status. |
| Knowledge Cores and RAG retrieval | [ADR-0028](docs/decisions/ADR-0028-rag-backed-knowledge-cores.md) | Initial canonical inputs, PostgreSQL hybrid retrieval, Team/source scope, Context Snapshot/manifest, bounds, freshness and rebuild contract are recorded. R6-D uses an OpenAI-compatible embeddings API adapter, initially targeting local BGE-M3 in LM Studio; other compatible local or hosted APIs can be configured without changing retrieval. Model identity, revision fingerprint, readiness/retry policy, and rebuild requirements are specified in ADR-0028. See PLAN.md for implementation status. |
| LLM-assisted experience distillation | [ADR-0029](docs/decisions/ADR-0029-llm-assisted-experience-distillation.md), INV-12 | Typed evidence-linked proposals, evidence rule, explicit operator review/commit, version lifecycle, and retrieval publication rules are recorded. |
| R6-E generation provider and adapter | [ADR-0031](docs/decisions/ADR-0031-cloudflare-workers-ai-generation.md), [generation guide](docs/development/cloudflare-workers-ai-generation.md), `core/generation.py`, `core/generation_smoke.py` | Initial Cloudflare Workers AI Llama 3.1 8B FP8 provider. The adapter returns final JSON plus usage only; it cannot write or commit. The real Task path still requires Context Snapshot/manifest, StrategyProposer validation, and Task-level cost accounting; see PLAN.md. |
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
