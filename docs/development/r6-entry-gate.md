# R6 Entry Gate — Knowledge-Grounded Execution and Experience Distillation

## Status and authority

- **R6-G0 design decisions: RECORDED.** The operator explicitly requested resolution of the remaining G0 decisions on 2026-10-25. The accepted records are ADR-0025, ADR-0026, ADR-0028, ADR-0029, and ADR-0030.
**Current milestone status:** see [PLAN.md](../../PLAN.md). This document defines gate decisions and acceptance criteria rather than duplicating the current milestone table. The original G0 preflight and authorization record below is retained as historical evidence.
- **ADR-0027 remains Proposed.** Its Task-start quota semantics are separate; this decision record neither accepts that ADR nor changes quota behavior.
- **R6-E provider/model decision: ACCEPTED for R6-E only (2026-10-30).** ADR-0031 records Cloudflare Workers AI `@cf/meta/llama-3.1-8b-instruct-fp8`; PR #28 merged on 2026-11-01 and R6-E is formally closed. ADR-0031 does not authorize R6-F use. R6-F Checkpoints 1–4 were separately authorized, implemented, verified, and merged by PRs #29–#32. The combined C3+C4 operator-local disposable-PostgreSQL verification passed against the exact source tree subsequently merged by PR #33; full evidence and the pre-merge timing qualification are in `docs/testing.md`. D10 remains create-only. R6-G was separately authorized, verified 10/10, explicitly approved and merged by PR #35 on 2026-11-04. See PLAN.md for authoritative status.
- Git baselines: PR #8 merge commit `44c0944720600f8a1d4018d4eb39424a9660168e` is the historical baseline for the original decision set; PR #9 merge commit `f9207156533b6944d320a6adfff42963f7e1e17c` is the verified current `main` baseline. Neither is evidence of the operator's local branch, HEAD, worktree, or database state; the verified local state is recorded in the preflight record below.
- R5 remains formally closed. Its immutable Plan, prerequisite, provenance, lifecycle, completion-precondition, and single-runtime constraints remain mandatory.
- **Implementation boundaries:** TaskRuntime remains the lifecycle authority; TaskDispatcher executes one configured-source `ingest_source` Task through the restricted fetcher and IngestionService. `Outcome` is canonical terminal evidence, and `ExecutionAssessmentBuilder` reconstructs it read-only. R6-E delivered bounded RAG Context assembly and the model-backed StrategyProposer. R6-F Checkpoints 1–4 are complete: persistent Evaluation/EvidenceLink records, canonical KnowledgeItem/LearningChange foundations, bounded ExperienceDistiller proposals, trusted in-process Operator review/canonical create-only commit, and Team Experience publication/retrieval through the existing Context path. D10 still excludes revise/retire proposal and commit paths. R6-G demonstrated and delivered the full integrated loop; current milestone status and authorization remain solely in PLAN.md.

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

- The implemented dispatcher path is intentionally narrow: it supports one configured-source ingest_source Task; a general multi-task-type dispatcher and scheduler are not part of this slice.
- IngestionService validates and commits fetched bytes supplied to it; the configured-source fetch and dispatch path is implemented separately in TaskDispatcher.
- `Outcome` is canonical terminal evidence. `ExecutionAssessmentBuilder` reconstructs execution evidence read-only; persistent Evaluation/KnowledgeItem/LearningChange records remain unimplemented, as do RAG Context assembly and experience distillation.
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

### D9 — Initial Evaluation source (resolved 2026-11-03)

**Accepted choice:** the first R6-G integrated slice uses a deterministic, code-defined rule-based evaluator. It does not use human-supplied or model-generated Evaluations. The evaluator is a read-only producer of a typed draft; the existing `EvaluationService` remains the proposal/evidence/disposition boundary, and `TaskRuntime` remains the sole lifecycle authority.

