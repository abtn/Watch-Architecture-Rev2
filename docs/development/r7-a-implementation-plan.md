# R7-A — Evidence Lineage and Knowledge-Quality Assessment Implementation Plan

## Status and authority

**Authorized implementation phase — 2026-11-04.** ADR-0032 is Accepted. The Operator authorized R7-A only. R7-B lifecycle operations and R7-C retrieval/citation/downstream-use work remain unauthorized.

This plan is the frozen R7-A implementation contract; source implementation is in progress under the separate Operator authorization. It does not select a production evaluator provider or authorize live external model calls.

## 1. Bounded deliverables

1. Deterministic classification of evidence relationships between distinct source-Task cases in a LearningChange's existing canonical evidence basis.
2. A dedicated KnowledgeQualityAssessment ORM/migration/model/service contract. Existing Evaluation and Evaluation-only EvidenceLink remain unchanged and Outcome-scoped.
3. A narrow assess_knowledge_quality Task, created as a TaskRuntime-managed side effect when a propose_learning_change Task successfully finalizes its create proposal.
4. A typed, attributable, idempotent assessment record bound to the exact LearningChange ID, proposed-state hash, evidence-basis hash, rubric revision, evaluator identity/revision, and deterministic lineage report.
5. A mandatory approval guard: an accepted KnowledgeItem create cannot commit unless exactly one valid, recorded KnowledgeQualityAssessment exists for that exact proposal and evidence basis.
6. Deterministic tests for lineage classification, assessment validation/replay, Task admission/finalization/recovery, and the Operator create-approval guard.

No revise, revalidate, supersede, retire, KnowledgeItem current-pointer change, new status, downstream citation, retrieval benchmark, reranker, new runtime, dispatcher, or production provider is included.

## 2. Canonical case identity and lineage contract

A case is identified by the tuple (source_task_id, outcome_id, evaluation_id) in one LearningChange evidence-basis entry. The current distiller already rejects repeated source Task IDs; R7-A preserves that rule.

For every case, derive the following canonical lineage data from source_task_provenance and its normalized evidence_links:

- Source Task identity and its optional complete PlanAction pair (plan_id, action_id).
- The case's primary Outcome ID and observation Snapshot ref/hash. The primary Outcome is not treated as an upstream shared anchor.
- Every non-primary Outcome evidence reference: exact Outcome ID and its Snapshot ref/hash.
- Every Signal evidence reference: exact Signal ID and its Snapshot ref/hash.

A lineage anchor is complete only when its canonical source identity and immutable Snapshot ref/hash are present and consistent with the canonical record. The ExperienceDistiller.validate_learning_change rebuild remains the evidence authority; the new classifier does not trust free-form fields or a worker-supplied lineage report.

### Pairwise classification

For each unordered pair of cases, ordered by canonical Evaluation UUID:

- **related** when a deterministic common upstream anchor exists: the same non-primary Signal ID, the same non-primary Outcome ID, the same immutable upstream Snapshot ref/hash, or the same complete (plan_id, action_id) pair.
- **unknown** when either case has no complete non-primary upstream anchor or required lineage data is unavailable/incomplete. Unknown must not be upgraded to independent merely because Task IDs differ.
- **independent** only when both cases have at least one complete upstream anchor and none of the related conditions match.

Do not compare Team ID, Objective ID, or task type as duplicate keys. A shared Team, Objective, or task class alone does not make cases related. Do not use fuzzy/semantic similarity or infer near-duplicates in R7-A. Exact content duplication is represented by a shared canonical Snapshot hash; near-duplicate detection remains out of scope.

The persisted report is deterministic and includes a schema revision, canonical case references, pairwise relationship, and structured shared-anchor reason codes. Ordering is stable. The classifier is read-only and cannot alter case selection or the existing two-distinct-Task minimum.

Related and unknown cases continue to count toward the ADR-0029 two-distinct-Task proposal threshold. Their relationships are exposed to the assessor and must limit any breadth/independence claim.

## 3. KnowledgeQualityAssessment contract

### Rubric

Rubric identity: watch.r7a.knowledge-quality, revision 1.

Every assessment contains exactly these seven dimensions:

1. evidence_fidelity
2. case_coverage_relationship
3. contradiction_handling
4. applicability_boundaries
5. uncertainty_calibration
6. specificity_actionability
7. novelty_overlap

