# R6-G Integrated Fixture and Service-Interaction Design

## Status and authority

**Prepared 2026-11-03; design only.** This document makes the integrated R6-G fixture, service calls, durability boundaries and tests concrete. It does not implement R6-G, authorize a code branch or migration, approve a production provider, merge a PR, or close the R6 gate. The separate authorization recorded in PLAN.md remains mandatory.

PLAN.md owns milestone status. The R6 entry gate and ADR-0028/0029/0030/0031 govern architecture. docs/tasks.md owns Task types, write scopes and budgets. The accepted D9 choice is unchanged: evaluator_kind rule, evaluator_identity watch.r6g.ingest-source-rules, evaluator_revision 1; configured-source ingest_source terminal Outcomes only; no model/human Evaluation producer. The evaluator returns an EvaluationDraft only; EvaluationService validates and records it; TaskRuntime owns Task lifecycle. No general dispatcher, second runtime, or production provider is introduced.

## 1. Implementation gaps found during design

The prior outline required two successes and one terminal failure to reach ExperienceDistiller. Inspection of the current code found that this cannot work unchanged. Three integration corrections are required.

### 1.1 Enqueue the Evaluation Task atomically with source terminalization

Creating an evaluator Task in a separate transaction after the source Outcome commits creates a crash gap: the source Outcome can be durable while the follow-up Task is never created. There is no general scheduler or dispatcher authorized to repair the missing enqueue.

**Required design:** when TaskRuntime.finalize commits a terminal task_execution Outcome for a configured-source ingest_source Task, it also creates exactly one ordinary evaluate_outcome Task and its evaluation_task_requested Event in the same database transaction. The source Outcome ID, observation Snapshot reference/hash, source attempt/result, PlanAction provenance and pinned policy version are then known. A rollback leaves neither terminal source state nor evaluator request; a committed source finalization cannot exist without its evaluator request.

This is a narrow TaskRuntime-managed K side effect, not a second lifecycle owner. The request Event is owned by the new evaluator Task. A replay of the source terminal result verifies the exact evaluator Task/Event; it never repairs or duplicates missing or contradictory records.

Use a fixed UUIDv5 namespace. Derive the evaluator Task ID from Team ID, target Outcome ID, evaluator identity and revision. Hash canonical JSON containing Team, source Task, attempt/result, Plan/Action references, pinned policy version, Outcome ID, Snapshot reference/hash, and evaluator identity/revision. Atomic Task/Event creation plus the Task primary key is the idempotency boundary. Do not add an idempotency column or migration unless PostgreSQL concurrency tests demonstrate an integrity gap.

### 1.2 Preserve terminal failed cases in distillation

Current ExperienceDistiller accepts source Tasks only when status is done and requires a task_completed Event. D9 correctly records terminal ingestion failure as status failed with task_attempt_failed and task_failed Events. A failed D9 Evaluation therefore currently raises source_task_not_eligible.

**Required design:** extend canonical evidence reconstruction so it admits:
- a worked case only when its source Task is done, the current-attempt task_completed Event matches the terminal Outcome/Snapshot, and the recorded D9 Evaluation conclusion is worked;
- a failed case only when its source Task is failed, the current-attempt task_attempt_failed and task_failed Events match the attempt/reason/Outcome/Snapshot, the immutable observation Snapshot verifies, and the recorded D9 Evaluation conclusion is failed.

A failed case is eligible only if no contradictory successful ingestion business Event exists for that source Task. Retryable attempts that leave the source Task pending have no terminal Outcome and no Evaluation request; they are not cases. Missing, corrupt, stale, cross-Team/domain or contradictory evidence fails closed.

ADR-0029 requires disconfirming cases to remain inspectable. For this first positive-experience fixture, classify each Evaluation case relative to the proposed reusable execution practice:
- Evaluation conclusion worked: its Evaluation and primary Outcome are supporting case references.
- Evaluation conclusion failed: its Evaluation and primary Outcome are contrary case references.
- Preserve each canonical EvidenceLink stance unchanged in storage. In the distillation document retain the original link stance and a separate derived case-relative stance. For a failed case, invert supports/challenges when translating a link to the positive practice's perspective; mentions remains context. This is an evidence-pack interpretation only, not an update to Evaluation or EvidenceLink.

