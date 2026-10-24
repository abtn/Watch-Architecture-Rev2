# R6 Entry Gate and Implementation Traversal

## Status

- **R6-G0: IN PROGRESS.** The operator authorized starting the R6 path and its entry-gate work on 2026-10-24.
- **Implementation slices R6-A onward have not started.** This document is a gate proposal, not permission to silently decide architecture, schema, security, or provider questions.
- Baseline inspected: `main` at `1c7436ef3f7b1db89289af9230f7499aba81c1e0` (2026-10-24).
- R5 remains formally closed. Its durable Plan completion preconditions remain mandatory. ADR-0027 remains Proposed unless separately accepted.

## 1. R6 outcome

Deliver the first testable end-to-end Control loop:

```text
Objective
  → deterministic StateAssessment
  → proposed StrategyProposal
  → application validation and accepted Strategy Event
  → immutable Plan and ordinary Tasks
  → existing Task admission/execution/commit path
  → durable execution result / Outcome
  → new StateAssessment based on the changed durable state
```

The loop must remain recoverable without model transcripts. Workers propose; application code validates and commits. Plan remains immutable intent, while Task/Event/Signal/Outcome records establish what happened. Reactive Tasks still work without an Objective or Plan. There is one Task runtime, not a separate Plan executor or scheduler.

## 2. What exists now, and what does not

### Existing foundations

- `core/objectives.py`: application-controlled Objective creation and lifecycle.
- `core/state_assessment.py`: deterministic, read-only StateAssessment construction.
- `core/strategy.py` and `core/strategy_proposal.py`: proposal validation, accepted-event provenance, and reconstruction. The service validates a supplied proposal; it does not itself call a model to create one.
- `core/plans.py`: Plan materialization, reconstruction, lifecycle, and completion precondition checks.
- `core/task_runtime.py`: atomic pending-to-running admission, policy/quota checks, Task-attributed `task_started` Event, and Plan prerequisite admission. It does not implement successful completion, failure, retry/requeue, or worker dispatch.
- `core/ingestion.py`: bounded proposal validation and atomic ingestion commit for provided fetched bytes. It does not fetch a configured source or run a Task.
- Current ORM classes in `core/models.py` include Team, TeamPolicy, Objective, Plan, PlanAction, Task, Signal, and Event. **There is no Outcome ORM model or Outcome migration**, although `docs/architecture.md` defines the intended Outcome entity.
- The documented K1 boundary deliberately does not implement a source connector, Task dispatcher, scheduler, worker lifecycle, or a model-backed Strategy proposer.

### Consequence

The missing R6 path is not just a missing `running → done` assignment. A real execution path must own admission, bounded handler invocation, success/failure/retry transitions, required Events, idempotent recovery, and the connection between durable execution results and a subsequent assessment.

## 3. R6-G0: decisions required before implementation

These decisions are deliberately left **unresolved** in this proposal. The relevant ADRs stay Proposed until the operator explicitly decides otherwise.

### G0-D1 — ADR-0025 and ADR-0026 status

- **ADR-0025 — Plan Is Derived Execution State:** Proposed.
- **ADR-0026 — Dual-Entry Execution Model:** Proposed.

**Recommendation:** review both against the already implemented R5 contracts, then explicitly accept or revise them before R6-A. Their intended boundaries are essential to R6: Plan is intent, Tasks/Events/Outcomes are execution evidence, reactive and deliberative work converge on ordinary Tasks, and there is no second runtime. This document does not mark either ADR accepted.

### G0-D2 — Owner of Task completion, failure, and retry

Select and document one application-controlled owner for `running → done`, `running → pending` on a retryable failure, and `running → failed` when retries are exhausted. It must record the appropriate Task-attributed Event, set `completed_at` only on terminal success, reject illegal transitions, and make retries safe.

**Recommendation:** extend the existing `TaskRuntime` boundary or add a narrowly scoped lifecycle service used by the same runtime. Keep the state transition and Event atomic; never let the worker write Task status or Event rows directly. Do not add another scheduler or workflow engine. Specify retry ownership and maximum-attempt semantics before coding; do not invent a new Task column unless the chosen policy requires one.

### G0-D3 — First supported worker capability and network boundary

The first end-to-end vertical slice should be the bounded configured-source `ingest_source` Task, because its proposal validation and commit path already exist and the Plan currently materializes that Task type. It should not initially execute arbitrary model-proposed tools or URLs.

Before enabling network access, define and test: permitted URL schemes; validation of configured source URLs and resolved destinations; treatment of loopback, private, link-local, and metadata-service addresses; redirect policy and revalidation; connection/read timeouts; response-size limits; and the behavior for HTTP errors, malformed content, and cancellation. A configured source is input to validate, not authority to access arbitrary network resources.

**Recommendation:** implement one injectable source-fetch interface, use a fake fetcher in tests, and make the production fetcher restricted to configured sources with explicit timeout/size/redirect rules. Do not expose general filesystem, shell, or arbitrary network tools to workers.

### G0-D4 — Meaning and persistence of Outcome in R6

The architecture describes an `Outcome` entity, but the current ORM and migrations do not implement it. This is a schema/API decision, not something the worker should improvise.

**Recommendation:** add the smallest Outcome implementation required by the first loop, aligned with the existing architecture definition in `docs/architecture.md`; do not pull Evaluation, prediction scoring, or learning into R6. Specify the first outcome type and observation provenance before migration work. The Task completion Event and Signal/Event evidence must remain consistent and idempotent on retries. Decide whether Outcome recording belongs in the final application-controlled completion transaction or in a separate Task operation, and test crash/replay behavior either way.

### G0-D5 — Strategy proposal generation

