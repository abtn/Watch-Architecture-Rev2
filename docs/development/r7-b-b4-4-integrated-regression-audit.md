# R7-B B4.4 — Integrated Regression Audit
**Status: STARTED — initial read-only source/test audit recorded (2026-11-11).**
**Baseline:** exact merged main commit 5f37927ff33d9e740c0ff56512d261dace36ab67.
**Implementation parent:** B4.3 merge commit f9c585c174799cf26fc0d7bf8ed57a8396e2b5aa.
**Scope:** B4.4 only. This audit makes no production-code or test changes and does not authorize B5, B6, or R7-C.
## 1. Purpose and authority
B4.4 is the integrated regression and closeout phase defined by the accepted B4.0 architecture decision §6. It must verify the combined B4.1 proposal/assessment contracts, B4.2 revise commit, and B4.3 revalidate commit across lifecycle invariants, concurrency, stale assessments, retries/recovery, projection visibility, exact-head hosted CI, and Operator source/diff review.
This is a read-only audit of the exact merged main tree named above. The current status remains **B4.4 started, not complete**. No implementation PR, B4.4 hosted run, or final Operator closeout review is claimed by this record.
## 2. Source and test surface inspected
### Production source
- core/experience_distiller.py — create/revise/revalidate proposal construction and replay.
- core/knowledge_quality.py — revise assessment recording and validation.
- core/knowledge_revalidation.py — revalidation assessment recording, evidence, target binding, and freshness.
- core/knowledge_approval.py — operation-specific approval binding and assessment provenance.
- core/operator_approval.py — request schema, supported-operation predicate, and approval fingerprint.
- core/operator_application.py — trusted host identity, request admission, idempotency, and orchestration.
- core/learning_commit.py — canonical revise/revalidate decision, compare-and-set, state snapshots, decision Event, and replay.
- core/task_runtime.py — approval admission, terminal validation, recovery, and replay.
- core/learning_history.py — immutable history reconstruction and transition invariants.
- core/knowledge_index.py and core/context_assembly.py — existing projection/retrieval publication gates.
### Regression tests
- tests/test_experience_distiller.py
- tests/test_knowledge_approval.py
- tests/test_knowledge_quality.py
- tests/test_knowledge_revalidation.py
- tests/test_learning_history.py
- tests/test_operator_application.py
- tests/test_operator_approval.py
- tests/test_task_runtime.py
- tests/test_team_experience.py
## 3. Existing proof inventory
| B4 proof area | Existing evidence on baseline | Audit disposition |
|---|---|---|
| Revise proposal and exact target binding | test_revise_proposal_pins_exact_target_and_records_bound_assessment (content and confidence-only variants; NULL and configured review interval variants) | Existing coverage |
| Accepted revise commit | Same test exercises accepted revise, same-item identity, pointer advance, version +1, status preservation, confidence behavior, dates, snapshots, and Task-attributed decision Event | Existing coverage |
| Revise recovery and replay | Same test invokes recover_interrupted after the decision commit and verifies completion; it then replays the original approval after a later competing accepted revise | Existing coverage |
| Rejected revise | Same test verifies canonical state unchanged and rejected decision replay | Existing coverage |
| Stale revise proposal / competing winner | Same test makes one revision stale after another proposal is accepted; stale decision leaves no decision Event or partial state | Existing sequential winner/loser coverage; not a simultaneous race |
| Accepted revalidate commit | test_operator_commits_supported_revalidation_without_changing_content verifies needs_review → active, unchanged content hash/version/origin, pointer advance, validation/review dates, decision Event assessment references, TaskRuntime finalization, and immediate replay | Existing coverage |
| Rejected revalidate | test_rejected_revalidation_does_not_mutate_the_knowledge_item verifies no canonical mutation and TaskRuntime rejection finalization | Existing coverage |
| Revalidation proposal/assessment integrity | test_revalidation_proposal_replays_after_task_completion, test_revalidation_rebuild_rejects_changed_canonical_evidence_before_admission, test_revalidation_target_and_proposal_drift_fail_before_admission_and_approval, and operation-specific assessment/binding tests in test_knowledge_revalidation.py and test_knowledge_approval.py | Existing coverage |
| History semantics | tests/test_learning_history.py covers status-preserving revise, revalidation confidence immutability, parent/pointer reconstruction, forks, cross-Team history, snapshot mismatch, and timestamp ordering | Existing coverage |
| Approval binding and unauthorized operations | tests/test_knowledge_approval.py, tests/test_operator_approval.py, and tests/test_operator_application.py cover assessment type/count, payload hashes, host identity, policy, Team scope, stale binding, and rejection of unsupported lifecycle operations | Existing coverage |
| Projection invalidation and republish | test_revalidation_pointer_only_transition_invalidates_old_projection, test_needs_review_item_is_not_retrievable_even_if_projection_remains, and test_revalidated_item_is_hidden_until_its_new_projection_is_published | Existing coverage |
| Create compatibility | test_original_create_approval_replays_after_later_history_transition and existing create proposal/approval tests | Existing coverage |
| Generic competing approval requests | test_competing_approval_tasks_terminalize_the_losing_request covers competing approval Tasks and recovery of the losing Task | Existing coverage; the tested fixture is create-oriented |
## 4. Gaps requiring B4.4 regression proof
The following are gaps in the identified test evidence, not claims that the implementation is defective. B4.4 should add the smallest tests that prove the frozen requirements; it should not add infrastructure or widen authority.
### G1 — True concurrent compare-and-set race on one KnowledgeItem
The revise regression constructs competing proposals and commits the winner before attempting the stale loser. The competing approval test likewise sequences the winner and loser. The inspected test inventory does not establish two concurrently executing PostgreSQL approval transactions racing on the same target.
**Required proof:** use separate sessions/transactions against disposable PostgreSQL with controlled synchronization. Exactly one canonical transition wins; the loser fails closed; no partial state, duplicate decision Event, duplicate version/pointer advance, or terminal success for the loser is persisted. Cover the shared compare-and-set boundary for revise and revalidate, or demonstrate why one parameterized common test proves both.
### G2 — Revalidation approval crash/recovery after canonical decision commit
The revise regression exercises interrupted recovery after its canonical decision. test_operator_recovery_finalizes_a_committed_decision_after_crash exercises the Operator adapter crash boundary with a create proposal. The revalidation-specific recovery test concerns the assessment Task, not the later Operator approval Task after a revalidation decision has committed.
**Required proof:** simulate process loss after accepted revalidation commits but before approval Task finalization; recover through the existing TaskRuntime; prove exactly one terminal Outcome/Snapshot/Event and no duplicate canonical write. Also cover rejected revalidation recovery if the common typed failure/success path is not already proved by a direct operation-specific test.
### G3 — Revalidation approval replay after a later history transition
The inspected revalidation commit test proves immediate replay. The explicit replay-after-later-transition test currently covers create; the revise regression covers a revise replay after a later accepted competing revise. No equivalent revalidation approval replay after a later accepted transition was identified.
**Required proof:** commit and finalize revalidation, apply a later accepted history transition to the same item through the existing canonical path/fixture, then replay the original revalidation approval. It must return the original result without changing the later current state or duplicating Events/Outcomes.
### G4 — One integrated revise → revalidate sequence on the same item
The identified revise and revalidate commit tests establish each operation in separate fixtures. The audit did not identify a single end-to-end regression that exercises both operation paths sequentially on the same canonical item, including assessment freshness across the pointer/version change.
**Required proof:** revise an item, then obtain a fresh revalidation assessment against the resulting current state after the item enters needs_review; prove the old assessment/target binding cannot be reused, then revalidate and verify both transitions in reconstructed history and projection eligibility. Keep this test bounded to B4 operations.
### G5 — Revalidation rejection replay and decision-record idempotency
The revalidation rejection test proves no KnowledgeItem mutation and TaskRuntime rejection finalization. Unlike the accepted revalidation test, it does not visibly assert replay of the rejected Operator approval and unchanged decision/Event/Outcome counts.
**Required proof:** replay the original rejected revalidation approval and assert the original rejection is returned with no duplicate decision Event, Outcome, or canonical mutation.
### G6 — Accepted revise commit from needs_review
The revise approval-binding test uses a needs_review target, and the history unit test proves the transition validator preserves that status. The identified end-to-end canonical revise test starts from an active item; no accepted revise commit starting from a needs_review KnowledgeItem was identified.
**Required proof:** commit a valid revise against a current needs_review item and verify the status remains needs_review, content/version/pointer/date semantics follow the revise contract, history reconstructs, and the current projection remains ineligible while status is needs_review.
## 5. Scope and stop conditions
- Keep the supported B4 operations exactly create, revise, and revalidate.
- Keep the existing propose_learning_change Task, LearningCommitService, trusted Operator path, and single TaskRuntime.
- No migration, new Task type, runtime, dispatcher, scheduler, API, authentication subsystem, synchronous indexing shortcut, or production evaluator/provider.
- Do not implement supersede, retire, or create-with-successor; B5/B6/R7-C remain unauthorized.
- If a required proof cannot be established without changing frozen B0/B1/B2 semantics, schema, or authority boundaries, stop and report the smallest blocker.
## 6. B4.4 sequence
1. **Audit baseline — recorded here:** inspect exact merged main and map existing source/tests to the frozen B4 requirements.
2. **Close regression gaps G1–G6:** implement only missing deterministic tests and minimal demonstrated corrections.
3. **Run exact-head hosted CI:** fresh disposable PostgreSQL migration/single-head, Ruff, Mypy, git diff --check origin/${GITHUB_BASE_REF}...HEAD, full pytest, and hosted disposable-service cleanup. Record exact PR head and workflow run.
4. **Operator source/diff review:** review the complete final source/test diff and the frozen B4.1 contract matrices. CI does not replace this review.
5. **Documentation closeout:** reconcile PLAN, CHANGE_MAP, this implementation plan, and docs/testing; record B4 exit only after all required evidence and explicit Operator acceptance.
## 7. Verification evidence available at start
B4.3 PR #100 final PR head 2f4135a7affe38cf1b564409e5b1b077ba4cb3ae passed exact-head hosted CI run #932 and was merged to main at f9c585c174799cf26fc0d7bf8ed57a8396e2b5aa.
The Operator additionally ran local verification on the exact merged-main documentation tree 5f37927ff33d9e740c0ff56512d261dace36ab67: fresh migration/single-head checks, 232 focused B4.3 tests, Ruff, Mypy (38 source files), and the full suite (949 passed, 113 warnings in 211.03s). Pytest exit code was 0; the disposable PostgreSQL container was removed. This is supplemental B4.3 verification evidence, not B4.4 hosted exact-head evidence.
**B4.4 is started.** The gaps above remain open; no B4.4 regression implementation, hosted verification, or closeout is claimed yet.