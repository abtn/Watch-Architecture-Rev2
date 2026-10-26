# R6-G0 Decisions — Accepted Defaults and Staged Choices

## Status and authority

**Decision record: all architectural/design decisions requested for R6-G0 are recorded as of 2026-10-25.** This is planning authority only and does not authorize any R6 implementation. **R6-G0 is COMPLETE as of 2026-10-25**: the recorded design decisions are complete and the local checkout preflight is documented. **R6-A additionally requires a separate explicit operator instruction** and is not authorized by this record or by the G0 closeout.

Governing records:
- [ADR-0025](../decisions/ADR-0025-plan-is-derived-execution-state.md) — accepted unchanged.
- [ADR-0026](../decisions/ADR-0026-dual-entry-execution-model.md) — accepted unchanged.
- [ADR-0027](../decisions/ADR-0027-team-policy-daily-task-quota.md) — remains Proposed; not accepted by implication.
- [ADR-0028](../decisions/ADR-0028-rag-backed-knowledge-cores.md) — accepted RAG contract.
- [ADR-0029](../decisions/ADR-0029-llm-assisted-experience-distillation.md) — accepted distillation contract.
- [ADR-0030](../decisions/ADR-0030-r6-bounded-execution-source-safety-outcome.md) — accepted Task lifecycle, source-fetch safety, and Outcome contract.

## Decision summary

| G0 item | Decision | Authority |
|---|---|---|
| D1 — Existing Control decisions | Accept ADR-0025 and ADR-0026 unchanged; keep ADR-0027 Proposed. | ADR-0025–0027 |
| D2 — Task lifecycle and recovery | TaskRuntime is the sole lifecycle authority; three total starts; 30-second worker deadline; recover a running attempt after 60 seconds using attempt-number fencing. | ADR-0030, `docs/tasks.md` |
| D3 — Source fetch | Only exact configured HTTPS sources; reject non-public or unsafe destinations; no redirects; 3/10/15-second connect/read/total timeouts; 2 MiB decompressed body ceiling. | ADR-0030 |
| D4 — Outcome | Exactly one terminal `task_execution` Outcome per Task; immutable observation Snapshot; terminal Task state, Event, and Outcome committed atomically. | ADR-0030, `docs/architecture.md` |
| D5 — RAG | Signal + immutable source Snapshot form the initial Domain Knowledge inputs; accepted KnowledgeItems form Team Experience; PostgreSQL full-text + pgvector hybrid retrieval; RRF (k=60), at most 8 passages / 8,000 characters. | ADR-0028 |
| D6 — Distillation | Typed LearningChange payload with provenance and limits; two independently evaluated Tasks for cross-case abstractions; one-case candidate limited to a low-confidence, narrowly scoped practice; explicit operator approval. | ADR-0029 |
| D7 — Providers | Provider-neutral interfaces and fakes. Select/pin embedding provider/model before R6-D; generation provider/model before R6-E. No early SDK, secrets, or external calls. | ADR-0028/0029 |
| D8 — Acceptance domain | Fictional newsroom/scientific-reporting fixture, with conflicting evidence, Team isolation, rejection, stale-index, and crash/replay tests. Deterministic acceptance tests use fake fetch and model providers. | R6 entry gate |

## Initial canonical-data and retrieval boundaries

The Domain Knowledge Core initially reads canonical Signal records and immutable source Snapshots (`snapshot_ref`, `content_hash`). Signals are not Team-owned in the current ORM; initial retrieval is authorized against the requesting Team's current `TeamPolicy.rules["sources"]` allowlist using exact `(origin_url, source_type)` pairs, then filtered by Team/domain before model exposure. If authorization or canonical provenance cannot be resolved, fail closed.

The Team Experience Core contains only accepted, versioned KnowledgeItems committed through the authorized learning path. Proposed/rejected LearningChanges, retired or superseded items, and items marked `needs_review` or past their review date are excluded. Do not implement every conceptual World-memory entity in the first slice.

