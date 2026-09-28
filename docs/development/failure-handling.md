# Failure handling

When a prerequisite or check fails, preserve the repository and make the
failure visible. Prefer stopping and reporting over guessing, silently
degrading, or expanding scope to work around an unknown constraint.

## Failure categories and response

| Category | Examples | Expected response |
|---|---|---|
| **Specification conflict** | `CHANGE_MAP.md` does not establish authority; an invariant conflicts with the requested behavior; milestone documents disagree | Stop before the conflicting change. Cite the relevant sources, describe the conflict without choosing a side, and request the decision or documented resolution. |
| **Ambiguous requirement** | Unspecified behavior, acceptance criteria, toolchain choice, migration scope, or destructive action | Resolve only from an authoritative source if unambiguous. Otherwise ask the Operator or stop with the smallest concrete question. Do not convert a preference into a requirement. |
| **Environment failure** | Missing Python version, unavailable Docker daemon, database not reachable, missing local configuration | Report the failed prerequisite and evidence. Do not claim the implementation is defective unless evidence supports that conclusion. Do not install dependencies or alter the environment unless authorized and needed. |
| **Missing dependency** | Test or command reports an unavailable package/tool | Report the exact missing dependency and command. Install or restore only after a manifest change or when the chosen validation fails for that reason, following repository instructions and approval boundaries. Never invent the package manager or setup command. |
| **Tool failure** | Command unavailable, tool invocation errors, external service timeout, authentication failure | Report which tool or service failed, the operation attempted, and whether any state may have changed. Do not claim the intended operation succeeded. Retry only when safe and useful; do not bypass authentication or access controls. |
| **Implementation defect** | A focused test fails against changed behavior; type or lint checks identify a change-related problem | Inspect the failure, make a scoped correction, and rerun the relevant check. Do not weaken acceptance criteria or tests merely to obtain a pass. |
| **External service unavailable** | Registry, database image, or remote service cannot be reached | Report the service and failed operation; distinguish service availability from code correctness. Avoid substituting an unapproved service or version. |

## Safe response sequence

1. Stop the affected operation when continuing could cause data loss, an
   unauthorized architectural choice, or an inaccurate success report.
2. Preserve existing user changes and any partial state; inspect before cleanup
   or retry.
3. Classify the failure using the table and capture the exact command or
   relevant error evidence without exposing credentials.
4. Determine whether the issue blocks all work or only a specific verification.
   Continue independent, safe work only if it remains within the task scope.
5. Report what succeeded, what failed, what was not attempted, the likely
   category, and the smallest required decision or action.

A failed test is not automatically an environment problem; an unavailable
service is not automatically an implementation defect. State uncertainty
explicitly and do not silently fall back to weaker verification.
