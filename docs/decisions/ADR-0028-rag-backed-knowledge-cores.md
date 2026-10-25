# ADR-0028 — RAG-backed Knowledge Cores

## Status

**Accepted — architectural principles only, 2026-10-25, by explicit operator agreement with the RAG-backed Knowledge Core design.** This acceptance does not authorize implementation. Retrieval-store selection, embedding/reranking choices, canonical input types, Context-basis persistence, freshness mechanics, and other concrete implementation choices remain within R6-G0.

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

R6 should begin with one bounded Team/domain and a small, auditable retrieval flow. It should be possible to use a single physical index while maintaining separate logical retrieval filters for Domain Knowledge and accepted Team Experience. The initial keyword/vector/hybrid strategy, embedding model, optional reranking, persistence of a Context manifest, index freshness mechanism, and concrete index storage are open G0 choices; this ADR does not select a provider or mandate a schema.

## Consequences

- Broad-subject context becomes a persistent and retrievable capability rather than a prompt assembled from an entire transcript.
- LLM proposals can be traced to the particular source records and accepted experience they consumed.
- Context retrieval remains replaceable and rebuildable without changing canonical knowledge semantics.
- The R6 plan includes implementation and tests for RAG-backed retrieval and Context assembly before the first integrated intelligent loop is considered complete.

## Alternatives considered

- **Treat the vector index as the authoritative knowledge store:** rejected. Similarity and indexing freshness cannot establish truth, status, ownership, or the provenance of a claim.
- **Put every source and lesson into every prompt:** rejected. It is unbounded, poorly scoped, difficult to audit, and does not provide reliable cross-Task persistence.
- **Require a separate physical RAG service for every logical core:** not required by the design. Logical scope and semantics must be separate; physical deployment can be selected against the project's actual scale and operational needs.

## Implementation decisions remaining for R6-G0

- Which exact canonical entity types and source records are in the initial Domain Knowledge Core?
- Does the first version need a separate durable subject brief/context-core entity, or can it derive the view from existing canonical records?
- What retrieval approach, embedding model/version, and optional reranker are appropriate for the first bounded slice?
- How are filters for Team/domain, sensitivity, status, and knowledge layer enforced and tested?
- What context size/ranking policy is used, and how are conflicting evidence and stale records presented?
- What exact Context/retrieval manifest must be persisted to reconstruct why a Strategy proposal was made?
- How are index versions, deletion/retirement, retries, rebuilds, and partial update failures handled?

## Acceptance criteria for a future implementation

- Tests show that relevant canonical source and knowledge records can be retrieved for a bounded query and traced to their canonical references.
- Team/domain and access filters are enforced before material is exposed to a worker.
- Rejected, superseded, stale, or unauthorized records are not treated as current because an index is stale.
- Index projections can be rebuilt from canonical state, and failures never mutate canonical knowledge.
- Retrieved evidence preserves source provenance and relevant uncertainty; retrieval ranking alone cannot validate or commit a claim.
- The selected Context is bounded and its basis is explainable from durable records.
- The implementation does not bypass existing Task, policy, evidence, and Kernel/application validation boundaries.

These criteria describe the accepted architectural target, not completed tests or current capabilities.
