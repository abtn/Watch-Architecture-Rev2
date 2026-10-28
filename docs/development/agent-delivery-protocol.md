# Agent delivery protocol

Compact, persistent operating protocol for accelerated delivery. It supplements
[`AGENTS.md`](../../AGENTS.md); it does not replace the authority chain or the
stop conditions there. `PLAN.md` remains the sole authority for current
milestone status.

## Standing conditional authorization

- The operator has authorized continued work through **R6-A, R6-B, and R6-C**
  without separate approval for every checkpoint.
- Within those milestones the agent may implement bounded changes, correct
  defects revealed by tests or review, run focused and full verification against
  a positively identified disposable database, create one local commit per
  accepted checkpoint or coherent infrastructure change, and push feature
  branches and create/update pull requests.
- **R6-D and R6-E remain outside this authorization.** Provider-selection and
  architecture decisions for those slices require separate explicit approval.

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
