# R6 Entry Gate — Knowledge-Grounded Execution and Experience Distillation

## Status and authority

- **R6-G0: IN PROGRESS.** The operator authorized R6 entry-gate planning on 2026-10-24 and approved revising the design direction on 2026-10-25.
- **No R6 implementation slice has started or is authorized by this document change.** This is a documentation/design revision only. No application code, schema, migrations, providers, vector indexes, or runtime behavior are changed here.
- **ADR-0028 and ADR-0029 are Accepted for architectural principles only**, based on the operator's explicit agreement with the design direction on 2026-10-25. Their concrete implementation choices remain unresolved R6-G0 decisions. This acceptance does not authorize implementation.
- Repository baseline after merge of PR #7 and subsequent main update: remote GitHub main at 9eb01aa0e9b5bad3289b131cce51b29d33a3986c (2026-10-25). This is not evidence of the operator's current local branch, HEAD, or worktree. Verify the actual local checkout before implementation.
- R5 remains formally closed. Its Plan materialization, lifecycle, prerequisite, provenance, and completion-precondition requirements remain mandatory. The end-to-end Task-execution dependency remains assigned to R6. ADR-0027 remains Proposed unless separately accepted.

## 1. Revised R6 purpose

R6 should deliver the first small, testable **knowledge-grounded Watch loop**, not only a Task-completion path.

The intended cycle is:

1. Maintain a domain knowledge core for what the team knows about a subject, including source provenance, claims, evidence, uncertainty, and relevant context.
2. Use RAG to retrieve a bounded set of relevant records for a specific task or Objective.
3. Assemble a traceable context from retrieved records, current authoritative state, applicable policy, and the task's purpose.
4. Let an LLM propose a strategy or perform a bounded task, while existing application validation and Kernel commit boundaries remain authoritative.
5. Record what actually happened in durable Tasks, Events, source records, and Outcomes.
6. Use LLMs to propose reusable abstractions from recorded experience—patterns, practices, methods, or playbooks—rather than merely retaining transcripts or summarizing individual runs.
7. Validate and commit accepted experience through the authorized learning path, then make accepted knowledge retrievable for future work.

This is the target design, not a claim that the full cycle exists today.

### Logical knowledge layers

The design distinguishes three logical roles without requiring three separate databases:

- **Domain Knowledge Core — what we know about the subject.** Canonical source records, subject context, claims or hypotheses, evidence, provenance, freshness, and unresolved questions. Existing World-memory records and immutable source Snapshots are relevant foundations; the exact core representation remains a G0 decision.
- **Team Experience Core — what we have learned by doing the work.** Accepted, versioned practices, patterns, methods, and playbooks based on evaluated experience and supporting evidence. The architecture describes KnowledgeItem and LearningChange concepts, but their current ORM/migration implementation must be verified and completed as part of the approved path.
- **Task Context — what is relevant now.** A bounded, task-specific assembly of retrieved knowledge, canonical records, current state, policy constraints, and source/version references. It is a derived input, not a new authority.

RAG is the retrieval mechanism across these logical layers. A single physical index may serve multiple logical cores, provided team/domain scope, access control, record kind, status, and provenance remain explicit. The index is a regenerable projection, never the source of truth (INV-11).

## 2. Existing foundations and gaps

### Existing foundations

- Objective creation/lifecycle and deterministic, read-only StateAssessment construction.
- Strategy proposal validation, accepted-event provenance, and reconstruction; StrategyService validates a supplied proposal but does not currently call a model to create it.
- Plan materialization, reconstruction, lifecycle, Action-to-Task mapping, prerequisite admission, and durable completion preconditions.
- TaskRuntime admission with policy/quota checks and Task-attributed task_started Event.
- Ingestion proposal validation and atomic commit for fetched bytes supplied to the service.
- World-memory concepts, immutable source Snapshots, EvidenceLinks, and architecture-level KnowledgeItem, Outcome, Evaluation, and LearningChange specifications.

### Gaps that must not be mistaken for implementation

