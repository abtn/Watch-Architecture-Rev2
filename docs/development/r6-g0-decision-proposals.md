# R6-G0 Decision Proposals — Recommended Defaults for Operator Review

## Status and authority

**Status: recommendation packet only — no decisions accepted.** Prepared for R6-G0 on 2026-10-25 after the documentation redesign was merged to `main` at `83148dc0aedef5c69d2a9491cd0933efb11ca419`.

This document makes the open gate easier to resolve. It does not amend ADR statuses, authorize implementation, select a production provider, or replace the canonical rules in `PLAN.md`, `AGENTS.md`, `CHANGE_MAP.md`, specs, and accepted ADRs. Every item below is a recommendation for explicit operator approval or revision.

## Summary of recommended direction

| Decision | Recommendation | Still requires |
|---|---|---|
| ADR-0025 — Plan as derived execution state | Accept unchanged | Explicit operator disposition |
| ADR-0026 — Dual-entry execution | Accept unchanged | Explicit operator disposition |
| ADR-0027 — Daily Task-start quota | Leave Proposed for now; do not broaden R6 scope | Separate disposition if desired; preserve current documented behavior |
| Task lifecycle/retry | One application-controlled lifecycle owner used by the existing runtime; typed and auditable transitions | Agree transition/event semantics, retry bound, and required schema |
| First worker/network | One configured-source `ingest_source` capability; HTTPS and publicly routable destinations only for the first slice; validate every redirect | Approve security contract and exact finite limits before code |
| First Outcome | A durable, typed Task-execution observation for the terminal result; separate observation from Evaluation | Agree payload, Snapshot/provenance, uniqueness, and atomicity contract |
| RAG substrate | Start with existing PostgreSQL + pgvector capability; evaluate hybrid keyword/vector retrieval; do not add a separate vector service without evidence | Choose embedding provider/model/version and retrieval test set before R6-D |
| Knowledge cores | Domain knowledge and accepted team experience remain logically distinct, even if they share one retrieval index | Confirm initial canonical record types and permissions |
| Context provenance | Preserve an immutable, source/version-linked context basis; no transcript dependency | Choose Snapshot/manifest representation and retention/access rules |
| Experience distillation | LLM proposes scoped abstractions from durable Outcomes/Evaluations/evidence; initial acceptance is reviewable and goes through the existing learning authority | Approve evidence threshold, proposal fields, version lifecycle, and publication rule |
| Model providers | Define provider-neutral interfaces and test with fakes; defer production selection until the relevant slice needs network access | Explicit model and embedding provider choices before R6-D/R6-E |
| First acceptance domain | Use a small newsroom/scientific-reporting fixture as a pressure test; keep Kernel, schemas, and core contracts domain-neutral | Agree fixture data and exact end-to-end test cases |

## G0-D1 — ADR-0025 and ADR-0026

### Recommendation

Accept both ADRs unchanged after explicit operator review.

- **ADR-0025:** Plan is immutable, bounded intent, not execution history, team memory, or a second source of truth. Tasks, Events, source records, and Outcomes describe execution.
- **ADR-0026:** reactive and deliberative entry paths converge on the same ordinary Task runtime. RAG Context and strategy generation sit before Task execution; they do not create a second runtime or bypass existing admission, scope, budget, or commit checks.

These principles already align with the R5 Plan contract and the revised R6 direction. The RAG index, Context snapshot/manifest, and accepted team knowledge must not be stored by silently expanding Plan into a mutable memory store.

**No status change is made here.** The operator must explicitly accept or request revision to each ADR. ADR-0027 remains a separate Proposed decision and is not silently accepted by this packet.

## G0-D2 — Task completion, failure, retry, and recovery

### Recommendation

Keep the existing `TaskRuntime` boundary as the single application-controlled lifecycle owner, adding narrowly scoped lifecycle operations there or in a service it owns. Worker handlers return typed success/failure results; they never update Task status or write lifecycle Events directly.

Recommended transition contract:

| Current state | Condition | Next state | Required durable effect |
|---|---|---|---|
| `pending` | Valid admission | `running` | Existing `task_started` Event and attempt increment, atomically |
| `running` | Valid terminal success | `done` | Set `completed_at` and record `task_completed` in the same transaction |
| `running` | Retryable failure with attempts remaining | `pending` | Record `task_retry_scheduled` with attempt and reason metadata, atomically |
| `running` | Non-retryable failure or retry limit exhausted | `failed` | Record `task_failed` with a categorized reason, atomically |

Every transition is checked against the expected prior state. A repeated completion/retry call must be idempotent or rejected as a conflicting transition; it must not emit a second terminal result. A failed business commit must not leave the Task marked completed. A crash after a business commit but before task finalization must be recoverable through the existing operation/Event idempotency—not by repeating the business effect.

The effective attempt limit should be pinned when a Task is created so a future configuration change does not silently change the meaning of an already-running Task. G0 must choose its storage location and initial value; do not infer or hardcode them during implementation. Exhaustion means the configured maximum number of total starts has been consumed, with `attempt_count` incremented by the existing admission operation.

