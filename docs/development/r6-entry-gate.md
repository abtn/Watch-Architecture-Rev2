# R6 Entry Gate — Knowledge-Grounded Execution and Experience Distillation

## Status and authority

- **R6-G0 design decisions: RECORDED.** The operator explicitly requested resolution of the remaining G0 decisions on 2026-10-25. The accepted records are ADR-0025, ADR-0026, ADR-0028, ADR-0029, and ADR-0030.
- **R6-G0 milestone status: COMPLETE — 2026-10-25.** The design decisions are recorded and the local checkout preflight is documented below. **This closeout did not itself authorize R6-A or any implementation**; R6-A required a separate explicit operator instruction, which was subsequently given.
- **R6-A current status: COMPLETE — merged to `main` by PR #12** (merge commit `ebbc48d`, 2026-10-28). Four checkpoints were delivered on branch `r6a-step1-schema-outcome`: Step 1 schema at `42257ad` (migration `0009_task_lifecycle_outcome`, the `Outcome` ORM mapping, and explicit `max_attempts=3` pinning in `PlanService._create`, with focused schema tests); Checkpoint 2A terminal finalization at `c3e9428`; Checkpoint 2B retry scheduling and attempt exhaustion at `e05a8a4`; and Checkpoint 2C interrupted-task recovery at `da47694` in `TaskRuntime.recover_interrupted()`, with focused recovery tests in `tests/test_task_lifecycle_recovery.py`. Automated CI is committed at `bda8d55` and passed on the merged head `ffe8e76`. The R6-A exit criteria in §4 are satisfied. Dispatcher wiring is R6-B. See `PLAN.md` for the authoritative milestone status.
- **ADR-0027 remains Proposed.** Its Task-start quota semantics are separate; this decision record neither accepts that ADR nor changes quota behavior.
- Git baselines: PR #8 merge commit `44c0944720600f8a1d4018d4eb39424a9660168e` is the historical baseline for the original decision set; PR #9 merge commit `f9207156533b6944d320a6adfff42963f7e1e17c` is the verified current `main` baseline. Neither is evidence of the operator's local branch, HEAD, worktree, or database state; the verified local state is recorded in the preflight record below.
- R5 remains formally closed. Its immutable Plan, prerequisite, provenance, lifecycle, completion-precondition, and single-runtime constraints remain mandatory.
- Current implementation gaps remain real: TaskRuntime admits Tasks, finalizes terminal results, handles retry/exhaustion, and recovers interrupted Tasks, but does not dispatch work; configured-source fetch is absent; the `Outcome` entity exists in the ORM and migrations (R6-A Step 1) and is written by terminal finalization (Checkpoint 2A), while Evaluation/KnowledgeItem/LearningChange persistence plus RAG Context assembly/distillation remain unimplemented. This record changes no code, schema, migration, provider, network, index, or runtime behavior.

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

- **Domain Knowledge Core — what we know about the subject.** Canonical source records, subject context, claims or hypotheses, evidence, provenance, freshness, and unresolved questions. Existing World-memory records and immutable source Snapshots are relevant foundations; the exact core representation is recorded in ADR-0028.
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

- No complete worker dispatcher/lifecycle path dispatches work: terminal finalization, retry/exhaustion transitions (R6-A Checkpoints 2A/2B), and interrupted-task recovery (Checkpoint 2C) are implemented, but dispatch is not.
- Ingestion does not fetch a configured source or execute it as a Task.
- The current ORM/migrations implement the documented `Outcome` entity (R6-A Step 1) and terminal finalization writes one (Checkpoint 2A), but Evaluation and KnowledgeItem are not implemented. Confirm actual branch state before planning further schema work.
- There is no implemented RAG-backed knowledge-core retrieval/context assembly path established by this baseline.
- There is no end-to-end LLM-assisted experience-distillation and accepted-knowledge re-indexing path established by this baseline.
- There is no model-backed Strategy proposer established by this baseline.
- The production model provider, embedding/reranking choices, index implementation, freshness mechanics, and detailed context-packet persistence semantics are not selected by this proposal.

## 3. R6-G0 — resolved decisions and exit boundary

The concrete G0 decisions are recorded in the following authorities. The decision packet is a summary and navigation aid, not a competing specification.

