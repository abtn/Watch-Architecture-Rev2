# R7-B B5.3.0 — Baseline and Code-Path Audit

**Audit date:** 2026-11-14
**Status:** The B5.3.0 remote baseline/code-path audit and B5.3 implementation are complete. B5.3 was formally accepted/closed by the Operator and squash-merged in PR #120 at `7fbac0656f9eda9983a73dfe84fae859fd7e98f9`. Exact implementation/test and documentation-inclusive hosted verification passed. See the final closure record below.
**Implementation PR:** [#120](https://github.com/abtn/Watch-Architecture-Rev2/pull/120), draft at this closeout checkpoint.
**Scope:** B5.3 Supersede only. No B5.4, B6, R7-C, or R8 work.

## 1. Exact baseline

- Repository: `abtn/Watch-Architecture-Rev2`
- Base branch: `main`
- Exact remote `main` SHA: `cde40b2c9edb17a693eff43e7e1158515302cd69`
- This SHA is the squash merge of documentation PR [#119](https://github.com/abtn/Watch-Architecture-Rev2/pull/119).
- The implementation branch was created directly from that SHA.
- A remote compare confirmed `main` was identical to the merge SHA when the branch was created.
- The B5 plan records `0018_r7b_lifecycle_review_date` as the expected Alembic head. This audit did not run Alembic or access the Operator's local checkout; the local single-head check is still required.

No local tests, migrations, Ruff, Mypy, or database checks were run as part of this remote audit.

**Subsequent Operator-local verification record (2026-11-14):** The user ran the implementation-branch sync/test script from the expected local branch and starting HEAD `7ae56f92646dd2800ff152ff5e4024fa828d2e91`. It verified repository root, branch, origin, clean worktree, fetched the exact target, fast-forwarded to `3f3c4c26ca6fb771bd9ff1f31653622f68179e69`, started disposable PostgreSQL on a dynamic localhost port, upgraded to `0018_r7b_lifecycle_review_date`, and passed Ruff, Mypy, `git diff --check`, and the full suite (**987 passed, 113 warnings in 377.50s**). The script restored `DATABASE_URL` and `TEST_DATABASE_URL` and removed its disposable container. Exact-head hosted CI passed in [run #43607884811](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/43607884811) (run #1109). This is implementation-branch verification, not a separately recorded local checkout of `main`.

## 2. Existing code and test coverage

| Concern | Existing implementation | Current proof and boundary |
|---|---|---|
| Lifecycle proposal validation | `core/knowledge_lifecycle.py`: `_validate_proposed_state`, `_proposal_context`, `_successor_binding`, `build_lifecycle_task_request` | Supersede proposal shape and exact predecessor/successor snapshot checks already exist. The validator binds Team, pointers, versions, semantic hashes, full-state hashes, reciprocal relation, and review date. |
| Lifecycle assessment | `KnowledgeLifecycleAssessmentService`, `KnowledgeLifecycleAssessmentTaskRunner`, and TaskRuntime lifecycle-assessment validation | Supersede assessment creation, deterministic findings, immutable record, Task-attributed Event, replay, and successor binding are implemented. The assessment does not mutate canonical KnowledgeItems. |
| Assessment/approval binding | `core/knowledge_approval.py::build_approval_binding`; `core/operator_approval.py` request schema and fingerprint | The schema accepts the supersede operation and the complete successor binding. The binding builder can bind the recorded lifecycle assessment and successor snapshot. |
| Proposal production | `ExperienceDistiller.propose_retirement`; `OperatorApplicationAdapter.propose_retirement` | A host-authenticated retirement proposal exists. There is no corresponding production supersede proposal entry point. The ordinary `propose_learning_change` Task is the intended shared Task path. |
| Operation admission | `core/operator_approval.py::is_supported_learning_change`; `OperatorApplicationAdapter.request_learning_change_decision` | The supported-operation predicate currently admits create, revise, revalidate, and retire—not supersede. The adapter therefore rejects supersede before creating an approval Task. |
| Approval Task lifecycle | `core/task_runtime.py::_validate_operator_admission`, `_validate_learning_change_decision_result`, and `_validate_learning_change_result` | Lifecycle assessment Tasks understand supersede. Operator approval admission, decision finalization/replay, and proposal Task finalization still have retire-only or four-operation allowlists. |
| Canonical commit | `core/learning_commit.py::LearningCommitService.decide` and `_replay_decision` | Create, revise, revalidate, and retire are implemented. There is no supersede commit branch or supersede replay contract. Retirement already supplies the nearest predecessor-only lifecycle commit pattern. |
| History and graph integrity | `core/learning_history.py::_validate_transition`, `_validate_live_supersession_links`; `core/models.py` | Supersede history semantics, reciprocal same-Team links, cycle detection, self-link constraints, and the relevant model fields/constraints already exist. |
| Retrieval and Context | `core/knowledge_index.py::_accepted_learning_change_is_canonical`, `_supersession_publication_is_visible`; `core/context_assembly.py::_validate_team_experience_passage` | The candidate is hidden until the predecessor is retired with the reciprocal pointer and accepted supersede LearningChange. A predecessor with a successor is hidden. Retrieval uses a repeatable-read transaction; final Context persistence locks the Team before rechecking passages, serializing against Team-locked graph commits. |
| Projection | `TeamExperienceIndexer.index_knowledge_item` | Publication rechecks canonical current state and review eligibility under the item lock. The existing reciprocal visibility check remains the consumer gate; no synchronous reindexing shortcut is needed for supersede. |

### Existing focused tests

- `tests/test_knowledge_lifecycle.py`: supersede proposal shape, deterministic eligibility findings, complete successor binding, cross-Team/wrong-predecessor rejection, and stale successor binding.
- `tests/test_experience_distiller.py::test_b37_supersede_assessment_round_trips_successor_and_rechecks_approval_binding`: manually constructs a supersede LearningChange and proves assessment recording, immutable evidence, approval-binding reconstruction, and drift rejection. It proves assessment only; it does not commit supersession.
- `tests/test_knowledge_approval.py::test_lifecycle_supersede_binding_includes_full_successor_snapshot_and_provenance`: verifies the approval binding shape.
- `tests/test_operator_approval.py::test_schema_v3_supersede_successor_is_part_of_request_fingerprint`: verifies successor state participates in the immutable request fingerprint.
- `tests/test_team_experience.py`: existing reciprocal-visibility checks include final Context validation.
- B5.2 retirement integration tests cover retirement races, stale bindings, and replay, but do not prove a supersede commit.

## 3. Confirmed implementation gap

The missing capability is not the lifecycle schema, assessment service, graph representation, or consumer visibility gate. It is the end-to-end supersede proposal and trusted canonical decision path.

The smallest implementation surface is:

1. Add a host-authenticated supersede proposal entry point using the existing `propose_learning_change` Task and `LearningChange` record. Bind the exact predecessor and already accepted candidate; do not create or mutate the candidate.
2. Extend the existing TaskRuntime proposal validation/finalization contract for the supersede-specific proposal shape, source Event, terminal Outcome, provenance, and idempotent replay.
3. Admit supersede through the existing supported-operation predicate and trusted Operator approval Task. Reuse the existing assessment and successor binding; do not create a second approval path.
4. Extend approval Task admission, finalization, recovery, and replay to validate the supersede assessment and complete two-item binding.
5. Add one supersede branch to `LearningCommitService`: lock the Team first, then lock predecessor and candidate KnowledgeItems in ascending UUID order; recheck both exact snapshots, Team ownership, reciprocal relation, candidate active status and future review date, current pointers, and assessment/approval binding under lock.
6. In that same transaction, update only the predecessor to `retired`, set `superseded_by_id`, advance its current LearningChange pointer, and persist the required immutable LearningChange/Event state. The candidate row must remain byte-for-byte unchanged.
7. Extend decision replay to return the original result without a second pointer advance or duplicate Event/Outcome/history writes.
8. Add integrated PostgreSQL tests for success, rejection, stale bindings at admission/commit, concurrency, rollback, replay after later lifecycle activity, candidate immutability, and retrieval/Context visibility.

## 4. Specific points to settle in B5.3.1

- `build_approval_binding` currently rejects a supersede approval request when `require_assessment=False`; retirement is the only lifecycle operation exempted from that rule. This means a supersede rejection request currently cannot be created without a recorded assessment. Confirm and test whether that is intentional. The default should not be changed silently; acceptance must remain assessment-bound.
- The lifecycle assessment path currently takes the Team lock and then reads/locks the predecessor before the successor. The canonical supersede commit must follow the frozen Team-first, ascending-UUID item-lock order. Do not copy the assessment lock order into the two-item commit.
- Preserve the existing lock order and exact binding contracts. If a new schema/migration, Task type, runtime, dispatcher, scheduler, authentication boundary, retrieval redesign, or other frozen architecture change appears necessary, stop and return for a decision.

## 5. Explicit non-goals

- No schema or migration change is currently indicated by the inspected model, history, assessment, and projection contracts.
- No new Task type, TaskRuntime, dispatcher, scheduler, public API, or Watch-owned authentication.
- No second canonical write path or direct worker/model/assessment write to KnowledgeItem.
- No candidate mutation, candidate rewrite, synchronous indexing shortcut, or Context manifest redesign.
- No B5.4 integrated closeout, B6, R7-C, or R8 implementation.

## 6. B5.3.0 exit status

**Remote code-path audit: PASS.** The existing architecture supported the intended operation and the smallest missing implementation surface was identified. This is the B5.3.0 baseline result, not the B5.3 final acceptance decision.

**Initial local preflight at the B5.3.0 audit checkpoint: PENDING (historical; superseded).** The original audit correctly required a clean, exact-main preflight before implementation. That checkpoint was subsequently superseded: the implementation branch was created from the exact merged base `cde40b2c9edb17a693eff43e7e1158515302cd69`, and the Operator-local B5.3.3 verification and final B5.3.6 verification are recorded below.

## 7. B5.3 implementation and final verification closeout — 2026-11-14

**Final PR/implementation head:** `6821dba35da3fecd1540483f2e30cbff7aebcf15` on `r7b-b5-3-implementation-20261114`.

**Operator-local exact-head verification:** `uv sync --locked`; fresh disposable PostgreSQL migration to the single Alembic head `0018_r7b_lifecycle_review_date`; Ruff; Mypy (38 source files); and full suite (**996 passed, 113 warnings in 407.23s**) all passed. Warnings are Alembic `path_separator` deprecations. The disposable container was removed, `DATABASE_URL` and `TEST_DATABASE_URL` were restored, and the script confirmed the exact branch/HEAD and clean worktree.

**Hosted CI:** exact final implementation/test head passed [run #1146](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/43618529970).

**Implementation/scope review:** no blocking code findings. The proposal, lifecycle assessment, trusted Operator approval, TaskRuntime, and canonical LearningCommit paths are reused. The canonical commit locks the Team first, then both KnowledgeItems in ascending UUID order, rechecks exact predecessor/candidate bindings, and mutates only the predecessor. The accepted candidate row and immutable `supersedes_item_id` remain unchanged. Reciprocal publication checks and D7 eligibility remain enforced. No migration, schema change, second write path, new Task/runtime/dispatcher/scheduler/authentication boundary, or B5.4/B6/R7-C/R8 scope was introduced.

**Test-only isolation corrections:** distillation LearningChange absence assertions are scoped to the test's `distillation_task_id`; ingestion Event-count assertions are scoped to the proposal's `task_id`. This avoids false failures from unrelated stale records in a reused local test database without weakening production behavior.

**Disposition:** B5.3 is formally accepted and closed by squash-merged PR #120 at `7fbac0656f9eda9983a73dfe84fae859fd7e98f9`. Exact implementation/test head `6821dba35da3fecd1540483f2e30cbff7aebcf15` passed local verification and hosted CI #1146; documentation-inclusive head `2aa6cb09419feb2342dbc1d1ba38b4c1fc1394c1` passed hosted CI #1150. B5.4 planning is documented separately; its implementation remains gated. B6 and R7-C remain unauthorized.
