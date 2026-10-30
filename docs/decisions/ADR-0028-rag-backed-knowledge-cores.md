# ADR-0028 — RAG-backed Knowledge Cores

## Status

**Accepted — architectural principles and initial R6 implementation contract, 2026-10-25, under the operator's explicit request to resolve the remaining R6-G0 decisions.** The initial embedding provider decision and R6-D authorization are recorded below; this does not authorize R6-E or change its separate generation-provider gate.

## Context

Watch needs to support work on broad subjects, such as a newsroom's coverage area, where an LLM cannot rely on the current prompt or a previous conversation to establish what the team knows. It needs to retrieve a focused, source-traceable body of context that survives individual Tasks and model runs.

The existing architecture already distinguishes World memory (what is observed or believed about the subject) from Team memory (what the team has learned from its work). Signals, immutable Snapshots, Threads, Hypotheses, EvidenceLinks, Outcomes, Evaluations, and KnowledgeItems are relevant concepts. The current implementation does not yet provide the complete canonical KnowledgeItem/Outcome/Evaluation model set or an end-to-end RAG-backed Context assembly path; confirm the actual branch state before implementation.

A vector index is useful for locating relevant content, but it is a lossy, derived projection. It must not become the source of truth or a way to bypass the existing evidence and application-validation rules.

## Decision

### 1. Three logical roles

The system should distinguish the following roles. They do not require three separate databases or vector stores.

- **Domain Knowledge Core — what the team knows about the subject.** Canonical source records and their Snapshots, relevant subject context, claims or hypotheses, evidence supporting or challenging them, source quality and freshness, uncertainty, and unresolved questions. Its purpose is to make the team's current subject knowledge retrievable without reducing it to an unqualified summary.
- **Team Experience Core — what the team has learned by doing the work.** Accepted and versioned practices, patterns, methods, and playbooks derived from evaluated experience and traceable supporting evidence. It changes only through the authorized learning path (INV-12).
- **Task Context — what is relevant to this job.** A bounded, derived selection assembled for one Task or Objective from retrieved candidates, their current canonical records, current state, applicable policy, and source/version provenance. A Context is an input to reasoning, not an authority.

A physical retrieval service may index both cores. Retrieval must preserve the logical layer, Team/domain ownership, access restrictions, record kind, lifecycle/acceptance status, and provenance so that one core cannot silently be treated as the other.

### 2. Retrieval flow

The intended flow is:

1. Determine retrieval intent and permitted scope from the Task and Objective.
2. Retrieve a bounded candidate set from the applicable knowledge layers.
3. Resolve each candidate to its current canonical record and verify Team/domain ownership, access, lifecycle status, and relevant source references.
4. Assemble a Context that preserves uncertainty, supporting and challenging evidence, and the distinction between source material and interpretation.
5. Send only the authorized, budget-bounded Context to the LLM.
6. Preserve enough retrieval and source/version provenance to explain the proposal and support later reconstruction, subject to the G0 decision about the exact persistence representation.

A retrieved result is relevant material to inspect, not a verified fact. The underlying canonical records and the existing commit/quote validation rules govern. Existing immutable Snapshots, hash checks, EvidenceLink validation, and INV-11 remain in force.

### 3. Canonical authority and index lifecycle

- Canonical durable records remain authoritative. Embeddings, summaries, retrieval rankings, chunks, and index metadata are projections.
- The retrieval index must be rebuildable from canonical records and version/configuration information. A failed or delayed index update must not commit or lose canonical state.
- A canonical status, access, or version change must be reflected in retrieval eligibility. Superseded, rejected, retired, revoked, or unauthorized material must not be returned as current merely because an old vector remains in an index.
- Source Snapshot immutability is preserved. Corrections are represented by new source evidence and explicit domain-state transitions, not by silently replacing a stored Snapshot.
- Retrieval results should point back to stable canonical identifiers and relevant source references. Model-authored citations are not authoritative; output citation assembly and evidence validation continue to use the existing application rules.
- Team, Objective, Task, and tool/write-scope boundaries cannot be widened by a retrieval query or a model-generated request.

### 4. Initial implementation boundary

