# AGENTS.md — Watch repository operating contract

## 1. Purpose

Watch is an architecture-sensitive project developed in small, auditable milestones.

These instructions are for coding agents working in the repository.

The primary rule is:

> **Understand the current repository and architecture first; make the smallest justified change second.**

Do not treat every request as a generic coding task.

The project values:

- small changes;
- explicit ownership;
- deterministic validation;
- durable, reconstructable state;
- strong tests;
- clear milestone boundaries;
- documented workflow observations.

Avoid speculative infrastructure and premature abstractions.

---

## 2. Determine current state from the repository

Do not trust a hard-coded milestone statement in this file.

At the start of an architecture-sensitive session, determine the real state from:

1. Git branch and commit;
2. worktree status;
3. `PLAN.md`;
4. `CHANGE_MAP.md`;
5. relevant implementation and tests;
6. relevant workflow/audit records.

The current phase is the repository's current phase, not a historical value copied into `AGENTS.md`.

For milestone transitions, the normal sequence is:

```
completed phase
    ↓
merge into main
    ↓
create next phase branch from main
    ↓
design/reality gate
    ↓
implementation
    ↓
adversarial audit
    ↓
commit
    ↓
merge into main
```

Do not skip the branch boundary merely because implementation is small.

---

## 3. Mandatory preflight

Before changing code or architecture, inspect:

```text
git branch --show-current
git rev-parse HEAD
git status --short --branch
git log --oneline -12
git diff --check
```

For milestone transitions, also inspect the relevant local/remote branches and ancestry.

Never:

- reset user work;
- discard changes;
- stash without explicit instruction;
- rebase merely for convenience;
- force-push;
- rewrite completed milestone history.

If repository state differs from the expected task state, report the discrepancy before making architectural decisions.

Repository state is more authoritative than assumptions from prior conversations.

---

## 4. Authority and conflict handling

Use `CHANGE_MAP.md` to determine which documents govern which concepts.

General rule:

- mapped Revision 2 documents govern the concepts they explicitly revise;
- original Watch documents remain authoritative for unmapped concepts;
- `docs/invariants.md` remains authoritative for invariants unless a mapped Revision 2 source explicitly revises one;
- ADRs record architectural decisions and must be consulted for their named concepts.

Never resolve contradictory documents by intuition.

When authority is genuinely ambiguous:

> **STOP and report the ambiguity.**

Do not silently invent a schema, lifecycle, authority path, or exception.

Do not modify a historical decision merely to make current implementation convenient.

---

## 5. Core architectural rules

These are boundaries, not permission to implement future components early.

### Authority

```
model / worker proposes
        ↓
application validates
        ↓
Kernel/application commits
        ↓
database preserves authoritative state
```

The model is never the authority for durable state.

### Persistent experience

Model reasoning is temporary.

Durable records are the persistent experience of Watch.

Do not make transcripts the primary memory mechanism.

### Derived state

A computed projection, assessment, or view is not authoritative merely because it exists.

In particular:

> `StateAssessment` is derived, read-only, deterministic, and non-authoritative.

### Execution

Tasks are the execution unit.

Reactive and deliberative entry paths converge on the existing Task runtime.

Do not create a second execution runtime or commit kernel.

### Planning

A Plan records intended execution structure.

It is not execution history.

Tasks, Events, and Outcomes describe what actually happened.

### Provenance

A reference between records does not automatically establish causality.

Preserve provenance without making unsupported causal claims.

### Future entities

Do not simulate unimplemented domain entities with arbitrary fields or repurposed records.

If an entity such as Strategy, Plan, Outcome, Evaluation, Hypothesis, EvidenceLink, or Memory is not implemented by the current milestone, do not quietly invent it early.

---

## 6. Milestone discipline

For every new milestone, reason in this order:

1. What capability is being added?
2. Why is it needed?
3. What does it mean?
4. What existing durable state supports it?
5. What is the smallest useful implementation?
6. What explicitly waits for a later milestone?

Do not begin by choosing tables/classes/files.

Do not implement a later milestone merely because its concepts are already mentioned in architecture documents.

A milestone is complete only when its documented exit criteria and verification are actually satisfied.

---

## 7. Design/reality gates

Architecture-sensitive milestones require a design/reality gate before implementation.

A gate should establish:

- semantic meaning;
- ownership;
- authority;
- persistence requirements;
- invariants;
- recovery/retry implications;
- exact boundary with the next milestone;
- smallest implementation slice.

A gate may conclude:

```
READY
```

or:

```
NOT READY — unresolved issue
```

Do not force a READY conclusion.

If implementation exposes a genuine architecture conflict, stop rather than silently changing the architecture.

---

## 8. Workflow validation is mandatory when workflow is being tested

Workflow validation is not optional when the task is testing, simulating, auditing, or evaluating the development process.

A task is a workflow-validation task whenever it asks the agent to do any of the following:

- simulate a development session;
- perform a workflow simulation;
- run a design/reality gate whose purpose includes testing agent behavior;
- audit the Codex/VS Code process;
- test repository instructions;
- verify whether the agent followed the intended development workflow;
- report discrepancies between expected and observed agent behavior;
- perform a milestone preflight/readiness exercise whose result is intended to improve repository instructions.

The user does **not** need to repeat the words "update workflow-validation.md" for this requirement to apply.

### Required workflow-validation procedure

When the task is workflow validation:

