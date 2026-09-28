# AGENTS.md — Watch workspace instructions

## Current state and K0 boundary

- This checkout contains design/planning documents only; no implementation, dependency manifest/lockfile, tests, migrations, or Docker Compose configuration is present.
- **K0 is the current implementation target.** Its specified stack is Python 3.12+, PostgreSQL + pgvector via Docker Compose, Alembic, pytest, Ruff, and mypy. These are planned K0 components, not an implemented toolchain here.
- During K0, do not implement Control-layer entities or behavior: no Objective, StateAssessment, StrategyProposal, Plan, or LLM integration.
- Do not begin K1 unless explicitly requested. Check `PLAN.md` and `docs/05-implementation-plan.md` for the current milestone and acceptance criteria.
- No implementation code exists to establish additional code-style conventions. Do not infer them from future architecture plans.

## Source of truth

- Use `CHANGE_MAP.md`: original Watch documents govern unmapped concepts; mapped Revision 2 documents govern only the concepts they explicitly revise.
- Do not resolve document conflicts by inference. If `CHANGE_MAP.md` does not establish authority, stop and report the ambiguity.
- Do not change original baseline documents merely to resolve a Revision 2 conflict. See `docs/09-migration-from-original-design.md` for reconciliation guidance.

## Architectural boundaries

These constrain the architecture; they do not authorize implementing future components during K0.

- Agents/workers propose; application code validates and commits.
- Durable state changes go through the Kernel; the Kernel is authoritative for committed state.
- Tasks are the execution unit. Reactive and deliberative entry paths converge on ordinary Task execution.
- Control must not create a second commit kernel or execution runtime.
- A Plan records execution intent, not execution truth; Tasks and Events record execution.
- StateAssessment is derived and non-authoritative.
- Never bypass Kernel validation for durable state changes or silently change an architectural decision. Stop on a design conflict; consult the relevant ADR.

## Development and verification

1. Read this file, `CHANGE_MAP.md`, the relevant task in `PLAN.md`, and only the detailed documents needed for that task.
2. Make the smallest requested change; keep unrelated files untouched and do not combine architectural redesign with implementation.
3. Run the verification that is executable for the current milestone; report skipped checks, deviations, and unresolved ambiguity.
4. When changing a documented invariant, update `docs/invariants.md` first, then this file, then the related tests, as required by the invariant change process.

### Workflow validation
When a task is explicitly designated as a workflow simulation, workflow validation, or Codex-process test, do not modify implementation files unless the task explicitly requests implementation.
After completing the simulation, update docs/development/workflow-validation.md with the observed result.
Each entry should record:
the simulation objective/scenario;
the repository state relevant to the simulation;
the observed Codex behavior;
expected behavior versus actual behavior;
discrepancies, ambiguities, or failures discovered;
lessons or workflow rules derived from the result;
any resulting documentation or AGENTS.md changes.
Do not fabricate expected results after the fact. Clearly distinguish documented expectations from observations.
Keep the validation record chronological and append new results rather than rewriting historical observations.
A workflow-validation result does not by itself authorize architectural or implementation changes. Apply changes only when explicitly requested or when the repository's documented change process requires them.

### Commands and tooling status

No environment/dependency setup command or essential development command is defined for this checkout. K0 requires a Python 3.12+ virtual environment and dependency lock, but does not specify an install command or dependency manager; do not invent one. No single-test command is established yet.

The following are the K0 specification's target verification commands, **not currently runnable here** because their supporting project files/configuration do not exist. Use them after K0 setup is implemented; do not report them as run or verified in this checkout:

```text
docker compose up -d
alembic upgrade head
pytest
ruff check .
mypy core
```

## Documentation lookup

| Topic | Source |
|---|---|
| Authority mapping | `CHANGE_MAP.md` |
| Architecture | `docs/01-architecture-revision.md` |
| Control layer | `docs/02-control-layer.md` |
| Runtime | `docs/03-runtime-model.md` |
| Schema | `docs/04-data-model-changes.md` |
| Milestones | `PLAN.md`, `docs/05-implementation-plan.md` |
| VS Code workflow | `docs/06-codex-vscode-workflow.md` |
| Vocabulary | `docs/glossary.md` |
| Invariants | `docs/invariants.md` |
| Architecture decisions | `docs/decisions/`; read ADR-0026 before Task, Plan, Objective, Trigger, or scheduler changes |
