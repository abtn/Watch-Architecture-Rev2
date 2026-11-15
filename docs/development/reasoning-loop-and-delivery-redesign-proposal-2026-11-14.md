# Proposal: Add the Reasoning Loop Before R8, and Redesign How We Deliver

**Date:** 2026-11-14  
**Status:** Proposed for a decision session. Documentation and discussion only. This proposal authorizes no implementation, schema change, migration, or PLAN.md change until the Operator records decisions D1–D10.  
**Proposed phase name:** RW (reasoning slice); the name is the Operator's choice.

## 1. Purpose

Watch aims to make AI-assisted teams systematic by requiring work to pass through durable, governed records. The architecture describes a reasoning loop built around Threads, competing Hypotheses, verified evidence, and graded confidence (INV-04 to INV-08; architecture flows F1–F3).

This proposal has two parts:

1. **Product path:** add the missing reasoning loop before the R8 pressure test, if the Operator decides that R8 must validate the complete Watch vision.
2. **Delivery process:** change how slices are scoped, implemented, proved, documented, and accepted so recurring process problems do not continue.

## 2. Criticism of the path so far

These are process findings, not personal criticism. They were prepared from a static repository read on 2026-11-14; the current-main review in the companion project-path review records which findings still hold.

| # | Criticism | Evidence cited in the original report |
|---|---|---|
| C1 | **Depth before breadth.** Significant R7-B effort went into governing revisions, retirement, and supersession of lessons before the loop that produces world knowledge existed. | No Thread, Hypothesis, or ConfidenceChange tables and no update_thread worker in the code. |
| C2 | **Milestones close on contracts and CI, not on value.** The project lacks a stable measure of whether a team becomes better at its domain. | The R8 acceptance criteria are mostly scenario and safety proofs; no value metric was defined. |
| C3 | **Proof comes after code.** Follow-up proof work repeatedly expanded after an implementation was first presented as complete. | B2 residual gaps, B4 G1–G6 follow-up proofs, and B5.2 supplemental acceptance proofs; the report noted a one-test increase for one operation. |
| C4 | **Specification runs ahead of implementation.** The architecture can read as though all described flows are present. | F1–F8 and their entities/tasks are specified, but several have no implementation. |
| C5 | **Status is duplicated and drifts.** Historical narrative is copied into active documents and later becomes contradictory. | Stale PR #113 and closure statements appeared in PLAN.md and the R8 plan. |
| C6 | **Paperwork grows with each slice.** A slice can produce a planning PR, implementation PR, proof follow-up, and closeout PR. | The B4.4 and B5.2 delivery sequences. |
| C7 | **Dates drive scope.** A fixed R8 date and entry gate were set while important prerequisites and product scope remained unsettled. | R8 target November 23, 2026, while the reasoning layer was absent and B5.2 acceptance was still in progress at the report date. |
| C8 | **Cheap hygiene stays open.** Known warnings and unexplained failures remain unresolved. | 113 Alembic warnings, one unexplained 36-failure run, and alleged migration filename/revision mismatches. |
| C9 | **Claims are copied faster than verified.** Summaries can repeat a passed status or acceptance claim without tracing it to the exact source. | The author identified an earlier B5.2 draft that repeated an unverified CI claim and marked decisions Accepted while the proposal status remained Proposed. |

**What to keep:** the single propose/validate/commit path, immutable evidence, exact-SHA verification, disposable-PostgreSQL race tests, stop conditions, and Operator approval at gates. The criticism is about sequencing and enforcement, not a request to weaken rigor.

## 3. What this is and is not

This is a proposed resequencing and delivery-process redesign. The Hypothesis design already exists in ADRs, architecture sections F1–F3, the Task write-scope matrix, and INV-04 to INV-08.

It is **not** a Kernel redesign. It proposes no second write path, runtime, scheduler, or model-writable policy. One contract question must be resolved before implementation: the current EvidenceLink design is restricted to evaluation subjects and outcome/signal sources in the existing schema; carrying Hypothesis evidence may change an accepted shape (D3).

## 4. Proposed delivery-process redesign

### 4.1 Walking skeleton and value harness

Before adding another subsystem, define one thin, repeatable end-to-end scenario on one real domain:

