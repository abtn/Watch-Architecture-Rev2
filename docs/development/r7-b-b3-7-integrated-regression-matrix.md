# R7-B B3.7 — Integrated Regression Matrix Plan

**Status:** B3.7 test implementation complete (2026-11-10); all matrix IDs are mapped to merged tests; B3.8 exact-head verification has not run  
**Predecessor:** B3.6 — approval-time assessment binding (implemented and merged in PR #68)  
**Implementation gate:** Explicit Operator authorization granted after B3.6 merge  
**Normative contracts:** ADR-0032 and the frozen B3.1 assessment contracts  
**Current status authority:** `PLAN.md`

## 1. Purpose

B3.7 turns the frozen B3 assessment contracts and the ordered B3 sequence into an integrated regression plan. Its tests must exercise the actual persistence, TaskRuntime, Event, assessment, and approval-validation boundaries rather than proving correctness only through isolated helpers.

The matrix must prove both sides of the contract:

1. Valid assessment requests produce the exact immutable assessment record, attributable Event, and correct TaskRuntime terminal result.
2. Invalid, stale, cross-Team, tampered, replayed, or over-scoped requests fail closed without unauthorized canonical writes or duplicate durable records.

This document is the frozen test plan and completion trace. B3.7 test implementation is merged and hosted CI is green; Operator-local exact-head verification remains a B3.8 task and has not been run.

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



### 4.2 B3.7 implementation trace — complete

| Matrix IDs | Exact test mapping | Merged evidence and durable assertions |
|---|---|---|
| RV-01 / RV-02 / RV-03 / E2E-01 | `test_revalidation_task_records_once_and_recovers_without_canonical_writes`; `test_revalidation_rebuild_rejects_changed_canonical_evidence_before_admission` in `tests/test_experience_distiller.py`. | PRs [#69](https://github.com/abtn/Watch-Architecture-Rev2/pull/69), [#76](https://github.com/abtn/Watch-Architecture-Rev2/pull/76), [#77](https://github.com/abtn/Watch-Architecture-Rev2/pull/77), [#84](https://github.com/abtn/Watch-Architecture-Rev2/pull/84), and [#86](https://github.com/abtn/Watch-Architecture-Rev2/pull/86). Covers all five freshness dispositions through completion/retry/recovery; changed EvidenceLink stance and source Outcome hash; time-sensitive claims requiring a new observation; no assessment/Event/Outcome on pre-admission drift; same-Task recovery. |
| RV-04 / RV-05 | `test_revalidation_rejects_untrusted_provider_draft_without_record_and_recovers` in `tests/test_experience_distiller.py`; `test_draft_must_use_only_rebuilt_references_and_cover_evidence_links`, `test_draft_must_account_for_all_canonical_evidence_links`, `test_draft_must_classify_canonical_contrary_evidence`, and `test_finding_rejects_duplicate_or_empty_evidence_references` in `tests/test_knowledge_revalidation.py`. | PRs [#78](https://github.com/abtn/Watch-Architecture-Rev2/pull/78), [#86](https://github.com/abtn/Watch-Architecture-Rev2/pull/86), and [#87](https://github.com/abtn/Watch-Architecture-Rev2/pull/87). Seven malformed/untrusted evaluator variants, invented and omitted references, a real foreign-Team EvidenceLink reference, malformed/duplicate reference unit cases, retryability, no-record/no-write assertions, and valid same-Task recovery. |
| RV-06 / AP-02 | `test_revalidation_target_and_proposal_drift_fail_before_admission_and_approval` in `tests/test_experience_distiller.py`. | PR [#80](https://github.com/abtn/Watch-Architecture-Rev2/pull/80). Seven target/proposal drift variants cover current pointer, content version/hash, full-state hash, hash-scheme request binding, proposal hash, and complete proposed-state hash at pre-admission and approval-time boundaries. |
| LC-01 / LC-04 / E2E-02 | `test_lifecycle_retire_assessment_records_once_without_canonical_writes` in `tests/test_experience_distiller.py`; `test_operator_rationale_preserves_original_structure_and_order`, `test_operator_rationale_rejects_malformed_or_untrusted_fields`, and `test_retire_proposal_requires_exact_rationale_and_no_successor_fields` in `tests/test_knowledge_lifecycle.py`. | PR [#82](https://github.com/abtn/Watch-Architecture-Rev2/pull/82). Malformed retire payload/rationale variants reject before Task creation; valid retire assessment persists one immutable record and Task-attributed Event without canonical lifecycle mutation. |
| LC-02 / LC-03 / LC-05 / E2E-03 | `test_b37_supersede_assessment_round_trips_successor_and_rechecks_approval_binding` in `tests/test_experience_distiller.py`; `test_assessment_and_proposed_state_hash_domains_are_distinct`, `test_successor_binding_matches_complete_proposal_snapshot`, `test_successor_binding_rejects_state_drift_before_assessment`, and `test_successor_binding_rejects_cross_team_and_wrong_predecessor` in `tests/test_knowledge_lifecycle.py`. | PRs [#69](https://github.com/abtn/Watch-Architecture-Rev2/pull/69) and [#81](https://github.com/abtn/Watch-Architecture-Rev2/pull/81). Covers the full supersede successor snapshot and nine approval-time successor/proposal drift variants; assessment hash domains and deterministic lifecycle findings remain separately unit-tested. |
| DB-01 / DB-02 / DB-03 / DB-04 | `test_0017_rejects_cross_team_wrong_operation_and_wrong_event_task`, `test_0017_rejects_duplicate_assessment_identity_and_retire_successor_fields`, `test_0017_creates_contract_constraints_and_immutability_triggers`, `test_0017_accepts_complete_supersede_binding_and_restricts_successor_delete`, and `test_0018_constraint_and_immutability_contract_are_preserved` in `tests/test_r7b_assessment_migration.py`; service-level proposal delete assertion in `test_revalidation_task_records_once_and_recovers_without_canonical_writes`. | PR [#87](https://github.com/abtn/Watch-Architecture-Rev2/pull/87) adds a real foreign-Team evidence reference; PR [#92](https://github.com/abtn/Watch-Architecture-Rev2/pull/92) proves a persisted assessment restricts deletion of its LearningChange proposal. Every hosted checkpoint also runs fresh PostgreSQL migrations and verifies one Alembic head. Direct PostgreSQL tests cover UPDATE/DELETE/TRUNCATE protection, uniqueness, ownership, and successor/reference deletion restrictions. |
| TK-01 / TK-02 | `test_assessment_task_has_only_its_own_typed_write_scope` in `tests/test_knowledge_lifecycle.py`; both TaskRunner integration tests in `tests/test_experience_distiller.py`; Task-envelope/write-scope regression slice in PR #75. | PR [#75](https://github.com/abtn/Watch-Architecture-Rev2/pull/75). Both Task types preserve exact one-model write scopes, same-Team request bindings, three-attempt limit, zero tool/cost budget, and 30-second deadline; malformed envelopes fail closed. |
| EV-01 / EV-02 | Revalidation and lifecycle TaskRunner tests in `tests/test_experience_distiller.py`; `test_request_creates_one_pending_task_and_one_attributed_event`, `test_task_runtime_rejects_operator_request_event_identity_tampering` in `tests/test_operator_application.py`; wrong-Task migration test in `tests/test_r7b_assessment_migration.py`. | PR [#91](https://github.com/abtn/Watch-Architecture-Rev2/pull/91) adds missing and duplicate recorded-Event rejection for both assessment types. Existing tests cover request Event substitution, recorded Event payload-hash tampering, Task attribution, and replay/finalization failure. |
| RP-01 / RP-02 / RP-03 | `test_revalidation_task_records_once_and_recovers_without_canonical_writes`, `test_lifecycle_retire_assessment_records_once_without_canonical_writes`, and TaskRuntime retry/failure-history tests in `tests/test_experience_distiller.py`; idempotency conflict tests in `tests/test_operator_application.py`. | PRs [#85](https://github.com/abtn/Watch-Architecture-Rev2/pull/85), [#89](https://github.com/abtn/Watch-Architecture-Rev2/pull/89), and [#90](https://github.com/abtn/Watch-Architecture-Rev2/pull/90) add assessment-persistence rollback and same-Task recovery for both assessment types, plus terminal finalization/recovery rollback. Existing exact replay, changed-request conflict, retry fencing, terminal failure, and repeated replay remain covered. |
| AP-01 / AP-02 / AP-03 / AP-04 / AP-05 / E2E-04 | `test_revalidation_binding_pins_current_target_evidence_and_assessment`, `test_lifecycle_supersede_binding_includes_full_successor_snapshot_and_provenance`, `test_assessment_type_mismatch_and_duplicate_records_fail_closed`, `test_assessment_hash_principal_and_policy_are_fingerprint_inputs`, `test_missing_revalidation_assessment_fails_at_approval_binding`, `test_stale_or_tampered_recorded_assessments_fail_closed_at_approval`, and `test_cross_team_assessment_binding_fails_closed` in `tests/test_knowledge_approval.py`; create-only request/admission/finalization/recovery/commit tests in `tests/test_operator_application.py`. | B3.6 PR [#68](https://github.com/abtn/Watch-Architecture-Rev2/pull/68), drift tests in PRs #80/#81, and the integrated approval checks in PR #69. Complete assessment hashes and host principal are fingerprinted; stale/mismatched/cross-Team/duplicate bindings fail closed; changed principal/proposal/decision under one idempotency key conflicts; all non-create operations remain rejected at each boundary. |
| E2E-05 | Failure-atomicity assertions in `test_revalidation_rejects_untrusted_provider_draft_without_record_and_recovers`, `test_revalidation_task_records_once_and_recovers_without_canonical_writes`, and `test_lifecycle_retire_assessment_records_once_without_canonical_writes`. | PRs [#85](https://github.com/abtn/Watch-Architecture-Rev2/pull/85), [#89](https://github.com/abtn/Watch-Architecture-Rev2/pull/89), [#90](https://github.com/abtn/Watch-Architecture-Rev2/pull/90), [#91](https://github.com/abtn/Watch-Architecture-Rev2/pull/91), and [#92](https://github.com/abtn/Watch-Architecture-Rev2/pull/92). Covers validation/Event/persistence/finalization/recovery/approval failures with no partial assessment, duplicate Event/Outcome, or unauthorized canonical write. |

**Completion record (2026-11-10):** All matrix IDs have concrete test mappings; no omission was accepted or required. Cumulative merged regression PRs are #69–#82, #84–#87, and #89–#92. PRs #83 and #88 were superseded and closed after their changes were carried forward by #86 and #89. Latest hosted exact-head CI is PR #92 run [42831066494](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42831066494): fresh PostgreSQL migration/single-head, Ruff, Mypy, **946 passed, 113 existing Alembic warnings**. Operator-local exact-head verification has not been run; that is B3.8, not a B3.7 test-implementation result. The approval allowlist remains exactly `{"create"}`. B3.7 test implementation is complete; B3.8 exact-head verification, B3.9 closeout, and explicit Operator B3 exit acceptance remain pending. B3 completion does not authorize B4–B6 or R7-C.

This implementation trace maps every matrix ID to concrete test files and test names. PRs #69–#92 are cumulative checkpoints, not production-scope expansion. The approval allowlist remains exactly `{"create"}`.
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
