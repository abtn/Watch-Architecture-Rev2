# RW4-1 F1 per-call-site lock and DML reconciliation — source audit

**Status:** Working source audit for review. Not a grant specification, accepted physical contract, or implementation authorization.

**Baseline:** PR #222 branch `rw41-exact-ddl-freeze-draft-20261128`, based on `main` at `c648892e4896113700c8103397be01c11c0d22ed`.

**Purpose:** Reconcile the existing SQLAlchemy row-lock call sites with the DML capabilities actually required by their workflows. The result deliberately separates (1) row-lock permission, (2) mutation authority on the locked row, (3) writes to other relations in the same transaction, and (4) the missing deployed runtime identity. These are related but are not interchangeable.

## 1. Finding and recommended reconciliation

A single table-level grant for every relation appearing in `.with_for_update()` is not acceptable. PostgreSQL requires SELECT plus UPDATE privilege on at least one column of a relation for a row-locking SELECT, including `FOR SHARE`. Giving that UPDATE privilege to the application role is still mutation authority; it is not a harmless lock token.

Use a two-layer model:

1. **Call-site lock ledger (this document):** every production SQLAlchemy lock site records the selected relation, lock mode, transaction ownership, and whether that exact call site mutates the locked row. A call site that only serializes/reads must not cause a direct UPDATE grant on the relation.
2. **Relation DML capability ledger (to be finalized after the writer audit):** enumerate all INSERT/UPDATE/DELETE/TRUNCATE/sequence operations, including writes to relations not locked at that call site; identify exact changed columns, caller/transaction owner, and supported runtime identity. Only this ledger determines direct DML grants.

The implementation direction is therefore hybrid:

- Real writers receive only the required table-level INSERT/DELETE or exact column-level UPDATE privileges, subject to database invariants and explicit tests.
- Lock-only call sites use a small number of fixed, owner-controlled lock functions grouped by stable business lock protocol—not one generic dynamic helper per Python call and not one function for every individual query.
- Shared helpers are classified by their callers before deciding whether they can be converted to lock-only functions.
- A helper only acquires a transaction-scoped lock. The caller retains transaction ownership and performs the normal SELECT in that same transaction. The helper does not return application data, commit, or refresh SQLAlchemy identity-map state.
- The final matrix remains deployment-specific. The repository has no production composition root/runtime DSN consumer or complete maintenance/external writer inventory. Do not claim F1 feasibility or freeze grants until that identity is supplied and exercised.

## 2. Classification key

| Code | Meaning | Privilege consequence |
|---|---|---|
| **R** | This call site locks and reads/validates/serializes the selected row; it does not mutate that selected row in the same operation. | No direct UPDATE grant justified by this call site. Use an approved lock function if the runtime must execute it. |
| **W** | The operation changes the selected row in the same transaction. | Direct UPDATE may be justified, but only on the exact changed columns and after checking DB guards. |
| **H** | Shared lock helper or helper-like function whose callers determine whether the locked row is subsequently changed. | Must classify callers and transaction paths before selecting direct DML or helper mechanism. |
| **C** | Lock mode or query shape is conditional. | Preserve both branches in the matrix and test both; do not silently count it as a single fixed mode. |

Lock mode: **U** = default `FOR UPDATE`; **S** = `FOR SHARE`; **C** = conditional. Line numbers refer to the current PR branch source at the baseline above and must be refreshed if source changes.

Transaction ownership:
- **Service**: the enclosing method opens `session_factory.begin()` and owns the transaction.
- **Caller**: a Session is supplied to the function; the caller owns the transaction.
- **Mixed**: the API supports both an internally opened transaction and a supplied Session.
- **Shared**: the lock helper receives a Session and is reused by multiple service transactions.

The R/W classification is deliberately about mutation of the **locked relation**, not whether the overall transaction writes anything. For example, an ingestion transaction inserts Signal/Event rows while its Task, Team, and TeamPolicy locks are R at those call sites.

## 3. Complete source lock-site ledger

The 114 sites below reconcile to the source count in PR #222 §6.3: 89 unconditional U, 24 unconditional S, and one conditional Event lock.

