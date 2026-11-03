# Watch — Session Context

Watch is a persistent, evidence-oriented team system. **Model intelligence is temporary; team experience is persistent.**

## Core architecture

**Worker → Proposal → application validation → Kernel/application commit → durable state.** Model output is never the authority for durable state.

Reactive and deliberative work converge on the same ordinary Task runtime. Tasks, Events, and committed records describe what actually happened; Plans describe intended work.

## Current R6 design direction (architectural principles accepted; phase status in PLAN.md)

R6-G0 and R6-A through R6-E are complete; R6-F Checkpoints 1–2 are merged. C3 is implemented on [PR #31](https://github.com/abtn/Watch-Architecture-Rev2/pull/31), with hosted CI green on follow-up head `b9f1baf` (fresh PostgreSQL migration/head, Ruff, mypy 27 files, 579 tests). The D12 competing-approval fix makes a losing Task fail through TaskRuntime and recover consistently; this exact follow-up still needs operator-local disposable-PostgreSQL verification. C3's earlier code head `581ad185` passed 83 focused and 577 full-suite local tests. C4 is separately authorized and implemented on stacked [PR #32](https://github.com/abtn/Watch-Architecture-Rev2/pull/32); the user-local 588-test run on `8333d69` predates the D12 follow-up, so sequential integration remains. D10 is resolved: C3 is create-only and revise/retire proposal production/commitment are deferred. D7 is resolved: optional TeamPolicy interval pinned to the approval Task, UTC due boundary, NULL excluded from retrieval, and the deterministic review_knowledge Task owns active → needs_review. No schema migration was added for C3. The host owns authentication; no Watch-owned API/CLI or auth subsystem is added. C4 is outside this PR; R6-G remains separately gated.

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
