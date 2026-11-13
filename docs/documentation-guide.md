# Documentation Guide

## Purpose

This guide defines where project information belongs and what an agent or programmer should read first. It reduces repeated status summaries and unnecessary context loading without deleting accepted decisions or historical evidence.

## Authority order

1. **Current milestone status and authorization — PLAN.md.** It is the only current status authority. Other documents link to it instead of maintaining independent status tables.
2. **Concept ownership and specification location — CHANGE_MAP.md.** It points to the canonical specification, accepted ADR, implementation, and tests for each concept.
3. **Repository operating rules — AGENTS.md.** It governs safe changes, verification, and stop conditions.
4. **Concept contract — the linked canonical specification or accepted ADR.** The actual contract lives in that source, not in this navigation guide.
5. **Implementation truth — current code, migrations, tests, exact Git state, and verified CI.** Plans and documentation do not override implementation evidence.
6. **Verification instructions and evidence — docs/testing.md.** Read the relevant section; historical results prove only the exact commands and snapshots recorded.

If these sources conflict, stop and report the exact conflict. Do not silently choose a status or reinterpret a proposed ADR as accepted.

## Normal session reading set

For ordinary repository work, start with:

- PLAN.md
- CHANGE_MAP.md
- AGENTS.md

Then open only the canonical spec/ADR, Task contract, implementation plan, code, and tests relevant to the requested slice.

Use CONTEXT.md and README.md for orientation, not as additional authorities. Do not read the full documentation tree at session start.

## Document classes

### Active project control

- PLAN.md — current milestone state, gates, authorization, next action.
- CHANGE_MAP.md — concept-to-authority map.
- AGENTS.md — repository operating contract.
- docs/development/r8-delivery-plan.md — canonical R8 scope, schedule, entry gate, and acceptance criteria while R8 is the next planned delivery.
- docs/documentation-guide.md — this navigation and maintenance policy.

### Orientation

- README.md — public project overview and entry links.
- CONTEXT.md — short session orientation and minimum reading path.

These files may summarize status for navigation, but must point to PLAN.md and must not become independent status authorities.

### Stable architecture and domain references

Read when the task needs them:

- docs/architecture.md — general/original architecture where not superseded.
- docs/control-model.md — Revision 2 Control contract.
- docs/invariants.md — non-negotiable system constraints.
- docs/tasks.md — Task types, write scopes, and budgets.
- docs/domains.md — domain-pack contracts and open domain questions.
- docs/glossary.md — terminology.
- docs/decisions.md — ADR index; open the relevant ADR, not every ADR.

Accepted ADRs are durable decision records. Do not rewrite their historical acceptance scope to match later implementation. Update an ADR only when its decision or an accepted amendment changes; current delivery status belongs in PLAN.md.

### Historical plans, audits, and closeouts

Completed phase plans, entry gates, implementation audits, regression matrices, workflow simulations, and closeout reports are historical evidence. Examples include the R6 implementation plans, R7-A plan, completed R7-B B0–B3 records, and completed B4 G1–G5 proof plans and the G6 implementation plan (G6 proof complete; B4.4 closeout still separately gated).

Preserve them when they explain a decision, acceptance criterion, verification result, or residual limitation. Do not load them by default. Open only the record relevant to the current invariant or historical question.

A completed plan should state its final disposition and point to PLAN.md for current status. Historical checkpoints must remain clearly labelled as historical; do not rewrite old statements as though they were current when written.

### Testing and verification

docs/testing.md is the evidence archive and testing reference. Its historical entries are not current test instructions unless explicitly identified as such. Use the repository's current test commands and AGENTS.md for the operating procedure. Do not move or delete verification evidence merely to reduce file size.

## Maintenance rules

- Keep current status in PLAN.md; do not copy detailed milestone tables into README, CONTEXT, ADRs, or implementation plans.
- Keep CHANGE_MAP.md focused on authority and implementation locations, not a second project history.
- Keep README.md public-facing and concise.
- Keep CONTEXT.md short enough to orient a new session quickly.
- Keep one canonical delivery plan per active phase. For R8, that file is docs/development/r8-delivery-plan.md.
- Keep accepted ADRs and meaningful historical verification records. Prefer labelling and linking over deleting.
- When a phase closes, update PLAN.md first, then reconcile only the summaries and active plans that need to reflect the new state.
- When recording test results, include the exact commit/PR head, command or workflow, result, and known limitations. Never transfer a test count from one SHA to another.
- Do not claim formal closure from code presence or CI alone; record the explicit gate decision.

## R8 source of truth

docs/development/r8-delivery-plan.md is the sole canonical R8 delivery plan in the repository. Any exported or copied R8 plan is a convenience copy only and must not be independently maintained. Reconcile useful content into the canonical file before removing a duplicate from an external Project source set.