### Known model/spec alignment issue to resolve

The architecture's Task definition lists `created_at` and `completed_at`; the current `core/models.py` Task ORM shown on `main` has neither field. The ORM also has `attempt_count` but no explicit per-Task max-attempt field. R6-A must reconcile the actual current migrations, ORM, creation paths, and Task specification before choosing the smallest justified schema change. This is an implementation prerequisite, not permission to assume a migration.

## G0-D3 — Bounded `ingest_source` and network safety

### Recommendation

Use one injectable fetcher available only to the configured-source `ingest_source` handler. The model must not choose an arbitrary URL or turn retrieved text into network authority.

For the initial production fetch boundary, propose:
- accept only explicitly configured HTTPS source URLs;
- reject loopback, private, link-local, multicast, reserved, and metadata-service destinations;
- validate the resolved destination at the connection boundary, not only by checking the URL text;
- disable redirects by default, or follow them manually with the full URL/DNS/IP validation repeated for every hop;
- apply explicit finite connect/read/total timeouts and a response-size limit, with their numerical values selected and frozen before implementation;
- reject unsupported schemes, unsafe destinations, oversized responses, malformed responses, and unapproved redirects with a categorized failure Event;
- use a fake fetcher for deterministic tests; keep network calls outside database transactions.

HTTPS and destination restrictions are a conservative first-slice proposal, not a claim that a specific HTTP library or production fetcher has been selected.

## G0-D4 — First durable Outcome

### Recommendation

Use the existing architecture-level `Outcome` concept and add one explicitly defined first type, proposed as `task_execution`, whose subject is the terminal Task. Do not invent a separate execution-history runtime.

The Outcome should capture a deterministic observation packet, not an LLM explanation: terminal result category, relevant Signal/Artifact/other canonical record identifiers, content hashes or Snapshot references, and observation time. `success_signal_created`, `success_no_change`, and terminal failure are illustrative result categories to validate against the actual first handler. Attempt-level failures remain visible in Task Events; the Outcome represents the terminal Task result, not every retry attempt. An Evaluation can then interpret the Outcome separately.

Recommended consistency boundaries:
- canonical business effects, such as Signal creation/no-change, retain their existing atomic commit and idempotency rules;
- Task terminal state, its transition Event, and the terminal Outcome should commit atomically if the final result is already reconstructable;
- if a crash occurs after ingestion commit but before terminal finalization, retry/replay must discover the prior committed result and finalize without duplicate Signals or duplicate terminal Outcomes;
- define a uniqueness/idempotency rule for the terminal Outcome per Task and validate Team ownership, Task attribution, and provenance.

The architecture's `Outcome` fields include observation Snapshot reference/hash and `recorded_by_task_id`; they do not currently give the ORM implementation a completed generic result payload. G0 should decide whether a content-addressed typed observation Snapshot is sufficient or whether a narrowly scoped model field is justified. Do not implement before that decision and a migration plan are recorded.

## G0-D5 — RAG and canonical knowledge

### Recommendation

Start with the project's existing PostgreSQL infrastructure and pgvector extension (migration `0001_enable_pgvector.py` already enables it). Do not add a separately operated vector database for the first slice. Evaluate hybrid keyword/vector retrieval: exact names, entities, and source terms matter alongside semantic similarity in broad-subject work. Add the required Python adapter and retrieval projection only after model/version, canonical input scope, chunking, and acceptance tests are selected.

Recommended logical separation:

- **Domain Knowledge Core:** source-grounded subject material and its validated domain state, with canonical source/Snapshot references, claims or hypotheses when available, evidence for/against, status, and uncertainty.
- **Team Experience Core:** accepted, versioned KnowledgeItems produced through the authorized learning path; proposed/rejected LearningChanges are not accepted retrieval knowledge.
- **Task Context:** bounded material assembled for one job from permitted records in either core plus current Objective/assessment/policy state.

These are logical layers, not a mandate for separate stores. Retrieval chunks and embeddings are rebuildable projections tagged with Team/domain, source record kind/ID, canonical version/hash, chunk identity, embedding model/version, and relevant lifecycle/access metadata. Access and status filters must be applied before content is exposed to the model and must be checked against canonical records at retrieval time. A stale vector entry must not revive a rejected, superseded, retired, or unauthorized record.

The current ORM baseline is much smaller than the architecture description; it has Team, TeamPolicy, Objective, Plan, PlanAction, Task, Signal, and Event but not the documented Thread/Hypothesis/EvidenceLink/KnowledgeItem/Outcome/Evaluation models. G0 must decide which of these canonical representations are required for the first slice and sequence their implementation; do not create every documented entity merely because it appears in the conceptual architecture.

### Context basis