**Ruleset identity:** `evaluator_kind="rule"`, `evaluator_identity="watch.r6g.ingest-source-rules"`, `evaluator_revision="1"`. The identity/revision are persisted in each Evaluation. A semantic rule change requires a new revision; previously recorded Evaluations retain the version that produced them.

**Version 1 scope and predicates:** only `ingest_source` Task Outcomes are in scope. The evaluator reads the durable `task_execution` Outcome and its immutable observation Snapshot, the source Task and its pinned PlanAction/policy provenance, the matching current-attempt terminal Events, the matching `signal_ingested` or `fetch_no_change` Event, and the referenced same-Team/domain Signal and immutable Snapshot. It checks exact ID/reference/hash/attempt/status agreement; it does not interpret arbitrary source prose or use model output.

- `success_signal_created` → `worked` only when Task status is `done`, the `task_completed` Event agrees on attempt/result/Outcome/Snapshot, exactly the expected `signal_ingested` business result is present, and its Signal/Snapshot IDs and hashes agree.
- `success_no_change` → `worked` only when Task status is `done`, the terminal Event agrees, the matching `fetch_no_change` result is present, and the referenced existing same-Team/domain Signal/Snapshot is intact.
- `terminal_failure` → `failed` only when Task status is `failed`, the terminal failure Events and Outcome agree on attempt/reason/Snapshot, and no contradictory successful ingestion result exists for that Task.
- A mismatch, missing required record, stale attempt, cross-Team/domain reference, corrupt hash, unsupported Task class, or unknown result category is an evaluator error: create no Evaluation. Revision 1 does not emit `mixed`; it does not turn missing/corrupt evidence into `inconclusive`.

**Interpretation limit:** `worked` means the configured-source ingestion execution contract was satisfied (including a legitimate no-change result). It does not mean the source content is true, relevant, complete, or useful; it does not establish causation or Objective achievement. `failed` means the execution contract ended in a recorded terminal failure; it does not infer why the external world caused the failure beyond the recorded evidence. Findings must state this limitation and preserve uncertainty.

**Task path:** in the same transaction that `TaskRuntime` commits a terminal `task_execution` Outcome for a configured-source `ingest_source` Task, a narrow application-managed creator inserts exactly one ordinary same-Team `evaluate_outcome` Task and its immutable `evaluation_task_requested` Event. The Event belongs to the evaluator Task and binds source Task/attempt/result, PlanAction and policy pin, target Outcome ID and observation Snapshot ref/hash, and evaluator identity/revision. A fixed UUIDv5 identity over Team + Outcome + ruleset identity/revision and a canonical request fingerprint make the enqueue replay-safe. The evaluator Task is pending, unlinked to Objective/Plan/Action, copies the source policy pin, has exactly `['Evaluation', 'EvidenceLink']` write scope, zero tools/cost, 30-second deadline and three maximum attempts. Its request/Event/Task shape is verified before TaskRuntime admission; source terminal replay verifies the exact request rather than repairing it. The evaluator verifies canonical records, returns an `EvaluationDraft`, and calls EvaluationService.propose/record; TaskRuntime finalizes the evaluator Task. TaskRuntime interrupted recovery must finalize a fully recorded Evaluation before retry exhaustion can fail that Task. This is a narrow service entrypoint, not a general dispatcher, scheduler, or second runtime. No migration is assumed; add one only if tests expose a real integrity gap.

**Distillation fixture — implemented:** the R6-G branch uses three independent `ingest_source` Tasks of one Task class: two successful cases and one contrasting terminal-failure case, with one rule Evaluation per case. ExperienceDistiller receives all three recorded Evaluations explicitly; the two distinct successful Task IDs satisfy the cross-case threshold, while the failed case remains contrary evidence. The v2 pack validates terminal failure Events/Outcome and derives case-relative contrary stance without mutating canonical EvidenceLinks. Historical R6-F v1 reconstruction remains supported, including old unmarked evidence-basis records. This tests evidence handling without claiming causal proof.

