# Verification protocol

Verification establishes whether the requested change meets its acceptance
criteria. Inspection alone is not proof that a command, test, migration, or
external service works.

## Verification steps

1. Translate each acceptance criterion into evidence: a focused test, static
   check, migration/database check, documented manual check, or expected
   repository-state inspection.
2. Read the milestone's documented verification instructions. Do not invent
   commands when the repository has not established them; ask or state the
   limitation.
3. Run the smallest relevant check first. Run broader milestone checks when
   required by the task or when the focused result calls for them.
4. Where applicable, verify the resulting file set and ensure unrelated or
   user-owned changes were preserved.
5. Compare observed results with every acceptance criterion and report gaps.

## Watch-specific application

- Preserve the invariants in [`docs/invariants.md`](../invariants.md); do not
  claim the invariant suite passes unless the relevant tests exist and were
  run.
- Follow the current milestone and acceptance criteria in
  [`PLAN.md`](../../PLAN.md), not a later phase's checks.
- For schema changes, use the repository's authoritative migrations and the
  applicable migration checks; do not infer schema behavior from narrative
  documentation alone.
- Do not use a Task, Plan, projection, or derived assessment to bypass
  authoritative Kernel validation. Refer to the applicable architecture and
  ADRs for task-specific boundaries.
- Respect `AGENTS.md` tooling status. In the documentation-only checkout,
  commands listed as future K0 acceptance checks are targets for after setup,
  not commands to report as already runnable or verified.

## Reporting evidence

State precisely:

- each command actually run and its result;
- tests or checks skipped, and why;
- whether a result came from execution, inspection, or reasoning;
- failures and what they do or do not establish;
- any acceptance criterion still unverified.

Never convert “not run,” “could not run,” or “not applicable” into “passed.”
A green static check does not establish runtime correctness; a passing test
does not prove undocumented behavior.