Each dimension has:
- disposition: supported, limited, contradicted, or insufficient_evidence;
- one or more concise findings;
- zero or more exact evidence-reference keys from the bound LearningChange evidence basis.

A non-insufficient_evidence disposition must cite at least one valid reference. insufficient_evidence may have no references. Empty findings are invalid. Unknown dimension names, missing dimensions, extra fields, unrecognized dispositions, references outside the canonical basis, and duplicate references are rejected.

The assessment also includes a bounded overall narrative and the deterministic lineage report. There is no aggregate score, confidence threshold, or machine-generated pass bit. The recorded assessment is evidence for the trusted Operator; it is not commit authority. The Operator may accept or reject the LearningChange after reviewing all dimensions. A contradicted or insufficient_evidence finding is not silently converted into a positive result.

The novelty/overlap dimension must say insufficient_evidence unless the assessment has explicit, validated same-Team KnowledgeItem references in its bounded evidence basis. R7-A does not implement a semantic retrieval search over Team Experience.

### Evidence-reference vocabulary

References are derived from, and must exactly resolve within, the current LearningChange evidence basis:

- evaluation:<canonical-uuid>
- outcome:<canonical-uuid>
- evaluation_task_outcome:<canonical-uuid>
- source_task:<canonical-uuid>
- signal:<canonical-uuid>
- snapshot:<sha256-digest>
- evidence_link:<canonical-reference-key>

The service recomputes the allowed reference set from the canonical basis after ExperienceDistiller.validate_learning_change rebuilds it. The worker cannot invent or supply a new canonical source. R7-A does not extend EvidenceLink or give the assessment Task any Outcome/EvidenceLink write scope.

### Persisted record

Add knowledge_quality_assessments with:
- UUID primary key and same-Team foreign keys to LearningChange and creating Task;
- one assessment per LearningChange create proposal;
- exact LearningChange proposal hash and evidence-basis hash;
- rubric identity/revision;
- evaluator kind, stable identity, and revision pinned by the Task request Event;
- JSONB seven-dimension rubric result, bounded narrative, deterministic lineage report, and complete evidence-reference hash;
- immutable proposal hash, idempotency key, creating Task, and recorded timestamp.

The row has one terminal status: recorded. A malformed/unverifiable draft is not persisted; the Task fails through TaskRuntime and can use the ordinary retry/recovery path. A valid assessment may contain any rubric dispositions, including contradicted and insufficient_evidence; those are findings, not a rejected record state.

The unique constraint on LearningChange ID prevents multiple competing current assessments in R7-A. Re-assessment/revision semantics are deferred; they require a later decision and must not be improvised in this phase.

## 4. Task and lifecycle integration

### Task request

After TaskRuntime validates and commits a successful propose_learning_change Task finalization, the same database transaction creates exactly one deterministic pending assess_knowledge_quality Task and its knowledge_quality_assessment_task_requested Event.

Task contract:
- same Team and policy version as the proposal Task;
- no Objective, Plan, or PlanAction;
- exact worker write scope ["KnowledgeQualityAssessment"];
- zero tools and zero configured generation spend in R7-A; no live model invocation is wired;
- three maximum starts and the ordinary bounded deadline;
- a deterministic Task ID derived from Team, LearningChange ID, rubric revision, and evaluator contract identity/revision.

The immutable request Event binds Task/Team/policy, LearningChange ID, exact proposed-state hash, evidence-basis hash, rubric revision, evaluator kind/identity/revision, deterministic lineage-report hash, and a request fingerprint over the complete payload.

TaskRuntime.admit validates exact Task shape, request Event, deterministic ID, source proposal Task, current proposed LearningChange, exact proposal/evidence hashes, and recomputed lineage report before starting an attempt. No dispatcher or second runtime is added.

### Assessment write and finalization

KnowledgeQualityAssessmentService accepts a strict typed draft only for a running assess_knowledge_quality Task with the exact write scope and one valid request Event. The service:
- locks and verifies the LearningChange is still the same proposed create;
- rebuilds the entire evidence basis with ExperienceDistiller.validate_learning_change;
- recomputes lineage and the allowed evidence-reference set;
- validates all seven dimensions and evaluator/rubric identity against the immutable request;
- computes canonical payload/reference hashes;
- inserts one immutable recorded assessment and one Task-attributed knowledge_quality_assessment_recorded Event;
- returns the stored record for an identical idempotent replay and rejects changed-payload reuse.