**Provider boundary:** deterministic fake StrategyProposer and ExperienceDistiller providers and a deterministic test embedding provider are used in the acceptance fixture. This D9 decision authorizes no external model call and does not alter D6: no production R6-F distillation provider is approved.

**Scope of D9 decision:** D9 selected the initial Evaluation source only. It did not itself authorize implementation, a human/model evaluator, broader Task-class evaluation, automatic acceptance, D10 revise/retire, a dispatcher expansion or a second runtime. A separate Operator authorization was subsequently given for the bounded R6-G implementation; PR #35 records the merged work. The Operator approved the R6 exit gate after the ten-proof technical review on 2026-11-04.

**Frozen initial limits:** three total Task starts per Task; 30-second worker deadline; recover an orphaned running Task after 60 seconds with attempt-number fencing; source connect/read/total timeouts of 3/10/15 seconds; 2 MiB decompressed response ceiling; no redirects; maximum eight retrieved passages and 8,000 Unicode characters of retrieved knowledge. Production embedding and generation providers are deliberately staged to R6-D and R6-E, respectively.

### Explicitly deferred

No production provider/SDK or credentials path before its slice; no external reranker or separate vector service; no arbitrary URLs, redirect following, PDFs, shell, or general-purpose tools; no additional World-memory entity families unless the first slice proves them necessary; no unattended learning acceptance, direct TeamPolicy mutation, autonomous policy learning, or general multi-domain automation.

## 4. Proposed implementation traversal after G0 exits

These sections define implementation-slice scope and exit criteria. Current milestone status is maintained only in PLAN.md. R6-D and later require predecessor gates; external provider/model choices require explicit user sign-off at the applicable milestone.

### R6-A — Task execution lifecycle and atomic terminal Outcome

Implement the application-controlled lifecycle following TaskRuntime admission: success, retryable failure, exhausted failure, Events, timestamps, concurrency/conflict handling, replay, and idempotency. R6-A includes the minimum complete terminal `task_execution` Outcome persistence required by [ADR-0030 §4](../decisions/ADR-0030-r6-bounded-execution-source-safety-outcome.md): on terminal success or terminal failure the Outcome, immutable observation Snapshot reference/hash, terminal Task status, and terminal Task Event commit atomically in the same transaction, with the ADR-0030 uniqueness/idempotency and Task-attribution rules applied from the first implementation.

**Exit:** legal transitions only; Task state and Events agree; terminal finalization cannot commit without its required Outcome; retries and crashes do not double-commit or leave partial lifecycle changes.

### R6-B — One bounded configured-source worker

Add a small dispatcher/handler for the configured-source ingest_source Task. It loads durable Task/source context, uses the approved restricted fetcher, invokes the existing IngestionService, and reports outcomes through the lifecycle owner. The handler cannot commit business rows or lifecycle state directly.

**Exit:** integration tests cover admission → handler → ingestion commit → lifecycle completion, including no-change, rejection, retry, crash after ingestion commit, and replay without duplicate Signals or Events.

**Implementation status: COMPLETE — merged to `main` by PR #14** (merge commit `226c6b7`, 2026-10-28). `core/dispatcher.py` provides `TaskDispatcher` (`find_eligible_task`, `dispatch`, `recover_interrupted`); `core/source_fetch.py` provides the approved `RestrictedFetcher` and its URL/DNS/redirect/media-type/timeout/byte-ceiling contract. Durable source identity is the Task's `PlanAction` (`origin_url`, `source_type`), authorized against `TeamPolicy.rules["sources"]`; a Task with no Plan Action has no durable source identity and is rejected before admission. `tests/test_r6b_dispatcher.py` covers the successful path, no-change, retryable and non-retryable failure, exhaustion, configuration rejection, startup recovery, crash-after-ingestion-commit replay, and the fetcher's safety contract.

### R6-C — Outcome-backed deterministic reassessment and follow-on integration

