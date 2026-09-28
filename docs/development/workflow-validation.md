# Workflow validation

Development-workflow simulations are a formal way to check whether a human
Operator and Codex can carry out important work safely and efficiently before
the implementation itself begins.

## When to simulate

Use a simulation before important implementation work, or when the workflow,
repository instructions, or task protocol changes. Simulations can expose
ambiguous terminology, missing instructions, inefficient inspection steps,
unclear ownership, and unsafe assumptions without requiring implementation.

A simulation may be inspect-only or may ask Codex to produce a proposed plan.
Respect the scenario's explicit boundary: a no-edit simulation must not modify
implementation files.

## Standard simulation record

Record each simulation chronologically, distinguishing expectations supported
by repository instructions from observed behavior. Include:

1. **Task/scenario** — the request being simulated and its intended boundary.
2. **Repository state** — relevant files, milestone, and pre-existing changes.
3. **Expected behavior** — cite documented expectations where available; mark
   any expectation not defined by the repository as unresolved rather than
   retroactively inventing it.
4. **Observed behavior** — what Codex actually inspected, changed, verified,
   or reported.
5. **Discrepancies** — ambiguity, missing guidance, mistakes, or explicit
   absence of a discrepancy.
6. **Lessons** — process improvements supported by the evidence.
7. **Resulting documentation changes** — files updated because of the
   simulation, or state that none were made. A simulation does not authorize
   architecture or implementation changes.

Append new records; do not rewrite historical observations. Do not describe a
workflow finding as an architectural fact unless an authoritative architecture
source establishes it.

## Recorded simulations

### 1. M0/K0 inspect-only request

- **Task/scenario:** The Operator requested an implementation-free inspection
  and a concrete account of how to implement “M0,” including files, assumptions,
  commands, required information, and expected final state.
- **Repository state:** The checkout was documentation-only. The then-inspected
  [`AGENTS.md`](../../AGENTS.md) and [`PLAN.md`](../../PLAN.md) identified K0
  as the current implementation milestone; the requested name M0 also appeared
  in historical workflow material.
- **Expected behavior:** The prompt explicitly required no implementation.
  The repository instructions required checking the current milestone and
  reporting ambiguity rather than silently selecting an authority.
- **Observed behavior:** Codex made no file changes, identified K0 as the
  current scope, distinguished that from the M0 wording, and described the
  K0 tooling plan and missing setup decisions.
- **Discrepancies:** The first request used M0 without defining whether it
  meant K0 or an older milestone label. Current
  [`PLAN.md`](../../PLAN.md) now explicitly labels K0 as current and M0 as
  historical terminology; older references such as
  [`docs/invariants.md`](../invariants.md) and
  [`docs/walkthrough.md`](../walkthrough.md) still use M0 in their own
  contexts. This is a terminology/workflow finding, not evidence of a Watch
  architectural conflict. Whether every older M0 item has been reassigned to
  K0 remains unspecified.
- **Lessons:** Name the current milestone explicitly in implementation requests.
  If a task relies on a historical milestone label, ask what scope is intended
  instead of assuming equivalence.
- **Resulting documentation changes:** This record captures the observed
  finding. It does not change milestone definitions or architecture.

### 2. K0 implementation-plan simulation

- **Task/scenario:** The Operator clarified that K0 was intended and requested
  a concrete implementation plan without file changes, including file-by-file
  justification, constraints, verification, failure modes, and human decisions.
- **Repository state:** K0 was the current milestone; the checkout had no
  application implementation, dependency manifest/lockfile, migrations,
  tests, or Compose configuration. Repository guidance did not define a
  package manager, install command, or initial migration scope.
- **Expected behavior:** Respect the no-edit boundary, follow K0 deliverables
  and acceptance commands, avoid Control and K1 work, and distinguish
  requirements from choices and unresolved decisions.
- **Observed behavior:** Codex made no file changes, outlined a proposed K0
  file set and verification sequence, and identified choices requiring
  Operator input rather than presenting them as established conventions.
- **Discrepancies:** The plan included suggested filenames and tooling layout
  as proposals, not documented requirements. Those proposals would require
  approval before implementation. No K0 setup or verification command was
  actually run.
- **Lessons:** For a plan-only task, clearly label proposed file paths and
  choices as provisional; do not turn a plan into approval to implement them.
  Report verification as planned, not passed.
- **Resulting documentation changes:** This record captures the observed
  workflow. No K0 implementation was performed.
