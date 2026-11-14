# R7-B B5.4.0 — Baseline and Coverage Audit

**Audit date:** 2026-11-14  
**Status:** Remote source/test and fixture inventory complete. Read-only audit only; no source, tests, migrations, schemas, dependencies, or runtime files changed. Local Operator worktree/database preflight remains unverified.  
**Implementation branch:** `r7b-b5-4-implementation-20261114`  
**Exact implementation base:** `eef7815db922984c798e95ebd91d6d5c6c87e3b0` (squash merge of documentation PR #121)  
**Planning PR:** [#121](https://github.com/abtn/Watch-Architecture-Rev2/pull/121), merged at `eef7815db922984c798e95ebd91d6d5c6c87e3b0).  
**Hosted verification:** [CI run #1155](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/43634784291) passed on reconciled docs head `64682393320b3f66f7fdde1392498c9cf31ab60b`. The code/test tree was unchanged from merged `main`; CI completed fresh PostgreSQL migration, single-head check, Ruff, Mypy, patch check, full test suite, and disposable-container cleanup.

## 1. Authority and scope

The Operator authorized B5.4.0 on 2026-11-14 for:
- Creating the implementation branch from the then-current verified `main`.
- Read-only inspection of the accepted lifecycle code paths, tests, and fixtures.
- Recording the baseline, coverage map, and bounded follow-up proposal.

This checkpoint does **not** authorize source/test edits, migrations, schema/model changes, dependencies, runtime changes, or implementation of B5.4.1–B5.4.5. Any production defect or need to change an accepted B0/B4 invariant is a stop-and-return condition. B6 and R7-C remain unauthorized. B5.4 is not an automatic R8 prerequisite.

## 2. Exact baseline and repository facts

| Item | Verified result |
|---|---|
| Repository | `abtn/Watch-Architecture-Rev2` |
| `main` at branch creation | `eef7815db922984c798e95ebd91d6d5c6c87e3b0` |
| Implementation branch | `r7b-b5-4-implementation-20261114` |
| Branch start SHA | `eef7815db922984c798e95ebd91d6d5c6c87e3b0` |
| PR #121 | Closed/merged; squash merge `eef7815db922984c798e95ebd91d6d5c6c87e3b0` |
| PR #121 changed files | Seven Markdown files only |
| Latest PR #121 hosted CI | Run #1155 passed on documentation head `64682393320b3f66f7fdde1392498c9cf31ab60b` |
| Migration graph | 18 version files; linear single tip `0018_r7b_lifecycle_review_date`, down from `0017_r7b_assessments` |
| Local worktree / origin / local branch | Not observable from this remote audit; Operator-local preflight remains pending |
| Persistent database | Not accessed |

The branch was created only after verifying that PR #121 had merged and that remote `main` pointed to the merge commit above. The branch initially pointed to the same SHA. The audit does not claim that the Operator's local checkout is clean or synchronized.

## 3. Accepted constraints rechecked

The audit treated the following sources as normative:
- [ADR-0032](../decisions/ADR-0032-knowledge-quality-evaluation-and-lifecycle.md), especially the reciprocal candidate relationship, candidate eligibility, visibility, retirement, and Team-scoped graph-lock rules.
- [B4.0 architecture decision](r7-b-b4-0-architecture-decision.md): reuse the existing `propose_learning_change` Task, assessment, trusted Operator approval, TaskRuntime, and canonical `LearningCommitService`; no parallel lifecycle workflow.
- [B5 implementation plan](r7-b-b5-implementation-plan.md): accepted create-with-successor, retirement, supersede, replay, history, and publication contracts.
- [B5.4 integrated regression plan](r7-b-b5-4-integrated-regression-plan.md): integrated regression only; prefer existing application entry points and test-only work.

The core invariants retained for the coverage review:
- Canonical KnowledgeItem writes stay on the proposal → deterministic validation/assessment → trusted Operator approval → `LearningCommitService` → TaskRuntime path.
- Candidate `supersedes_item_id` is immutable. Only accepted supersede writes predecessor `superseded_by_id`; supersede mutates the predecessor only.
- The accepted candidate remains unchanged by supersede.
- Candidate and predecessor are not simultaneously visible. Projection, retrieval, and Context use reciprocal canonical state and D7 eligibility.
- Graph operations retain Team-first locking and deterministic affected-item lock ordering.
- Replay returns the original durable decision without duplicate canonical side effects or overwriting later history.
- No second write path, Task type/runtime, scheduler, dispatcher, authentication boundary, migration, or schema/model change is introduced by B5.4.

## 4. Existing implementation and test inventory

### Application paths inspected

| Concern | Existing source path | Role in the contract |
|---|---|---|
| Proposal and lifecycle assessment | `core/knowledge_lifecycle.py`, `core/knowledge_lifecycle_tasks.py` | Operation-specific lifecycle proposals, deterministic eligibility findings, recorded assessment, Task execution/recovery |
| Revise and revalidate assessment | `core/knowledge_quality.py`, `core/knowledge_revalidation.py`, `core/knowledge_revalidation_tasks.py` | Existing quality and revalidation assessment boundaries |
| Approval binding | `core/knowledge_approval.py`, `core/operator_approval.py` | Immutable target/successor evidence and trusted host Operator decision |
| Canonical commit and replay | `core/learning_commit.py` | `LearningCommitService.decide` and canonical decision replay |
| History | `core/learning_history.py` | Snapshot validation, pointer-chain reconstruction, transition and reciprocal-link checks |
| Projection and retrieval | `core/knowledge_index.py` | Canonical indexing, reciprocal supersession publication, D7 retrieval gates |
| Context | `core/context_assembly.py` | Final canonical passage validation and immutable Context snapshot |
| Task runtime | `core/task_runtime.py` | Existing admission, attempt fencing, finalization, Outcome, retry, and recovery behavior |

### Existing focused and integrated proofs

| Required area | Existing evidence found | Coverage observation |
|---|---|---|
| Proposal/assessment binding | `tests/test_knowledge_lifecycle.py`; `tests/test_knowledge_approval.py`; `tests/test_knowledge_revalidation.py` | Proposal shape, D7 findings, exact target/successor snapshot, provenance, assessment and drift rejection already have focused coverage |
| Create-with-successor | `tests/test_experience_distiller.py::test_create_with_successor_commits_hidden_candidate_through_existing_path` (around line 6488); `test_concurrent_create_with_successor_commits_only_one_candidate` (around line 6650) | Existing path, immutable predecessor link, candidate hidden before reciprocal commit, exact binding, immediate replay, and single-winner concurrency are covered |
| Review and revise | `tests/test_experience_distiller.py::test_accepted_revise_preserves_needs_review_and_retrieval_ineligibility` (around line 10536); `test_revise_then_revalidate_rejects_stale_pre_revision_assessment` (around line 2687) | Scheduled review to `needs_review`, accepted revise preserving that state, history and retrieval behavior, and stale pre-revision assessment rejection are covered |
| Revalidate | `tests/test_experience_distiller.py::test_original_revalidation_approval_replays_after_later_history_transition` (around line 3304) | Revalidation followed by a later accepted revise; replay returns the original Task/change/Outcome identity and preserves later canonical state |
| Create replay after later transition | `tests/test_experience_distiller.py::test_original_create_approval_replays_after_later_history_transition` (around line 8243) | Ordinary root-create approval replay after later revision is covered |
| Retire and candidate replacement | `tests/test_experience_distiller.py::test_b5_2_integrated_retirement_candidate_lifecycle_sequences` (around line 10847) | Ordinary create→retire, candidate create→retire→replacement, predecessor retirement without candidate mutation, history, replay and side-effect counts are integrated |
| Retire races and replay | `tests/test_experience_distiller.py` tests around lines 11401–12963 | Concurrent retirement, predecessor retirement/candidate creation race, candidate cancellation/replacement races, stale-binding rejection, idempotency conflicts, and later-history retirement replay are covered |
| Supersede commit | `tests/test_experience_distiller.py::test_b5_3_supersede_proposal_assessment_and_atomic_predecessor_commit` (around line 12964) | Existing trusted proposal/assessment/approval/canonical commit; predecessor-only mutation; candidate state unchanged; history and replay |
| Supersede visibility | `tests/test_experience_distiller.py::test_b5_3_4_reciprocal_publication_is_shared_by_projection_retrieval_and_context` (around line 13224); `tests/test_team_experience.py` | Pending/committed visibility, predecessor exclusion, candidate eligibility, projection/retrieval/Context agreement and tamper rejection |
| Supersede concurrency and later replay | `tests/test_experience_distiller.py` tests around lines 13545–14245 | Competing approvals, supersede-vs-retire race, candidate-retire-vs-supersede race, accepted replay after successor retirement, rejected replay after later acceptance, and stale replay are covered |
| History reconstruction | `tests/test_learning_history.py`; `tests/test_team_experience.py` | Pointer chains, immutable snapshots, legal transitions, reciprocal same-Team relations, and canonical current-state checks are covered |
| Task finalization/recovery | `tests/test_task_lifecycle_finalize.py`, `tests/test_task_lifecycle_recovery.py`, `tests/test_task_runtime.py` | Terminal Outcome/Event atomicity, identical replay, rollback, concurrent finalization/recovery and obsolete-recovery fencing have focused coverage |
| Migration contracts | `tests/test_r7b_assessment_migration.py`, `tests/test_r7b_history_migration.py`, `tests/test_team_experience_projection_migration.py` | History/assessment constraints, immutability, invalid migration inputs, downgrade guards and migration behavior have focused coverage |

## 5. B5.4 coverage matrix and findings

| B5.4 scenario | Existing proof | B5.4.0 disposition |
|---|---|---|
| Full `create → review → revise → revalidate → create-with-successor → supersede` chain | Separate create/review/revise/revalidate tests; create-with-successor and supersede tests | **Integration gap:** no identified single cohesive end-to-end test (or minimal explicitly linked test set) proves the entire six-transition history through the existing trusted entry points |
| Candidate cancellation and replacement | B5.2 integrated retirement/candidate lifecycle sequence and concurrency tests | Existing substantial proof; reuse and add only a specific missing assertion if later review finds one |
| Terminal `create → retire` without successor | B5.2 integrated retirement/candidate lifecycle sequence | Existing proof; reuse rather than duplicate |
| Replay of original create approval after later history | Original root-create approval replay after later revision | Covered for ordinary root create |
| Replay of original revise approval after later history | Revise proposal/approval immediate replay and accepted revise state/history tests | **Replay gap:** no identified test replays an accepted revise approval after a subsequent accepted lifecycle transition and verifies original IDs/timestamp/Outcome plus preservation of current later state |
| Replay of original revalidation approval after later history | Original revalidation approval replay after later revise | Covered |
| Replay of original retire approval after later history | B5.2 integrated retirement replay and specialized rejected/stale replay tests | Covered by existing focused proofs |
| Replay of original supersede approval after later history | Original accepted supersede replay after successor retirement; rejected/stale replay cases | Covered by existing focused proofs |
| Projection/retrieval/Context reciprocity and D7 | B5.3.4 integrated publication test and Team Experience/Context tests | Covered; reuse existing path and assertions |
| No duplicate side effects / races | B5.2/B5.3 integrated race/replay tests and TaskRuntime finalization/recovery tests | Covered across focused proofs; do not duplicate without a specific missing scenario |

### Interpretation point to preserve

B5.4.4 lists “Create” without distinguishing ordinary root creation from create-with-successor. Current evidence proves later-history replay for ordinary root creation and immediate replay for create-with-successor. Before treating the candidate-creation replay as an additional required case, the Operator should decide whether “Create” in B5.4.4 means root create only or every accepted create variant. Do not silently expand the frozen acceptance matrix.

## 6. B5.4.0 conclusion and bounded proposal

**Remote audit result: PASS.** The inspected architecture already provides the needed application paths. No production defect, missing schema capability, migration requirement, second write path, new Task/runtime, dispatcher, scheduler, or authentication boundary was identified by this read-only inventory.

The smallest proposed B5.4 implementation surface, subject to separate B5.4.1/B5.4.4 authorization, is test-only:
1. Add one cohesive end-to-end test (or minimal explicitly linked test set) for the full create → review → revise → revalidate → create-with-successor → supersede history, using existing proposal, assessment, approval, commit, TaskRuntime, history, retrieval, and Context entry points. Do not hand-fabricate canonical lifecycle rows.
2. Add one later-history replay test for accepted revise approval after a subsequent accepted transition. Assert original Task, LearningChange, decision, Operator attribution, commit timestamp and Outcome identity; assert no duplicate Events/Outcomes/LearningChanges/snapshots/pointer writes and that later canonical state is unchanged.
3. Reuse existing B5.2 candidate replacement and terminal retirement proofs and B5.3 supersede publication/concurrency/replay proofs. Add only assertions that the eventual coverage review identifies as genuinely missing.
4. Resolve the create-with-successor replay interpretation before adding it to the mandatory B5.4.4 matrix.

No source/test change is made or authorized by this audit. If the end-to-end proof reveals a production defect or requires changes to an accepted invariant, migration, schema/model, runtime, dispatcher, scheduler, authentication boundary, or canonical write path, stop and return for a separate Operator decision.

## 7. Database and local verification boundary

The remote source configuration establishes:
- `tests/_database_config.py::resolve_test_database_url` requires an explicit `TEST_DATABASE_URL`, PostgreSQL backend, and named non-`watch` database. It does not fall back to `DATABASE_URL`.
- `tests/conftest.py` obtains its database URL through that resolver.
- `migrations/env.py` reads `DATABASE_URL` and otherwise has a default URL for a database named `watch`. Future local migration/test commands must explicitly set **both** `DATABASE_URL` and `TEST_DATABASE_URL` to the same uniquely named disposable PostgreSQL database, preserve and restore any prior values, and never use the persistent `watch` database.
- The repository migration graph has one linear head, `0018_r7b_lifecycle_review_date`, as confirmed by the migration files and hosted CI migration/head steps.

No local Windows checkout, local Git worktree, Docker daemon, local environment variables, or database was accessed in this remote audit. The Operator-local branch sync/clean-tree preflight and any local database-configuration check remain pending. No local test result is claimed.

## 8. Exit and next gate

**B5.4.0 remote audit: COMPLETE.** The implementation branch starts from the verified merged `main` SHA above. The audit found two bounded coverage gaps: the complete six-transition composition and accepted revise replay after later history. The create-with-successor replay scope requires clarification before inclusion as a mandatory case.

**Next decision:** Review this audit and explicitly authorize B5.4.1 (and, when appropriate, the revise replay addition within B5.4.4) before source/test changes. B5.4.0 does not authorize implementation. B5.4.2–B5.4.5, B6, and R7-C remain separately gated.

