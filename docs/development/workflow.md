# Human–Agent Development Workflow

This document explains the practical loop. It does not override architecture, milestone gates, or write scopes.

## 1. Interpret and bound the task

1. Read `AGENTS.md`, the relevant portion of `PLAN.md`, and `CHANGE_MAP.md`.
2. Open only the spec, ADR, code, and tests needed for the request.
3. Write a short scope: intended behavior, allowed files, required tests, excluded work, and stop conditions.
4. If authority or a required decision is unclear, stop before editing and report the conflict.

## 2. Confirm repository state

Check branch, HEAD, worktree, recent commits, and existing diff. Preserve unrelated and uncommitted changes. A ZIP/text export is not evidence of Git branch or merge state.

## 3. Implement the smallest complete slice

- Prefer a failing regression test that expresses the behavior.
- Follow existing service/model/migration patterns.
- Do not introduce an entity, scheduler, runtime, migration, default, or write scope without authority and a demonstrated need.
- Keep validation, state transition, durable Event, and related writes in the required transaction.
- Update the actual authority document and decision record when behavior/authority changes. Update `CHANGE_MAP.md` if the authority path changes.

## 4. Verify and review

Run focused tests and relevant static checks, then broader checks required by the task/milestone. Review the final diff, including generated migration changes and documentation links. Use `docs/testing.md` for the verification contract.

## 5. Stop conditions

Stop and report rather than guessing when:

- authoritative docs conflict;
- a proposed ADR is being treated as accepted;
- a milestone is paused or its entry/exit gate is unmet;
- behavior needs an unapproved schema, security, budget, or public-contract decision;
- a test environment is unavailable or a command failure makes evidence inconclusive;
- satisfying the request would require unrelated refactoring or destructive operations.

## 6. Final handoff

Report exact changed files, commands run and results, assumptions, remaining risks, unrun checks, unresolved decisions, and final Git state if relevant. Distinguish code presence, source-recorded evidence, freshly executed verification, and formal milestone closure.

## Archived workflow-validation evidence

The former workflow-validation log is preserved at [`obsolete-workflow-validation.md`](obsolete-workflow-validation.md) as historical evidence only. It is obsolete and must not receive new entries. Current development work follows the verification and reporting rules in `AGENTS.md` and `docs/testing.md`.