| # | Source location | Locked relation | Mode | Tx owner | Locked-row DML classification |
|---:|---|---|:---:|---|:---:|
| 1 | `core/objectives.py:129 ObjectiveService._create` | Objective | U | Service | R — replay validation |
| 2 | `core/objectives.py:182 ObjectiveService._transition` | Objective | U | Service | R — replay validation |
| 3 | `core/objectives.py:200 ObjectiveService._transition` | Objective | U | Service | W — changes Objective.status |
| 4 | `core/objectives.py:229 ObjectiveService._lock_task` | Task | U | Shared | H — callers include Task/Task-attributed writers; classify caller |
| 5 | `core/objectives.py:242 ObjectiveService._validate_task` | Team | S | Service | R |
| 6 | `core/objectives.py:254 ObjectiveService._validate_task` | TeamPolicy | S | Service | R |
| 7 | `core/strategy.py:437 StrategyService._validate_scope` | Team | S | Service | R |
| 8 | `core/strategy.py:447 StrategyService._validate_scope` | TeamPolicy | S | Service | R |
| 9 | `core/strategy.py:457 StrategyService._validate` | Objective | U | Service | R |
| 10 | `core/strategy.py:471 StrategyService._validate` | Objective | S | Service | R |
| 11 | `core/strategy.py:487 StrategyService._validate` | TeamPolicy | S | Service | R |
| 12 | `core/strategy.py:538 StrategyService._validate` | Task | U | Service | R |
| 13 | `core/strategy.py:546 StrategyService._validate` | TeamPolicy | S | Service | R |
| 14 | `core/ingestion.py:114 IngestionService._commit` | Task | U | Service | R — writes Signal/Event, not Task |
| 15 | `core/ingestion.py:253 IngestionService._validate_task_and_team` | Team | S | Service | R |
| 16 | `core/ingestion.py:265 IngestionService._validate_task_and_team` | TeamPolicy | S | Service | R |
| 17 | `core/ingestion.py:401 IngestionService._record_rejection` | Task | U | Service | R — inserts rejection Event |
| 18 | `core/plans.py:113 PlanService._create` | Objective | U | Service | R |
| 19 | `core/plans.py:171 PlanService._create` | Plan | U | Service | R — existence/replay check |
| 20 | `core/plans.py:336 PlanService._transition` | Plan | U | Service | W — changes Plan lifecycle fields |
| 21 | `core/plans.py:473 PlanService._validate_stop` | Plan | S | Service | R |
| 22 | `core/plans.py:495 PlanService._validate_task` | Team | S | Service | R |
| 23 | `core/plans.py:505 PlanService._validate_task` | TeamPolicy | S | Service | R |
| 24 | `core/plans.py:526 PlanService._accepted` | Event | C | Service | R — Event is immutable; S for normal read, U for exclusive materialization |
| 25 | `core/evaluations.py:191 EvaluationService.record` | Evaluation | U | Service | W — changes status/resolution fields |
| 26 | `core/evaluations.py:258 EvaluationService.reject` | Evaluation | U | Service | W — changes status/rejection fields |
| 27 | `core/evaluations.py:282 EvaluationService._require_task` | Task | U | Service | R |
| 28 | `core/update_thread_context.py:114 UpdateThreadContextAssembler.assemble` | Task | U | Service | R |
| 29 | `core/update_thread_context.py:129 UpdateThreadContextAssembler.assemble` | Team | U | Service | R |
| 30 | `core/update_thread_context.py:137 UpdateThreadContextAssembler.assemble` | Thread | U | Service | R |
| 31 | `core/update_thread_context.py:168 UpdateThreadContextAssembler.assemble` | Hypothesis | U | Service | R |
| 32 | `core/update_thread_context.py:193 UpdateThreadContextAssembler.assemble` | EvidenceLink | U | Service | R |
| 33 | `core/update_thread_context.py:425 UpdateThreadContextAssembler.verify_context` | Task | U | Service | R |
| 34 | `core/operator_application.py:214 OperatorApplication.create_update_thread_task` | Team | U | Service | R |
| 35 | `core/operator_application.py:222 OperatorApplication.create_update_thread_task` | Thread | U | Service | R |
| 36 | `core/operator_application.py:276 OperatorApplication.create_update_thread_task` | TeamPolicy | S | Service | R |
| 37 | `core/operator_application.py:411 OperatorApplication.request_learning_change_decision` | LearningChange | S | Service | R |
| 38 | `core/operator_application.py:528 OperatorApplication.request_learning_change_decision` | Team | U | Service | R |
| 39 | `core/operator_application.py:542 OperatorApplication.request_learning_change_decision` | TeamPolicy | S | Service | R |
| 40 | `core/operator_application.py:692 OperatorApplication.operator_update` | Team | U | Service | R |
| 41 | `core/operator_application.py:702 OperatorApplication.operator_update` | Thread | U | Service | R |
| 42 | `core/operator_application.py:721 OperatorApplication.operator_update` | TeamPolicy | S | Service | R |
| 43 | `core/operator_application.py:815 OperatorApplication.operator_update` | Task | U | Service | R — recovery observation |
| 44 | `core/operator_application.py:925 OperatorApplication.decide_learning_change` | Task | U | Service | R — failure recovery observation |
| 45 | `core/operator_application.py:1005 OperatorApplication.decide_learning_change` | Task | U | Service | R — conflict recovery observation |
| 46 | `core/update_thread.py:251 load_pinned_policy` | TeamPolicy | S | Caller | R |
| 47 | `core/learning_commit.py:210 LearningCommitService.decide` | LearningChange | U | Service | W — commits decision state |
| 48 | `core/learning_commit.py:226 LearningCommitService.decide` | Team | U | Service | R — eligibility/serialization |
| 49 | `core/learning_commit.py:261 LearningCommitService.decide` | KnowledgeItem | U | Service | W — supersede state transition |
| 50 | `core/learning_commit.py:343 LearningCommitService.decide` | Team | U | Service | R |
| 51 | `core/learning_commit.py:353 LearningCommitService.decide` | TeamPolicy | S | Service | R |
| 52 | `core/learning_commit.py:545 LearningCommitService.decide` | KnowledgeItem | U | Service | R — predecessor eligibility |
| 53 | `core/learning_commit.py:696 LearningCommitService.decide` | KnowledgeItem | U | Service | W — revise target |
| 54 | `core/learning_commit.py:805 LearningCommitService.decide` | KnowledgeItem | U | Service | W — revalidate target |
| 55 | `core/learning_commit.py:887 LearningCommitService.decide` | KnowledgeItem | U | Service | W — retire target |
| 56 | `core/learning_commit.py:1206 LearningCommitService._validate_proposer_terminal` | Task | S | Caller | R |
| 57 | `core/context_assembly.py:397 TaskContextAssembler._scope_in_session` | Task | U | Caller | R — optional lock |
| 58 | `core/context_assembly.py:427 TaskContextAssembler._scope_in_session` | Team | U | Caller | R — optional lock |
| 59 | `core/context_assembly.py:428 TaskContextAssembler._scope_in_session` | Objective | S | Caller | R — optional lock |
| 60 | `core/context_assembly.py:429 TaskContextAssembler._scope_in_session` | TeamPolicy | S | Caller | R — optional lock |
| 61 | `core/update_thread_worker.py:335 UpdateThreadWorker.run` | Task | U | Service | R |
| 62 | `core/update_thread_worker.py:418 UpdateThreadWorker._record_receipt` | Task | U | Service | R |
| 63 | `core/update_thread_worker.py:545 UpdateThreadWorker._record_proposals` | Task | U | Service | R |
| 64 | `core/update_thread_worker.py:650 UpdateThreadWorker._record_proposals` | TaskGenerationCharge | U | Service | R — validates reconciled charge |
| 65 | `core/world_memory.py:931 _verified_model_receipt` | TaskGenerationCharge | U | Caller | R |
| 66 | `core/world_memory.py:1817 WorldMemoryService.commit_model` | Task | U | Service | R |
| 67 | `core/world_memory.py:1873 WorldMemoryService.commit` | Task | U | Mixed | R — writes memory/evidence rows, not Task |
| 68 | `core/world_memory.py:1928 WorldMemoryService.commit` | Team | U | Mixed | R |
| 69 | `core/world_memory.py:1936 WorldMemoryService.commit` | Thread | U | Mixed | R |
| 70 | `core/world_memory.py:2005 WorldMemoryService.commit` | Hypothesis | U | Mixed | R — existing Hypothesis validation/serialization |
| 71 | `core/world_memory.py:2632 resume_update_thread_in_session` | TaskGenerationCharge | U | Caller | R |
| 72 | `core/knowledge_quality.py:548 _revision_target_binding` | KnowledgeItem | U | Caller | R — conditional current-state lock |
| 73 | `core/knowledge_quality.py:859 require_recorded_assessment` | KnowledgeQualityAssessment | U | Caller | R |
| 74 | `core/knowledge_quality.py:1175 KnowledgeQualityAssessmentService.record` | Task | U | Service | R |
| 75 | `core/knowledge_quality.py:1209 KnowledgeQualityAssessmentService.record` | LearningChange | U | Service | R |
| 76 | `core/knowledge_quality.py:1300 KnowledgeQualityAssessmentService.record` | KnowledgeQualityAssessment | U | Service | R — idempotency/replay |
| 77 | `core/task_runtime.py:481 TaskRuntime.admit` | LearningChange | S | Service | R |
| 78 | `core/task_runtime.py:539 TaskRuntime.admit` | Team | U | Service | R — serializes Team admission/quota |
| 79 | `core/task_runtime.py:557 TaskRuntime.admit` | TeamPolicy | S | Service | R |
| 80 | `core/task_runtime.py:728 TaskRuntime._validate_operator_admission` | LearningChange | U | Caller | R |
| 81 | `core/task_runtime.py:1258 TaskRuntime._commit_due_knowledge_reviews` | Team | U | Caller | R |
| 82 | `core/task_runtime.py:1282 TaskRuntime._commit_due_knowledge_reviews` | KnowledgeItem | U | Caller | R — review candidate serialization |
| 83 | `core/task_runtime.py:1990 TaskRuntime._validate_update_thread_result` | TaskGenerationCharge | U | Caller | R — receipt validation |
| 84 | `core/task_runtime.py:2216 TaskRuntime._committed_operator_decision_observation` | LearningChange | U | Caller | R |
| 85 | `core/task_runtime.py:4337 TaskRuntime._validate_learning_change_decision_result` | LearningChange | U | Caller | R |
| 86 | `core/task_runtime.py:4927 TaskRuntime._validate_learning_change_result` | KnowledgeItem | U | Caller | R |
| 87 | `core/task_runtime.py:5083 TaskRuntime._validate_learning_change_result` | KnowledgeItem | U | Caller | R |
| 88 | `core/task_runtime.py:5160 TaskRuntime._validate_learning_change_result` | Team | U | Caller | R |
| 89 | `core/task_runtime.py:5182 TaskRuntime._validate_learning_change_result` | KnowledgeItem | U | Caller | R |
| 90 | `core/task_runtime.py:5285 TaskRuntime._validate_learning_change_result` | Team | U | Caller | R |
| 91 | `core/task_runtime.py:5315 TaskRuntime._validate_learning_change_result` | KnowledgeItem | U | Caller | R |
| 92 | `core/task_runtime.py:5846 TaskRuntime._require_prerequisites` | Task | S | Caller | R |
| 93 | `core/knowledge_index.py:219 KnowledgeIndexService.index_signal` | Signal | U | Service | R — Signal is immutable; projection/index update follows |
| 94 | `core/knowledge_index.py:668 KnowledgeIndexService._upsert_index_state` | KnowledgeItem | U | Caller | R |
| 95 | `core/knowledge_index.py:692 KnowledgeIndexService._upsert_index_state` | TeamExperienceIndexState | U | Caller | W — insert-or-update index state |
| 96 | `core/knowledge_index.py:891 KnowledgeIndexService.index_knowledge_item` | KnowledgeItem | U | Service | R |
| 97 | `core/knowledge_lifecycle.py:793 _proposal_context` | Team | U | Caller | R — conditional current-state lock |
| 98 | `core/knowledge_lifecycle.py:803 _proposal_context` | KnowledgeItem | U | Caller | R — conditional current-state lock |
| 99 | `core/knowledge_lifecycle.py:876 _successor_binding` | KnowledgeItem | U | Caller | R — conditional current-state lock |
| 100 | `core/knowledge_lifecycle.py:1069 validate_lifecycle_task_request` | LearningChange | U | Caller | R |
| 101 | `core/knowledge_lifecycle.py:1446 require_recorded_assessment` | KnowledgeLifecycleAssessment | U | Caller | R |
| 102 | `core/knowledge_lifecycle.py:1676 KnowledgeLifecycleAssessmentService.create_task` | LearningChange | U | Service | R — creates Task, does not mutate LearningChange |
| 103 | `core/knowledge_lifecycle.py:1744 KnowledgeLifecycleAssessmentService.record` | Task | U | Service | R — creates assessment, does not mutate Task |
| 104 | `core/generation_cost.py:496 GenerationCostService._locked_charge` | TaskGenerationCharge | U | Caller | H — lock helper used by charge mutation operations |
| 105 | `core/knowledge_revalidation.py:626 _proposal_context` | KnowledgeItem | U | Caller | R — conditional current-state lock |
| 106 | `core/knowledge_revalidation.py:797 validate_revalidation_task_request` | LearningChange | U | Caller | R — conditional current-state lock |
| 107 | `core/knowledge_revalidation.py:1024 KnowledgeRevalidationAssessmentService.create_task` | LearningChange | U | Service | R — creates Task, does not mutate LearningChange |
| 108 | `core/knowledge_revalidation.py:1129 KnowledgeRevalidationAssessmentService.record` | Task | U | Service | R — creates assessment, does not mutate Task |
| 109 | `core/knowledge_revalidation.py:1281 require_recorded_assessment` | KnowledgeRevalidationAssessment | U | Caller | R |
| 110 | `core/experience_distiller.py:458 ExperienceDistiller.propose_retirement` | Team | U | Service | R |
| 111 | `core/experience_distiller.py:656 ExperienceDistiller.propose_supersede` | Team | U | Service | R |
| 112 | `core/experience_distiller.py:716 ExperienceDistiller.propose_supersede` | KnowledgeItem | U | Service | R — captures/validates prior state |
| 113 | `core/experience_distiller.py:1057 ExperienceDistiller._propose_candidate` | Team | U | Service | R — conditional supersede serialization |
| 114 | `core/experience_distiller.py:1292 ExperienceDistiller._capture_target_state` | KnowledgeItem | U | Caller | R — conditional state-capture lock |