Consume the terminal Outcomes already made durable by R6-A: build a new deterministic assessment from those durable records while preserving the original decision basis, and complete the remaining Outcome-driven integration. R6-C does not own the initial terminal Outcome representation or write path; it must not defer, duplicate, or weaken R6-A's atomic terminal finalization contract.

**Exit:** restart/replay reconstructs the Plan and explains the execution result from the Outcomes and Events R6-A already committed; reassessment is reproducible from the same durable state; replay after restart produces no duplicate Outcome, Event, or derived record.

### R6-D — RAG-backed Knowledge Cores

Implement the minimal canonical knowledge selection and a regenerable retrieval projection consistent with ADR-0028. Retrieve source-grounded Domain Knowledge Core records and, where available, accepted Team Experience Core records. Preserve access and status filtering, canonical references, index freshness/rebuild behavior, and a bounded context budget.

**Exit:** tests prove relevant retrieval, Team/domain isolation, status/access filtering, traceable source references, stale-index rejection after a canonical change, and index rebuild/replay. No retrieval-only assertion can commit a fact or lesson.

### R6-E — Task Context assembly, StrategyProposer, and cost accounting

R6-E is delivered in three separately verified checkpoints. Each checkpoint must be committed to the existing R6-E branch and pass hosted CI before the operator syncs and runs local verification. Do not begin the next checkpoint until the operator confirms the previous local verification.

#### Step 1 — Context assembly

Assemble a bounded Context from current, authorized Domain Knowledge Signal passages plus the same-Team active Objective, exact StateAssessment, pinned TeamPolicy, and Task budget. Persist the exact canonical Context bytes as one immutable content-addressed Snapshot and one Task-attributed `context_assembled` Event with a versioned manifest containing the selected canonical Signal/Snapshot references and hashes, logical core, query hash, chunk IDs, retrieval configuration, and embedding identity. A replay must reuse the exact original Snapshot/Event; changed content must reject rather than replace it. The operational manifest Event must not mutate the domain-state assessment basis.

**Exit:** deterministic tests cover current-policy authorization, canonical Signal/Snapshot/hash and chunk verification, 8-passage/8,000-character bounds, manifest completeness, immutable replay/conflict, Task write scope, and assessment-basis stability. No generation provider call occurs in this step.

#### Step 2 — StrategyProposer

Use the existing generation-provider boundary to turn the assembled Context into one strictly typed StrategyProposal. Keep the producer free of write authority; submit its result through the existing StrategyService validation and durable acceptance/rejection audit. Invalid, incomplete, malformed, unsupported, or stale output must be rejected; provider errors must not create a Plan.

**Exit:** deterministic fake-provider tests cover valid and invalid proposals, exact Context/assessment provenance, provider failure, replay/conflict, and proof that only StrategyService can accept. Production generation remains disabled until Step 3 supplies enforceable Task spend reservation/reconciliation.

#### Step 3 — Task cost accounting

Add a durable Task-attributed reservation/usage ledger. Reserve the maximum possible request charge before provider invocation, reconcile against provider-reported usage/cost afterwards, and prevent concurrent or repeated calls from exceeding Task `max_cost_usd`. Failed calls and ambiguous/missing usage must remain accounted for conservatively and fail closed; retries must not bypass the reservation.

Before the HTTP request, compute a quote for the exact system/user prompt using UTF-8 byte lengths plus 128 message-framing tokens, the configured output cap (at most 1,024 tokens), the selected model's pinned rate card, and its 32K context ceiling. Under a Task-row lock, reserve the maximum quote only if the sum of all prior reconciled costs and unresolved reservations plus this charge remains within the Task's `max_cost_usd`. Persist one unique Task/attempt/operation charge and its reservation Event before invoking the provider. Never retry a provider request inside one Task attempt.

