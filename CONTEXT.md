# Watch — Session Context

Watch is a persistent, evidence-oriented team system. **Model intelligence is temporary; team experience is persistent.**

## Core architecture

**Worker → Proposal → application validation → Kernel/application commit → durable state.** Model output is never the authority for durable state.

Reactive and deliberative work converge on the same ordinary Task runtime. Tasks, Events, and committed records describe what actually happened; Plans describe intended work.

## Current R6 design direction (architectural principles accepted; phase status in PLAN.md)

R6-G0 and R6-A through R6-E are complete; R6-F Checkpoints 1–4 are merged. C3 was merged by PR #31 at `99f8b6bbd76521eaac47761dcf432ebb3c0d28e3`; final local verification passed 85 focused/579 full-suite tests, Ruff, mypy (27 files), one fresh `0012_learning_foundation` head, and `git diff --check`. The D12 competing-approval loser Task is terminalized and recoverable through TaskRuntime. C4 was merged by PR #32 at `c8e7317da6144a15725231e499b07f1c110c4c22`. Hosted CI run [41599452685](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/41599452685) passed on exact PR head `0b625506`: fresh migration to one `0013_team_experience_projection` head, Ruff, mypy (27 files), and 590 tests. The combined operator-local disposable-PostgreSQL run was not repeated before merge; that gate was expressly waived for integration and remains pending post-merge. C4 includes the separate Team Experience projection/publication ledger, canonical indexing/rebuild, dual-core PostgreSQL hybrid retrieval, Context v2 provenance with immutable v1 replay, D7 policy-pinned UTC review dates, and TaskRuntime-owned review completion. D10 remains create-only for C3; revise/retire are deferred. R6-G remains separately gated. The host owns authentication; no Watch-owned API/CLI or authentication subsystem is added.

## Open the smallest relevant set of documents

1. [`PLAN.md`](PLAN.md) — the only source for current milestone status, gates, and next action.
2. [`AGENTS.md`](AGENTS.md) — repository operating rules and stop conditions.
3. [`CHANGE_MAP.md`](CHANGE_MAP.md) — where each concept is authoritatively specified.
4. [`docs/control-model.md`](docs/control-model.md) — the Revision 2 Control model.
5. Read only the specific supporting source needed for the task:
   - [`docs/invariants.md`](docs/invariants.md) — non-negotiable rules.
   - [`docs/tasks.md`](docs/tasks.md) — Task types, write scopes, and budgets.
   - [`docs/architecture.md`](docs/architecture.md) — the original/general architecture for concepts not replaced by Revision 2.
   - [`docs/glossary.md`](docs/glossary.md) and [`docs/domains.md`](docs/domains.md) — terms and domain-pack boundaries.
   - [`docs/decisions.md`](docs/decisions.md) — ADR index; open the linked ADR when its decision matters.
   - [`docs/testing.md`](docs/testing.md) — verification requirements.

Do **not** read every document at session start. Use the authority map, then follow references relevant to the requested change.

## Authority rules

- `PLAN.md` owns current milestone status; do not copy status claims into other documents.
- `CHANGE_MAP.md` names the authority for revised concepts.
- ADRs record decisions; an ADR marked `Proposed` is not an accepted decision.
- Code presence is not proof that a milestone is authorized or formally closed. Test evidence is not a substitute for a phase gate.
- If authoritative sources conflict or a required gate is unclear, stop and report the exact conflict instead of silently reconciling it.

## Durable boundaries

- Workers propose; application code validates and commits.
- `StateAssessment` is derived, read-only, and non-authoritative.
- A Plan is immutable intended execution structure, not execution truth.
- A Task may be reactive or Plan-linked; both use the same runtime and commit gates.
- Domain packs cannot extend or bypass the Kernel.