### 3.1 Count reconciliation

| Source module | Sites |
|---|---:|
| `core/objectives.py` | 6 |
| `core/strategy.py` | 7 |
| `core/ingestion.py` | 4 |
| `core/plans.py` | 7 |
| `core/evaluations.py` | 3 |
| `core/update_thread_context.py` | 6 |
| `core/operator_application.py` | 12 |
| `core/update_thread.py` | 1 |
| `core/learning_commit.py` | 10 |
| `core/context_assembly.py` | 4 |
| `core/update_thread_worker.py` | 4 |
| `core/world_memory.py` | 7 |
| `core/knowledge_quality.py` | 5 |
| `core/task_runtime.py` | 16 |
| `core/knowledge_index.py` | 4 |
| `core/knowledge_lifecycle.py` | 7 |
| `core/generation_cost.py` | 1 |
| `core/knowledge_revalidation.py` | 5 |
| `core/experience_distiller.py` | 5 |
| **Total** | **114** |

Lock-mode reconciliation: 89 U + 24 S + 1 C = 114. The conditional Event site is not silently assigned to either unconditional count.

## 4. Relation-level DML capability ledger — what can and cannot be granted now

This table is a source-derived capability classification, not a final GRANT statement. The exact column list is deliberately marked unresolved where the full writer path, schema guards, or deployed runtime identity has not been validated.

