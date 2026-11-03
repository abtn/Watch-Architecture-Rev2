# Watch — Persistent, Evidence-Oriented Team System

Watch is designed to turn temporary model workers into durable, auditable team experience. Model workers propose; application code validates and commits; durable records preserve what the system learned and did.

> **Model intelligence is temporary. Team experience is persistent.**

## Architecture in one line

**Reactive or deliberative entry → ordinary Task → Worker proposal → application validation → Kernel/application commit → durable records and Events.**

## What Watch is

**Watch is an attempt to build a persistent, evidence-oriented organization around temporary AI reasoning.** It turns information and goals into bounded Tasks, gives each worker relevant and authorized context, treats model output as proposals, validates those proposals in application code, and records decisions, execution, and Outcomes as durable, attributable history. Assessment and retrieval use that history to inform later work; the longer-term design is to distil carefully reviewed, evidence-linked lessons into reusable team knowledge.

This is our current working abstraction, shaped by the initial design and by what implementation has taught us. It is a way to explain the whole system, not a complete specification or a claim that every capability is already implemented. Persistence alone does not create expertise: an Outcome does not prove what caused it, evaluation methods can themselves be biased, and stored mistakes can become institutional memory. Watch's central challenge is to make adaptation more reliable by examining evidence, uncertainty, limitations, counterexamples, and the conditions under which a lesson should—or should not—transfer between domains.

So Watch is not simply a chatbot with memory or a universal expert. It is a reusable framework for building domain-specific expertise workflows. Its intelligence is distributed across models, persistent state, retrieval, execution, assessment, policies, and human review; no single component is sufficient on its own.


A Plan is intended work, not execution truth. Tasks and Events record execution. Derived assessments do not become authority merely because a model produced them.

## Current state (snapshot 2026-11-03)

[`PLAN.md`](PLAN.md) is the single source of current milestone status; the summary below is a convenience snapshot, not an authority record.

**Completed foundations and R6 slices**