The failure reason and its limitations must remain visible. Two successes do not prove causation, source truth, universal reliability or Objective achievement. Version this interpretation as r6f-experience-evidence-pack-v2. Preserve the v1 reconstruction path for LearningChanges already stored under the prior contract; revalidation must choose the original version and never reinterpret old evidence silently. Put an explicit version marker in each new persisted evidence-basis representation and include it in the basis hash.

### 1.3 Recover a recorded Evaluation before failing its Task

EvaluationService.propose and EvaluationService.record commit separately from TaskRuntime.finalize. A crash after Evaluation is recorded but before Task finalization leaves a durable result. The current generic interrupted-task path may eventually fail the Task at attempt exhaustion without first reconciling that Evaluation.

**Required design:** add a narrow committed-Evaluation recovery check in TaskRuntime, analogous to committed Operator-decision recovery. Before retry scheduling or terminal failure, validate the request Event, exact Evaluation for the Task/request, recorded/rejected status, creating/resolving Task, evaluator identity/revision, proposal hash, disposition Event and canonical EvidenceLinks. If complete, reconstruct the typed success TerminalObservation and finalize through TaskRuntime. Use the durable current-attempt task_started timestamp for observed_at so recovery is deterministic. If only a proposed Evaluation exists, retry the Task; the deterministic draft and request idempotency must replay through EvaluationService and complete record/finalize. Corruption fails closed.

After the evaluator Task is already terminal, repeated runner invocation is read-only replay. It must not admit another attempt or create another Evaluation/Outcome.

## 2. Fixture topology

Use one active Team, one active Objective and one Domain. The fixture owns one valid current TeamPolicy containing three configured HTTPS sources and a valid schema-v2 review.knowledge_item_interval_days rule. The review interval must produce a non-null future review_after so accepted Team Experience is eligible for retrieval.

Seed one canonical Domain Knowledge Signal and immutable Snapshot as baseline setup. Build its existing Signal projection with a deterministic fake embedding provider. Assertions must use the real HybridKnowledgeRetriever and TaskContextAssembler, not a hand-built Context or mocked retrieval response. The baseline seed is not counted among the three execution cases.

One accepted Strategy has three independent ingest_source Actions with no prerequisites. Each Action references one exact configured source entry, has no tools and zero Action cost. PlanService materializes one Plan, its PlanActions and three ordinary source Tasks. All three source Tasks share Task class, Team, Domain and policy pin but have distinct Task and PlanAction IDs.

### Three source cases

| Case | Deterministic fetch fixture | Business record | Terminal result | D9 Evaluation |
|---|---|---|---|---|
| A — new content | Fixed valid bytes for configured source A | signal_ingested; one new Signal and immutable Snapshot | done / success_signal_created | worked |
| B — unchanged | Existing same-Team/domain Signal for source B has the exact returned content hash | fetch_no_change; intact existing Signal/Snapshot, no duplicate Signal | done / success_no_change | worked |
| C — terminal failure | Non-retryable SourceFetchError for configured source C, before any ingestion commit | No signal_ingested or fetch_no_change Event for this Task | failed / terminal_failure | failed |

Use a stable failure reason code. Do not simulate a crash after a successful ingestion commit in case C; that is a separate replay test. Do not emit any success business Event for C.

The Plan remains active because one of its three Tasks is terminally failed. Do not mark it completed, replace the failed Task or claim the Objective succeeded. R5 Plan completion rules remain unchanged. This fixture demonstrates mixed experience, not successful completion of every Plan action.

## 3. Integrated service sequence

### 0 — Prepare canonical fixture data

Create the Team, schema-valid TeamPolicy, active Objective and pre-existing Domain Knowledge Signal/Snapshot. Build the Domain Knowledge projection with deterministic fake embeddings. Use disposable PostgreSQL only.

### 1 — Assemble immutable Context

