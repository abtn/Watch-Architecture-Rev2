# R6-F Checkpoint 3 — Operator Task and Trusted Identity Audit

**Audit status:** completed from the repository at Checkpoint 2 merge commit `61be8db75b6bd4e23fcc91ef00f1a8f0a833dde0` and the documentation-only Checkpoint 3 branch.

**Audit date:** 2026-11-01.

**Implementation status:** no application code or migration changed by this audit.
**Conclusion:** the repository has a usable Task lifecycle service, but does not currently provide a production creation/caller path for an Operator approval Task or a trusted Operator identity boundary. Checkpoint 3 implementation must not claim a production approval route until these are supplied or explicitly built as a narrow application adapter.

## 1. Executive findings

| Area | Finding | Status |
|---|---|---|
| Manual Operator Task creation | ADR-0011 and `docs/tasks.md` describe API/CLI-created manual Tasks, but this repository has no API/CLI package or generic production Task-creation service. The only production `Task(...)` constructor found in `core/` is Plan materialization in `core/plans.py`; it creates Plan-linked Action Tasks with `allowed_writes=["Signal"]`. | **Missing** |
| Task admission | `TaskRuntime.admit(task_id)` can admit a pre-existing pending same-Team Task after policy, status, attempt, prerequisite, quota, and budget checks. It does not create the Task and does not establish the actor who requested it. | **Available, but only after creation** |
| Approval Task execution | `TaskDispatcher` intentionally supports only `ingest_source`. It rejects other Task types before admission. No Operator approval executor/caller is present. | **Missing** |
| Approval finalization | `TaskRuntime` has a typed result only for `success_learning_change_proposed`; its LearningChange validator is specific to `propose_learning_change`. There are no accepted/rejected approval result categories or matching validation. | **Missing** |
| Trusted Operator identity | No User/Operator principal model, auth middleware, API, or CLI identity adapter was found. Existing `operator_id` use is a caller-supplied string, not an authenticated principal. | **Missing** |
| Durable approval intent/replay | The Task ORM has no `input_refs`, approval target field, or manual-request idempotency key. The approval Task therefore needs a durable association to its LearningChange and a stable replay identity. | **Unresolved** |
| Operator Task timing/recovery | TaskRuntime requires a positive `deadline_seconds` value in every Task budget, while the documented approval Task has no enforced deadline. Interrupted-task recovery scans all running Tasks and applies a 60-second stale threshold. | **Contract mismatch to resolve** |

## 2. Task creation: design exists, implementation does not

**Normative intent.** ADR-0011 says Operator actions such as `approve_learning_change` are manual Tasks created by an API, with Operator identity recorded in Event payloads. `docs/tasks.md` likewise lists API/CLI as the creation source for manual Operator Tasks.

**Repository reality.**

- The repository tree at the audited commit contains `core/`, `migrations/`, `tests/`, and documentation, but no `api/`, `app/`, `web/`, or `cli/` package.
- `pyproject.toml` declares SQLAlchemy, Alembic, psycopg, and Pydantic; no HTTP framework, authentication dependency, or CLI framework is configured.
- The only production `Task(...)` constructor found in `core/` is `PlanService` materialization in `core/plans.py`. It creates pending Plan Action Tasks with `allowed_writes=["Signal"]` and the ingestion budget. It is not a manual Task factory.
- The ORM `Task` model stores task type, Team, status, policy version, scopes, budget, and optional Objective/Plan links. It does not store the documented `input_refs`, an Operator identity, the approval target, or a general request idempotency key.

**Consequence.** There is currently no production operation that creates a pending `approve_learning_change` Task, durably identifies which LearningChange it is deciding, and attributes the request to a trusted Operator. Tests that insert a Task row directly prove service behavior under fixtures; they do not provide this production caller.

## 3. What the existing TaskRuntime can and cannot do

### Available behavior

`TaskRuntime.admit(task_id)` is an appropriate lifecycle boundary **after** an authorized caller has created the pending Task. It locks the Task and checks pending status, maximum starts, Plan prerequisites, active Team (with the documented setup exceptions), matching TeamPolicy version, budget shape, and configured daily Task-start quota. It then atomically increments the attempt, changes `pending → running`, and records `task_started`.

