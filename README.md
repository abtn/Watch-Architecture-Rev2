# Watch — Persistent, Evidence-Oriented Team System

Watch is designed to turn temporary model workers into durable, auditable team experience. Model workers propose; application code validates and commits; durable records preserve what the system learned and did.

> **Model intelligence is temporary. Team experience is persistent.**

## Architecture in one line

**Reactive or deliberative entry → ordinary Task → Worker proposal → application validation → Kernel/application commit → durable records and Events.**

A Plan is intended work, not execution truth. Tasks and Events record execution. Derived assessments do not become authority merely because a model produced them.

## Current state (snapshot 2026-10-29)

[`PLAN.md`](PLAN.md) is the single source of current milestone status; the summary below is a convenience snapshot, not an authority record.

**Completed foundations**

- **K0, K1:** tooling baseline (Python 3.12+/uv, PostgreSQL + pgvector, Alembic, pytest, Ruff, mypy) and the smallest proposal → validation → atomic Kernel commit → Event path (`ingest_source`).
- **R0–R3:** Revision 2 semantics and boundaries, Kernel/Task compatibility, durable Objective model and lifecycle, and the deterministic read-only `StateAssessment` with provenance.
- **R4 (closed 2026-10-20):** StrategyProposal boundary — multi-Vision/Workstream/Action Strategy semantics with deterministic validation and reconstruction.
- **R5 (closed 2026-10-24):** Plan materialization and lifecycle — one accepted Strategy materialized as one durable Plan with ordinary Tasks and enforced lifecycle constraints.

**R6 in progress — first knowledge-grounded end-to-end loop**

- **R6-G0 (complete, 2026-10-25):** design decisions recorded in ADR-0025/0026/0028/0029/0030 and the R6 entry gate. ADR-0027 remains Proposed.
- **R6-A (complete, PR #12):** Task lifecycle — outcome schema and migration, atomic terminal `task_execution` Outcome finalization, retry scheduling and attempt exhaustion, and bounded interrupted-task recovery (`TaskRuntime.recover_interrupted()`).
- **R6-B (complete, PR #14):** the first working execution path — `TaskDispatcher` and `RestrictedFetcher` run one configured-source `ingest_source` Task end to end through the Kernel with startup recovery and policy-authorized source identity.
- **R6-C (complete, PR #16):** deterministic, read-only `ExecutionAssessmentBuilder` that rebuilds Plan intent and Task attempt history from durable records, validates Outcome/Snapshot/Event/Signal consistency, and hashes the canonical result. It adds no migration and no write path.
- **R6-D (code merged by PR #22; local smoke gate pending):** provider-neutral embeddings, an OpenAI-compatible embeddings API adapter, the `knowledge_chunks` projection, an idempotent Signal indexer, snapshot/hash verification, model-readiness polling, and a current-policy-scoped PostgreSQL full-text/vector hybrid retriever. The operator selected local BAAI/BGE-M3 served through LM Studio (2026-10-29); R6-D stays in progress until the local smoke gate confirms the configured model through the API (1,024-dimensional vectors, indexing, idempotency, authorized retrieval).
- **Verification baseline:** CI runs fresh PostgreSQL migrations, Ruff, mypy, and the full test suite on every merge — 462 tests passing at the R6-D merge head.

**Next actionable step:** run the R6-D local smoke gate — sync `main`, load an embedding-capable BAAI/BGE-M3 model in LM Studio, configure Watch with the exact ID from `GET /v1/models`, and follow [`docs/development/local-embeddings.md`](docs/development/local-embeddings.md), including `uv run python -m core.embedding_smoke` against a migrated development or disposable PostgreSQL database. Until that real local check passes, R6-D remains in progress.

## Future plan

Roadmap per [`PLAN.md`](PLAN.md); future phases are not authorized by the existence of code or proposed documents.

- **R6 remaining:** **R6-E** — bounded Task Context assembly with its Snapshot/Event manifest and a model-backed StrategyProposer (generation provider/model sign-off required first); **R6-F** — LLM-assisted experience distillation committed through the authorized learning path; **R6-G** — the integrated vertical slice, full verification, and explicit exit gate.
- **R7 — Distillation quality and knowledge lifecycle:** cross-case evaluation of abstractions, contradictory evidence and counterexamples, transferability tests, retrieval quality, review/expiry, staleness detection, supersession, and retirement — always preserving explicit provenance, canonical authority, and controlled commits.
- **R8 — Multi-domain pressure test:** exercise the same Control layer across newsroom, development-team, and generalist settings while domain-specific knowledge stays outside the Kernel.
- **R9 — Agent-assisted production workflow:** codified bounded task packets, test-first changes, architecture reviews, verification evidence, and human approval boundaries.
- **Deferred cross-cutting work:** execution security (per-worker filesystem/network/tool surface, secret isolation) and complete spend accounting before expanding beyond tightly bounded workers; a broad multi-domain experience library beyond the initial R6 slice.

## Repository guide

- [`CONTEXT.md`](CONTEXT.md) — concise session orientation.
- [`PLAN.md`](PLAN.md) — current milestone status, gates, and next action.
- [`AGENTS.md`](AGENTS.md) — instructions for coding agents.
- [`docs/development/agent-delivery-protocol.md`](docs/development/agent-delivery-protocol.md) — standing delivery authorization, automatic advancement, and merge conditions.
- [`docs/development/local-embeddings.md`](docs/development/local-embeddings.md) — local LM Studio / BGE-M3 embedding API setup and smoke gate.
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