1. Read `docs/development/workflow-validation.md` before starting.
2. Determine the next chronological entry number from the file itself.
3. Treat the workflow record as part of the task, not optional reporting.
4. During the task, distinguish documented expectations from actual observations.
5. At completion, append exactly one chronological record unless the task explicitly requires multiple records.
6. Include:
   - task/scenario;
   - relevant repository state;
   - expected behavior, supported by repository instructions;
   - observed behavior;
   - discrepancies or absence of discrepancy;
   - lessons/workflow rules;
   - resulting documentation or `AGENTS.md` changes.
7. Never rewrite old observations merely to make them cleaner.
8. Do not fabricate expected behavior after observing what the agent did.
9. Verify the workflow-validation file was actually changed before final reporting.

### No-edit simulations

If a workflow-validation task says "no implementation edits", that does **not** mean "no file may change".

The permitted documentation change is normally:

```
docs/development/workflow-validation.md
```

unless the task explicitly names another file.

Do not edit source code during a no-edit simulation.

### Implementation tasks that reveal workflow failures

If an implementation task is explicitly also evaluating the workflow/process, record the workflow finding as required above while respecting the implementation boundary.

Do not use workflow validation as an excuse to alter architecture.

---

## 9. Reporting requirements

Reports must be grounded in evidence.

Never claim:

- tests passed when they were not run;
- a branch was merged when it was not;
- a file was changed when it was not;
- an architecture decision is authoritative when it is only a proposal.

For verification, report exact results and distinguish:

- clean isolated database verification;
- existing/shared database verification;
- skipped checks;
- environment/tooling limitations;
- unrelated pre-existing failures.

When a workflow-validation task completes, the final response must identify the appended workflow-validation entry.

---

## 10. Development changes

Make the smallest justified change.

Keep unrelated files untouched.

Before editing, identify the expected file set.

Prefer:

```
small implementation
+
focused tests
+
minimal documentation
```

over speculative flexibility.

Do not introduce infrastructure merely because it may be useful later.

Do not combine architecture redesign with implementation unless an explicit authority change has been approved.

---

## 11. Tests and verification

Use the repository's configured environment.

For Python, prefer:

```bash
uv sync --python 3.12
uv run pytest
uv run ruff check .
uv run mypy core
git diff --check
```

Do not assume globally installed tools are available.

For database tests, distinguish test-environment setup from production behavior.

Prefer isolated reproducible verification when shared database state can contaminate global-count or fixture assumptions.

Do not modify or delete an existing database merely to make tests pass.

---

## 12. Invariant changes

When an existing invariant must change:

1. identify the exact conflict;
2. stop implementation;
3. update the authoritative architecture/invariant documentation according to the repository's change process;
4. update affected tests;
5. only then implement the revised behavior.

Do not weaken an invariant silently.

---

## 13. Documentation changes

Documentation should describe the current architecture accurately.

When adding milestone guidance:

- distinguish current behavior from future design;
- distinguish semantic requirements from implementation choices;
- preserve historical records;
- append chronological workflow observations;
- avoid duplicate competing definitions.

`PLAN.md` defines milestone scope.

`CHANGE_MAP.md` defines authority mapping.

`docs/development/workflow-validation.md` records observed development-process behavior.

---

## 14. Current milestone information

Do not maintain a manually edited "current milestone" claim in this file.

Use:

```
git branch
+
PLAN.md
+
recent milestone commits
```

to determine the current phase.

This prevents `AGENTS.md` from becoming stale after a branch transition.

---

## 15. Documentation lookup

| Topic | Primary source |
|---|---|
| Authority mapping | `CHANGE_MAP.md` |
| Milestone scope | `PLAN.md` |
| Architecture | `docs/01-architecture-revision.md` |
| Control layer | `docs/02-control-layer.md` |
| Runtime | `docs/03-runtime-model.md` |
| Data model | `docs/04-data-model-changes.md` |
| Tasks | `docs/tasks.md` |
| Invariants | `docs/invariants.md` |
| Workflow validation | `docs/development/workflow-validation.md` |
| Implementation planning | `docs/05-implementation-plan.md` |
| VS Code/Codex workflow | `docs/06-codex-vscode-workflow.md` |
| Vocabulary | `docs/glossary.md` |
| Architecture decisions | `docs/decisions/` |

For Task, Plan, Objective, Trigger, scheduler, or Control changes, read ADR-0026 and the mapped authorities before implementation.

---

## 16. Final pre-completion checklist

Before declaring a milestone step complete, ask:

```text
[ ] Did I verify the real Git state?
[ ] Did I read the current authority chain?
[ ] Did I identify the smallest capability being added?
[ ] Did I preserve earlier invariants?
[ ] Did I keep later milestones out of scope?
[ ] Did I run the relevant verification?
[ ] Did I report deviations honestly?
[ ] If this was workflow validation, did I append workflow-validation.md?
[ ] Did I verify that append actually exists?
[ ] Is the worktree state reported accurately?
```

The last two questions are mandatory for workflow-validation tasks.

---

## 17. Operating principle

The goal is not maximum implementation speed.

The goal is:

```
small semantic step
+
strong invariant
+
durable evidence
+
reproducible verification
=
safe architectural progress
```

When uncertain:

> **Prefer the smallest reversible decision that preserves future options.**

When the repository cannot answer the question:

> **Stop and report the ambiguity instead of guessing.**
