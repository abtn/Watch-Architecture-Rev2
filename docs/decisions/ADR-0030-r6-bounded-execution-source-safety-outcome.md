# ADR-0030 — R6 Bounded Execution, Recovery, and Outcome Contract

## Status

**Accepted 2026-10-25** under the operator's explicit request to resolve the remaining R6-G0 decisions. This is an architecture/implementation contract, not implementation authorization.

## Context

R6 depends on a real Task execution path, but current `TaskRuntime` only admits a pending Task and records `task_started`. No current worker path finalizes Tasks or persists the architecture-level Outcome. The current Task ORM also lacks the architecture's `created_at` and `completed_at` fields and has no pinned retry limit. The first worker must fetch only configured sources and must not turn LLM output into network authority.

## Decision

### 1. One lifecycle authority

`TaskRuntime` remains the single application-controlled authority for `pending → running → pending | done | failed`. A narrowly scoped internal lifecycle service is permitted only if it is called by `TaskRuntime` and shares the same validation/commit authority. Worker handlers return typed results; they never mutate Task status, attempt counters, or lifecycle Events directly.

The R6-A schema change must add `Task.created_at`, nullable `Task.completed_at`, and `Task.max_attempts`. `max_attempts` is pinned when the Task is created and defaults to **3 total successful starts** (the initial start plus at most two retries); `attempt_count` counts successful `pending → running` admissions and remains the audit count. `completed_at` is set only on `done`; terminal failure time is available from the Task-attributed `task_failed` Event. Existing rows must be backfilled by a migration and task creation paths must set the pinned limit. These fields are not all present in the current ORM baseline.

| Current state | Result/condition | Next state | Atomic durable effect |
|---|---|---|---|
| `pending` | Valid admission | `running` | Increment `attempt_count`; emit `task_started` |
| `running` | Terminal success | `done` | Set `completed_at`; emit `task_completed`; persist one terminal `task_execution` Outcome |
| `running` | Retryable failure and `attempt_count < max_attempts` | `pending` | Emit `task_attempt_failed` and `task_retry_scheduled`, including attempt and categorized reason |
| `running` | Non-retryable failure or attempts exhausted | `failed` | Emit `task_attempt_failed` and `task_failed`; persist one terminal failure `task_execution` Outcome |

Every operation checks the expected prior status and expected attempt number. Repeated finalization is idempotent only when it resolves to the same already-committed terminal result; conflicting retries/finalizations are rejected without extra Events or Outcomes. The Task transition Event and terminal Outcome commit in the same transaction as the terminal status update.

### 2. Retries and interrupted execution

For the first configured-source worker, retryable failures are transient connection errors/timeouts and HTTP 408, 429, or 5xx responses. Security/policy rejection, unsupported media type, prohibited redirects, malformed data, other 4xx responses, and application validation failures are non-retryable. The first slice makes at most one attempt per dispatcher invocation; it does not create an unbounded in-process retry loop or introduce a new scheduler. A `pending` retry becomes eligible through the existing runtime and normal dispatch flow. Each new successful admission consumes the existing daily Task-start quota if configured; ADR-0027 remains Proposed.

A worker execution has a hard 30-second deadline. On dispatcher startup, a `running` Task whose latest `task_started` Event is older than 60 seconds is treated as interrupted: return it to `pending` with a retry Event if attempts remain, otherwise terminalize it as `failed` with `task_failed` and an Outcome. Recovery is a compare-and-set lifecycle operation, not a second runtime. A worker must supply the attempt number it was admitted with when reporting its result. If recovery/re-admission has advanced the attempt, a late worker result is rejected. Business effects must remain idempotent so recovery cannot duplicate them.

### 3. First executable capability and network boundary

The first handler is `ingest_source` for a source explicitly configured in the requesting Team's current `TeamPolicy.rules["sources"]` list. A configuration entry authorizes the exact `(origin_url, source_type)` pair, matching the current `IngestionService._source_is_configured` contract. The model cannot supply or modify a URL, and a Task payload alone does not grant source access.

- Accept only HTTPS URLs from the exact configured-source allowlist. Reject URL user-info, IP-literal hosts, unsupported schemes, fragments, and non-canonical/mismatched URLs.
- Resolve DNS at connection time. Reject the request if any resolved destination is loopback, private, link-local, multicast, reserved, unspecified, or a metadata-service address. Connect only to a validated resolved address while preserving the original hostname for TLS SNI/certificate validation; do not permit DNS rebinding to bypass the address check.
- **Do not follow redirects in the first slice.** Any 3xx is a non-retryable `source_redirect_not_allowed` failure; the operator must configure the final HTTPS URL explicitly.
- Accept only 2xx responses with `text/html`, `text/plain`, `application/rss+xml`, or `application/atom+xml`. Reject other media types.
- Enforce connect timeout **3 seconds**, read timeout **10 seconds**, total request timeout **15 seconds**, and at most **2 MiB of decompressed response bytes**. Stream and enforce the byte limit even when `Content-Length` is absent or compression is used.
- Keep network calls outside database transactions. Use an injectable fetch interface and a deterministic fake fetcher in tests. Do not provide shell, arbitrary filesystem access, or general-purpose network tools to the worker.