- No complete worker dispatcher/lifecycle path performs Task completion, failure, retries, and recovery.
- Ingestion does not fetch a configured source or execute it as a Task.
- The current ORM/migrations do not yet implement the documented Outcome, Evaluation, and KnowledgeItem entities; confirm actual branch state before planning schema work.
- There is no implemented RAG-backed knowledge-core retrieval/context assembly path established by this baseline.
- There is no end-to-end LLM-assisted experience-distillation and accepted-knowledge re-indexing path established by this baseline.
- There is no model-backed Strategy proposer established by this baseline.
- The production model provider, embedding/reranking choices, index implementation, freshness mechanics, and detailed context-packet persistence semantics are not selected by this proposal.

## G0 recommendation packet

See [R6-G0 Decision Proposals](r6-g0-decision-proposals.md) for a concrete recommendation per unresolved decision, grounded in the current code/spec baseline. That document is advisory only: no ADR has been accepted by implication, and operator decisions must be recorded explicitly in the relevant ADR/spec before the gate can exit.

## 3. R6-G0: required decisions before implementation

R6-G0 remains open until the decisions below are recorded in authoritative documents and the first vertical-slice contract is testable. Recommendations are not accepted decisions.

### G0-D1 — Existing Control decisions and authority

Review and explicitly decide ADR-0025 (Plan is derived execution state) and ADR-0026 (dual-entry execution model). ADR-0027 also remains Proposed and must not be treated as accepted by implication.

Preserve these established R5/R6 boundaries: Plan is immutable intent; Tasks, Events, source records, and Outcomes describe execution; reactive and deliberative entry paths converge on ordinary Tasks; no second runtime; Task and Plan safeguards remain in force.

### G0-D2 — Task lifecycle and recovery

Choose one application-controlled owner for successful completion, retryable failure, exhausted failure, attempt semantics, timestamps, Task-attributed Events, idempotency, and replay recovery. Extend TaskRuntime or define a narrowly scoped lifecycle service used by the same runtime. Worker code must not write Task lifecycle state or Events directly.

### G0-D3 — First executable capability and network boundary

The first worker remains a bounded configured-source ingest_source Task. Define permitted URL schemes; validation of configured and resolved destinations; private, loopback, link-local, and metadata-service protections; redirect revalidation; connection/read timeouts; response-size limits; malformed responses; HTTP failures; and cancellation behavior.

Prefer one injectable source-fetch interface, a fake fetcher in tests, and a production fetcher restricted to approved configured sources. Do not expose arbitrary model-chosen URLs, shell, or general filesystem access.

### G0-D4 — Outcome and reassessment contract

Define the first supported Outcome kind, subject and Team ownership, source/provenance requirements, Task write scope, transaction boundary, event semantics, idempotency, and crash/replay behavior. Decide whether Outcome persistence is part of the application-controlled final completion transaction or a separate scoped Task operation. Preserve the historical StateAssessment basis used by the originating Strategy/Plan; a follow-up assessment must be deterministic and read-only.

### G0-D5 — Remaining implementation choices for Knowledge Cores and RAG ([ADR-0028](../decisions/ADR-0028-rag-backed-knowledge-cores.md))

Decide:
- Which canonical records make up the initial Domain Knowledge Core and which accepted records make up the Team Experience Core.
- Whether the first slice needs a distinct durable context-core/brief entity or can derive the view from existing canonical records; do not add entities for convenience.
- Retrieval scoping and authorization by Team/domain, knowledge layer, entity kind, current status, and sensitivity.
- Retrieval/index design, including keyword/vector or hybrid matching, embedding model/version, optional reranking, context budget, freshness, re-indexing, and failure behavior.
- How retrieved candidates are resolved back to current canonical records and how source Snapshots, hashes, statuses, and conflicting claims are represented in the Context.
- Whether and how the selected context basis is durably recorded so a Strategy/Outcome can be explained and reconstructed later.

The retrieval index must remain regenerable and non-authoritative. A vector match alone is not proof of a claim. Corrections, supersession, rejection, retirement, or access changes must prevent stale or unauthorized indexed content from being treated as current. Existing source/quote validation remains in force.

### G0-D6 — Remaining implementation choices for experience distillation ([ADR-0029](../decisions/ADR-0029-llm-assisted-experience-distillation.md))

