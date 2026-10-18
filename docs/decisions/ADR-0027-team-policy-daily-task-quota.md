# ADR-0027 — TeamPolicy Daily Task Quota

## Status

Proposed

## Context

Watch admits Tasks through the existing application-controlled Task runtime. A Team may need a deterministic limit on the number of Tasks that can successfully start during one day.

The daily limit must be enforced at the Task admission boundary, where the application controls the Task state transition and records the `task_started` Event. Counting only currently running Tasks would be insufficient: a Task that starts and later finishes has still consumed a unit, and a successful retry is another start. The limit must also remain correct when multiple workers attempt to admit Tasks for the same Team concurrently.

The daily Task-count quota is distinct from Strategy-level constraints. In particular, `StrategyProposal.constraints.max_tasks` is an upper bound on Actions in a Strategy; it is not a Team-wide daily execution quota.

## Decision

### Configuration and scope

A TeamPolicy may configure the daily quota at:

```python
rules["budgets"]["max_tasks_per_day"]
```

When configured, the value must be a non-negative integer. Boolean values, negative values, and other types are invalid. A value of `0` permits no successful Task starts during the UTC calendar day.

The quota applies to the aggregate successful Task starts of the Team, across its Tasks, Objectives, and Plans. It is not a separate quota for each Task, Objective, Plan, or Strategy.

When `max_tasks_per_day` is absent, Watch preserves the existing no-limit behavior. No default daily limit is introduced by this decision.

### What consumes quota

A successful Task admission that records a `task_started` Event consumes one unit for the UTC calendar day containing that Event's start timestamp.

- Each successful start consumes one unit.
- A successful retry that starts the Task again consumes another unit.
- An admission rejected before a successful start consumes no unit.
- The daily window is the UTC calendar day, from `00:00:00 UTC` inclusive to the next day's `00:00:00 UTC` exclusive.

The durable `task_started` Events, associated with Tasks belonging to the Team, are the accounting source of truth. The quota is not computed from the number of Tasks currently running.

### Admission, concurrency, and atomicity

Quota enforcement belongs in `TaskRuntime.admit`, at the existing application-controlled admission boundary.

The implementation must serialize quota accounting for a given Team using a database-level lock or an equivalent database mechanism that is safe across processes and workers. A process-local lock is insufficient.

For a successful admission, the quota check and count, Task transition to `running`, attempt-count increment, and creation of the `task_started` Event must be part of one database transaction. They must either commit together or roll back together.

If the quota is exhausted, admission is rejected using the existing `TaskNotEligible` rejection convention. A rejected admission must not leave the Task running, increment its attempt count, or create a successful `task_started` Event.

These rules ensure that concurrent admissions for the same Team cannot collectively exceed the configured daily limit.

### Boundary with other limits

`StrategyProposal.constraints.max_tasks` remains a Strategy-level Action bound. It must not be compared with, substituted for, or interpreted as `TeamPolicy.rules["budgets"]["max_tasks_per_day"]`.

This decision establishes a Task-count quota only. It does not claim to enforce a daily monetary, compute, token, or other cost quota. Existing Task budgets and any applicable Plan/TeamPolicy budget hierarchy remain separate constraints.

## Consequences

- Teams can configure an explicit daily cap without changing behavior for Teams whose policy does not specify one.
- Durable start Events provide auditable accounting, including successful retries.
- A Team-level database lock serializes admission accounting for that Team; concurrent admissions for different Teams need not be serialized by this rule.
- Event timestamps and the UTC calendar-day boundary must be handled consistently by the implementation and its tests.
- A separate quota ledger or migration is not required solely for this decision while durable start Events provide the required accounting records. Such infrastructure must not be introduced without a demonstrated need.
- Tests must cover below-limit admission, exhausted-quota rejection without partial changes, successful retries, concurrent admissions competing for the final unit, and the absence of a configured quota.

## Rejected alternatives

### Count only currently running Tasks

Rejected because completed or failed starts would not count, and successful retries would not be accounted for consistently.

### Use a process-local lock

Rejected because multiple worker processes or application instances could independently admit Tasks and exceed the limit.

### Add a separate quota counter as the initial source of truth

Rejected because it duplicates information already represented by durable `task_started` Events and introduces additional synchronization and recovery requirements without an established need.

### Interpret `StrategyProposal.constraints.max_tasks` as the daily quota

Rejected because it is a Strategy-level bound on intended Actions, not an aggregate Team-level limit on successful Task starts over time.

### Impose an implicit default quota

Rejected because it would silently change behavior for Teams whose policies do not configure a daily Task limit.

## Implementation and milestone boundary

This ADR defines the quota semantics and admission invariants. It does not by itself close the R4 gate, authorize other R5 scope, release a milestone pause, or authorize work on R6. Milestone authorization remains governed by the repository's authoritative milestone documents and gate evidence.
