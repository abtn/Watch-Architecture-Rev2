# Agent delivery protocol

Compact, persistent operating protocol for accelerated delivery. It supplements
[`AGENTS.md`](../../AGENTS.md); it does not replace the authority chain or the
stop conditions there. `PLAN.md` remains the sole authority for current
milestone status.

## Standing conditional authorization

- **R6-A through R6-E are complete.** R6-D's embedding provider decision and R6-E's generation provider decision are recorded in their governing ADRs. The Cloudflare provider selected for R6-E remains authorized for R6-E only and outside automatic Task dispatch.
- **R6-F Checkpoints 1–4 are complete and merged.** Checkpoints 1–2 merged through PRs #29/#30; C3 create-only Operator approval/canonical commit was separately authorized on 2026-11-01 and merged by PR #31; C4 Team Experience projection/retrieval was separately authorized on 2026-11-02 and merged by PR #32. Combined C3+C4 operator-local verification passed against the exact source tree merged by PR #33; see `docs/testing.md` for evidence and timing. D10 remains create-only: revise/retire proposal production and commitment are deferred to separately authorized lifecycle work. No production R6-F distillation provider/model is approved; deterministic fakes remain the test path.
- **R6-G implementation is explicitly authorized and in progress** on `r6g-implementation-20261103` / draft PR #35. Exact-head hosted CI and programmer-local disposable-PostgreSQL verification passed on 2026-11-04; see `PLAN.md` and `docs/testing.md`. This authorization covers the bounded implementation scope only. It does not authorize merge or R6 closure: the ten-proof acceptance review and a separate explicit operator decision on the R6 exit gate remain required.

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
