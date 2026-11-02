# Watch — Session Context

Watch is a persistent, evidence-oriented team system. **Model intelligence is temporary; team experience is persistent.**

## Core architecture

**Worker → Proposal → application validation → Kernel/application commit → durable state.** Model output is never the authority for durable state.

Reactive and deliberative work converge on the same ordinary Task runtime. Tasks, Events, and committed records describe what actually happened; Plans describe intended work.

## Current R6 design direction (architectural principles accepted; phase status in PLAN.md)

R6-G0 and R6-A through R6-E are complete. R6-F Checkpoints 1–2 are merged and verified; Checkpoint 3's create-only approval lifecycle is implemented and verified locally and in hosted CI on code head `581ad185` (83 focused and 577 full-suite local tests; 577 hosted tests). Draft [PR #31](https://github.com/abtn/Watch-Architecture-Rev2/pull/31) contains the typed host-principal adapter, approval-specific admission, canonical LearningChange decision service, typed TaskRuntime accepted/rejected finalization, synchronous `admit → decide → finalize`, same-Task replay, and committed-decision recovery. No schema migration was added. **D10 was resolved on 2026-11-02:** Checkpoint 3's production scope is limited to genuine Checkpoint 2 create proposals; revise/retire proposal production and commitment are deferred to a separately authorized knowledge-lifecycle scope. PR #31 remains open/draft/unmerged pending documentation CI, review, and merge. D7 (`review_after`) remains open for Checkpoint 4; Checkpoint 4 and R6-G remain gated. Recovery finalizes an already committed decision before retry/exhaustion; a pre-decision crash follows ordinary Task retry. The host owns authentication; no separate deployed Watch API/CLI or Watch authentication subsystem is planned. ADR-0031 authorizes Cloudflare for R6-E only; no production R6-F provider is approved.

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