Create the ordinary running propose_strategy Task with its existing empty worker write scope and budget. Use TaskContextAssembler with the real HybridKnowledgeRetriever. Verify relevant baseline Domain Knowledge retrieval, same-Team/domain canonical-source validation, current status/hash checks, the eight-passage/8,000-character bounds, content-addressed Context Snapshot, and exact context_assembled manifest Event. A repeat must replay the original bytes/Event rather than retrieve a new Context.

### 2 — Propose and validate Strategy

Use StrategyProposer with a deterministic fake JSONGenerationProvider and the existing synthetic cost card. The fake returns exactly three configured-source ingest_source Actions and no tools. StrategyProposer submits untrusted output through StrategyService.submit_from_context. It does not create a Plan. Verify accepted disposition provenance includes the exact Context Snapshot/manifest and StateAssessment basis. Exercise a rejected Strategy proposal separately and prove no Plan is created from it.

### 3 — Materialize the Plan

Use a separate ordinary create_plan Task with exact Plan write scope and pinned policy. Call PlanService.create using the accepted Strategy Event ID and proposal hash. Verify the Plan, three PlanActions, three ordinary pending source Tasks and plan_created Event are committed atomically. Preserve exact action/source identity; no caller-supplied Action JSON bypasses validation.

### 4 — Dispatch the three source Tasks

Use the existing TaskDispatcher with a deterministic fake Fetcher. Do not expand TaskDispatcher to support evaluate_outcome. Dispatch each source Task separately; each call makes at most one attempt and delegates admission, retry/finalization, terminal Outcome/Snapshot and lifecycle Events to TaskRuntime.

Verify A creates exactly one Signal, B records legitimate no-change against the existing Signal, and C fails terminally without an ingestion business Event. Reuse R6-B component tests for unsafe URLs, redirects, byte/time bounds, transient retry and exhaustion rather than duplicating those low-level tests.

Run ExecutionAssessmentBuilder.build(plan_id) after source execution, then rebuild against the same committed database/Snapshot state. Its deterministic assessment hash must match and the builder must remain read-only. With two succeeded Actions and one terminal-failed Action, expect conclusion failed with integrity consistent while the Plan itself remains active. This is an execution-state projection, not an Evaluation or causal judgment.

### 5 — Create and run D9 Evaluation Tasks

TaskRuntime source terminalization creates the ordinary evaluator Task and its request Event atomically. The request binds Team, source Task/attempt/result, Plan/PlanAction, source policy pin, target Outcome ID and observation Snapshot reference/hash, evaluator kind/identity/revision and canonical request fingerprint.

The evaluator Task is pending; same Team; no Objective/Plan/PlanAction links; source policy pin; max_attempts 3; allowed_writes exactly [Evaluation, EvidenceLink]; budget exactly zero tools, zero cost and a 30-second deadline. It is an ordinary Task and must be admitted/finalized through TaskRuntime. It has no tools, network access, model call or generation charge.

Run the exact Task ID through a narrow RuleEvaluationTaskRunner. It is not a dispatcher, scheduler or lifecycle authority. Its order is:
1. validate exactly one intact request Event and canonical source records;
2. admit through TaskRuntime;
3. invoke pure IngestSourceRuleEvaluator, which returns an EvaluationDraft or categorized fail-closed error;
4. call EvaluationService.propose with the fixed D9 identity/revision;
5. call EvaluationService.record after verifying the proposed disposition and evidence;
6. finalize with TaskRuntime using success_evaluation_recorded and the Evaluation ID.

The runner never accepts caller-supplied evaluator identity, Outcome ID, Signal list or evidence pack that overrides the request Event. TaskRuntime repeats exact request/Task validation before consuming an attempt; the runner rechecks before evaluating. EvaluationService validates Team/domain ownership, evidence normalization, Snapshot/hash and quotes, proposal hash, disposition and corresponding Events.

### 6 — Deterministic rule results

| Source result | Required checks | Draft conclusion |
|---|---|---|
| success_signal_created | Task done; one matching current-attempt task_completed Event; result/Outcome/Snapshot IDs and hashes agree; matching signal_ingested Event; same-Team/domain Signal and intact Snapshot | worked |
| success_no_change | Task done; matching terminal Event and fetch_no_change Event; exact existing same-Team/domain Signal/Snapshot still validates | worked |
| terminal_failure | Task failed; task_attempt_failed and task_failed agree on current attempt, reason, Outcome and Snapshot; no successful ingestion business Event exists for this Task | failed |

