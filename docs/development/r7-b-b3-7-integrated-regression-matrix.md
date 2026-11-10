# R7-B B3.7 — Integrated Regression Matrix Plan

**Status:** B3.7 implementation in progress (2026-11-10); matrix remains the acceptance inventory  
**Predecessor:** B3.6 — approval-time assessment binding (implemented and merged in PR #68)  
**Implementation gate:** Explicit Operator authorization granted after B3.6 merge  
**Normative contracts:** ADR-0032 and the frozen B3.1 assessment contracts  
**Current status authority:** `PLAN.md`

## 1. Purpose

B3.7 turns the frozen B3 assessment contracts and the ordered B3 sequence into an integrated regression plan. Its tests must exercise the actual persistence, TaskRuntime, Event, assessment, and approval-validation boundaries rather than proving correctness only through isolated helpers.

The matrix must prove both sides of the contract:

1. Valid assessment requests produce the exact immutable assessment record, attributable Event, and correct TaskRuntime terminal result.
2. Invalid, stale, cross-Team, tampered, replayed, or over-scoped requests fail closed without unauthorized canonical writes or duplicate durable records.

This document is a test plan. It does not claim that the B3.7 tests have been implemented or run.

## 2. Entry dependencies and current implementation status

The ten-stage B3 sequence orders B3.7 after B3.6. PR #68 is merged at `4735b93c74025ddee3bd099ef6d5e64cbac34719`; exact PR head `86f3bcf91ca024486f3a3b918a2c7490ec0ea9da` passed hosted and Operator-local verification. The implementation in `core/knowledge_approval.py`, `core/operator_application.py`, `core/operator_approval.py`, `core/task_runtime.py`, and `core/learning_commit.py` binds and revalidates operation-specific B3 assessment data and fingerprints. The host request path and approval allowlist remain create-only (`{"create"}`).

- B3.7 implementation was explicitly authorized after B3.6 merge.
- No lifecycle commit authority, new runtime, dispatcher, scheduler, migration, public auth stack, production evaluator, or R7-C work is authorized by B3.7.
- If an integrated test reveals a conflict with ADR-0032 or frozen B3.1 contracts, record the discrepancy and stop. Do not weaken the contract or test an invented interface.

B3.2–B3.5 are the implemented foundation: immutable assessment persistence, revalidation assessment, deterministic lifecycle assessment, and the two assessment TaskRuntime paths. Their current code and test inventory is listed below.

## 3. Boundaries that every test must preserve

### 3.1 Assessment authority

- `KnowledgeRevalidationAssessment` and `KnowledgeLifecycleAssessment` are immutable evidence/validation records, not canonical KnowledgeItem mutations and not approval decisions.
- Assessment workers may record only their own typed assessment:
  - `assess_knowledge_revalidation`: `["KnowledgeRevalidationAssessment"]`
  - `assess_knowledge_lifecycle`: `["KnowledgeLifecycleAssessment"]`
- Neither assessment Task may write `KnowledgeItem`, `LearningChange`, Task lifecycle records, terminal Outcomes, or Kernel-managed lifecycle Events.
- TaskRuntime remains the sole owner of Task admission, attempt fencing, retry/recovery, finalization, lifecycle Events, and terminal Outcomes.
- Assessment Events must be attributable to their creating Task and bind the exact assessment identity and payload hash.
- The assessment Task paths remain explicit application-invoked paths; B3.7 must not add automatic TaskDispatcher registration or a generic Task registry.

### 3.2 Approval authority

- The approval allowlist remains exactly `{"create"}`.
- B3.6 may add assessment validation and fingerprint binding; it does not authorize `revalidate`, `retire`, or `supersede` commits.
- B3.7 must prove that non-create lifecycle attempts remain rejected at every applicable approval boundary, including request/admission, finalization/recovery, and commit-service validation.
- No test may treat an assessment result of `supported` or `eligible` as approval or commit authority.

### 3.3 Scope exclusions

B3.7 is not a lifecycle-commit milestone. It must not introduce candidate creation, revise/revalidate/retire/supersede commit behavior, new schemas or migrations without a demonstrated contract requirement and separate review, a second runtime, a scheduler, automatic dispatch, a public API/authentication stack, a production evaluator/provider, or R7-C work.

## 4. Existing regression baseline

This is an inventory of existing coverage at the current B3.5 merged baseline. It is not a statement that the B3.7 integrated matrix is already complete.

| Existing test location | Existing coverage relevant to B3.7 | Remaining integrated question |
|---|---|---|
| `tests/test_knowledge_revalidation.py` | Freshness/result derivation; evaluator finding and evidence-reference validation; normalization and hash domains; historical target/current-pointer binding; typed TaskRuntime terminal-observation constraints. | Does the complete service/Task path preserve those rules through retries, immutable recording, Event verification, and later approval-time revalidation? |
| `tests/test_knowledge_lifecycle.py` | Original Operator rationale shape/provenance; retire/supersede proposal variants; deterministic findings; D7 successor status/review-date eligibility; complete successor snapshot and drift checks; exact lifecycle worker write scope. | Are all operation-specific rules preserved through persistence, TaskRuntime recovery/replay, and approval-time validation? |
| `tests/test_r7b_assessment_models.py` | Frozen model fields, required bindings, composite ownership references, assessment uniqueness, Event separation, and closed payload/vocabulary constraints. | Do database behavior and end-to-end services enforce the same constraints under real transactions? |
| `tests/test_r7b_assessment_migration.py` | PostgreSQL migration constraints, cross-Team/wrong-operation/event-task rejection, uniqueness, assessment immutability, truncate protection, successor reference protection, and downgrade safety. | Are the database guarantees exercised alongside successful and rejected service/Task flows in the integrated fixture? |
| `tests/test_experience_distiller.py` | B3.3/B3.4 assessment persistence and B3.5 TaskRuntime integration, including no-canonical-write assertions, recorded Events, replay/recovery and failure/retry history. It also contains the existing create-only Operator/quality-assessment path. | Does one integrated regression set cover both assessment types and the B3.6 approval pins without confusing the existing QualityAssessment binding with the new B3 assessment records? |
| `tests/test_task_runtime.py` | Shared TaskRuntime lifecycle and execution invariants. | Are the exact B3 assessment write scopes, request bindings, recovery observations, and terminal records enforced by the B3-specific runners? |

### 4.1 B3.6 approval-path baseline

B3.6 is now implemented and merged. Its exact PR head passed hosted and Operator-local verification. The B3.6 implementation adds operation-specific approval binding for `KnowledgeRevalidationAssessment` and `KnowledgeLifecycleAssessment`, including payload hashes, canonical host Operator identity, policy/evaluator/proposal/target/evidence pins, and the full supersede successor snapshot. Existing R7-A `KnowledgeQualityAssessment` coverage remains specific to create approval; it is not a substitute for integrated B3 assessment coverage. B3.7 must exercise the new binding through real assessment/Task/Event persistence and test its fail-closed drift behavior. The request path and approval allowlist remain create-only.



### 4.2 B3.7 implementation trace

| Matrix coverage | Implementation status | Evidence |
|---|---|---|
| RV-01 / RP-01 / RP-02 / AP-01 / AP-02 / E2E-01 (revalidation assessment and B3.6 approval binding) | Integrated binding assertions added to the existing real TaskRuntime/recovery test; hosted CI passed; Operator-local verification not run. | PR [#69](https://github.com/abtn/Watch-Architecture-Rev2/pull/69), `test_revalidation_task_records_once_and_recovers_without_canonical_writes` in `tests/test_experience_distiller.py`, parameterized across normal completion, first-attempt retry, and committed-assessment recovery. The test rebuilds the B3.6 binding from the persisted assessment and checks payload hash, current target, assessment Task policy pin, and canonical host principal. |
| LC-02 / LC-03 / AP-01 / AP-02 / E2E-03 (supersede assessment and successor approval recheck) | Initial integrated test added. Initial hosted run exposed a successor review-date type mismatch; narrow correction committed. Latest hosted CI passed; Operator-local verification not run. | PR [#69](https://github.com/abtn/Watch-Architecture-Rev2/pull/69), `test_b37_supersede_assessment_round_trips_successor_and_rechecks_approval_binding` in `tests/test_experience_distiller.py`, exact code head `b4ac92567ffcd9e324938932342c4dc1afeb8283`. The new case forced a persisted-successor path through lifecycle TaskRuntime and approval-binding revalidation. It also tampers with the recorded lifecycle Event payload and asserts `knowledge_lifecycle_recorded_event_invalid`. |

Hosted CI on exact code head `b4ac92567ffcd9e324938932342c4dc1afeb8283` passed run [42796818181](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42796818181): fresh PostgreSQL migration/single-head, Ruff, Mypy, **909 passed, 113 warnings**. The 113 warnings are the existing Alembic `path_separator` deprecations. The initial run [42795156884](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42795156884) had 908 passed and one failure; that failure exposed the successor review-date normalization issue corrected in the exact head above.

This is a partial implementation trace only. It does not mark all linked matrix rows complete until every assertion and remaining row is mapped during B3.7 closeout.

## 5. Integrated regression matrix

The following IDs are the planned B3.7 test inventory. The implementation may split or combine test functions, but it must preserve each assertion and must identify the test location for every row in the final report.

### 5.1 Revalidation evidence and target binding

| ID | Scenario | Required assertion | Existing base / planned gap |
|---|---|---|---|
| RV-01 | Valid current evidence basis | Application rebuilds canonical evidence references and hashes; a valid current evaluator draft records one immutable assessment with exact Team, proposal, target, evaluator identity/revision, Task, and attempt bindings. | Revalidation domain rules and service recording exist; add/confirm an end-to-end TaskRuntime + Event assertion. |
| RV-02 | Temporal freshness dispositions | `current` may support only when all required findings support it. `stale`, `insufficient`, `conflicting`, and `unassessable` cannot produce `supported`. | Domain tests exist; ensure the integrated Task result and absence of unauthorized writes are asserted. |
| RV-03 | Time-sensitive or changed evidence | Expired/changed sources, a time-sensitive claim without new observations, and material newer/contradictory evidence cannot be silently reused as current support. | Some source/freshness checks exist; cover the frozen negative cases through the canonical rebuild and recording boundary. |
| RV-04 | Evidence-reference integrity | Missing, duplicate, malformed, invented, cross-Team, or hash-mismatched references are rejected. Every canonical evidence link required by the rebuilt basis is accounted for; contrary evidence is not dropped. | Finding/draft unit coverage exists; add integrated persistence and no-record/no-write assertions where absent. |
| RV-05 | Evaluator provenance and draft trust | Missing or mismatched evaluator identity/revision and malformed, extra-field, or otherwise untrusted evaluator drafts are rejected; evaluator-supplied identities and hashes are never authoritative. | Domain validation exists; verify service-level rejection has no assessment/Event side effects. |
| RV-06 | Target and proposal drift | Changed current pointer, content version, content hash/scheme, target full-state hash, proposal hash, or complete proposed-state hash invalidates the request at the appropriate boundary. | Target binding coverage exists; exercise drift before admission/assessment and again before approval. |

### 5.2 Lifecycle variants and successor binding

| ID | Scenario | Required assertion | Existing base / planned gap |
|---|---|---|---|
| LC-01 | Retire variant | Retire binds the exact predecessor snapshot, proposal operation, structured original Operator rationale, and evidence. Every successor field is forbidden, including a field explicitly set to null. | Proposal/variant validation exists; exercise the immutable record and Task/Event path. |
| LC-02 | Supersede complete successor | Supersede requires the exact successor ID, same Team, current pointer, content version/hash/scheme, status, non-null future `review_after`, full-state hash, and exact reciprocal predecessor relationship. | Deterministic binding exists; test the full path and approval-time recheck after B3.6. |
| LC-03 | Successor mismatch and drift | Missing/extra fields, cross-Team successor, wrong predecessor, changed successor pointer/version/hash/status/review date/full-state hash, or invalid D7 eligibility fail closed. A successor ID alone is never sufficient. | Several unit/integration cases exist; ensure each required binding is asserted at assessment and approval boundaries. |
| LC-04 | Lifecycle rationale and operation integrity | Wrong operation, malformed rationale, missing provenance, substituted/model-generated rationale, evidence mismatch, or changed proposed-state hash is rejected. | Existing lifecycle domain tests cover core shapes; confirm persistence/Event side effects remain absent on rejection. |
| LC-05 | Assessment payload integrity | Recomputed canonical payload hash covers the complete typed variant and all required bindings; changing any semantic field changes/rejects the binding. | Hash-domain and normalization tests exist; add cross-boundary mutation cases where missing. |

### 5.3 Persistence, ownership, and immutability

| ID | Scenario | Required assertion | Existing base / planned gap |
|---|---|---|---|
| DB-01 | Required relational ownership | Assessment, Task, Team, LearningChange, target KnowledgeItem, evidence references, and successor references cannot be combined across Teams or rebound to an unrelated object. | Model and migration constraints exist; test representative cross-Team failures in real service transactions. |
| DB-02 | Assessment immutability | Database rejects row UPDATE, DELETE, and prohibited TRUNCATE operations independently of ORM/application checks. | Migration tests exist; retain a direct PostgreSQL assertion in the integrated verification set. |
| DB-03 | Idempotency uniqueness and references | One logical assessment identity per `(team_id, learning_change_id, assessment_type)`; request/recorded Event identities remain distinct and valid; required references cannot disappear through cascading deletion. | Model/migration tests exist; test duplicate and delete/restriction behavior in service-level transactions. |
| DB-04 | Migration compatibility | Fresh disposable PostgreSQL reaches one Alembic head and preserves the assessment constraints and immutability triggers. | B3.8 performs exact-head fresh migration verification; B3.7 must keep migration regression coverage and report schema drift if found. |

### 5.4 TaskRuntime, write scopes, Events, retry, and recovery

| ID | Scenario | Required assertion | Existing base / planned gap |
|---|---|---|---|
| TK-01 | Exact worker write scope | Revalidation Task has only `["KnowledgeRevalidationAssessment"]`; lifecycle Task has only `["KnowledgeLifecycleAssessment"]`. Attempts to write `KnowledgeItem` or `LearningChange` are rejected; Task lifecycle, Outcome, and Kernel-managed Event writes remain TaskRuntime-owned. | Exact scopes are implemented; ensure both paths are asserted together at admission/finalization boundaries. |
| TK-02 | Task envelope | Existing TaskRuntime path enforces the expected same-Team request, three-attempt limit, zero tool/cost budget, and 30-second deadline; no generic registry or automatic dispatch is assumed. | B3.5 lifecycle envelope and existing revalidation path exist; cover parity and fail-closed malformed envelopes. |
| EV-01 | Request Event binding | Request Event binds the Task, assessment type, exact proposal/target, idempotency identity, canonical request digest, and its own Event identity/payload digest. | Existing request validation exists; assert the event is the admitted request and cannot be substituted. |
| EV-02 | Recorded Event integrity | Recorded Event belongs to the creating Task and binds the exact assessment ID and payload hash; missing, duplicate, wrong-Task, wrong-hash, or mismatched Event fails finalization/replay. | Existing recording integrity checks exist; cover deliberate tampering and no fabricated repair. |
| RP-01 | Exact replay and conflict | Exact request replay returns the same assessment ID/hash and terminal result; changed request, bindings, payload, or idempotency reuse conflicts without a second assessment/Event/Outcome. | Existing replay/conflict coverage exists; add a matrix across both assessment types. |
| RP-02 | Interrupted attempt and recovery | A committed immutable assessment plus valid recorded Event is finalized by recovery; an uncommitted interrupted attempt follows existing retry disposition; stale/corrupt/mismatched records fail closed. | B3.5 recovery exists; verify both assessment types and negative corruption cases. |
| RP-03 | Terminal retry/failure history | Attempt history, retry scheduling, terminal failure Event, and Outcome match the current attempt; repeated replay produces no duplicate terminal records. | B3.5 regression specifically covers retry → terminal failure → repeated replay; retain it in the integrated set. |

### 5.5 Approval-time binding and create-only enforcement

These cases depend on B3.6 being implemented and accepted first.

| ID | Scenario | Required assertion | Dependency / planned gap |
|---|---|---|---|
| AP-01 | Assessment pin in approval fingerprint | Fingerprint includes the complete assessment payload hash, not only its ID, together with the frozen target/proposal/evidence/policy/Task-scope/successor bindings required by B0.3. | B3.6 implementation prerequisite; no current B3 coverage. |
| AP-02 | Assessment tampering | Missing, duplicate, stale, wrong-operation, cross-Team, wrong-target, changed evidence, changed successor, altered payload hash, or mismatched assessment ID/hash is rejected at approval validation. | B3.6 implementation prerequisite; derive tests from the frozen contract's negative-case matrix. |
| AP-03 | Trusted Operator identity | Host-authenticated canonical Operator issuer/subject is included in the request fingerprint and decision binding; a different principal cannot reuse the idempotency identity. | B3.6 implementation prerequisite; request-body/model asserted identity is not proof. |
| AP-04 | Idempotency conflict | Reusing a key with a changed principal, assessment payload, proposal, target state, or successor state conflicts; exact replay returns the original decision result. | B3.6 implementation prerequisite; assert no duplicate decision records. |
| AP-05 | Create-only allowlist | `revalidate`, `retire`, and `supersede` remain rejected at request/admission, finalization/recovery, and commit-service boundaries. No B3 assessment result authorizes a lifecycle commit. | B3.6 implementation prerequisite; active allowlist must remain exactly `{"create"}`. |

### 5.6 End-to-end combinations

| ID | Scenario | Required assertion |
|---|---|---|
| E2E-01 | Revalidation assessment path | Canonical evidence rebuild → request Event → TaskRuntime admission → assessment service → immutable assessment + recorded Event → TaskRuntime finalization/replay. The assessment Task creates no LearningChange disposition or KnowledgeItem mutation. |
| E2E-02 | Retire assessment path | Exact retire proposal/rationale/evidence → lifecycle TaskRuntime path → one immutable retire assessment and Task-attributed Event; no successor data and no canonical lifecycle mutation. |
| E2E-03 | Supersede assessment path | Exact predecessor/successor state → lifecycle TaskRuntime path → one immutable supersede assessment and Task-attributed Event; full successor binding retained; no canonical lifecycle mutation. |
| E2E-04 | Approval validation path | After B3.6, the approval request independently rechecks the recorded assessment and fingerprint. Non-create lifecycle operations remain rejected, and the KnowledgeItem/LearningChange canonical state remains unchanged. |
| E2E-05 | Cross-boundary failure atomicity | Force failures at validation, Event verification, assessment persistence, finalization, recovery, and approval validation. No partial assessment, duplicate Event/Outcome, or unauthorized canonical write remains. |

## 6. Test construction and execution strategy

- Reuse the existing PostgreSQL-backed fixtures and TaskRuntime paths. Add one or more focused integrated fixtures only where they reduce setup duplication without hiding which boundary is under test.
- Keep deterministic evaluator test doubles. Do not call a live model or add a production evaluator.
- Prefer real database constraints, persisted Event rows, TaskRuntime admission/finalization, and approval validation for boundary assertions. Unit tests remain useful for pure normalization and finding derivation but do not substitute for those boundaries.
- For each rejection, assert both the categorized failure and durable-state invariants: no assessment row when recording must not occur, no unauthorized KnowledgeItem/LearningChange mutation, and no duplicate Event/Outcome.
- For each successful assessment, assert exact IDs, hashes, Team/proposal/target/successor bindings, Task attempt, Event attribution, and stable replay.
- Keep revalidation and lifecycle variants distinct. Do not weaken the lifecycle discriminated union or accept a partial supersede binding to simplify shared fixtures.
- If a test reveals a need to change a frozen field, hash domain, operation vocabulary, approval allowlist, database ownership rule, or Task authority boundary, stop and return the discrepancy for Operator decision.

## 7. B3.7 completion criteria

B3.7 may be recommended complete only when:

1. Every matrix ID has an implemented test or an explicitly documented, Operator-accepted reason for omission.
2. Valid revalidation, retire, and supersede assessment paths are exercised through their real persistence, TaskRuntime, and Event boundaries.
3. All frozen negative cases relevant to assessment binding, evidence freshness, Team ownership, payload variants, immutable persistence, write scope, Event integrity, replay, and recovery are covered.
4. B3.6 approval fingerprints bind the required assessment payload hashes and host principal, and tampering/mismatch tests reject them.
5. All non-create lifecycle approval attempts remain rejected; the allowlist is still exactly `{"create"}`.
6. Tests prove the absence of unauthorized canonical `KnowledgeItem` and `LearningChange` writes, including failure and replay paths.
7. The test report maps each matrix ID to exact test names/files and identifies remaining gaps without describing unrun checks as passed.

B3.7 test completion is not B3.8 exact-head verification and is not B3 phase closure. B3.8 owns exact-head verification; B3.9 owns documentation closeout and explicit Operator B3 exit acceptance. B3 completion does not authorize B4–B6 or R7-C.

## 8. Verification hand-off to B3.8

After B3.7 implementation is separately authorized and its test changes are complete, B3.8 must independently run the focused groups, Ruff, Mypy, `git diff --check`, the full suite, fresh disposable PostgreSQL migration/single-head verification, full diff/scope review, and hosted/local exact-head comparison.

The local verification workflow must follow the repository's PowerShell script guide:

- exact repository/branch/HEAD/worktree preflight;
- refuse dirty worktrees and never discard/stash local work;
- verify exact SHAs, not only branch names;
- use a fresh disposable PostgreSQL container with a dynamically assigned loopback port, never persistent `watch` or host port 5432;
- save and restore `DATABASE_URL` and `TEST_DATABASE_URL`;
- clean only resources created by the script;
- check `$LASTEXITCODE` after each consequential native command;
- parse the generated `.ps1` before execution and finish with an unambiguous `PASSED:` line.

No B3.8 verification result is implied by this planning document.