| Relation | Lock-site status | Known same-relation writer path | Initial privilege direction | Remaining proof |
|---|---|---|---|---|
| Task | Mixed; shared `ObjectiveService._lock_task` plus many R callers | TaskRuntime lifecycle/admission/finalization and task-attributed services | Exact Task lifecycle columns only for the TaskRuntime writer; lock-only callers use fixed lock helper(s) | Enumerate every Task INSERT/UPDATE path and exact columns; ensure no bypass of TaskRuntime ownership |
| Team | Lock-only in all inventoried call sites | No production Team status/domain UPDATE found | No direct UPDATE for lock purposes; helper for required lock modes | Identify Team creation/activation writer, host/maintenance identity, and any out-of-repo operator |
| TeamPolicy | Immutable pinned reads/locks in inventoried paths | No production UPDATE path found; versioned inserts must be audited separately | No direct UPDATE; helper for lock-only reads | Enumerate TeamPolicy INSERT paths and sequence/UUID behavior |
| Objective | Mixed | ObjectiveService changes `status`; other sites lock for validation | UPDATE only on `status` if DB invariants and service boundary permit | Verify trigger/check constraints and all creation/update paths |
| Plan | Mixed | PlanService changes lifecycle fields | Exact lifecycle columns only | Enumerate all Plan inserts, action materialization and event writes |
| Event | Lock-only/conditional | Append-only Event INSERT across services; no application UPDATE/DELETE intended | INSERT only for authorized producers; lock helper for Event row lock | Map all Event producers and caller-owned transaction boundaries |
| Evaluation | Writer | EvaluationService.record/reject changes status/resolution/rejection fields | Exact changed columns only | Map INSERT and any future update writers |
| Thread | Lock-only in current production paths | No production Thread create/status/domain writer found | No direct INSERT/UPDATE/DELETE until F2 writer owner exists; lock helper for reads | Implement/inventory canonical lifecycle writer and host credentials |
| Hypothesis | Lock-only at call sites | WorldMemory writes Hypothesis rows; update-vs-insert semantics need exact branch audit | INSERT/UPDATE only if verified actual columns; lock helper for validation locks | Inspect commit path for existing-row mutation vs insert-only and exact fields |
| EvidenceLink | Lock-only at call sites | WorldMemory and Evaluation services insert EvidenceLink; no locked-row update identified | INSERT for supported writers; no UPDATE justified by lock | Map all insert producers and evidence immutability constraints |
| LearningChange | Mixed | LearningCommitService updates decision/commit state; other call sites read/validate | Exact decision/commit columns only; lock helper for read-only call sites | Map every LearningChange producer and lifecycle transition, including Operator paths |
| KnowledgeItem | Mixed/writer | LearningCommitService and lifecycle services mutate content/status/version/provenance fields | Exact columns by operation; no blanket UPDATE | Enumerate all writer methods, column sets, and history trigger compatibility |
| TaskGenerationCharge | Writer/helper | GenerationCostService reserve/reconcile/settle transitions charge state/accounting | Exact charge/accounting columns only; shared helper caller classification required | Map all charge transitions and recovery writes |
| KnowledgeQualityAssessment | Lock-only at listed sites | Assessment service inserts assessment; no update to locked prior assessment intended | INSERT only; helper for assessment locks | Verify no mutation/revision path exists |
| Signal | Lock-only at listed sites | Ingestion inserts Signal; KnowledgeIndex locks Signal but mutates projection tables | INSERT for ingestion; no UPDATE solely for index lock | Signal identity immutability and ingest writer identity |
| TeamExperienceIndexState | Writer | KnowledgeIndex upsert updates index state | Exact index-state columns required for upsert | Inspect insert/update SQL and uniqueness conflict behavior |
| KnowledgeLifecycleAssessment | Lock-only at listed sites | Lifecycle assessment service inserts assessment | INSERT only; helper for recorded-assessment lock | Verify no update/delete writer |
| KnowledgeRevalidationAssessment | Lock-only at listed sites | Revalidation assessment service inserts assessment | INSERT only; helper for recorded-assessment lock | Verify no update/delete writer |