The pure evaluator checks one current terminal attempt and does not interpret fetched prose. Each Evaluation includes its primary Outcome as EvidenceLink stance supports relative to that Evaluation's own conclusion. Signal EvidenceLink is included only when matching canonical business evidence exists. Findings use fixed wording, attribution not established, and uncertainty that explicitly denies inference about source truth, relevance, Objective achievement or causation. A failure finding preserves the recorded reason without inventing its cause.

Use an Evaluation idempotency key derived from the immutable request fingerprint and ruleset version. Same request/same draft replays the same proposal hash. Unsupported Task class/result, missing Event, stale attempt, cross-Team/domain reference, Snapshot corruption or conflicting business Event creates no Evaluation.

### 7 — Distill without dropping the failed case

Create a separate ordinary propose_learning_change Task with its existing exact LearningChange scope. Use a deterministic fake ExperienceDistiller provider and synthetic test cost card. Pass exactly the three recorded D9 Evaluation IDs; do not auto-discover wider Team history.

The v2 evidence pack contains three distinct source Task IDs, each source Outcome and terminal Event provenance, its Evaluation and evaluator identity/revision, the evaluator Task's recorded terminal Outcome/Event, canonical EvidenceLinks and immutable Snapshot refs/hashes. The two worked cases support the candidate. The failed case remains contrary evidence, with its failure reason and limitations visible. Preserve the canonical EvidenceLink stance and store derived case-relative stance separately.

The fake returns one deterministic cross-case Pattern/Method/Playbook candidate only if it references both successes as support, retains failure as contrary, distinguishes observation from explanation, preserves all references, and makes no causal, truth or universal-reliability claim. ExperienceDistiller recomputes the evidence pack and basis hash after provider return; changed evidence yields no LearningChange.

For the rejection branch, create a separate distillation Task using one worked Evaluation and a low-confidence narrow Practice proposal. Its evidence-basis hash/idempotency key differs from the three-case proposal. Reject it through the Operator adapter and prove no KnowledgeItem is created or indexed. Do not create two proposals from the same identical basis/idempotency key.

### 8 — Operator decision and publication

The three-case proposal is a real LearningChange with target_kind knowledge_item, operation create and target_id null. Submit it through the existing host-invoked OperatorApplicationAdapter with a fixture TrustedOperatorPrincipal and exact Team grant. No direct KnowledgeItem insert, seed path, approval shortcut, TeamPolicy write, revise or retire operation is permitted.

Verify acceptance atomically creates one canonical active KnowledgeItem version, commits LearningChange history, operator/Task attribution and decision Events. Use the pinned valid review interval so review_after is non-null and future-dated. Rejection creates no KnowledgeItem.

Only after canonical acceptance, call TeamExperienceIndexer. Verify current canonical item/version/hash and origin LearningChange in the projection. Inject index failure: canonical acceptance stays committed, projection is stale, and retrieval must not claim the item is available. Rebuild is idempotent and publishes only the current eligible version.

### 9 — Later-Task retrieval

Create a different later propose_strategy Task for the same Team/Objective and current policy. Assemble new Context through TaskContextAssembler and HybridKnowledgeRetriever. Verify the accepted KnowledgeItem is retrieved through the Team Experience core with current version/hash/LearningChange provenance and an exact Context manifest identifying logical core and retrieval/embedding configuration.

The new Context comes from canonical records and the current projection, not the earlier Task's Context, transcript or provider response. The original Context remains immutable. Verify stale, due, null-dated, superseded, unpublished and cross-Team chunks are excluded.

## 4. Durable Evaluation request contract

The request Event is the immutable execution input owned by the evaluator Task, not a mutable Task payload. It is created in the same transaction as source terminalization.

