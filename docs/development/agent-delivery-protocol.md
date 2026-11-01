# Agent delivery protocol

Compact, persistent operating protocol for accelerated delivery. It supplements
[`AGENTS.md`](../../AGENTS.md); it does not replace the authority chain or the
stop conditions there. `PLAN.md` remains the sole authority for current
milestone status.

## Standing conditional authorization

- The operator has authorized continued work through **R6-A, R6-B, and R6-C**
  without separate approval for every checkpoint.
- **R6-D is complete.** The operator explicitly selected Cloudflare Workers AI
  `@cf/meta/llama-3.1-8b-instruct-fp8` and authorized **R6-E** on 2026-10-30
  (ADR-0031). R6-E may proceed through bounded Context assembly, immutable
  Context Snapshot/manifest, the model-backed StrategyProposer, strict
  application validation, Task-level usage reservation/reconciliation, and
  required verification. The current branch contains only the initial provider
  adapter/smoke checkpoint; do not report R6-E complete until all remaining
  acceptance criteria and checks pass.
- **R6-F and R6-G remain outside this authorization.** No work may advance into
  experience distillation or the integrated R6 exit gate without separate
  operator authorization.

## Automatic advancement

- Advance to the next pre-authorized checkpoint automatically once the current
  checkpoint's acceptance criteria are satisfied and its evidence is recorded.
- Do not pause for routine authorization between pre-authorized checkpoints.
- Diagnose and correct routine test failures without asking for approval.

## Commits and branches

- Keep each coherent checkpoint or infrastructure change in its own commit.
- Do not combine CI configuration with implementation changes, or documentation
  changes with implementation changes.
- Do not amend an earlier commit.
- Push feature branches with normal, non-destructive pushes. Never force-push.

## Merge authorization

Merging is authorized only when **all** of the following hold:

- the entire scope of the PR satisfies its accepted milestone criteria;
- all required CI checks pass;
- the commit and file scope are verified;
- no unresolved architectural blocker remains.

Do not merge an incomplete milestone.

## Status authority

- `PLAN.md` is the sole source of current milestone status. Other documents
  reference it rather than copying status tables.
- Code presence does not authorize a milestone or prove formal closure.

## Stop conditions

Stop and report — do not proceed — for any of:

- a genuine architectural contradiction;
- an unsafe or ambiguous database target;
- data-loss risk;
- security or permission expansion;
- an irreversible or externally costly decision;
- a change materially beyond the accepted authority.

## Reporting

Report files changed, checks actually run and their results, assumptions made
within existing authority, unresolved conflicts or blocked gates, and the final
branch/HEAD/worktree state when Git operations were part of the task. Use
`DONE`, `BLOCKED`, or `FAILED` accurately.