### 4.1 DML outside the locked relation

The lock ledger cannot determine all DML grants by itself. Each transaction also writes relations that it may not lock explicitly. At minimum the full grant audit must include:

- Task/TaskRuntime: Task INSERT/UPDATE and Task Event/Outcome writes; preserve TaskRuntime as terminal-state owner.
- Control Room: Task INSERT and related request Event writes under caller-owned transactions.
- Ingestion: Signal INSERT, Snapshot persistence outside SQL, Event INSERT; no Signal UPDATE.
- Objective/Plan/Strategy: Objective/Plan/PlanAction/Task/Event writes and Task producer authority.
- Evaluation: Evaluation and EvidenceLink INSERT; Evaluation lifecycle UPDATE; Event INSERT.
- Operator/update-thread: Task and request Event INSERT; existing Thread/Team/Policy locks are not Thread mutation rights.
- WorldMemory: Hypothesis, EvidenceLink, ConfidenceChange inserts/updates as actually used; do not infer Thread UPDATE from Thread lock.
- Learning lifecycle: LearningChange/KnowledgeItem/assessment/Task/Event writes; split proposer, assessor, approver, and TaskRuntime finalizer transaction ownership.
- KnowledgeIndex: derived KnowledgeItem/index-state writes; Signal lock remains read-only.
- GenerationCost: TaskGenerationCharge INSERT/UPDATE and any sequence requirements.
- Database-owned triggers/functions: record writes performed under invoker or definer security separately from application-issued DML.