**Initial retrieval decisions:** use the existing PostgreSQL database with its enabled pgvector extension; do not add a separately operated vector service or reranker for the first slice. Use hybrid PostgreSQL full-text and vector retrieval, combine the top 20 candidates from each channel with reciprocal-rank fusion (RRF, k=60), then select at most 8 passages and 8,000 Unicode characters of retrieved knowledge. Chunk source text at a maximum of 1,200 characters with 150-character overlap. The selected initial embedding provider, model, dimensions, revision, and configuration fingerprint are recorded in the R6-D provider decision below. CI and deterministic acceptance tests use deterministic fake embeddings and never make inference-provider calls; production projections record the exact model/configuration identity and entries from another vector space are never mixed into a query.

## Consequences

- Broad-subject context becomes a persistent and retrievable capability rather than a prompt assembled from an entire transcript.
- LLM proposals can be traced to the particular source records and accepted experience they consumed.
- Context retrieval remains replaceable and rebuildable without changing canonical knowledge semantics.
- The R6 plan includes implementation and tests for RAG-backed retrieval and Context assembly before the first integrated intelligent loop is considered complete.

## Alternatives considered

- **Treat the vector index as the authoritative knowledge store:** rejected. Similarity and indexing freshness cannot establish truth, status, ownership, or the provenance of a claim.
- **Put every source and lesson into every prompt:** rejected. It is unbounded, poorly scoped, difficult to audit, and does not provide reliable cross-Task persistence.
- **Require a separate physical RAG service for every logical core:** not required by the design. Logical scope and semantics must be separate; physical deployment can be selected against the project's actual scale and operational needs.

## Initial canonical records, scope, and Context contract

- **Domain Knowledge Core for the first slice:** existing canonical `Signal` records and their immutable source Snapshots, identified by `snapshot_ref` and `content_hash`. Do not add Thread, Hypothesis, EvidenceLink, or a separate subject-brief/Context entity solely to support the first slice; add other canonical types only when a later approved slice demonstrates the need.
- **Team Experience Core:** accepted, versioned `KnowledgeItem` records only. R6 must add the minimum missing `KnowledgeItem` and `LearningChange` persistence/commit path required by ADR-0029; the current ORM does not yet provide them.
- **Task Context:** a derived per-Task view containing permitted Domain Knowledge, accepted Team Experience, Objective/StateAssessment and policy constraints. No standalone Context row is required.
- **Team/domain isolation:** Signals are not Team-owned in the current schema. For the first slice, a Signal is eligible only if its exact `(origin_url, source_type)` pair appears in the requesting Team's current `TeamPolicy.rules["sources"]` allowlist, using the existing ingestion configuration shape; resolve that authorization at retrieval time as well as when projecting. Team Experience is scoped by `team_id`. Filter before model exposure and fail closed if authorization or canonical provenance cannot be resolved.
- **Canonical resolution:** every candidate must be resolved to its current Signal/KnowledgeItem and source Snapshot before use. Preserve source URL, Snapshot reference/hash, record kind/ID, canonical status/version, Team/domain scope, chunk identity, and index/embedding configuration. Include supporting and challenging source references where they exist. Ranking is relevance, not truth.
- **Context basis:** preserve the exact assembled Context bytes as an immutable content-addressed Snapshot using the existing Snapshot mechanism, and emit a Task-attributed `context_assembled` Event with a versioned manifest of selected canonical references/hashes, logical core, query hash, chunk identifiers, ranking/config version, and embedding model/version. Do not add a standalone Context entity. Apply existing access rules and bounded retention to the Snapshot.
- **Freshness/rebuild:** store canonical content hash/version and configuration version with each index projection. At query time, exclude any entry whose canonical record is missing, no longer authorized, no longer eligible, or has changed hash/version. Rebuild/update is idempotent from canonical records. Projection failure must not roll back a canonical Signal or accepted KnowledgeItem; record/reconcile staleness and do not claim a newly accepted version is retrievable until its projection is current. Rejected, retired, superseded, and `needs_review` knowledge is not eligible.
- A source-policy change takes effect immediately at query time even if stale vectors remain. If source access cannot be established from current policy, retrieval returns no such record rather than guessing.

## R6-D provider decision — 2026-10-29 (updated)

The operator selected **local BAAI/BGE-M3 served by LM Studio through an OpenAI-compatible embeddings API** as the initial real embedding path. This supersedes the earlier local-serving-adapter choice while preserving the model/retrieval boundary. The implementation uses one generic adapter for providers that implement the standard `/v1/models` and `/v1/embeddings` contract; it does not depend on an LM Studio SDK or a vendor-specific embedding schema.