The approval operation should reuse this lifecycle authority. It must not set Task status, attempt count, or lifecycle Events directly.

### Important constraints

1. **Task-type and write-scope validation are operation-specific.** Admission is generic; it does not establish that a Task's `allowed_writes` match its `task_type`. The approval service must require the exact `approve_learning_change` type, same Team, running current attempt, matching policy version, and exactly the authorized KnowledgeItem/LearningChange write set. It must reject extra grants and all TeamPolicy writes.
2. **The current finalizer cannot report an approval decision.** `TerminalObservation` currently allows `success_learning_change_proposed`, not accepted/rejected approval results. The only LearningChange-specific finalizer validator requires `task_type="propose_learning_change"`, exact `allowed_writes=["LearningChange"]`, a still-proposed create operation, the proposal Event, and reconciled distillation cost. A separate approval validator/result path is required.
3. **A rejection is a successfully executed Operator decision.** The approval Task should complete as a successful Task with a typed rejected-decision result; it must not be conflated with Task execution failure. The LearningChange status itself remains `rejected`.
4. **The existing transaction pattern is reusable.** Ingestion commits its business result independently and atomically, then TaskRuntime finalizes the Task/Outcome. A crash between those commits is handled by replaying the existing business result. Checkpoint 3 should follow the same pattern: atomically commit LearningChange + KnowledgeItem (if accepted) + one decision Event, then finalize the approval Task. Replaying the same Task must return the recorded decision and allow TaskRuntime finalization without creating another version.
5. **The dispatcher is not the Operator runner.** `TaskDispatcher` filters for `ingest_source` and rejects every other type. Do not broaden it into a general dispatcher for this purpose. The approval should be a synchronous application/API operation that calls the existing TaskRuntime and the narrow learning commit service.

## 4. Trusted identity: existing fields are attribution, not authentication

- `ObjectiveService.create` and `ObjectiveService.transition` accept `operator_id: str | None` from their caller and copy it into Event payloads. They do not resolve, authenticate, or authorize that identity. Tests pass literal strings such as `"operator-1"`; this proves payload attribution only.
- `LearningChange.operator_id` is a nullable `String(255)`. Database constraints require a non-empty value for accepted/rejected changes, but there is no User/Operator foreign key or issuer/subject relation.
- `LearningChange.committed_by_task_id` has a composite same-Team foreign key to Task. That protects Team consistency; it does not enforce that the referenced Task has type `approve_learning_change`, was running at commit time, or was admitted through TaskRuntime.
- No auth package, principal type, session/token middleware, or API/CLI boundary exists in this repository.

**Required trust contract.** The learning service must not accept a bare `operator_id` as proof of authority. A trusted host application boundary must authenticate the caller and pass a stable principal subject to the service through an explicit trusted-caller interface. The service persists that canonical subject in `LearningChange.operator_id` and the decision Event. A test fake may exercise this boundary in unit tests, but must not be described as a production authentication provider. Building a general authentication system is not implied by Checkpoint 3.

## 5. Durable Task intent and replay requirement

The ORM Task has no input-reference or approval-target field. The manual approval request therefore needs a durable, same-Team link between its Task and the `learning_change_id` it is deciding. Passing the ID only as transient API request data is insufficient for restart/retry recovery.

The API caller must also avoid creating a new approval Task every time the same approval request is retried. The same decision must be recoverable against the original Task identity, or the request must have a durable idempotency key that resolves to that Task. The current Task schema has no generic manual-request idempotency key. The audit does not prescribe a new column: a Task-attributed creation/request Event with a validated, uniqueness-enforced key may suffice, or a minimal schema addition may be justified after inspecting the existing Event constraints. Do not silently assume a request body is durable.

## 6. Deadline and interrupted-task recovery mismatch

- The documented `approve_learning_change` budget has zero tool calls and zero model cost, with no enforced deadline.
- `TaskRuntime.admit` currently requires every Task budget to include a positive integer `deadline_seconds`; it rejects a missing, null, or zero value.
- `TaskRuntime.recover_interrupted` discovers every `running` Task, not only ingestion Tasks, and treats a current attempt older than 60 seconds as interrupted. `TaskDispatcher` exposes `recover_interrupted()` as its startup recovery entrypoint; when host startup calls it, the global scan runs.
- A manual approval must not wait for a human inside a running Task. The intended action is initiated only after the Operator has decided, then runs synchronously. Nevertheless, a crash after the canonical decision Event but before TaskRuntime finalization requires same-Task replay. If generic recovery has returned that Task to pending, the API caller must re-admit the same Task and replay the decision. The ingestion dispatcher will not execute it.

