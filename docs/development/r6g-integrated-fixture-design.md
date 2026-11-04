# R6-G Integrated Fixture and Service-Interaction Design

## Status and authority

**Design prepared 2026-11-03; implementation authorized and in progress 2026-11-04.** This document records the R6-G service boundaries and intended integrated fixture, together with the implemented behavior on `r6g-implementation-20261103` / PR #35. It does not itself close R6-G or authorize a merge. PLAN.md remains the only milestone-status authority.

PLAN.md owns milestone status. The R6 entry gate and ADR-0028/0029/0030/0031 govern architecture. docs/tasks.md owns Task types, write scopes and budgets. The accepted D9 choice is unchanged: evaluator_kind rule, evaluator_identity watch.r6g.ingest-source-rules, evaluator_revision 1; configured-source ingest_source terminal Outcomes only; no model/human Evaluation producer. The evaluator returns an EvaluationDraft only; EvaluationService validates and records it; TaskRuntime owns Task lifecycle. No general dispatcher, second runtime, or production provider is introduced.

## 1. Implemented corrections to the original gaps

The implementation closes the three integration gaps identified during design:

### 1.1 Enqueue the Evaluation Task atomically with source terminalization

**Implemented:** TaskRuntime.finalize creates exactly one ordinary `evaluate_outcome` Task and its `evaluation_task_requested` Event in the same database transaction as a terminal `task_execution` Outcome for a Plan-linked configured-source `ingest_source` Task. The source Outcome ID, observation Snapshot reference/hash, source attempt/result, PlanAction provenance and pinned policy version are bound in the immutable request. A database rollback leaves neither terminal source state nor evaluator request. The content-addressed Snapshot blob remains outside the database transaction, as in R6-A; a rollback may leave only an unreferenced blob.

**Boundary:** this is a narrow TaskRuntime-managed side effect, not a second lifecycle owner. The request Event is owned by the evaluator Task. A terminal source replay verifies the deterministic Task ID and exact request Task/Event; it does not repair missing or contradictory records.


Evaluator Task identity uses the fixed UUIDv5 namespace and binds Team ID, Outcome ID, evaluator identity and revision. The canonical request fingerprint covers Team, source Task, attempt/result, Plan/Action references, policy pin, Outcome ID, Snapshot reference/hash and evaluator identity/revision. The Task primary key plus source-Task row lock and transaction are the idempotency boundary. Do not expand DispatchResult/TaskDispatcher or add a startup poller.

### 1.2 Preserve terminal failed cases in distillation

**Implemented:** ExperienceDistiller now admits a worked case only when its source Task is done, the current-attempt `task_completed` Event matches the terminal Outcome/Snapshot, and the recorded D9 Evaluation conclusion is `worked`. A failed case is admitted only when its source Task is failed, the current-attempt `task_attempt_failed` and `task_failed` Events match the attempt/reason/Outcome/Snapshot, the immutable observation Snapshot verifies, the D9 Evaluation conclusion is `failed`, and no contradictory successful ingestion business Event exists. Retryable attempts that leave a source Task pending are not cases. Missing, corrupt, stale, cross-Team/domain or contradictory evidence fails closed.

**Evidence interpretation:** ADR-0029 requires disconfirming cases to remain inspectable. Each worked Evaluation and primary Outcome is classified as supporting the candidate execution practice; each failed Evaluation and primary Outcome is contrary. The canonical EvidenceLink stance is never changed. The evidence pack retains original `stance` and adds a derived `case_relative_stance`; for failed cases, `supports` and `challenges` are inverted relative to the positive practice, while `mentions` remains context. Failure reason and limitations remain visible. Two successes do not prove causation, source truth, universal reliability or Objective achievement.
### 1.3 Recover a recorded Evaluation before failing its Task

**Implemented:** before retry scheduling or terminal failure, TaskRuntime checks the immutable evaluator request and reconstructs an already recorded or rejected Evaluation only when its Task/request binding, creating/resolving Task, evaluator identity/revision, proposal hash, disposition Event and canonical EvidenceLinks validate. It finalizes through the ordinary TaskRuntime path using the current-attempt `task_started` timestamp for deterministic `observed_at`. A proposed but unrecorded Evaluation is not promoted: the runner can replay its deterministic proposal and record it while attempts remain; when attempts are exhausted before record, the evaluator Task fails and the proposal is not distillation evidence. Corruption fails closed. Terminal runner replay is read-only.

**Recovery boundary:** TaskRuntime remains the only authority for retry, exhaustion, terminal Outcome and Task state. EvaluationService owns proposal/record state; the rule runner only orchestrates the existing services.

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

No database transaction spans fetch, snapshot object-store operations, embedding or generation-provider calls. The atomic source-finalize/enqueue transaction covers canonical database rows, the Outcome's Snapshot reference/hash, Task status and Events, plus the evaluator Task/request Event—not the external Snapshot blob write. Use bounded transactions, immutable snapshots, exact idempotency and TaskRuntime recovery. Never hold a database transaction open during network/model work.

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