| Decision | Recorded disposition | Governing authority |
|---|---|---|
| G0-D1 — Control authority | Accept ADR-0025 and ADR-0026 unchanged. Keep ADR-0027 Proposed and separate. | ADR-0025, ADR-0026, ADR-0027 |
| G0-D2 — Task lifecycle/recovery | One TaskRuntime lifecycle authority; three total starts; attempt-number fencing; bounded interrupted-task recovery; atomic terminal Event + Outcome. | ADR-0030; `docs/tasks.md` |
| G0-D3 — Source-fetch security | One configured-source HTTPS fetcher; no redirects; public-address/DNS-rebinding defenses; finite time/size limits; fake fetcher in tests. | ADR-0030 |
| G0-D4 — Outcome | One terminal `task_execution` Outcome per Task, backed by immutable observation Snapshot and committed atomically with terminal Task state/Event. | ADR-0030; `docs/architecture.md` |
| G0-D5 — Knowledge/RAG | Initial Domain Knowledge is Signal + immutable source Snapshot; accepted Team KnowledgeItems are Experience Core; PostgreSQL full-text + pgvector hybrid retrieval; bounded, immutable Context provenance; stale/unauthorized candidates fail closed. | ADR-0028 |
| G0-D6 — Distillation | Typed, evidence-linked LearningChange; two evaluated Tasks for cross-case abstractions; one-case practice stays narrow/low-confidence; explicit operator review; only current accepted versions are retrievable. | ADR-0029 |
| G0-D7 — Providers | Provider-neutral interfaces and deterministic fakes. Defer embedding provider/model choice until immediately before R6-D and generation provider/model until immediately before R6-E. Those choices must be recorded before their respective slices. | ADR-0028, ADR-0029, `PLAN.md` |
| G0-D8 — First acceptance fixture | Domain-neutral implementation tested with a small fictional newsroom/scientific-reporting fixture, including conflicting evidence, Team isolation, rejection, stale index, and crash/replay cases. No external network/model calls in the deterministic acceptance suite. | This gate; `docs/testing.md` |

The accepted architectural loop remains:

Domain Knowledge + accepted Team Experience → bounded RAG Context → validated Strategy → immutable Plan + ordinary Tasks → bounded worker execution → durable Outcome → deterministic reassessment → evidence-linked distillation proposal → authorized learning commit → current retrieval projection → later Task reuse.

RAG rank is not truth; LLM output is never authority for durable writes. Team memory changes only through INV-12's learning path. The first slice does not introduce a second runtime, a general scheduler, arbitrary tools, automated TeamPolicy changes, or recursive self-modification.

### First integrated acceptance contract

The deterministic end-to-end fixture must demonstrate all of the following before R6-G completion:

1. Ingest configured HTTPS source fixtures into canonical Signal/Snapshot records, without arbitrary URL selection.
2. Retrieve relevant Domain Knowledge with the approved hybrid strategy; prove source authorization, Team/domain isolation, canonical hash/status checks, and the 8,000-character Context limit.
3. Persist a content-addressed Context Snapshot and Task-attributed manifest with canonical references and retrieval configuration.
4. Use a fake StrategyProposer. A valid proposal passes the existing validator and preserves accepted provenance before one immutable Plan creates ordinary Tasks; a rejected proposal creates no Plan.
5. Execute through the single Task runtime. Test unsafe-host rejection, no redirects, response limits, transient retry, three-start exhaustion, and a crash after ingestion commit but before terminal finalization without duplicate Signal/Event/Outcome records.
6. Record exactly one terminal `task_execution` Outcome with its Snapshot and finalize Task status/Event atomically; reproduce deterministic follow-up StateAssessment from the same durable state.
7. Feed at least two independently evaluated Task Outcomes, plus a contrasting case, to a deterministic fake distiller. Validate the typed proposal and its basis hash. A one-case candidate may only be a narrowly scoped low-confidence practice.
8. Reject a LearningChange and prove it is not retrievable; separately accept one through the authorized learning path and prove only that current canonical version is eligible.
9. Retrieve the accepted Team Experience in a later Task without using the previous transcript. Exercise stale-index exclusion and rebuild after a canonical version/status change.
10. Inject provider, transaction, projection, and replay failures; verify canonical writes remain atomic and index failure never pretends to accept or publish knowledge.

**Frozen initial limits:** three total Task starts per Task; 30-second worker deadline; recover an orphaned running Task after 60 seconds with attempt-number fencing; source connect/read/total timeouts of 3/10/15 seconds; 2 MiB decompressed response ceiling; no redirects; maximum eight retrieved passages and 8,000 Unicode characters of retrieved knowledge. Production embedding and generation providers are deliberately staged to R6-D and R6-E, respectively.

### Explicitly deferred

No production provider/SDK or credentials path before its slice; no external reranker or separate vector service; no arbitrary URLs, redirect following, PDFs, shell, or general-purpose tools; no additional World-memory entity families unless the first slice proves them necessary; no unattended learning acceptance, direct TeamPolicy mutation, autonomous policy learning, or general multi-domain automation.

## 4. Proposed implementation traversal after G0 exits