Recommend persisting a small immutable, Task-attributed Context basis through the existing Snapshot/Event provenance patterns, rather than adding a standalone Context entity by default. It should identify the exact canonical record and Snapshot/version/hash references selected, the logical core, and the retrieval/chunking/embedding configuration needed to explain the context. Whether to preserve the exact assembled context text as a content-addressed Snapshot or a structured manifest plus source snapshots remains an explicit G0 decision; account for privacy/access and bounded retention.

The context is an LLM input, not authoritative memory. Context selection must not overwrite the original assessment basis, mutate source records, change policy, or itself validate claims.

## G0-D6 — Experience distillation and publication

### Recommendation

Distillation input should be durable Task/Outcome/Evaluation records plus their evidence basis—not the free-form transcript. The LLM proposes a typed Practice, Pattern, Method, or Playbook with:
- the situation and task class it applies to;
- its proposed method/pattern and assumptions;
- supporting Outcome/Evaluation/evidence references;
- boundaries, known limitations, missing information, uncertainty, and counterexamples or contrary cases;
- a basis hash/version so stale or conflicting proposals can be rejected or re-proposed.

Use the existing `LearningChange` boundary for proposal and commit where it fits the authoritative schema. The model never writes accepted KnowledgeItems or TeamPolicy directly. For the first R6 loop, acceptance should be explicitly reviewable through the authorized learning path; do not auto-promote a lesson because a Task succeeded.

For broad or transferable patterns, prefer multiple independently evaluated cases and represent contradictory evidence explicitly. A single case may at most motivate a narrowly scoped candidate; it must not be presented as a general rule without an approved basis. A numerical evidence threshold must be selected as part of G0 only if the first task requires one—do not treat “two examples” alone as proof of causation or general validity.

Publication rule: only an accepted canonical KnowledgeItem version is eligible for retrieval. A proposed/rejected LearningChange never becomes accepted context. Index update failure does not roll back the canonical learning commit, but the system must report the index as stale and not claim the new version is retrievable until indexing and current-state checks succeed.

## G0-D7 — StrategyProposer and provider choice

### Recommendation

Define a small provider-neutral StrategyProposer and embedding-provider boundary. Test the orchestration and validation using deterministic fakes. Do not call a production provider inside a database transaction, and never pass raw model output directly to Plan materialization.

It is reasonable to defer the production provider choice until R6-E, and the embedding provider/model choice until R6-D, provided the interfaces, configuration, secrets boundary, cost attribution, timeouts, and failure semantics are agreed before those slices start. Do not add an SDK or credentials path in R6-A through R6-C. The existing architecture mentions Anthropic but the current `pyproject.toml` does not include a provider SDK, so no provider should be inferred as selected from source prose alone.

## G0-D8 — First integrated acceptance domain and boundaries

### Recommendation

Use a small **newsroom/scientific-reporting fixture** as the first test domain because it exercises broad-subject context, named entities, conflicting sources, original-study provenance, and reusable editorial methods. This is test data, not a newsroom-specific Kernel or a restriction of Watch to journalism.

The first vertical slice should prove the full knowledge cycle:

1. A configured source is ingested through the single Task runtime with safe-fetch rules.
2. Canonical source/evidence records become eligible for a bounded, traceable Domain Knowledge retrieval.
3. An approved Task Context is assembled and its provenance preserved.
4. The Strategy proposer generates a proposal; the existing validator either rejects it or records accepted provenance before Plan creation.
5. The accepted Plan materializes ordinary Tasks and executes through the same runtime.
6. A terminal Task result and durable Outcome can be reconstructed after a crash/replay; follow-up StateAssessment is deterministic and read-only.
7. An LLM proposes an evidence-linked reusable abstraction from durable experience.
8. The authorized learning path accepts or rejects it explicitly; only accepted canonical knowledge is indexed as Team Experience.
9. A later Task retrieves the accepted abstraction and can trace it to its source cases without depending on the earlier transcript.

Tests must include at least one conflicting/negative case and rejection path. They must also prove Team/domain isolation, stale-index behavior, duplicate/replay safety, and no Plan for a rejected Strategy.

## Suggested decision order

To minimize rework, resolve G0 in this order:

1. **Authority:** explicit disposition of ADR-0025/0026; confirm ADR-0027 stays separate.
2. **Execution contract:** Task lifecycle/retry bound, safe fetch boundary, and Outcome shape/atomicity.
3. **Knowledge contract:** initial canonical record set, pgvector/hybrid retrieval direction, Context basis/provenance, index freshness and access filters.
4. **Distillation contract:** required evidence inputs, approval/commit path, versioning, and publication after acceptance.
5. **Providers and tests:** decide how model/embedding choices can be deferred; freeze the newsroom fixture and full failure/recovery acceptance test.
6. **Preflight:** verify the actual local branch, HEAD, worktree, migrations, and disposable database before any implementation branch is started.

A decision becomes authoritative only when the operator explicitly approves/revises it and the relevant ADR/spec and `PLAN.md` are updated. Until then, these are proposed defaults for review, R6-G0 remains IN PROGRESS, and no implementation slice is authorized.