On trustworthy usage, recompute cost from the rates persisted with the reservation and reconcile the charge. A response whose actual model differs from the reserved model, whose usage is missing/malformed, or whose reconciliation is uncertain cannot produce a Strategy; an unresolved call retains its full reservation. Usage exceeding the quoted token or cost bounds is persisted as an overrun at no less than the reserved amount and also cannot produce a Strategy. A new ordinary TaskRuntime attempt may make a new call only if its own maximum reservation fits on top of all prior Task charges. StrategyService must require the exact current-attempt charge to be `reconciled` before accepting a Context-backed proposal. These accounting records and Task lifecycle protocol Events remain auditable but do not mutate the Objective-domain StateAssessment basis; current Task status remains projected separately.

**Exit:** deterministic tests cover atomic reservation, cap enforcement under concurrent reservation, provider success/failure/model mismatch, missing/invalid usage, overrun, one-call-per-attempt fencing, retry after an unknown charge, exact replay, accepted-Strategy charge provenance, no-charge rejection, and reconciliation rollback/recovery. Only after Steps 1–3 pass may the production Task path call the generation provider.

### R6-F — First experience-distillation path

**Implementation status: R6-F CHECKPOINTS 1–4 COMPLETE AND MERGED; R6-G COMPLETE AND CLOSED.** C1–2 merged by PRs #29/#30; C3 create-only merged by PR #31; C4 merged by PR #32. The combined C3+C4 operator-local verification passed against the exact source tree incorporated by PR #33; timing and merge-tree equivalence are documented in `docs/testing.md`. R6-G was separately authorized, verified, reviewed 10/10, explicitly approved and merged by PR #35 on 2026-11-04.

D1–D4 were resolved in Checkpoint 1. D5 was resolved in Checkpoint 4 through a distinct `team_experience_chunks` projection while preserving the Signal-only Domain Knowledge projection. D6 remains a production-provider approval gate for R6-F distillation; deterministic fake providers are used in tests and R6-E provider approval does not extend to R6-F. D7 is resolved and implemented in C4: optional pinned-policy UTC review dates, exact due boundary, NULL/due retrieval exclusion, and ordinary `review_knowledge` Task completion. D8 is implemented as a thin in-process host-invoked Operator adapter; host authentication remains outside Watch. D9 is resolved 2026-11-03: R6-G v1 uses only the deterministic `watch.r6g.ingest-source-rules` ruleset (revision `1`) for configured-source `ingest_source` Outcomes; see the normative contract above. Human/model Evaluation producers are not wired or authorized in this slice. D10 is resolved: Checkpoint 3 remains create-only; revise/retire proposal production and commitment are deferred to a separately authorized knowledge-lifecycle scope. D11 and D12 are implemented, including approval-task no-deadline semantics and attempt-fenced competing-request recovery. No second runtime, general dispatcher, automatic learning acceptance, TeamPolicy mutation, or bypass path is permitted.

**Exit:** tests cover valid/invalid Evaluation evidence, one-case narrow Practice versus distinct-Task multi-case abstraction, missing/mismatched/contrary evidence, deterministic basis hashing, explicit approval/rejection, duplicate/replay/concurrency, version/supersession, cost failure, and failed/stale Team Experience publication. R6-F Checkpoint 4 also proves that a separately created later Task can retrieve the accepted Team Experience through Context. R6-G proved this capability as part of the complete Objective-to-learning integrated loop; see the implementation and closeout record.

### R6-G — Integrated vertical slice and formal gate

The implementation and acceptance evidence are recorded in [R6-G Integrated Fixture and Service-Interaction Design](r6g-integrated-fixture-design.md) and [docs/testing.md](../testing.md). The implementation includes one Team/Objective fixture, three configured-source cases (new content, legitimate no-change, terminal failure), atomic source terminalization plus evaluator-Task enqueue, the D9 rule runner, failed-case preservation in a versioned distillation evidence pack, Operator rejection/acceptance, Team Experience publication and later-Task retrieval.