Before implementation, decide whether the approval path is strictly short-lived and compatible with the 60-second global recovery, or whether a narrowly scoped recovery-policy change is needed. Also reconcile the no-deadline Task specification with admission's positive `deadline_seconds` requirement. Do not invent a sentinel value or silently impose a timeout.

## 7. Recommended narrow execution contract

Subject to the missing trusted caller being identified, the safest in-repository service sequence is:

1. The host API/CLI authenticates the Operator. It supplies a stable principal subject through the trusted application boundary; no model or request-body field can choose that identity.
2. The application creates one pending `approve_learning_change` Task for the same Team and current TeamPolicy version, with no Plan/Action link, an exact KnowledgeItem + LearningChange write grant, zero tools, zero model cost, and durable target/idempotency reference.
3. The same application flow calls `TaskRuntime.admit(task_id)`.
4. A narrow learning commit service locks the Task and LearningChange, verifies the trusted principal, exact Task/type/scope/policy/team, and revalidates the complete evidence basis/hash, all referenced records, target operation/version/status, and replay/concurrency preconditions.
5. Acceptance atomically writes the canonical KnowledgeItem state/version, LearningChange accepted disposition/history/operator/task metadata, and one decision Event. Rejection atomically writes the LearningChange rejected disposition/reason/operator/task metadata and one decision Event without changing/creating a KnowledgeItem. No TeamPolicy write is permitted.
6. The caller invokes `TaskRuntime.finalize` with a typed accepted/rejected decision result. Runtime validation proves the same Task/Team, committed_by_task_id, operator identity, decision Event, and final LearningChange disposition. Same-Task replay returns the existing decision and does not duplicate a KnowledgeItem version.
7. The API returns the durable decision. It does not add this Task to `TaskDispatcher` or wait for a later worker.

This is a core-service/caller contract, not evidence that the external API exists. Do not expose it as a production-authenticated route until the trusted caller is connected.

## 8. Decisions required before Checkpoint 3 implementation

| Decision | Current audit result | Required closure |
|---|---|---|
| Trusted caller location | No API/CLI/auth adapter exists in this repository; ADR-0011 describes one conceptually. | Identify the external authenticated application boundary, or explicitly authorize a thin in-repository caller adapter whose identity is still supplied by a trusted host. |
| Manual Task creator | No production manual Task factory exists. | Define the single creation operation and its transaction with target reference and idempotency protection. |
| Durable approval target | Task ORM lacks input_refs/learning_change_id. | Pin a Task-attributed creation Event or minimal schema representation, plus same-Team and replay checks. |
| TaskRuntime decision result | Only distiller proposal result exists. | Add typed accepted/rejected approval result categories and strict finalizer validation. |
| Task execution/recovery | Dispatcher supports ingestion only; recovery scans all running Tasks after 60 seconds. | Keep Operator execution synchronous; test crash/replay and resolve the deadline/recovery contract. |
| Revision/retirement proposal source | ExperienceDistiller currently emits create only. | Retain D10: do not add a seed/bypass path; decide reachability before claiming full create/revise/retire acceptance. |
| Review-date semantics | `review_after` policy is not pinned. | Retain D7; no expiry/retrieval claim in Checkpoint 3. |

## 9. Audit conclusion and next action

**The audit is complete; production approval implementation is not yet unblocked.** The TaskRuntime can be reused, but Task creation and trusted Operator identity must come from a real authenticated application boundary. The codebase currently contains only the domain core, not that boundary.

The next required decision is whether the trusted API/CLI/authentication adapter already exists outside this repository and can call the core, or whether Checkpoint 3 should include a thin in-repository manual-task application adapter. Either option must preserve the trust boundary: the core must never treat an arbitrary string as proof of Operator identity.

No application code, schema migration, provider configuration, TeamPolicy grant, dispatcher extension, or Checkpoint 4 work is authorized by this audit.
