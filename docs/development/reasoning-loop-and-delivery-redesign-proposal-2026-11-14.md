# Proposal (v2): Add the Reasoning Loop Before R8, and Redesign How We Deliver

**Date:** 2026-11-14
**Status:** Proposed for a decision session. Documentation only. It authorizes no implementation, schema change, migration, or PLAN.md change until the Operator records decisions D1–D10.
**Proposed phase name:** `RW` (reasoning slice). The name is the Operator's choice.
**Companion documents:** `project-review-and-implementation-hints.md` (findings F1–F8) and the B5.2 acceptance decision record.

## 1. Purpose

Watch exists to force an LLM to work systematically inside a durable team, so the team becomes expert in a domain. The architecture says how: the model proposes, code validates and commits, and reasoning runs through Threads, competing Hypotheses, verified evidence and graded confidence (INV-04 to INV-08, flow F2).

This proposal does two things:

1. **Product path:** add the missing reasoning loop before the R8 pressure test.
2. **Delivery process:** change how we build, so the problems below do not recur.

## 2. Criticism of the path so far

These are findings about the process, not about the people or the architecture, which is sound. Each is grounded in the repository as read; nothing was executed.

| # | Criticism | Evidence |
|---|---|---|
| C1 | **Depth before breadth.** Roughly two weeks of R7-B went into governing how learned lessons are revised, retired and superseded, before the loop that produces knowledge existed. | No `threads`, `hypotheses` or `confidence_changes` tables in `core/models.py`. No `update_thread` worker. Their names appear only in `core/ingestion.py`. |
| C2 | **Milestones close on contracts and CI, not on value.** Nothing measures whether a team gets better at a domain. The only integrated path is the R6-G three-case fixture. | PLAN.md exit criteria are proofs, hashes and approvals. R8 has no defined value metric. |
| C3 | **Proof comes after the code, every time.** B2 left residual gaps, B4 needed a six-part G1–G6 follow-up, and B5.2 has six open gaps. The plan lists required tests, but nothing enforces them. | B5.2 moved the suite from 961 to 962 tests for a whole operation. |
| C4 | **Spec runs ahead of code, and the docs read as finished.** `architecture.md` describes flows F1–F8 as the system. Only part exists. | `update_thread`, `triage_signal`, `apply_decay`, `render_output`, Consultations and the setup advisor have no implementation. |
| C5 | **Status is duplicated and drifts.** The "single source of status" rule is broken by long narratives copied across files. | PLAN.md still calls PR #113 open and closure pending after recording B4.4 as closed. The R8 plan repeats bullets and calls #113 unmerged. |
| C6 | **Paperwork grows with each slice.** A slice tends to need a documentation PR, an implementation PR, a proof follow-up and a closeout PR, each with its own evidence narrative. | B4.4 (#103–#114), B5.2 documentation checkpoint plus implementation. |
| C7 | **Dates drove scope.** The R8 date and entry gate were set before prerequisites were settled. | R8 is scheduled 2026-11-23 while B5.2 is unaccepted and the reasoning layer is absent. |
| C8 | **Cheap hygiene left open.** | 113 constant Alembic warnings, one unexplained 36-failure run, migration filename/revision mismatches. |
| C9 | **Claims are copied faster than they are verified.** This includes my own work in this conversation: my first B5.2 draft repeated "CI passed on latest head" from the report without tracing it to the PR, and marked decisions "Accepted" while the status said "Proposed". | The corrections made earlier in this conversation. |

**What to keep:** the single propose/validate/commit path, immutable evidence, exact-SHA verification, disposable-PostgreSQL race tests, the stop conditions, and Operator approval at gates. The problem is sequencing and enforcement, not rigor.

## 3. What this is and is not

**It is a re-sequencing plus a process redesign.** The Hypothesis design already exists: ADR-0001 to ADR-0019, `docs/architecture.md` §3 and §5 (F1–F3), the `docs/tasks.md` write-scope matrix, and INV-04 to INV-08.

**It is not a Kernel redesign.** No new write path, runtime, scheduler or model-writable policy. One real contract question exists: the `evidence_links` table is restricted to `subject_kind = 'evaluation'` with `outcome`/`signal` sources, so carrying hypothesis evidence changes an accepted shape (D3).

## 4. Redesign of the delivery process

### 4.1 Walking skeleton and a value harness (fixes C1, C2, C7)
Before any new subsystem, define one thin, repeatable end-to-end scenario on one real domain, and run it at every milestone gate: source → Thread/Hypothesis → Task → Outcome → Evaluation → lesson → retrieval in the next run. Record a small fixed set of numbers each time:

- share of model claims that survive deterministic validation, and the rejection rate;
- whether a second run of the same task improves because of retained experience (rule-based comparison where possible);
- Hypothesis confidence calibration against recorded Outcomes.

A milestone that cannot say which number it moves, or which part of the vision it serves, goes on a parked list until the harness shows a need.

### 4.2 One slice, one PR set, proofs included (fixes C3, C6)
A slice is code, its full proof matrix and its documentation update, merged together. There are no separate proof sub-phases and no closeout sub-phase. "Implementation complete" means every required-test row names a test that passes.

### 4.3 Machine-checked proof matrix (fixes C3)
For each slice, keep a short matrix file: requirement ID → test node ID. Mark tests with `@pytest.mark.proof("<id>")`. A small CI script fails the build if a listed ID has no test or no passing result. Also flag suspicious deltas (for example, one new test for a whole operation) for human review.

### 4.4 Status that cannot drift (fixes C5)
Keep PLAN.md to about one page of current state. Move verification narratives to `docs/testing.md` as structured records (exact verified code head, current PR head, CI run IDs, test count, warning count). Link instead of copying. Add two fields to every PR summary: **verified code head** and **current PR head**, each with its CI run, or "unconfirmed". At each documentation checkpoint, sweep for stale "open PR" and "pending" text.

### 4.5 Spec honesty (fixes C4)
Add an `Implemented: yes | partial | no (migration / test)` marker to each entity and flow in `architecture.md` and `tasks.md`. A small script compares the entity list against `core/models.py` and flags a spec entity with no table.

### 4.6 Complexity budget and scope-cut order (fixes C1, C7)
Every new operation, table or phase must name the harness number or vision element it serves. When a date is at risk, cut features in a pre-agreed order and never cut proofs. Keep one slice in flight at a time.

### 4.7 Hygiene PR, separately authorized (fixes C8)
- Add `path_separator` to `alembic.ini` to remove the 113 warnings.
- Align migration filenames with revision IDs, or document the difference.
- Investigate the 36-failure run: run the full suite repeatedly, once with concurrency tests isolated and once included, in fixed and random order. Record the result in `docs/testing.md`.

### 4.8 Test and code structure (supports all of the above)
- Split `tests/test_experience_distiller.py` (10,881 lines) by area with shared fixtures, in a PR that changes no test bodies.
- Extract a generic race helper so a new race test is a few lines.
- Prefer several small tests over one long integrated test, so a failure does not hide later checks.
- Put the per-operation branches of `learning_commit.py` behind one small interface, as its own behavior-preserving PR, using existing tests as the safety net.

### 4.9 Verifying claims (fixes C9)
Every number, SHA and "passed" in a report or summary must be traceable to a source: a run ID, a command output or a file. Reviewers, human or AI, reject summaries that cannot cite one.

## 5. Proposed product path

**Finish** B5.2 to its accepted bar (race, stale-state, replay and negative-case proofs). **Park** B5.3, B5.4, B6 and R7-C. The R8 plan already excludes them unless a blocker appears. Check the legacy-snapshot retirement question (F8) before B6.

**Insert RW before R8:**

| Slice | Content | Prevents |
|---|---|---|
| RW-0 | Documentation only: the value harness definition, resolution of D1–D10, updates to PLAN.md, CHANGE_MAP.md, `docs/tasks.md` and the R8 plan. Ends with a recorded decision. | C1, C2, C7 |
| RW-1 | Schema: `threads`, `hypotheses`, `confidence_changes`, plus a minimal `signal_dispositions` only if triage is in scope. Widen `evidence_links` as D3 decides. One migration, one head. Constraint tests for each CHECK/FK. | C3 |
| RW-2 | Deterministic commit service with **no LLM**, entered through `operator_update` (human as worker, ADR-0021). Proves INV-04 to INV-07 without model nondeterminism. | C3 |
| RW-3 | `update_thread` model worker: bounded Context, typed proposal schema, existing generation provider and cost accounting, rejection Events with reasons. | Model nondeterminism |
| RW-4 | Minimal deterministic `triage_signal` (Operator-created Threads acceptable at first), and a read path so Hypotheses enter Task Context as Domain Knowledge. | Scope creep |
| RW-5 | `apply_decay` (F3). Before or after R8 per D2. | |

**Deferred beyond R8 unless a blocker appears:** `render_output`/Artifacts, Consultations, the setup advisor and `TeamDraft`, and domain-pack machinery beyond a configured Team plus generalist defaults.

## 6. Required proofs for the reasoning loop

Each needs its own database-backed test in the same slice as its code, and a mutation check (remove the guard in a scratch copy and confirm the test fails).

1. A quote that is not the exact substring at the offsets of the hashed Snapshot is rejected, and nothing is written (INV-04).
2. Evidence with stance `mentions` cannot anchor a ConfidenceChange (INV-06).
3. A ConfidenceChange without exactly one valid cause is rejected (INV-05).
4. A new favored Hypothesis never deletes or silently demotes a rival. Rejection and supersession need a reason and an Event (INV-07).
5. An unsubstantiated Hypothesis, model- or human-authored, enters at `low` (ADR-0021).
6. A proposal set commits atomically or not at all; one invalid proposal rejects the set with recorded reasons.
7. Replay of the same Task or proposal creates no duplicate evidence, Hypothesis or confidence change.
8. Concurrent `update_thread` Tasks on one Thread: exactly one wins or both serialize cleanly, with no lost update. Run each race test repeatedly, not once.
9. Cross-Team Thread, Hypothesis, Signal or Snapshot references are rejected.
10. `last_touched_at` moves only when evidence is accepted. Quiet time never rejects a Hypothesis (INV-08).

## 7. Guardrails: where each slice is likely to fail

| Slice | Likely failure | Prevention |
|---|---|---|
| RW-1 | Widening `evidence_links` breaks existing evaluation evidence or hash constraints. | Run the existing evidence and distillation suites first; add constraint tests for both subject kinds. |
| RW-2 | Validation passes the happy path only. | Write the rejection proofs (§6) before the success path; apply mutation checks. |
| RW-3 | Tests depend on live model output and flake. | Stubbed-provider fixtures for all proofs; one live smoke test kept separate. |
| RW-3 | Rejection rate is hidden. | Emit rejection reasons as Events; the harness reports the rate. |
| RW-4 | Triage grows into a heuristic engine. | Operator-created Threads first; minimal deterministic matching only. |
| All | "Done" declared with gaps. | Proof matrix in CI (§4.3); one slice in flight. |
| All | Status drift after merge. | Two-SHA PR fields and the documentation sweep (§4.4). |

## 8. Decisions requested

| # | Decision | Recommendation |
|---|---|---|
| D1 | Insert RW before R8 and park B5.3, B5.4, B6, R7-C? | Yes, after finishing B5.2 to its accepted bar. |
| D2 | Re-baseline the R8 date? | Yes. Do not compress proofs to hold 2026-11-23. My estimate, not based on measured velocity, is that RW-0 to RW-3 will not fit in the remaining days. Decay after R8 unless R8 needs it. |
| D3 | Widen `evidence_links` or add a sibling table? | Widen it, matching the polymorphic design in the ADRs. If this changes an accepted contract, record an ADR addendum before RW-1. |
| D4 | Build `operator_update` before `update_thread`? | Yes. |
| D5 | Allow a bounded model "repair" re-proposal after a rejection? | Not in the first slice. Measure the rejection rate first. |
| D6 | Model-call test strategy? | Stubbed fixtures for proofs, one separate live smoke test. |
| D7 | Link Hypotheses into Evaluation and distillation now? | No. Keep R6/R7 flows unchanged until RW-3 has data. |
| D8 | Who freezes the value metrics and when? | The Operator, at the R8 entry gate, before any scenario runs. |
| D9 | Adopt the process redesign in §4 (proof matrix in CI, two-SHA PR fields, one-page PLAN.md, spec markers, complexity budget)? | Yes. Start with §4.3 and §4.4, which are cheap and address the most repeated failures. |
| D10 | Authorize the hygiene and test-structure PRs (§4.7, §4.8) as separate, behavior-preserving work? | Yes, scheduled between slices so they do not interleave with feature PRs. |

## 9. Boundaries and process

- No new Task type beyond `docs/tasks.md`, no new runtime, scheduler, dispatcher or authentication boundary, and no model writes to TeamPolicy or KnowledgeItem (INV-12).
- Domain knowledge stays outside the Kernel. A domain that needs a Kernel change is a stop-and-return finding.
- AGENTS.md stop conditions apply. Each slice needs separate authorization, exact-head CI, a local full-suite run on disposable PostgreSQL, and explicit Operator acceptance.

## 10. Session outputs

1. Recorded decisions on D1–D10.
2. An RW implementation plan in `docs/development/` with slices, proof matrices and stop conditions.
3. The value harness definition (RW-0).
4. PLAN.md, CHANGE_MAP.md, `docs/tasks.md` and R8 plan updates for the new order and date.
5. An ADR addendum if D3 changes an accepted contract.
6. A short process-changes note covering §4.3 to §4.5 (PR template fields, the CI proof check, spec markers).

## 11. Risks

- **Process overhead:** §4 adds checks. Keep them small and automated; if a check needs manual upkeep it will drift like the status text did.
- **Scope creep:** hold the slice boundaries in §5.
- **Model nondeterminism:** D4 and D6.
- **Schedule pressure:** decide D2 explicitly so the date does not set the scope.
- **Unverified assumptions:** this proposal rests on a static read of a snapshot. The first act of RW-0 is to confirm the gaps in §2 against the current `main`.

---

## Operator roadmap decision — 2026-11-15

This dated addendum records decisions made after the proposal was written. It does not rewrite the original proposal or silently accept every D1–D10 recommendation.

### Decisions now established

1. **The complete foundational architecture must precede R8.** R8 is a pressure test of the integrated architecture, not a development phase in which a missing fundamental layer such as the reasoning loop is added.
2. **R8 is planned to start on November 23, 2026.** November 23 is not an R8 completion deadline. R8 has no fixed completion date in this decision.
3. **The current lifecycle position is B6.** B5.4 is complete and closed; it must not be reopened without a demonstrated defect. B6 is the next lifecycle track and begins with baseline verification and a read-only audit.
4. **The intended sequence is B6 → RW-0 through RW-5 → foundation exit gate → R8.** If the foundation is not ready, R8 does not start on the target date. Do not compress unfinished architecture into R8 or weaken the entry gate.

### B6 boundary

The B6 audit must define the actual scope from demonstrated defects and missing regression proofs. It must investigate F8 (legacy-rooted KnowledgeItems and retirement eligibility), but must not assume that the dead end exists. No production changes, migrations, broad refactors, or implementation branch are authorized by the audit itself. Implementation requires a reviewed acceptance checklist and explicit Operator scope approval.

The current B6 delivery plan is [r7-b-b6-legacy-lifecycle-hardening-plan.md](r7-b-b6-legacy-lifecycle-hardening-plan.md).

### Decisions still open

The remaining D1–D10 details—including the minimum EvidenceLink contract, vertical-slice design, exact value-harness measures, and whether R7-C capabilities are needed to measure retained-experience use—must be recorded explicitly during RW-0. RW-0 must also decide whether other specified future capabilities (rendered Artifacts/output, Consultations, the setup advisor, TeamDraft, and expanded domain-pack machinery) are truly foundational to the chosen R8 product claim or can remain deferred. This addendum does not imply that every proposal decision has been resolved or that RW implementation is authorized.

The original D1 wording that parks B5.4 is superseded: B5.4 is already complete. B6 is not parked; it is the next planned lifecycle track.


---

## Operator Checkpoint B addendum — 2026-11-15

This addendum records the additional Operator decision and points to the detailed RW-0 artifacts. It preserves the original proposal and the earlier roadmap addendum as historical records.

### Confirmed

- **Newsroom is the first real-world domain for the RW value harness.** The exact newsroom beat, source corpus, task brief, independent outcome set, and scoring thresholds remain to be frozen during RW-0.
- Checkpoint B is being documented on PR #123. This documentation work does not authorize RW implementation, schema changes, migrations, production code, or tests.
- The accepted EvidenceLink target is already defined by ADR-0007 and ADR-0020: one shared polymorphic model with Hypothesis/Evaluation subjects and Signal/Outcome/Artifact/Consultation sources. The current ORM is narrower; RW-1 must reconcile implementation with those accepted decisions rather than create a sibling evidence system.

### Still open

R7-C inclusion; whether persistent Artifact/output, Consultation workflows, setup advisor/TeamDraft, and expanded domain-pack machinery are foundational to the selected newsroom product claim; the exact newsroom scenario and thresholds; and the remaining RW-0 design decisions listed in the [RW-0 decision record](rw-0-decision-record.md).

### Current planning artifacts

- [RW-0 decision record](rw-0-decision-record.md)
- [RW implementation plan and proof matrix](rw-implementation-plan.md)
- [Newsroom value harness](rw-value-harness.md)

The detailed plan remains proposed until RW-0 is completed after B6 and the Operator explicitly authorizes the next implementation slice.

### Checkpoint B contract clarification — proposal-batch atomicity

The original proposal's §6 wording that one invalid proposal rejects an entire proposal set is a proposal, not an accepted contract. The current canonical `docs/tasks.md` and `docs/architecture.md` wording is: valid proposals commit atomically as one set; invalid proposals are rejected with reason Events; a Task whose proposals all fail is marked failed. RW-0 must confirm the exact mixed valid/invalid batch semantics before RW-2. Until an explicit Operator decision changes the contract and the canonical specifications are updated, implementation and tests must preserve the existing Task contract; do not silently strengthen or weaken it.