## 6. Typed Strategy and Plan Task completion

**Implemented decision:** service-protocol records for `propose_strategy` and `create_plan` are terminalized by narrow typed TaskRuntime results; they are not treated as ingestion outcomes or Objective-achievement evidence. Strategy disposition results bind to the exact accepted/rejected Strategy Event. Plan creation binds to the exact `Plan` and `plan_created` Event and reuses PlanService's full reconstruction validator. Rejected Strategy proposals are valid completed producer Tasks with no Plan. Interrupted Strategy/Plan Tasks are reconciled from their committed disposition through TaskRuntime recovery before retry/exhaustion.

Tests now cover accepted Strategy finalization/replay, rejected Strategy finalization, Plan creation finalization/replay, and interrupted Plan materialization recovery. These producer Tasks remain outside the three source-ingestion Evaluation cases.

## 7. Implemented test coverage

| Test module | Implemented proof |
|---|---|
| `tests/test_rule_evaluator.py` | D9 new-Signal, no-change and terminal-failure mappings; deterministic rule draft and contradictory-business-event fail-closed check. |
| `tests/test_evaluation_tasks.py` | Atomic source-terminal enqueue, rollback on enqueue failure, concurrent duplicate terminal finalization producing one Outcome/request, exact request Task/Event binding, tamper rejection, committed-Evaluation recovery and terminal runner replay. |
| `tests/test_experience_distiller.py` and `tests/test_r6g_distillation.py` | Failed-source provenance, claim-relative contrary evidence, canonical EvidenceLink stance preservation, per-case v2 marker/hash, legacy unmarked-v1 reconstruction, and unknown-version rejection. |
| `tests/test_r6g_vertical_slice.py` | Objective Context → Strategy → Plan → three source Tasks → Outcomes/Evaluations → reassessment → distillation → Operator reject/accept → Team Experience projection → later-Task retrieval. |

Additional component suites remain part of the acceptance evidence: `test_r6b_dispatcher.py`, `test_knowledge_index.py`, `test_team_experience.py`, `test_context_assembly.py`, `test_strategy_proposer.py`, `test_strategy.py`, `test_plans.py`, `test_task_lifecycle_retry.py`, `test_task_lifecycle_recovery.py`, `test_task_runtime.py`, `test_evaluations.py`, `test_operator_application.py` and `test_generation_cost.py.

R6-G exit still requires evidence mapped to all ten criteria in `docs/testing.md`, successful exact-head programmer-local verification with disposable PostgreSQL, review of the relevant failure-injection/replay cases, and explicit operator approval. Existing component coverage may satisfy a criterion; the integrated test does not need to duplicate every lower-level fault test.

## 8. Implementation and verification status

1. **Implemented:** branch/authority preflight and service-boundary review.
2. **Implemented:** immutable evaluator request contract, deterministic Task identity and atomic evaluator Task/Event enqueue.
3. **Implemented:** pure D9 rule evaluator and narrow Task runner.
4. **Implemented:** committed-Evaluation recovery, tamper validation and replay tests.
5. **Implemented:** versioned v2 evidence pack for failed-source cases and historical v1 reconstruction.
6. **Implemented:** typed TaskRuntime completion/recovery results for Strategy and Plan producer Tasks.
7. **Implemented:** integrated three-case fixture through later-Task Team Experience retrieval.
8. **Hosted CI passed on exact implementation head** `2a55acfeadaf37e23b9f2cffd8819b7b460ba6b3`, run [41782439302](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/41782439302): fresh PostgreSQL migration/head check, Ruff, Mypy and 614 tests in 44.93s. Programmer-local disposable-PostgreSQL verification also passed on this exact head: Python 3.12.12; fresh DB migrated to the single `0013_team_experience_projection` head; 134 focused tests and 614 full-suite tests passed; Ruff, Mypy (29 source files) and `git diff --check` passed. The disposable container/anonymous volume were removed and the worktree was clean. See `docs/testing.md` for the full operator-reported record.
9. **Technical acceptance review passed 10/10** on 2026-11-04; no blocking gap was found. The integrated fixture remains intentionally offline with fake fetch/model/embedding providers; relevant component suites cover URL/DNS/HTTP safety, hybrid retrieval and failure behavior. **Pending:** obtain the Operator's explicit R6-G exit approval. Code, CI or merge alone does not close R6.

## 9. Explicit non-goals

No production R6-G evaluator/provider; no human/model evaluator; no production R6-F distillation provider; no new model SDK/credentials; no general dispatcher, scheduler, queue or second runtime; no arbitrary source URL or wider network access; no D10 revise/retire; no TeamPolicy mutation; no automatic LearningChange acceptance; no new knowledge entity family; no weakening of R5 Plan prerequisites/completion rules; no use of the persistent watch database for tests.

**Current gate:** implementation was separately authorized and is in progress on PR #35 (draft/open, unmerged). No merge or R6 closure is implied. The explicit non-goals below remain binding.