Use PostgreSQL full-text plus pgvector, combine up to 20 candidates from each channel using reciprocal-rank fusion (k=60), and select at most eight passages, capped at 8,000 Unicode characters in total; chunks are at most 1,200 characters with 150-character overlap. No reranker or separate vector service is included. The embedding provider/model/version is selected immediately before R6-D, then pinned and recorded with the projection.

Persist the exact assembled Context as an immutable content-addressed Snapshot and record a Task-attributed `context_assembled` Event manifest with canonical references/hashes, logical core, query hash, chunk IDs, ranking/config version, and embedding model/version. Do not add a standalone Context table for this slice.

Projection entries are rebuildable. Resolve candidates against current canonical records and current access/status/hash before exposing them. A stale, unauthorized, rejected, retired, superseded, or review-due record is excluded even if its old vector remains. Projection failure never rolls back canonical data and never allows the system to claim that a newly accepted version is retrievable until the current projection is ready.

## Distillation and learning boundary

Distillation uses durable Task Events, terminal Outcomes, recorded Evaluations, and referenced canonical evidence—not an unbounded transcript. The proposal contains kind, title, statement, body, applicability/preconditions, assumptions, limitations, missing information, uncertainty, supporting Outcome/Evaluation/Signal/Snapshot references, counterexamples, and a deterministic basis hash. Store this proposal in the LearningChange proposed state; do not assume a new database column for every proposal field.

Two distinct Task Outcomes with recorded Evaluations are required to represent a cross-case Pattern, Method, or Playbook. A single case may only motivate a low-confidence practice tied to its exact situation and may not be generalized. Contradictory evidence remains visible. All first-slice LearningChanges are explicitly reviewed by an operator through `approve_learning_change`; the LLM cannot accept itself or revise TeamPolicy. Only the current accepted active version, not past its review date, is retrieval-eligible.

Accepted canonical knowledge and its index projection have separate failure semantics. If publishing/indexing fails, the canonical learning decision remains durable, but the new version is not claimed retrievable until projection recovery succeeds and retrieval-time canonical checks pass.

## First integrated acceptance contract

Use static fictional news/science sources, including at least one contradictory or negative source, and at least two independently evaluated Task Outcomes to exercise cross-case distillation. The full deterministic acceptance suite proves:

1. Configured-source ingestion with no arbitrary URL choice, redirects, unsafe destinations, or oversized body.
2. Hybrid retrieval and a bounded Context with exact Snapshot/manifest provenance.
3. Accepted Strategy validation followed by exactly one immutable Plan and ordinary Tasks; rejected Strategy means no Plan.
4. Task success, retryable failure, three-start exhaustion, interruption recovery, and crash after ingestion commit without duplicate Signals, Events, or Outcomes.
5. Exactly one terminal Outcome committed atomically with terminal Task state/Event and deterministic follow-up StateAssessment.
6. Typed distillation that preserves conflicting evidence; one-case generalization and invalid evidence references are rejected.
7. Explicit LearningChange rejection is never retrievable; explicit acceptance through the authorized learning path is retrievable by a later Task without prior transcript.
8. Team/domain isolation, stale-index exclusion/rebuild, provider/fetch failure, and idempotent replay.

## Deferred by design

- No selected production embedding or generation provider yet; their decision points are before R6-D and R6-E respectively.
- No SDK, credential, or external provider call before the relevant slice's decision and approval.
- No reranker, separate vector service, redirect-following, PDF fetch, arbitrary model-selected URL, shell, or general-purpose tools.
- No broad new World-memory model family, separate Context entity, second runtime, new general scheduler, unattended learning acceptance, direct TeamPolicy mutation, or recursive self-modification.

## Authorization prerequisite

The operational prerequisite — verify actual local branch, HEAD, status/diff, merge state, migrations, and disposable PostgreSQL database using `AGENTS.md` — is **satisfied 2026-10-25** and recorded in [PLAN.md](../../PLAN.md) and the [R6 entry gate](r6-entry-gate.md). R6-G0 is therefore COMPLETE.

This decision record still does not claim the code exists or that R6-A is authorized. The remaining gate is explicit operator authorization: R6-A requires a separate explicit operator instruction.