No final GRANT should be generated until this cross-relation writer list is complete.

## 5. Lock-helper grouping proposal

Do not create 89 separate helpers. Group helpers by a stable business lock protocol and relation/mode, with the smallest safe parameter surface. Candidate groups for detailed design (not implementation authorization):

1. **Task identity/lifecycle lock** — one narrowly typed Task lock primitive may serve read-only Task validation/replay paths only if it cannot be confused with TaskRuntime's write-owned lifecycle path. The shared `ObjectiveService._lock_task` callers must be inventoried before consolidation.
2. **Team admission/eligibility lock** — distinguish Team U serialization (e.g. quota/admission and TeamPolicy publication ordering) from Team S validation. Do not collapse U and S into a weaker common mode.
3. **Immutable policy lock** — TeamPolicy S reads can likely share one typed helper, with an explicit pinned version vs latest-version query contract.
4. **Existing Thread lock** — current update/Operator/world-memory paths lock existing Thread rows but do not own Thread lifecycle. A helper can grant serialization without granting Thread mutation; F2 still blocks lifecycle DML.
5. **Immutable evidence/history locks** — Event, Signal, EvidenceLink, Hypothesis, and recorded assessment locks may share a small number of narrowly typed helpers only where their authorization and lock order are identical.
6. **Mutable business aggregate locks** — Objective, Plan, Evaluation, LearningChange, KnowledgeItem, TaskGenerationCharge, and TeamExperienceIndexState require direct writer privileges only for actual mutation operations. Keep read-only locks separate from write paths where a single helper would obscure authority.