| Field | Meaning |
|---|---|
| schema_version | 1 |
| operation | evaluate_outcome |
| team_id | source Task Team |
| source_task_id | exact ingest_source Task |
| source_attempt / source_result_category | attempt and terminal result represented by lifecycle Events |
| source_plan_id / source_plan_action_id | exact durable PlanAction provenance |
| policy_version | copied source Task policy pin |
| outcome_id | exact task_execution Outcome |
| observation_snapshot_ref / observation_hash | immutable terminal observation |
| evaluator_kind / identity / revision | rule / watch.r6g.ingest-source-rules / 1 |
| request_fingerprint | SHA-256 of canonical fields, excluding the fingerprint itself |

Exact evaluator Task shape: same Team; type evaluate_outcome; pending; attempt_count 0; max_attempts 3; no Objective/Plan/PlanAction links; policy_version copied from source; allowed_writes exactly [Evaluation, EvidenceLink]; budget max_tool_calls 0, max_cost_usd 0, deadline_seconds 30.

Same-ID replay verifies every Task field and exactly one request Event with exact payload. A changed fingerprint, missing/duplicate Event, wrong owner, or mismatched Outcome is conflict/corruption, not a reason to repair silently or create a second Task. Under PostgreSQL READ COMMITTED, test the deterministic insert-on-conflict then re-read-and-verify pattern used by OperatorApplicationAdapter.

## 5. Atomicity and recovery

| Boundary | Atomic durable unit | Replay/recovery |
|---|---|---|
| Context assembly | Context Snapshot + context_assembled Event | exact Task-lock/manifest/byte replay |
| Strategy disposition | accepted/rejected Strategy Event | exact proposal/Context replay |
| Plan materialization | Plan + PlanActions + source Tasks + plan_created Event | PlanService replay; no partial materialization |
| Ingestion business commit | Signal/Snapshot + signal_ingested or fetch_no_change Event | same origin/hash idempotency |
| Source terminalization/enqueue | source terminal Outcome/Snapshot/status/Events + evaluator Task/request Event | one transaction; terminal replay validates request |
| Evaluation proposal | Evaluation proposed + EvidenceLinks + evaluation_proposed Event | same request/draft hash replays |
| Evaluation record | Evaluation recorded + evaluation_recorded Event | record replay reuses disposition |
| Evaluation Task finalization | evaluator task_execution Outcome/Snapshot + task_completed/status | TaskRuntime recovers recorded Evaluation; terminal replay is read-only |
| Learning proposal | LearningChange proposed + learning_change_proposed Event | exact evidence-basis idempotency and TaskRuntime result |
| Operator decision | canonical decision + optional KnowledgeItem + Event | existing adapter/commit replay |
| Team Experience | current projection rows/state | canonical commit survives index failure; stale projection excluded |
| Later Context | new Context Snapshot + manifest Event | new Context; old Context immutable |

No database transaction spans fetch, snapshot object-store operations, embedding or generation-provider calls. Use bounded transactions, immutable snapshots, exact idempotency and TaskRuntime recovery. Never hold a database transaction open during network/model work.

| Injected condition | Required result |
|---|---|
| Unsafe/unconfigured source | reject before admission; no attempt/fetch |
| Retryable fetch failure | source Task pending; no terminal Outcome or evaluator Task |
| Terminal fetch failure | failed Outcome/Event pair and one evaluator Task/request atomically |
| Crash after ingestion commit before finalization | replay same business Event/Signal; one terminal Outcome/request |
| Source terminal transaction rollback | neither terminal Outcome nor evaluator Task/Event |
| Concurrent evaluator Task creation | one exact deterministic Task and request Event |
| Request Event/Task mismatch | no evaluator admission or Evaluation |
| Corrupt D9 evidence | no Evaluation/EvidenceLink; evaluator Task fails through TaskRuntime |
| Crash before Evaluation proposal | replay deterministic draft from canonical records |
| Crash after proposal before record | reuse same Evaluation, record, then finalize |
| Crash after record before finalization | TaskRuntime committed-Evaluation recovery finalizes |
| Crash after evaluator finalization | read-only terminal replay |
| Evidence changes during distillation | basis hash mismatch; no LearningChange |
| Operator rejection | durable rejection; no KnowledgeItem/projection |
| Index failure after acceptance | canonical item remains; projection stale and excluded until rebuild |