- **K0, K1:** tooling baseline (Python 3.12+/uv, PostgreSQL + pgvector, Alembic, pytest, Ruff, mypy) and the smallest proposal → validation → atomic Kernel commit → Event path (`ingest_source`).
- **R0–R3:** Revision 2 semantics and boundaries, Kernel/Task compatibility, durable Objective model and lifecycle, and the deterministic read-only `StateAssessment` with provenance.
- **R4 (closed 2026-10-20):** StrategyProposal boundary — multi-Vision/Workstream/Action Strategy semantics with deterministic validation and reconstruction.
- **R5 (closed 2026-10-24):** Plan materialization and lifecycle — one accepted Strategy materialized as one durable Plan with ordinary Tasks and enforced lifecycle constraints.
- **R6-G0 (complete, 2026-10-25):** design decisions recorded in ADR-0025/0026/0028/0029/0030 and the R6 entry gate. ADR-0027 remains Proposed.
- **R6-A (complete, PR #12):** Task lifecycle — outcome schema and migration, atomic terminal `task_execution` Outcome finalization, retry scheduling and attempt exhaustion, and bounded interrupted-task recovery (`TaskRuntime.recover_interrupted()`).
- **R6-B (complete, PR #14):** the first working execution path — `TaskDispatcher` and `RestrictedFetcher` run one configured-source `ingest_source` Task end to end through the Kernel with startup recovery and policy-authorized source identity.
- **R6-C (complete, PR #16):** deterministic, read-only `ExecutionAssessmentBuilder` that rebuilds Plan intent and Task attempt history from durable records, validates Outcome/Snapshot/Event/Signal consistency, and hashes the canonical result. It adds no migration and no write path.
- **R6-D (complete; PRs #22 and #24):** provider-neutral embeddings, the `knowledge_chunks` projection, idempotent Signal indexing, snapshot/hash verification, model-readiness polling, and current-policy-scoped PostgreSQL hybrid retrieval. The operator verified local LM Studio BGE-M3 integration against a disposable PostgreSQL database using model ID `text-embedding-bge-m3`, 1,024-dimensional vectors, and the explicit `WATCH_EMBEDDING_REVISION=metadata-sha256:e8ffcf172118d67251eccbf45916e407b7e0537deef08f70bbd62e86518e9c69` pin.
- **R6-E (complete; PR #28 merged 2026-11-01):** all three checkpoints are integrated — bounded Task Context assembly with immutable Snapshot/manifest, a Context-bound model-backed `StrategyProposer`, and Task-attributed generation cost reservation/reconciliation. Operator verification passed all three checkpoints; Step 3 passed 43 focused tests, Ruff, mypy, the full suite, and `git diff --check` on disposable PostgreSQL at `0011_task_generation_cost`. Hosted CI passed fresh migrations, Ruff, mypy, and 515 tests in [run 41279796198](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/41279796198). The provider remains outside automatic Task dispatch and is not authorized for R6-F distillation.

**R6 continuation**

- **R6-F — C1–2 merged; C3 merged and locally verified; C4 reconciled to main with hosted CI green and local verification pending:** PR #31 merged at `99f8b6bbd76521eaac47761dcf432ebb3c0d28e3`; final C3 local verification passed 85 focused and 579 full-suite tests, Ruff, mypy, fresh single migration head `0012_learning_foundation`, and `git diff --check`. D12's distinct-key competing-approval loser Task is terminalized and recoverable through TaskRuntime. D10 remains create-only; revise/retire production is deferred. D7 is implemented in C4: optional schema-v2 TeamPolicy interval pinned to the approval Task, UTC review dates, NULL/due retrieval exclusion, and ordinary TaskRuntime review execution. PR #32 is reconciled with merged `main` at `923268b0efda16d2c87e1b53aba2acb1990680ad`; hosted CI run [41598895890](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/41598895890) passed fresh migration to one `0013_team_experience_projection` head, Ruff, mypy (27 files), and 590 tests. Operator-local disposable-PostgreSQL verification of the combined tree is pending. No Watch auth stack, TeamPolicy write through C3, second runtime, TaskDispatcher expansion, or production R6-F provider is introduced.
- **R6-G — later integration gate:** exercise the complete knowledge-grounded loop, full verification, and explicit R6 exit approval.

## Future plan

Roadmap per [`PLAN.md`](PLAN.md); `PLAN.md` remains the only authority for current milestone status.

- **R6 next:** run the full C4 disposable-PostgreSQL verification on reconciled head `923268b` after hosted CI `41598895890` passed. Then review and integrate C4 separately. R6-G requires its own authorization; no production R6-F provider is authorized.
- **R7 — Distillation quality and knowledge lifecycle:** cross-case evaluation of abstractions, contradictory evidence and counterexamples, transferability tests, retrieval quality, review/expiry, staleness detection, supersession, and retirement — always preserving explicit provenance, canonical authority, and controlled commits.
- **R8 — Multi-domain pressure test:** exercise the same Control layer across newsroom, development-team, and generalist settings while domain-specific knowledge stays outside the Kernel.
- **R9 — Agent-assisted production workflow:** codified task packets, test-first changes, architecture reviews, verification evidence, and human approval boundaries.
- **Deferred cross-cutting work:** execution security (per-worker filesystem/network/tool surface and secret isolation) and broader multi-domain experience-library work beyond the initial R6 slice.

## Repository guide

- [`CONTEXT.md`](CONTEXT.md) — concise session orientation.
- [`PLAN.md`](PLAN.md) — current milestone status, gates, and next action.
- [`AGENTS.md`](AGENTS.md) — instructions for coding agents.
- [`docs/development/agent-delivery-protocol.md`](docs/development/agent-delivery-protocol.md) — standing delivery authorization, automatic advancement, and merge conditions.
- [`docs/development/local-embeddings.md`](docs/development/local-embeddings.md) — local LM Studio / BGE-M3 embedding API setup and smoke gate.
- [`docs/development/r6-f-implementation-plan.md`](docs/development/r6-f-implementation-plan.md) — detailed R6-F technical checkpoints, open design decisions, and verification gates.
- [`CHANGE_MAP.md`](CHANGE_MAP.md) — authority map for concepts.
- [`docs/control-model.md`](docs/control-model.md) — Objective, StateAssessment, Strategy, Plan, and the dual-entry model.
- [`docs/architecture.md`](docs/architecture.md) — general/original architecture for concepts not replaced by Revision 2.
- [`docs/invariants.md`](docs/invariants.md) — architectural invariants.
- [`docs/tasks.md`](docs/tasks.md) — Task specifications, write scopes, and budgets.
- [`docs/decisions.md`](docs/decisions.md) — concise decision index; full ADRs are under `docs/decisions/`.
- [`docs/testing.md`](docs/testing.md) — test and verification strategy.

## Technical baseline

Python 3.12+, SQLAlchemy 2, PostgreSQL with pgvector, Alembic, `uv`, pytest, Ruff, and mypy. See `pyproject.toml`, `uv.lock`, and `compose.yaml` for the executable configuration. `.github/workflows/ci.yml` runs the same checks against a disposable PostgreSQL service container.

## Development rule

Make small, testable changes under the authority defined by `PLAN.md`, `CHANGE_MAP.md`, and the relevant spec/ADR. If the sources conflict or a milestone gate is blocked, stop and report rather than guessing. See `AGENTS.md` for the operating contract.