A function that locks multiple relations is acceptable only when it implements an already accepted lock order and its callers need the complete sequence. Do not create a generic `lock_row(regclass, uuid, mode)` API.

## 6. Ordered implementation and verification plan

### Step 1 — Freeze the source lock ledger (implemented in this document)
- Enumerate every SQLAlchemy `.with_for_update()` occurrence in the 19 production modules.
- Record relation, mode, function, line, and transaction ownership.
- Reconcile totals to 114, including the conditional Event mode.
- Re-run the source search at review time; fail the audit if the count or source module list changes without an updated ledger.

### Step 2 — Complete the DML writer ledger (next)
- Search every production `session.add`, ORM attribute assignment, `session.delete`, bulk `update/delete/insert`, Core `execute`, raw SQL DML, and database trigger write.
- For each writer, record relation, exact columns, INSERT/UPDATE/DELETE/TRUNCATE/sequence use, producer/service, transaction owner, and whether the operation is authorized through Control Room, TaskRuntime, Operator, ingestion, or a worker.
- Trace shared helpers to all callers. Do not classify by relation alone.
- Separate direct app DML from trigger/function-side DML and external storage writes.
- Result: one authoritative per-relation column-level DML ledger, with no guessed columns.

### Step 3 — Resolve transaction and runtime identity
- Identify the actual host/composition root, DSN configuration, service/worker process split, Operator credentials, migration credentials, bootstrap/admin identity, and maintenance/backup/indexer jobs.
- Produce an explicit mapping from each supported workflow to its database login and transaction owner.
- If the production host does not yet exist, label the matrix as source-only and defer grants; do not simulate a deployment identity with the CI bootstrap admin.
- Confirm whether all writers can be stopped/drained for the Option A credential cutover.