Deterministic evidence/validation errors are non-retryable. Only classified transient operational failures may retry. Never catch arbitrary exceptions and convert them to a generic successful result.

## 6. Control-Task lifecycle caveat

There is a separate current-contract gap for propose_strategy and create_plan producer Tasks. TaskContextAssembler and PlanService require running Tasks, and current component fixtures construct them in that state. TaskRuntime has no dedicated typed success result for a Strategy disposition or Plan materialization. Do not mark these Tasks done directly, and do not borrow success_no_change or an ingestion result category to make the integrated test appear complete.

**Recommendation before R6-G is represented as a fully closed Task-level vertical slice:** explicitly decide whether these are service-protocol records outside terminal Task execution, or add narrow TaskRuntime terminal results tied respectively to the exact Strategy disposition Event and plan_created Event. The latter better preserves the principle that Tasks are the execution unit, but is an additional R6-G design choice and must be included in the separate implementation authorization. In either case, exclude these producer Tasks from the three ingestion cases and never treat their status as evidence of Objective achievement.

## 7. Required tests

| Test | Proof |
|---|---|
| tests/test_rule_evaluator.py | all three D9 mappings; deterministic drafts; event/attempt/status/hash checks; fail-closed corruption, cross-Team/domain and contradictions |
| tests/test_evaluation_tasks.py | atomic source-terminal enqueue; exact Task/Event; UUIDv5 replay/concurrency; admission fencing; tamper rejection; propose/record/finalize replay; committed-Evaluation recovery |
| tests/test_experience_distiller.py | failed source provenance; claim-relative contrary evidence; v2 hashing; v1 historical replay; omission of contrary evidence rejected |
| tests/test_r6g_vertical_slice.py | Objective Context → fake Strategy → Plan → three source Tasks → Outcomes/Evaluations → distillation → Operator reject/accept → projection → later-Task retrieval |

Reuse component coverage in test_r6b_dispatcher.py, test_knowledge_index.py, test_team_experience.py, test_context_assembly.py, test_strategy_proposer.py, test_strategy.py, test_plans.py, test_task_lifecycle_retry.py, test_task_lifecycle_recovery.py, test_task_runtime.py, test_evaluations.py, test_operator_application.py and test_generation_cost.py.

In addition to the ten acceptance criteria in docs/testing.md, R6-G must prove atomic enqueue, failed-case inclusion, committed-Evaluation recovery, Task/Event concurrency and tamper safety, and an explicit decision about control-Task terminal semantics.

## 8. Implementation order after separate authorization

1. Preflight branch, HEAD, worktree and current docs authority. Reinspect the current TaskRuntime/EvaluationService transaction boundaries.
2. Implement the immutable request contract and in-transaction evaluator Task enqueue in source TaskRuntime terminalization; validate exact request shape before evaluator admission.
3. Implement the pure D9 evaluator and narrow runner.
4. Add committed-Evaluation recovery and replay/concurrency tests.
5. Extend ExperienceDistiller with a versioned v2 evidence pack and retain v1 historical reconstruction.
6. Resolve propose_strategy/create_plan terminal semantics within authorized scope.
7. Build the integrated fixture with fake Strategy/distillation providers, synthetic cost cards, deterministic embeddings and deterministic fetcher only.
8. Run focused tests, Ruff, Mypy, full suite, fresh disposable-PostgreSQL migrations/integration tests and git diff --check. Add a migration only if testing demonstrates an integrity constraint cannot be met using existing schema.
9. Record actual commands/results and request explicit R6-G exit approval. Code, tests or merge alone do not close R6.

## 9. Explicit non-goals

No production R6-G evaluator/provider; no human/model evaluator; no production R6-F distillation provider; no new model SDK/credentials; no general dispatcher, scheduler, queue or second runtime; no arbitrary source URL or wider network access; no D10 revise/retire; no TeamPolicy mutation; no automatic LearningChange acceptance; no new knowledge entity family; no weakening of R5 Plan prerequisites/completion rules; no use of the persistent watch database for tests.

**Authorization boundary:** this is a prepared design only. It authorizes no R6-G implementation branch, application code, migration, production provider invocation, PR, merge or R6 closure. A separate explicit operator decision remains required.