`StrategyService.submit` validates and records a proposal that is supplied to it; there is no current model-backed Strategy proposer in the repository. A full intelligent loop needs an explicit proposal-generation boundary while retaining the validator as the authority gate.

**Recommendation:** define a small `StrategyProposer` interface; tests use a deterministic fake, and one selected production provider implements the interface. Keep provider calls outside database transactions. Never pass model output directly to Plan materialization: it must pass existing Strategy validation and accepted-event provenance first. The architecture currently names the Anthropic Python SDK, so confirm that remains the intended production provider before adding its dependency, credential requirements, or network path. No provider is selected by this document.

### G0-D6 — First loop boundary

Define exactly what the first success proves and what is deferred. The first success should execute one supported configured-source Action from a real accepted Plan, produce a durable Signal and success/no-change evidence, finish its ordinary Task through the runtime-owned lifecycle, record the agreed Outcome representation, and build a new deterministic StateAssessment from the resulting records.

Keep broad scheduling, multiple worker types, arbitrary tools, autonomous policy changes, evaluation/learning, replanning, and multi-domain automation out of the first vertical slice unless an explicit decision expands scope.

## 4. Proposed delivery sequence

Each slice should be a small pull request with focused tests, then applicable static checks, a full-suite run at the milestone gate, and disposable-PostgreSQL migration/integration evidence when applicable. Do not begin the next slice while its predecessor's gate is unresolved.

### R6-A — Task execution lifecycle

Implement and test the application-controlled lifecycle that follows existing `TaskRuntime.admit`. Include success, retryable failure, exhausted failure, Event attribution, timestamps, concurrent/conflicting transitions, and idempotent recovery. Reuse the current policy version, quota, write-scope, and prerequisite checks. No worker dispatch or new scheduler in this slice unless the approved G0 contract explicitly requires it.

**Exit:** tests prove legal transitions only, one terminal result per Task execution attempt, durable Events agree with Task state, retry/replay does not duplicate commits, and failures cannot leave partial lifecycle changes.

### R6-B — One bounded `ingest_source` worker

Add a small dispatcher/handler that loads the Task and its durable configured Action/source context, uses the approved restricted fetcher, passes the fetched content into `IngestionService`, and reports success/failure through the lifecycle owner. The handler cannot commit business rows or Task/Event lifecycle state directly. No general-purpose agent runtime.

**Exit:** integration tests exercise the complete Task admission → handler → ingestion commit → Task completion path, including no-change, rejection, retries, crash after ingestion commit, and replay without duplicate Signals or Events.

### R6-C — Durable Outcome and re-assessment

Implement the G0-approved Outcome representation, schema migration if needed, Task scope, service, provenance, and idempotency. Build a new StateAssessment after the durable execution result; preserve the historical basis used by the original Strategy/Plan. Assessment remains read-only and does not mutate memory or policy.

**Exit:** a restart/replay test can reconstruct the Plan and explain the execution result from durable records, and the follow-up assessment is reproducible from the same database state.

### R6-D — Connect the deliberative path

Use the selected `StrategyProposer` implementation to propose against an existing Objective and deterministic assessment. Submit through `StrategyService`, materialize only the accepted proposal through `PlanService`, then dispatch the resulting ordinary Task through R6-B. Rejected proposals must not materialize a Plan. Model output cannot select tools, expand writes, change TeamPolicy, or bypass budget and dependency rules.

**Exit:** one integration test starts from an active Objective, runs the full loop, and asserts the accepted provenance, Plan/Task mapping, Task lifecycle, durable execution evidence, Outcome, and new assessment.

### R6-E — Gate, integrate, and close

Run the required focused tests, complete test suite, Ruff, mypy, and migration paths on disposable PostgreSQL. Verify clean diff, recovery behavior, and architecture boundaries. Record commands, environments, passed/failed/skipped checks, and any remaining limitations. Merge reviewed changes to main, then request an explicit R6 exit decision. R6 is not closed by tests or merge alone.

## 5. Non-negotiable invariants during R6

- Do not bypass `TaskRuntime.admit`, quota, policy-version, Task budget, Plan prerequisite, write-scope, or Kernel/application validation.
- Every durable write and Event remains attributable to a Task; worker output is a proposal, never authority.
- Plan intent and the selected historical assessment/proposal basis remain immutable and reconstructable.
- Do not use Task status alone as proof that declared Plan completion conditions were met; R5 durable evidence checks remain mandatory.
- Reactive Tasks remain valid without Objectives or Plans.
- Do not silently accept ADR-0025, ADR-0026, or ADR-0027. Do not broaden a Task-count quota into spend accounting.
- No destructive Git/database cleanup; tests use disposable databases, never the persistent `watch` database.
- The only current milestone status source is `PLAN.md`; update `CHANGE_MAP.md` when the governing map changes.

## 6. G0 exit checklist

R6-A can start when the following are explicitly resolved and reflected in the relevant authority documents:

- [ ] Operator decision recorded for ADR-0025 and ADR-0026.
- [ ] One owner and contract for Task completion, failure, retries, and Event semantics.
- [ ] First `ingest_source` execution boundary and network-safety requirements agreed.
- [ ] Outcome entity/scope/transaction/replay semantics decided against `docs/architecture.md`.
- [ ] Strategy proposer interface and production-provider choice (or a clearly bounded staged provider decision) recorded.
- [ ] First vertical slice acceptance tests, failure/recovery cases, and deferred scope frozen.
- [ ] R6-A branch base, current HEAD, clean worktree, and required disposable test database verified from the actual local checkout.

Until the checklist is satisfied, keep R6-G0 in progress and do not implement schema, network, provider, or lifecycle behavior by assumption.