### Step 4 — Choose lock mechanism per call site
- Direct UPDATE only where the same supported operation truly mutates the locked relation and the exact changed columns are independently protected.
- Fixed SECURITY DEFINER lock functions for lock-only call sites. Functions must be owner-owned, use fixed `pg_catalog` search_path and schema-qualified relations, typed identifiers, no dynamic SQL or caller predicates, PUBLIC EXECUTE revoked, and EXECUTE granted only to the actual runtime identity.
- Preserve lock mode and ordering exactly; a helper must not downgrade U to S or alter a transaction's lock order.
- Require READ COMMITTED only where post-wait visibility depends on it. Explicitly document that a helper does not refresh ORM identity-map values.
- Keep shared helper paths split where callers have materially different write authority.

### Step 5 — Implement the smallest privilege change
- Add no broad table UPDATE grant and no arbitrary `UPDATE(id)` lock workaround.
- Add only reviewed function definitions/EXECUTE grants and exact writer DML grants, with ownership set explicitly.
- Keep Event append-only, Signal identity immutable, Thread lifecycle DML withheld until F2, and SignalDisposition INSERT withheld until D2 composite FK plus Decision 7 gates.
- Do not change TaskRuntime transaction ownership or introduce a second terminalization path.

### Step 6 — Strengthen privilege tests
- For lock-only relations, assert no table-level UPDATE and no column-level UPDATE using `has_any_column_privilege`.
- For writer relations, assert the exact allow-list using `has_column_privilege`; assert every unlisted column remains non-updatable.
- Assert effective role membership/inherited privileges and PUBLIC grants, not only direct ACL rows.
- Under the exact runtime login, exercise each supported lock helper and prove lock lifetime survives function return until transaction end.
- Prove forbidden direct UPDATE/DELETE/TRUNCATE/DDL/role-switch/replication-bypass attempts fail.
- Run representative service workflows through the actual runtime DSN, including positive writes and expected negative cases.
- Add concurrency tests for lock order, post-wait visibility, and no transaction ownership leakage.

### Step 7 — Deployment cutover and acceptance
- Provision owner/migrator/runtime identities; stop and drain old app processes and connections; run the reviewed migration as migrator assuming owner; restart only with runtime DSN.
- Inspect active sessions and effective privileges after restart; prove no bootstrap/owner/migrator identity remains in application writers.
- Run full disposable PostgreSQL suite and hosted CI on exact PR head.
- Independent review must confirm the complete matrix and tests. F1 remains open until the host identity and all supported writers are covered.

## 7. Current implementation boundary and blockers

This work implements the **source-audit layer only**. It does not install grants or functions. That is intentional:

- There is no production host/composition root or runtime DSN consumer in this repository.
- No complete maintenance/external writer inventory has been provided.
- The lock ledger is now complete at source-call-site level, but the full cross-relation DML writer ledger is still Step 2.
- F2 Thread creation/status/domain writer ownership remains absent.
- F3/F4 remain design contracts without their PostgreSQL/SQLAlchemy race proofs.
- D4.1a, D4.2, RW-5 and Decision 7 remain separate gates.
- SignalDisposition has no runtime write grant; no disposition outcome is enabled.

**No runtime code, ORM, migration, SQL function, role grant, database operation, or test behavior is changed by this audit.** A separate explicit authorization is still required for any privilege/function/migration implementation after the full DML ledger and runtime identity are accepted.