- **API contract:** call `GET /v1/models` to confirm that the exact configured model ID is visible, then call `POST /v1/embeddings` with `model`, `input`, and `encoding_format: "float"`. The default base URL is `http://localhost:1234/v1`; the endpoint is configurable. An optional bearer token is read from configuration and never logged.
- **Model and dimensions:** BGE-M3 is the intended first local model and is expected to return 1,024-dimensional vectors. The exact API model ID must be copied from the server's model list after installation. Validate count, order, dimensions, numeric values, and finiteness for each response; do not silently accept vectors with a different width.
- **Provider and model identity:** the vector-space fingerprint covers the compatible API adapter, normalized endpoint identity, exact model ID, revision, dimensions, and versioned request configuration. For the qualified local BGE-M3 setup, the operator explicitly set `WATCH_EMBEDDING_REVISION=metadata-sha256:e8ffcf172118d67251eccbf45916e407b7e0537deef08f70bbd62e86518e9c69`. This is the same metadata fingerprint observed from `/v1/models`, so the explicit pin preserves the previously qualified vector-space key.
- **Revision honesty:** OpenAI-compatible APIs do not standardize an immutable model-weight digest. The metadata fingerprint is a best-effort identity, not proof that weights behind an unchanged model ID have not changed. The current explicit pin is `metadata-sha256:e8ffcf172118d67251eccbf45916e407b7e0537deef08f70bbd62e86518e9c69`; it is not a cryptographic digest of model-file or quantized-weight bytes. The operator must bump `WATCH_EMBEDDING_REVISION` whenever model weights, quantization, normalization, or preprocessing changes, including changes the API metadata cannot expose. A changed vector-space key makes the old projection ineligible and requires re-indexing rather than mixing vectors.
- **Local readiness and retries:** wait up to the configured readiness timeout (default 180 seconds), polling `/v1/models` with bounded exponential delay until the exact configured model ID appears. Use a conservative local batch size (default 8), a per-request timeout (default 180 seconds), and at most two embedding-request attempts by default. Retry only transient network, timeout, overload/rate-limit, and server failures; permanent request/model/configuration errors fail immediately. The adapter does not issue vendor-specific load/unload calls or assume that a model is on GPU. The local model manager owns model loading and CPU/GPU placement.
- **Execution and cost:** the local model is downloaded once by the operator into the model manager's cache, not the Watch repository. Local inference uses CPU/GPU time, RAM/VRAM, storage, and electricity; hosted compatible APIs may incur charges and data-handling implications. Do not commit model weights, local caches, private source snapshots, credentials, or tokens. CI uses deterministic fake embeddings and never calls an actual provider or downloads model weights.
- **Local qualification evidence (2026-10-30):** **Disposable database verification: PASSED. Embedding integration smoke test: PASSED.** The operator ran `uv run alembic upgrade head` and verified `0010_knowledge_chunk_projection (head)` on the dedicated disposable PostgreSQL database at `127.0.0.1:55450/watch_embedding_smoke`; both database environment variables targeted that database. With explicit revision pin `metadata-sha256:e8ffcf172118d67251eccbf45916e407b7e0537deef08f70bbd62e86518e9c69`, the LM Studio model `text-embedding-bge-m3` returned 1,024-dimensional vectors and passed projection indexing, repeat-indexing idempotency, and authorized hybrid retrieval.
- **Initial scope:** index only existing canonical Signal records and their immutable source Snapshots for the Domain Knowledge Core. Signals are not Team-owned; authorize each query using the requesting Team's current exact `(origin_url, source_type)` source allowlist. Team Experience indexing waits for canonical, accepted KnowledgeItems through ADR-0029; Task Context assembly remains R6-E work.

## Acceptance criteria for implementation

- Tests demonstrate relevant hybrid retrieval, Team/domain isolation, configured-source authorization, canonical reference/hash resolution, and bounded Context size.
- Rejected, retired, superseded, out-of-scope, or stale records never reach a model merely because a vector entry remains.
- Context provenance is reconstructable from its immutable Snapshot and Event manifest.
- Index update/rebuild is idempotent and projection failure leaves canonical state intact.
- Retrieval does not validate claims or commit knowledge; all writes still use the ordinary Task and authorized application/Kernel path.