TaskRuntime.finalize accepts only success_knowledge_quality_assessed with the exact assessment ID for this Task. It verifies the assessment's Team, creating Task, LearningChange, proposal hash, evidence-basis hash, rubric/evaluator identity, recorded Event, and current LearningChange proposed state before writing the Task Outcome and terminal Event.

Interrupted recovery reconstructs the same success observation when a complete recorded assessment exists; otherwise it follows the ordinary retry/exhaustion logic. Attempt fencing and replay remain mandatory.

### Existing create approval gate

For decision=accept, OperatorApplicationAdapter rejects approval-task creation unless the exact proposed LearningChange has one recorded same-Team assessment whose proposal/evidence hashes match the current canonical proposal. The request Event pins the assessment ID and payload hash.

LearningCommitService repeats this check under the LearningChange transaction lock immediately before commit. TaskRuntime independently validates the pinned assessment at approval-Task finalization. Rejection of a LearningChange remains available without a quality assessment, because it creates no canonical KnowledgeItem.

The assessment never writes or changes LearningChange, KnowledgeItem, TeamPolicy, or projection state. The only canonical write remains the existing trusted Operator approve_learning_change path.

## 5. Evaluator/provider boundary

The Task request pins a logical evaluator contract and rubric revision. R7-A adds no production provider adapter, model identifier, SDK, credentials, live generation call, or rate-card choice. Service tests use a deterministic fake assessment draft. A real evaluator cannot be invoked until a separate provider/model/data-handling/cost decision is accepted. Unknown or unmetered model usage is not permitted.

## 6. Migration and implementation file map

Expected source changes:

- migrations/versions/0014_knowledge_quality_assessment.py — new assessment table and constraints; down-revision must be the verified current single head.
- core/models.py — KnowledgeQualityAssessment.
- core/knowledge_quality.py — strict draft types, deterministic lineage classifier, canonical reference set/hash, assessment service.
- core/task_runtime.py — exact Task creation/request/admission/finalization/recovery integration; no second runtime.
- core/operator_application.py — assessment-bound approval request fingerprint/Event validation.
- core/learning_commit.py — mandatory recorded-assessment check before accepted create.
- docs/tasks.md — activate only the assess_knowledge_quality row and update the create-approval/read/write contract and scope matrix.
- docs/invariants.md — implementation evidence alignment only if the accepted INV-12 text needs a clarifying implementation note; no weakening.
- tests/test_knowledge_quality.py, focused TaskRuntime/approval tests, and docs/testing.md.

No change is expected in core/knowledge_index.py, core/context_assembly.py, KnowledgeItem schema, or the active LearningChange operation vocabulary in R7-A.

## 7. Acceptance and verification

R7-A is complete only when all of the following are demonstrated on the exact implementation head:

- Pure lineage tests cover related-by-Signal, related-by-Outcome, related-by-Snapshot, related-by-PlanAction, independent with complete disjoint anchors, unknown with missing upstream anchors, deterministic order/hash, and distinct Task ID minimum enforcement.
- Assessment schema tests reject missing/extra dimensions, invalid dispositions, blank findings, unsupported references, cross-Team/mismatched proposal, stale evidence, malformed hashes, and changed idempotency replay.
- Assessment record and Task finalization tests prove exact request binding, same-Team constraints, correct write scope, one assessment per LearningChange, atomic Task completion, stale-attempt rejection, and terminal replay.
- Interrupted recovery completes the same Task from a committed assessment without a duplicate record; incomplete assessments retry/fail under ordinary recovery.
- Acceptance is blocked for missing, non-recorded, stale, cross-Team, or hash-mismatched assessment. Operator rejection remains possible without one. Both application and TaskRuntime independently enforce the boundary.
- Existing R6 Evaluation, Distiller, LearningCommit, Team Experience, Context v2, R6-G and full-suite regressions pass.
- Fresh migrations reach one Alembic head on a disposable PostgreSQL database; Ruff, Mypy, focused tests, full suite, and git diff --check pass.
- No live provider/model call occurs. PR CI runs against the exact final SHA.

The implementation phase remains R7-A only. R7-B and R7-C require separate authorization.