These are implementation slices. G0 is complete and R6-A is complete (merged to `main` by PR #12, merge commit `ebbc48d`). The remaining slices must not begin until their predecessor gate is satisfied and a separate explicit operator instruction authorizes them.

### R6-A — Task execution lifecycle and atomic terminal Outcome

Implement the application-controlled lifecycle following TaskRuntime admission: success, retryable failure, exhausted failure, Events, timestamps, concurrency/conflict handling, replay, and idempotency. R6-A includes the minimum complete terminal `task_execution` Outcome persistence required by [ADR-0030 §4](../decisions/ADR-0030-r6-bounded-execution-source-safety-outcome.md): on terminal success or terminal failure the Outcome, immutable observation Snapshot reference/hash, terminal Task status, and terminal Task Event commit atomically in the same transaction, with the ADR-0030 uniqueness/idempotency and Task-attribution rules applied from the first implementation.

**Exit:** legal transitions only; Task state and Events agree; terminal finalization cannot commit without its required Outcome; retries and crashes do not double-commit or leave partial lifecycle changes.

### R6-B — One bounded configured-source worker

Add a small dispatcher/handler for the configured-source ingest_source Task. It loads durable Task/source context, uses the approved restricted fetcher, invokes the existing IngestionService, and reports outcomes through the lifecycle owner. The handler cannot commit business rows or lifecycle state directly.

**Exit:** integration tests cover admission → handler → ingestion commit → lifecycle completion, including no-change, rejection, retry, crash after ingestion commit, and replay without duplicate Signals or Events.

### R6-C — Outcome-backed deterministic reassessment and follow-on integration

Consume the terminal Outcomes already made durable by R6-A: build a new deterministic assessment from those durable records while preserving the original decision basis, and complete the remaining Outcome-driven integration. R6-C does not own the initial terminal Outcome representation or write path; it must not defer, duplicate, or weaken R6-A's atomic terminal finalization contract.

**Exit:** restart/replay reconstructs the Plan and explains the execution result from the Outcomes and Events R6-A already committed; reassessment is reproducible from the same durable state; replay after restart produces no duplicate Outcome, Event, or derived record.

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

## 6. G0 decision checklist and implementation authorization prerequisite

- [x] ADR-0025 explicitly accepted unchanged.
- [x] ADR-0026 explicitly accepted unchanged.
- [x] ADR-0027 explicitly remains Proposed; no quota status change.
- [x] Task lifecycle, retry limit, expected-attempt fencing, timestamps, Events, and interrupted-task recovery recorded in ADR-0030.
- [x] Bounded configured-source behavior and network-safety limits recorded in ADR-0030.
- [x] Terminal Outcome shape, provenance, uniqueness, transaction, and replay rules recorded in ADR-0030.
- [x] Initial canonical Knowledge Core inputs, PostgreSQL hybrid retrieval, scope/access filters, Context Snapshot/manifest, bounds, freshness, and rebuild behavior recorded in ADR-0028.
- [x] Distillation proposal fields, evidence rule, review/commit, versioning, and publication boundary recorded in ADR-0029.
- [x] Provider choices intentionally staged: embedding provider/model before R6-D; generation provider/model before R6-E.
- [x] First deterministic acceptance fixture and success, rejection, failure, and replay contract recorded above.
- [x] **Before implementation:** verify actual local branch, HEAD, merge status, worktree, current migrations, and disposable PostgreSQL database using `AGENTS.md`. The remote branch or a documentation export is not local preflight evidence. **Satisfied 2026-10-25 — see the preflight record below.**

**Gate status:** all design decisions requested for G0 are recorded and the local preflight is documented, so **R6-G0 is COMPLETE as of 2026-10-25**. Completing G0 did not itself authorize implementation; **R6-A required a separate explicit operator instruction, which was subsequently given.** **R6-A is now COMPLETE and merged to `main` by PR #12** (merge commit `ebbc48d`): checkpoints 1/2A/2B/2C are delivered and the R6-A lifecycle scope is covered end to end. ADR-0027 remains Proposed, and the embedding/generation provider choices remain staged to before R6-D and before R6-E.

## 7. R6-G0 local preflight record — 2026-10-25

Documentation-only closeout. No application code, tests, migrations, schema, Docker volumes, or persistent database contents were changed; no commit, push, merge, reset, or branch deletion was performed. No database commands or tests were run during this closeout — the preflight results below are the operator-supplied and previously recorded evidence.

**Verified local Git state:**

- Branch `R5-rebased`; HEAD `f9207156533b6944d320a6adfff42963f7e1e17c`.
- HEAD equals `origin/main` (`f920715`, merge of PR #9); no divergence and no local-only commits.
- The preflight checks were completed while the working tree was clean. The closeout itself introduces six intentional, unstaged documentation modifications (`PLAN.md`, this file, `docs/development/r6-g0-decision-proposals.md`, `CHANGE_MAP.md`, `CONTEXT.md`, `docs/control-model.md`). The working tree is therefore **not** clean at the end of this closeout; nothing is staged, committed, or pushed.

**Migrations:** the source chain is a single lineage `0001` → `0008_plan_lifecycle_state`. During preflight, `uv run alembic upgrade head`, `uv run alembic current`, and `uv run alembic heads` against the isolated disposable database `watch_r6_preflight` reported `0008_plan_lifecycle_state (head)` with exactly one head.

**Recorded preflight verification results:** `DATABASE_URL` and `TEST_DATABASE_URL` targeted `watch_r6_preflight` on `127.0.0.1:55448` (persistent `watch` database never targeted); `uv run pytest` → 260 passed in 25.88 seconds; `uv run ruff check core tests migrations` → passed; `uv run mypy core` → passed (11 source files); `git diff --check` → clean.

**Exit boundary:** every item in the §6 checklist above is satisfied. G0 completion does not authorize R6-A, does not accept ADR-0027, and does not select the embedding or generation providers.