Define the first distillation input and output contract:
- Inputs are durable experience records, Outcomes, applicable Evaluations, and referenced evidence—not an unbounded conversation transcript.
- The LLM proposes an abstraction that explains its supporting cases, scope/applicability, assumptions, limitations, counterexamples, and unresolved uncertainty.
- The first vocabulary should align with the existing KnowledgeItem kinds: practice, pattern, method, and playbook, subject to the actual schema and accepted authority.
- A proposal must retain provenance to its basis and must not convert correlation or a single successful case into unsupported general truth.
- Application validation and the existing authorized learning commit path govern persistence. The LLM does not directly create or revise KnowledgeItems or TeamPolicy.
- The accepted version, supersession/review behavior, and the point at which it becomes retrievable must be explicit. Only accepted canonical knowledge is published to retrieval; the index itself is not a commit path.
- The first R6 vertical slice should use a bounded, reviewable approval path. No autonomous policy changes, recursive self-modification, or automatic acceptance merely because a Task succeeded.

### G0-D7 — Strategy proposer and model-provider boundary

Define a narrow StrategyProposer interface that consumes the objective, deterministic assessment, policy constraints, and approved assembled Context. Provider calls occur outside database transactions. All model output passes existing Strategy validation and accepted-event provenance before Plan materialization. Select the production provider or explicitly stage that choice; do not add a dependency, credential path, or provider network behavior by assumption.

### G0-D8 — First end-to-end acceptance contract

Freeze the first test domain, seed/context setup, allowed source capability, first Outcome type, distillation basis, approval path, and deferred scope. The first integrated success should demonstrate:

- A Strategy proposal is grounded in a recorded, bounded RAG Context and is accepted through the existing validator.
- One accepted Strategy materializes one immutable Plan and ordinary Task(s).
- A bounded configured-source Task executes through the single runtime, with safe fetch rules and idempotent recovery.
- Durable execution evidence and an Outcome support a reproducible follow-up StateAssessment.
- An LLM proposes an evidence-linked reusable abstraction from that experience.
- The authorized learning path accepts or rejects it explicitly; rejected or unapproved knowledge is not published as accepted retrieval context.
- A subsequent task can retrieve an accepted abstraction, resolve its canonical provenance, and use it without relying on the prior transcript.

Broader scheduling, multiple worker types, arbitrary tools, autonomous policy changes, general replanning, multi-domain automation, and large-scale learning-quality optimization remain outside the first vertical slice.

## 4. Proposed implementation traversal after G0 exits

These are future implementation slices only. They must not begin until G0 exit decisions and acceptance criteria are recorded.

### R6-A — Task execution lifecycle

Implement the application-controlled lifecycle following TaskRuntime admission: success, retryable failure, exhausted failure, Events, timestamps, concurrency/conflict handling, replay, and idempotency.

**Exit:** legal transitions only; Task state and Events agree; retries and crashes do not double-commit or leave partial lifecycle changes.

### R6-B — One bounded configured-source worker

Add a small dispatcher/handler for the configured-source ingest_source Task. It loads durable Task/source context, uses the approved restricted fetcher, invokes the existing IngestionService, and reports outcomes through the lifecycle owner. The handler cannot commit business rows or lifecycle state directly.

**Exit:** integration tests cover admission → handler → ingestion commit → lifecycle completion, including no-change, rejection, retry, crash after ingestion commit, and replay without duplicate Signals or Events.

### R6-C — Durable Outcome and reassessment

Implement the G0-approved Outcome representation, scope, service, migration if required, provenance, and idempotency. Build a new deterministic assessment from the resulting durable records while preserving the original decision basis.

**Exit:** restart/replay reconstructs the Plan and explains the execution result; reassessment is reproducible from the same durable state.

### R6-D — RAG-backed Knowledge Cores

Implement the minimal canonical knowledge selection and a regenerable retrieval projection consistent with ADR-0028. Retrieve source-grounded Domain Knowledge Core records and, where available, accepted Team Experience Core records. Preserve access and status filtering, canonical references, index freshness/rebuild behavior, and a bounded context budget.

**Exit:** tests prove relevant retrieval, Team/domain isolation, status/access filtering, traceable source references, stale-index rejection after a canonical change, and index rebuild/replay. No retrieval-only assertion can commit a fact or lesson.

