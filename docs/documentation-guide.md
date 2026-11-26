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
- docs/development/r7-b-b6-legacy-lifecycle-hardening-plan.md — canonical B6 audit, scope-freeze, implementation, verification, and acceptance sequence.
- docs/development/r8-delivery-plan.md — canonical R8 scope and acceptance criteria; the former November 23, 2026 start target was withdrawn and the replacement date is TBD. B6 and the RW foundation exit gate precede it.
- docs/development/r8-development-states.md — canonical definitions of R8-ready internal testing and Full Design, including the scope boundary and instructions for developers/coding agents. PLAN.md remains the sole current-state authority.
- docs/development/rw-0-decision-record.md — records Operator-confirmed RW decisions, accepted ADR constraints, and unresolved RW-0 questions. It does not authorize implementation.
- docs/development/rw-implementation-plan.md — RW-1–RW-5 slice boundaries, proof matrix, stop conditions, and foundation exit gate.
- docs/development/rw-4-design-and-acceptance.md — RW-4 signal-triage/retrieval design proposal, source audit, open decisions, proposed implementation sequence, and proof obligations; documentation only, not implementation authorization.
- docs/development/powershell-local-sync-test-script-guide.md — required paste-safe construction, preflight, native-command error handling, environment restoration, and disposable-database rules for generated PowerShell scripts.
- docs/development/rw-value-harness.md — proposed newsroom-first value measurement contract; exact scenario and thresholds are frozen during RW-0.
- docs/documentation-guide.md — this navigation and maintenance policy.

### Orientation

- README.md — public project overview and entry links.
- docs/simple-explain.md — longer plain-language explanation of the product vision and memory model; orientation only, never a status or architecture authority.
- CONTEXT.md — short session orientation and minimum reading path.

These files may summarize status for navigation, but must point to PLAN.md and must not become independent status authorities.

### Stable architecture and domain references

Read when the task needs them:

- docs/architecture.md — general/original architecture where not superseded.
- docs/control-model.md — Revision 2 Control contract.
- docs/invariants.md — non-negotiable system constraints.
- docs/tasks.md — Task types, write scopes, and budgets. For RW work, its implementation-state audit and EvidenceLink contract section distinguish specified behavior from implemented behavior.
- docs/domains.md — domain-pack contracts and open domain questions.
- docs/glossary.md — terminology.
- docs/decisions.md — ADR index; open the relevant ADR, not every ADR.

Accepted ADRs are durable decision records. Do not rewrite their historical acceptance scope to match later implementation. Update an ADR only when its decision or an accepted amendment changes; current delivery status belongs in PLAN.md.

### Historical plans, audits, and closeouts

Completed phase plans, entry gates, implementation audits, regression matrices, workflow simulations, and closeout reports are historical evidence. Examples include the R6 implementation plans, R7-A plan, completed R7-B B0–B3 records, and completed B4 G1–G5 proof plans and the G6 implementation plan (the G6 proof and B4.4 closeout are now complete; this wording describes the historical gate at the time).

Preserve them when they explain a decision, acceptance criterion, verification result, or residual limitation. Do not load them by default. Open only the record relevant to the current invariant or historical question.

A completed plan should state its final disposition and point to PLAN.md for current status. Use the `historical-` filename prefix for completed R6/R7 plans, audits, regression matrices, and closeout records. Use `obsolete-` for retained records that are no longer part of the active workflow. Historical checkpoints must remain clearly labelled as historical; do not rewrite old statements as though they were current when written.

### Testing and verification

docs/testing.md is the evidence archive and testing reference. Its historical entries are not current test instructions unless explicitly identified as such. Use the repository's current test commands and AGENTS.md for the operating procedure. Do not move or delete verification evidence merely to reduce file size.

## Maintenance rules

- Keep current status in PLAN.md; do not copy detailed milestone tables into README, CONTEXT, ADRs, or implementation plans.
- Keep CHANGE_MAP.md focused on authority and implementation locations, not a second project history.
- Keep README.md public-facing and concise.
- Keep CONTEXT.md short enough to orient a new session quickly.
- Keep one canonical delivery plan per active phase. B6 uses docs/development/r7-b-b6-legacy-lifecycle-hardening-plan.md; R8 uses docs/development/r8-delivery-plan.md. Historical schedules are not active plans.
- RW-4 readiness and slice sequencing are governed by `docs/development/rw-4-readiness-and-delivery-plan.md`; the older RW-4 design/decision documents remain supporting proposals and must be reconciled to it. RW-4 production implementation is not authorized.
- Keep accepted ADRs and meaningful historical verification records. Prefer labelling and linking over deleting.
- When a phase closes, update PLAN.md first, then reconcile only the summaries and active plans that need to reflect the new state.
- When recording test results, include the exact commit/PR head, command or workflow, result, and known limitations. Never transfer a test count from one SHA to another.
- Do not claim formal closure from code presence or CI alone; record the explicit gate decision.

## R8 source of truth

docs/development/r8-delivery-plan.md is the sole canonical R8 delivery plan in the repository. The uploaded/exported Project source copy named `R8-Delivery-Plan.txt` is stale and must not be used as an active status or schedule authority. Any exported or copied R8 plan is a convenience copy only and must not be independently maintained. Reconcile useful content into the canonical file before removing or replacing a duplicate from an external Project source set.
