# Watch — Session Context

Watch is a persistent, evidence-oriented team system. **Model intelligence is temporary; team experience is persistent.**

## Core architecture

**Worker → Proposal → application validation → Kernel/application commit → durable state.** Model output is never the authority for durable state.

Reactive and deliberative work converge on the same ordinary Task runtime. Tasks, Events, and committed records describe what actually happened; Plans describe intended work.

## Current R6 design direction (architectural principles accepted; phase status in PLAN.md)

R6-G0 and R6-A through R6-E are complete. R6-F Checkpoints 1–2 are merged and verified; Checkpoint 3 is authorized/open. Draft [PR #31](https://github.com/abtn/Watch-Architecture-Rev2/pull/31) implements the typed host-principal adapter, approval-specific ordinary Task admission, create-only canonical LearningChange decision service, typed accepted/rejected TaskRuntime finalization, synchronous `admit → decide → finalize` orchestration, and committed-decision recovery. The request/Task and admission slices were locally verified on `2619eda` and `96bbddec`; the decision-service slice was locally verified on `bddd1e9` (78 focused Checkpoint 3 tests and 572 full-suite tests on disposable PostgreSQL). Finalization/orchestration code head `1c21b60` passed hosted CI run [41457072927](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/41457072927): fresh migrations, Ruff, mypy (27 source files), and 577 tests. Operator-local verification of this final increment remains pending. Recovery finalizes an already committed decision before retry/exhaustion; a pre-decision crash follows ordinary Task retry. The host owns authentication; no separate deployed Watch API/CLI or Watch authentication subsystem is planned. Checkpoint 4 and R6-G remain gated. ADR-0031 authorizes Cloudflare for R6-E only; no production R6-F provider is approved.

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