### R6-E — Task Context assembly and StrategyProposer

Assemble a bounded Context from RAG candidates resolved to current canonical records plus Objective, StateAssessment, policy constraints, and permitted task information. Record sufficient source/version provenance for later explanation. Use a fake proposer in tests and the G0-approved production-provider boundary. Submit the proposal through existing Strategy validation; only an accepted proposal may materialize a Plan.

**Exit:** tests cover source attribution, conflicting/uncertain evidence, context limits, model-output rejection, provider failure, and no Plan for a rejected proposal.

### R6-F — First experience-distillation path

Build a scoped distillation operation from durable Outcomes/Evaluations and their evidence basis. An LLM proposes a reusable practice, pattern, method, or playbook with scope, limits, counterexamples/uncertainty, and source references. Validate the proposal and route it through the approved LearningChange/learning commit path. Publish only accepted canonical versions to RAG.

**Exit:** tests cover a valid abstraction, missing or mismatched evidence, contradictory examples, single-case overgeneralization, rejection, duplicate/replay behavior, version/supersession, and failure to publish an unaccepted proposal.

### R6-G — Integrated vertical slice and formal gate

Exercise the full cycle from Objective/assessment and RAG Context through accepted Strategy, Plan/Task execution, durable Outcome, follow-up assessment, proposed and accepted distillation, index update, and retrieval by a later task. Verify recovery after restart and explainability from canonical records rather than transcripts.

Run required focused and full-suite tests, Ruff, mypy, and applicable disposable-PostgreSQL migration/integration checks. Record actual commands, environment, results, skipped checks, and remaining limitations. R6 is not closed by code, tests, or merge alone; request explicit operator exit approval.

## 5. Non-negotiable constraints

- Worker/model output is a proposal, never authority for a durable write.
- Preserve Task scope, budgets, policy-version checks, quota semantics, Plan prerequisites, and Kernel/application validation.
- Every durable write and Event remains attributable to an authorized Task.
- Plan intent and historical Strategy/assessment provenance remain immutable and reconstructable.
- StateAssessment remains deterministic, derived, read-only, and non-authoritative.
- RAG indexes, embeddings, summaries, and context rankings are projections; canonical records determine truth and current status.
- A claim's retrieved relevance is not a truth score. Preserve supporting and challenging evidence, uncertainty, and source provenance.
- Team memory changes only through the authorized learning path (INV-12); no direct worker writes and no automatic policy changes.
- Reactive Tasks remain valid without Objectives or Plans. No second runtime, scheduler, or workflow engine.
- R5's durable Plan-completion preconditions remain mandatory.
- ADR-0025, ADR-0026, and ADR-0027 must not be silently accepted. ADR-0028 and ADR-0029 are accepted only at the architectural-principle level; their remaining implementation choices stay gated.
- Use disposable databases for tests; never modify the persistent watch database to make tests pass.
- PLAN.md remains the single source of current milestone status; update CHANGE_MAP.md when authority mapping changes.

## 6. G0 exit checklist

- [ ] Explicit operator disposition recorded for ADR-0025 and ADR-0026.
- [ ] Task completion, failure, retry, attempt, Event, timestamp, and recovery contract agreed.
- [ ] Bounded ingest_source behavior and network-safety contract agreed.
- [ ] Outcome schema/scope/provenance/transaction/replay semantics agreed.
- [ ] ADR-0028's remaining implementation choices are explicitly decided: canonical record types, retrieval approach/model versions, Context-basis representation, scope/permissions, freshness, rebuild, and recovery.
- [ ] ADR-0029's remaining implementation choices are explicitly decided: first proposal schema, evidence/counterexample handling, review/approval mechanics, versioning, and retrieval publication boundary.
- [ ] StrategyProposer interface and production provider decision recorded, or provider choice explicitly deferred with a bounded fake-backed implementation scope.
- [ ] First integrated acceptance tests, first domain, review path, failure/recovery cases, and deferred scope frozen.
- [ ] Actual local branch, HEAD, merge status, worktree, and disposable database verified before implementation.

Until this checklist is satisfied, keep R6-G0 in progress. This documentation redesign does not start R6-A or authorize schema, network, provider, index, or lifecycle implementation.
