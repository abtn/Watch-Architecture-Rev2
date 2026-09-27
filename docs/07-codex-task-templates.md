# Codex Task Templates

## Template A — Inspect only

```text
Read:
- AGENTS.md
- <relevant architecture doc>
- <relevant PLAN section>
- <relevant code>

Do not edit files.

Answer:
1. What currently exists?
2. What is the intended architecture?
3. Where does the requested change belong?
4. What existing invariants affect it?
5. What files should be changed?
6. What tests should be added?
7. What ambiguity must be resolved before implementation?
```

## Template B — Implement one slice

```text
Implement exactly this slice:

<goal>

Read first:
- AGENTS.md
- <architecture docs>
- <plan>
- ADR-0026 if this slice touches Task, Plan, Objective, Trigger, or scheduler behavior

Required:
- <file/change>
- <tests>
- <migration if needed>

Constraints:
- no unrelated refactors
- no new entities unless justified by an invariant
- no direct durable writes from workers
- preserve existing invariants
- if the slice is before R2, do not add Objective/Plan/Strategy code

Acceptance:
- <criterion>
- <criterion>

Verification:
<commands>

At the end report:
- files changed
- tests run
- architectural assumptions
- anything unresolved
```

## Template C — Architecture review

```text
Review the current implementation against the stated architecture.

Do not change files.

Check:
- State vs Policy vs Strategy vs Plan boundaries
- dual-entry execution model preserved (reactive and deliberative paths converge on Tasks)
- Control layer does not bypass existing Task state machine or commit path
- Plan does not become a second mutable truth store
- Tasks remain valid without a Plan
- Trigger integration respects ADR-0026
- authoritative vs derived data
- worker authority
- commit boundaries
- task scopes
- concurrency/idempotency
- restart/replay behavior
- provenance

Return:
1. violations
2. risks
3. ambiguous boundaries
4. missing tests
5. unnecessary complexity
```

## Template D — Test-first

```text
Before changing implementation:

1. identify the invariant or behavior
2. write the failing test
3. implement the smallest change
4. run the focused test
5. run the relevant invariant suite

Do not weaken the test to make implementation easier.
```

## Template E — Refactor guard

```text
Refactor only.

The externally observable architecture must remain unchanged.

Prove:
- same state transitions
- same write scopes
- same Events
- same idempotency behavior
- same test results

Do not introduce new abstractions unless required to remove duplication.
```

## Template F — Stop condition

```text
If the repository contradicts the task or architecture:

STOP before inventing a solution.

Report:
- contradiction
- relevant files
- possible interpretations
- smallest ADR that would resolve it
```