source → Thread/Hypothesis → Task → Outcome → Evaluation → lesson → retrieval in a later run.

At each milestone gate, record a small fixed set of measures:

- share of model claims accepted by deterministic validation, with rejection reasons;
- whether a second run improves through retained experience, using a rule-based or independently assessed comparison where possible;
- Hypothesis confidence calibration against recorded Outcomes.

A milestone must identify which measure or vision element it serves. A metric is a diagnostic, not automatically a success target: a lower rejection rate, for example, could mean weaker validation rather than better proposals.

### 4.2 One slice, one reviewable PR set, proofs included

A slice should include code, its full proof matrix, and necessary documentation changes in the same reviewable PR set. Implementation is not complete while required-test rows are missing. Separate PRs remain appropriate where an independent authorization or review gate requires them.

### 4.3 Machine-checked proof matrix

For each slice, maintain a short mapping from requirement ID to pytest node ID. Mark tests with a proof identifier and make CI fail if a required identifier has no collected test or its test fails. Flag suspicious test-count or coverage deltas for human review rather than treating a crude count heuristic as proof.

### 4.4 Status that cannot drift

Keep PLAN.md focused on current state and next action. Keep verification narratives in docs/testing.md as structured evidence records containing the exact code/test head, documentation-inclusive PR head, CI run IDs, test count, warning count, and limitations.

Every PR summary should state:

- **Verified code/test head** and the CI run for that exact head.
- **Current PR head** and the CI run for that exact head, or explicitly say unconfirmed.

At each documentation checkpoint, search for stale open-PR, pending, and authorization language. Link to evidence instead of copying it.

### 4.5 Specification honesty

Add an Implemented: yes / partial / no marker to each entity and flow in architecture.md and tasks.md, with concise evidence. A checker should compare specification claims with models, migrations, services, Task handlers, and tests. A table's presence alone does not prove that a flow is implemented.

### 4.6 Complexity budget and scope-cut order

Every new operation, table, or phase must name the value-harness measure or vision element it serves. Keep one feature slice in flight at a time. When a date is at risk, cut nonessential features in a pre-agreed order; never cut required proofs.

### 4.7 Hygiene PR, separately authorized

- Add Alembic path_separator configuration to remove the known deprecation warnings, after verifying the correct configuration.
- Align migration filenames with revision IDs, or document deliberate differences.
- Investigate the historical 36-failure run with isolated and integrated full-suite runs in controlled order, then record what is known and what remains unknown.

### 4.8 Test and code structure

- Split the very large experience-distiller test module by area, initially without changing test bodies.
- Extract a small shared race-test helper only if it reduces duplication without hiding the concurrency behavior under test.
- Prefer independently diagnosable tests over one long test that can stop at its first failure.
- Simplify the per-operation branches in the learning commit service in a separate behavior-preserving change, protected by existing tests.

### 4.9 Verify claims

Every number, SHA, and passed/accepted statement in a report must point to a run ID, command output, source file, or recorded Operator decision. Untraceable claims should be marked unconfirmed, not repeated as fact.

## 5. Proposed product path

The original proposal recommended:

- Finish B5.2 to its accepted bar.
- Park B5.3, B5.4, B6, and R7-C.
- Insert RW before R8:
  - **RW-0:** documentation and decision session; freeze the value harness, resolve D1–D10, and update the relevant plans only after those decisions.
  - **RW-1:** schema for Threads, Hypotheses, and ConfidenceChanges; add SignalDispositions only if triage is in scope; resolve the EvidenceLink contract.
  - **RW-2:** deterministic commit service with no LLM, entered through the Operator path, proving INV-04 to INV-07.
  - **RW-3:** model-backed update_thread worker with bounded context, typed proposals, existing provider/cost accounting, and rejection Events.
  - **RW-4:** minimal deterministic triage and a read path that makes Hypotheses available in Task context.
  - **RW-5:** scheduled belief decay, before or after R8 according to the Operator's decision.

The original proposal deferred rendered Artifacts, Consultations, the setup advisor/TeamDraft, and domain-pack machinery beyond the initial reasoning slice unless an actual blocker requires them.

## 6. Required proofs for the reasoning loop