A rejected source/fetch attempt records a categorized, Task-attributed Event without persisting a raw response body or secret. Exact source identity and content hash feed the existing ingestion idempotency contract.

### 4. First terminal Outcome

The first Outcome type is `task_execution`, whose subject is the terminal Task (`subject_kind="task"`, `subject_id=task.id`, `recorded_by_task_id=task.id`, matching `team_id`). The Outcome is a deterministic observation, not a model interpretation. Its immutable, content-addressed observation Snapshot contains:
- terminal result category: `success_signal_created`, `success_no_change`, or `terminal_failure`;
- relevant Signal IDs and their `snapshot_ref`/content hashes, where present;
- the categorized terminal failure reason, where relevant;
- observation timestamp and the terminal attempt number.

There is at most one `task_execution` Outcome per Task, enforced by an idempotency key/unique constraint equivalent to `(recorded_by_task_id, outcome_type)`. The Outcome row, immutable observation Snapshot reference/hash, terminal Task status, and `task_completed` or `task_failed` Event are committed atomically. Attempt-level failures remain in Events and do not create terminal Outcomes until the Task reaches `done` or `failed`.

The existing ingestion business commit remains its own atomic/idempotent operation. If a crash occurs after Signal/Snapshot commit but before task finalization, replay must discover the prior ingestion result, not create duplicate Signals, and then finalize the Task/Outcome once. Outcome failure must never leave a Task falsely marked `done`.

### 5. R6-A / R6-C implementation boundary

This subsection clarifies **delivery sequencing only**. It does not change the accepted Outcome schema or semantics, the retry/recovery contract, the atomicity requirements, the source-fetch rules, or the single `TaskRuntime` lifecycle authority established above.

- **R6-A owns the minimum complete terminal Outcome path.** The R6-A slice must persist the terminal `task_execution` Outcome required by section 4 as part of the lifecycle it introduces. Terminal Outcome persistence is not a later enhancement to be supplied by R6-C.
- **Terminal finalization is one atomic commit.** On terminal success or terminal failure, the Outcome row, the immutable observation Snapshot reference/hash, the terminal Task status, and the corresponding terminal Task Event (`task_completed` or `task_failed`) commit in the same transaction. A partial commit is a defect, not an acceptable intermediate state.
- **R6-A is not complete without it.** R6-A's Task lifecycle implementation must not be considered complete if terminal finalization can commit without its required Outcome, or if the Outcome can commit without the terminal status and Event.
- **The Outcome contract applies from the first implementation.** The uniqueness/idempotency rule (at most one `task_execution` Outcome per Task, equivalent to `(recorded_by_task_id, outcome_type)`) and the Task attribution rules (`subject_kind="task"`, `subject_id=task.id`, `recorded_by_task_id=task.id`, matching `team_id`) are R6-A requirements, not R6-C additions.
- **R6-C consumes already-durable Outcomes.** R6-C implements deterministic reassessment over these durable Outcomes plus the remaining Outcome-driven integration (evaluation/reassessment wiring, derived-state reconstruction, and replay of that derivation). R6-C must not defer or re-implement the core terminal Outcome write path, must not introduce a duplicate Outcome representation, and must not weaken R6-A's atomicity guarantees.
- **A schema/migration for the Outcome belongs to the slice that first writes it.** Because R6-A writes the terminal Outcome, the representation it needs is introduced with R6-A. R6-C may extend derived read models and reassessment support, but it does not own the initial terminal Outcome persistence.

## Consequences and boundaries

- This contract does not add a second Task runtime, a general job scheduler, arbitrary tools, or autonomous policy change.
- The first R6 loop adds only the Outcome/Evaluation/KnowledgeItem/LearningChange persistence required by the accepted R6 contract; it does not implement every conceptual entity in the original architecture.
- Provider/network/index implementation remains staged by the R6 slices in `PLAN.md`. The concrete source-fetch limits above are the approved R6-B contract, not a claim that a fetcher already exists.
- ADR-0027 remains Proposed and is not accepted by this ADR.

## Verification required when implemented

- Legal state transitions only; status, attempt count, timestamps, Events, and Outcomes agree.
- Retry exhaustion produces one terminal failure; rejected admission produces no start Event or attempt increment.
- Concurrent admission/finalization and stale worker results cannot double-start, double-finalize, or overwrite a newer attempt.
- Crash after ingestion commit but before finalization recovers without duplicate Signal, terminal Event, or Outcome.
- SSRF/private-address, DNS-rebinding, redirect, content-type, response-size, and timeout cases are covered using a fake resolver/fetcher and controlled local tests; no public network is used in unit tests.
- All database tests use a disposable PostgreSQL database; no test touches the persistent `watch` database.
