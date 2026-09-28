# Watch development workflow

This directory documents the practical workflow between the human Operator and
Codex when inspecting, planning, implementing, and verifying changes to Watch.
Use it to make development tasks bounded, auditable, and consistent with the
repository's current instructions.

## Authority and scope

These documents describe **how development work is performed**. They do not
redefine Watch's architecture, entities, invariants, implementation order, or
technology choices.

Apply the repository sources of truth in this order:

1. [`AGENTS.md`](../../AGENTS.md) defines workspace instructions and authority
   handling.
2. [`CHANGE_MAP.md`](../../CHANGE_MAP.md) identifies which concepts are revised
   and which documents govern them.
3. [`PLAN.md`](../../PLAN.md) defines the current milestone and its acceptance
   criteria.
4. The applicable architecture, invariant, vocabulary, migration, and ADR
   documents define the behavior and constraints relevant to the task. Original
   documents remain authoritative for concepts not explicitly revised in the
   change map.

If sources conflict or authority is unclear, do not resolve the issue by
guessing. Follow [`AGENTS.md`](../../AGENTS.md): stop, report the ambiguity,
and identify the relevant documents. This process documentation cannot
override that rule.

## Documents

- [`codex-workflow.md`](./codex-workflow.md) describes the human–Codex
  collaboration from task intake through handoff.
- [`workflow-validation.md`](./workflow-validation.md) defines simulations as
  a way to evaluate and improve the development workflow and records supported
  findings from this conversation.
- [`task-protocol.md`](./task-protocol.md) gives a practical checklist for
  interpreting and bounding implementation tasks.
- [`verification-protocol.md`](./verification-protocol.md) describes how to
  verify work and report only what was actually checked.
- [`failure-handling.md`](./failure-handling.md) defines how to stop, diagnose,
  and report blockers rather than improvise.

Read only the documents relevant to the current task. These guidelines
complement the existing workflow guidance in
[`docs/06-codex-vscode-workflow.md`](../06-codex-vscode-workflow.md) and task
templates in [`docs/07-codex-task-templates.md`](../07-codex-task-templates.md);
they do not replace or silently revise them.
