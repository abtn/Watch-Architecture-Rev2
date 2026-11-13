# AGENTS.md — Repository Operating Contract

## 1. Purpose

Make the smallest justified change that satisfies the requested slice and its acceptance criteria. Watch is architecture-sensitive: preserve authority boundaries, durable provenance, Task write scopes, transaction semantics, and milestone gates. Do not implement speculative future architecture.

## 2. Read the authority chain

For documentation roles, active reading order, and historical-record handling, see [docs/documentation-guide.md](docs/documentation-guide.md). It supplements this operating contract; it does not override the authority chain below.

At task start, read `PLAN.md`, `CHANGE_MAP.md`, this file, and only the relevant canonical specs/ADRs/tests. `CONTEXT.md` is an orientation page, not a replacement for the authorities below.

- **Current milestone, gate, next step:** `PLAN.md` only.
- **Which document governs a concept:** `CHANGE_MAP.md`.
- **Repository behavior and safe workflow:** this file.
- **Standing delivery authorization and merge conditions:** [`docs/development/agent-delivery-protocol.md`](docs/development/agent-delivery-protocol.md). It supplements this file; it does not override the authority chain or the stop conditions below.
- **General/original architecture:** `docs/architecture.md` for concepts not replaced by Revision 2.
- **Revision 2 Control contract:** `docs/control-model.md` and linked ADRs.
- **Hard constraints:** `docs/invariants.md`.
- **Task types, write scopes, budgets:** `docs/tasks.md`.
- **Implementation truth:** current code, migrations, tests, and verified Git state.

If sources conflict, stop and report the source paths and the smallest decision needed. Do not silently choose an interpretation or turn a proposed ADR into an accepted rule.

## 3. Preflight before changing files

Run and preserve the output of:

```bash
git branch --show-current
git rev-parse HEAD
git status --short --branch
git log --oneline -12
git diff --check
```

Inspect the relevant diff before editing. Preserve all pre-existing changes. Never use `reset --hard`, destructive checkout/restore, stash, volume deletion, or cleanup commands to make the worktree look clean. Do not stage, commit, or push unless explicitly requested or authorized by the standing delivery protocol.

A supplied ZIP or text export is not Git evidence: it cannot prove branch, HEAD, merge status, or uncommitted work.

## 4. Milestone and design gates

- Code presence does not authorize a milestone or prove formal closure.
- A recorded test result proves only the named command, environment, and snapshot; it does not prove unrun checks or satisfy a separate phase-boundary gate by itself.
- Do not start a later phase while `PLAN.md` says its entry gate is blocked or paused.
- For an architecture-sensitive change, establish meaning, ownership, authority, persistence, invariants, atomicity/recovery behavior, and the next-milestone boundary before implementation.
- If resolving the request would change architecture, schema, security, externally visible behavior, or a milestone boundary without authority, stop and request a decision.

## 5. Non-negotiable design boundaries

- Worker/model output is a proposal, never authority for a durable write.
- Application code validates schema, ownership, scope, policy, transitions, provenance, and concurrency before commit.
- Durable writes use the existing Kernel/application commit path and emit the required Task-attributed Events.
- `StateAssessment` is deterministic derived state; it does not mutate world/team memory.
- Plan expresses immutable intended work. Tasks, Events, and Outcomes express execution history.
- Reactive and deliberative entry paths converge on ordinary Tasks; do not create a second runtime.
- Tasks may exist without an Objective or Plan unless the relevant contract explicitly requires one.
- Do not invent entities, write scopes, tools, defaults, or quota semantics.
- Domain packs add domain knowledge/configuration, not Kernel powers.

## 6. Implementation discipline

1. State the requested behavior and narrow file scope.
2. Add or update tests for the invariant/behavior before or with the implementation.
3. Implement the smallest complete change; avoid unrelated renames/refactors.
4. Add a migration only when the actual schema change requires one. Do not guess migration numbering from an old plan.
5. Update the authoritative spec/ADR and `CHANGE_MAP.md` when behavior or authority changes.
6. Keep rejected operations atomic: no partial state transitions, attempt updates, or success Events.

## 7. Verification

Run the smallest relevant tests first, then applicable project checks:

```bash
uv run pytest <focused-test-file>
uv run ruff check <changed-paths>
uv run mypy core
git diff --check
```

Run the full suite when the scope or milestone requires it. Report skipped checks and the reasons. Do not say a command passed unless it was run and passed.

Database tests must use the repository's configured disposable/test database. Never modify the persistent `watch` database to make tests pass. Never use `docker compose down -v` as generic cleanup. Positively identify the target database before running database-backed tests or migrations; an ambiguous target is a stop condition.

## 8. Reporting

Always report:

- files changed;
- checks actually run and their results;
- assumptions and decisions made within existing authority;
- unresolved conflicts, blocked gates, and unrun checks;
- final branch/HEAD/worktree state when Git operations were part of the task.

Use `DONE`, `BLOCKED`, or `FAILED` accurately. Do not claim a proposed decision is accepted, a milestone is closed, or a test is green without evidence.