The original integration gaps are implemented: (1) the evaluator request Task/Event is created atomically with the source terminal Outcome; (2) ExperienceDistiller includes a terminal failed source Task as contrary evidence in v2 while preserving historical v1 reconstruction; (3) TaskRuntime recovers an already-recorded Evaluation before retry exhaustion can fail its Task. Typed TaskRuntime terminal results also cover `propose_strategy` and `create_plan`; their committed dispositions are recovered through TaskRuntime rather than by direct Task status writes or ingestion result-category reuse.

Exercise Objective/assessment and RAG Context → accepted Strategy → immutable Plan → ordinary source Tasks → Outcomes/Evaluations → distillation → explicit Operator decision → canonical KnowledgeItem → current Team Experience projection → later-Task retrieval. Verify recovery and explainability from canonical records rather than transcripts. Run focused/full tests, Ruff, Mypy and fresh disposable-PostgreSQL migration/integration checks. Actual commands, environment, results and limitations are recorded in `docs/testing.md`. R6-G was closed only after the ten-proof review and separate explicit Operator exit approval on 2026-11-04; no approval for R7 follows from this closure.

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

**Historical gate-status snapshot (superseded; see `PLAN.md` for current status):** all design decisions requested for G0 are recorded and the local preflight is documented, so **R6-G0 is COMPLETE as of 2026-10-25**. Completing G0 did not itself authorize implementation; **R6-A required a separate explicit operator instruction, which was subsequently given.** **R6-A is COMPLETE and merged to `main` by PR #12** (merge commit `ebbc48d`). ADR-0027 remains Proposed. R6-D uses local LM Studio BGE-M3; R6-E's Cloudflare Workers AI Llama 3.1 8B FP8 provider is selected in ADR-0031, and all three R6-E checkpoints are operator/hosted verified. PR #28 merged on 2026-11-01; R6-E is formally closed. R6-F Checkpoints 1–2 are complete and merged (PR #29 at `9a0ba491`; PR #30 at `61be8db`). Checkpoint 3 is open under explicit operator authorization dated 2026-11-01; its initial path is on `r6f-checkpoint-3-operator-learning-commit`. Checkpoint 4 and R6-G remain gated.

## 7. R6-G0 local preflight record — 2026-10-25

Documentation-only closeout. No application code, tests, migrations, schema, Docker volumes, or persistent database contents were changed; no commit, push, merge, reset, or branch deletion was performed. No database commands or tests were run during this closeout — the preflight results below are the operator-supplied and previously recorded evidence.

**Verified local Git state:**

- Branch `R5-rebased`; HEAD `f9207156533b6944d320a6adfff42963f7e1e17c`.
- HEAD equals `origin/main` (`f920715`, merge of PR #9); no divergence and no local-only commits.
- The preflight checks were completed while the working tree was clean. The closeout itself introduces six intentional, unstaged documentation modifications (`PLAN.md`, this file, `docs/development/r6-g0-decision-proposals.md`, `CHANGE_MAP.md`, `CONTEXT.md`, `docs/control-model.md`). The working tree is therefore **not** clean at the end of this closeout; nothing is staged, committed, or pushed.

**Migrations:** the source chain is a single lineage `0001` → `0008_plan_lifecycle_state`. During preflight, `uv run alembic upgrade head`, `uv run alembic current`, and `uv run alembic heads` against the isolated disposable database `watch_r6_preflight` reported `0008_plan_lifecycle_state (head)` with exactly one head.

**Recorded preflight verification results:** `DATABASE_URL` and `TEST_DATABASE_URL` targeted `watch_r6_preflight` on `127.0.0.1:55448` (persistent `watch` database never targeted); `uv run pytest` → 260 passed in 25.88 seconds; `uv run ruff check core tests migrations` → passed; `uv run mypy core` → passed (11 source files); `git diff --check` → clean.

**Exit boundary:** every item in the §6 checklist above is satisfied. G0 completion does not authorize R6-A, does not accept ADR-0027, and does not select the embedding or generation providers.