Each proof should have its own database-backed test in the same slice as its code. The proposal also asks for mutation checks on critical guards.

1. A quote that is not the exact substring at the offsets of the hashed Snapshot is rejected, with no partial write (INV-04).
2. Evidence with stance mentions cannot anchor a ConfidenceChange (INV-06).
3. A ConfidenceChange without exactly one valid cause is rejected (INV-05).
4. A favored Hypothesis never silently deletes or demotes a rival; rejection and supersession require a reason and Event (INV-07).
5. An unsubstantiated Hypothesis, whether model- or human-authored, enters at low (ADR-0021).
6. A proposal set commits atomically or not at all; invalid proposals are rejected with recorded reasons.
7. Replay creates no duplicate evidence, Hypothesis, or confidence change.
8. Concurrent update_thread Tasks on one Thread serialize without lost updates; repeat the race test.
9. Cross-Team Thread, Hypothesis, Signal, or Snapshot references are rejected.
10. last_touched_at changes only when evidence is accepted; quiet time never rejects a Hypothesis (INV-08).

## 7. Guardrails

- **RW-1:** preserve existing evaluation evidence and hash constraints while resolving EvidenceLink polymorphism; add constraint tests for both subject kinds.
- **RW-2:** write rejection proofs before relying on the success path; use mutation checks for critical guards.
- **RW-3:** stub providers for deterministic tests; keep any live-model smoke test separate; emit rejection Events.
- **RW-4:** start with Operator-created Threads and avoid a heuristic engine until evidence justifies it.
- **All slices:** enforce the proof matrix and keep one feature slice in flight.

## 8. Decisions requested

| # | Decision | Original recommendation |
|---|---|---|
| D1 | Insert RW before R8 and park B5.3, B5.4, B6, R7-C? | Yes, after B5.2 acceptance. |
| D2 | Re-baseline the R8 date? | Yes; do not compress proofs to preserve November 23. |
| D3 | Widen EvidenceLink or add a sibling table? | Widen it, with an ADR addendum if an accepted contract changes. |
| D4 | Build operator_update before update_thread? | Yes. |
| D5 | Allow one bounded model repair re-proposal after rejection? | No; measure rejection first. |
| D6 | Model-call test strategy? | Stubbed proofs plus one separate live smoke test. |
| D7 | Link Hypotheses into Evaluation/distillation now? | No; keep R6/R7 flows unchanged until RW-3 has evidence. |
| D8 | Who freezes value metrics and when? | The Operator at the R8 entry gate, before scenarios run. |
| D9 | Adopt process changes in §4? | Yes; begin with proof matrix and two-SHA PR reporting. |
| D10 | Authorize hygiene and test-structure PRs separately? | Yes, scheduled between feature slices. |

**No decision in this table is accepted by inclusion in this document.** The Operator must explicitly record each decision.

## 9. Boundaries

- No new Task type beyond docs/tasks.md, no new runtime, scheduler, dispatcher, or authentication boundary.
- No model writes to TeamPolicy or KnowledgeItem (INV-12).
- Domain knowledge remains outside the Kernel. A domain requiring a Kernel change is a stop-and-return finding.
- AGENTS.md stop conditions apply. Each implementation slice requires separate authorization, exact-head CI, local full-suite verification on disposable PostgreSQL, and explicit Operator acceptance.

## 10. Session outputs requested

1. Recorded decisions D1–D10.
2. An RW implementation plan in docs/development with slices, proof matrices, and stop conditions.
3. The RW-0 value-harness definition.
4. Authorized updates to PLAN.md, CHANGE_MAP.md, docs/tasks.md, and the R8 plan.
5. An ADR addendum if D3 changes an accepted contract.
6. A short process-changes note covering the proof matrix, two-SHA PR fields, and specification markers.

## 11. Risks and first action

- **Process overhead:** automate only small checks; avoid a manual registry that will drift.
- **Scope creep:** preserve slice boundaries.
- **Model nondeterminism:** use deterministic stubs for proofs.
- **Schedule pressure:** decide explicitly whether R8 is still a fixed target.
- **Unverified assumptions:** the original report was based on a static snapshot. The first step is to re-check each finding against current main.
