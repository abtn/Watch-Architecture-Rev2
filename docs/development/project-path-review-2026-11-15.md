# Project path review: reasoning loop and delivery process

**Review date:** 2026-11-15
**Repository snapshot:** main at `29c954fe8685e0a5ddb9b205277a28b1a158c57e`
**Inputs:** the Operator's 2026-11-14 proposal; the uploaded Project source R8-Delivery-Plan.txt; current PLAN.md, CHANGE_MAP.md, README.md, CONTEXT.md, AGENTS.md, docs/documentation-guide.md, docs/architecture.md, docs/invariants.md, docs/tasks.md, docs/testing.md, docs/development/r8-delivery-plan.md, the R7-B B5 implementation plan including the B5.2 acceptance record, core/models.py, and core/ingestion.py.
**Method and limits:** static repository review. No tests, migrations, local checkout, or CI workflows were executed for this review. The companion report, **Watch — Project Review and Implementation Hints** (2026-11-14), has now been supplied and reviewed. Findings F1–F9 are incorporated below and in the decision addendum. Its repository snapshot is static and has no Git metadata or executed tests; it is advisory evidence, not proof of current branch, HEAD, merge, CI, or runtime state.

## 1. Executive view

The proposal identifies a real product-sequencing problem: the distinctive Watch reasoning loop—Threads, competing Hypotheses, EvidenceLinks, confidence changes, and decay—is specified in detail but is not implemented. Meanwhile, the team-experience lifecycle has received substantial implementation and regression work. That work is not wasted: it establishes valuable governance, provenance, replay, review, and retrieval foundations. The risk is that Watch becomes very good at preserving lessons before it can reliably form and revise the world-model beliefs from which many lessons should arise.

The most important unresolved question is not a technical detail. It is **what R8 is meant to prove**:

- The current R8 plan defines a three-domain pressure test of the architecture that exists today. It explicitly says the objective is to test the existing architecture, not add another architectural layer. Its acceptance criteria do not require Threads or Hypotheses.
- The product vision and the supplied proposal describe a broader claim: a team observes a domain, maintains competing beliefs, tests predictions, learns from misses, and improves later work. The current R8 plan cannot prove that complete loop because the belief subsystem is absent.

Both are coherent goals, but they are not the same acceptance target. Decide which one R8 represents before moving dates or inserting a new phase.

My recommendation is to approve a **decision-only RW-0 session first**, not to start RW-1 implementation immediately. Freeze the value harness and decide whether R8 is a bounded validation of current foundations or a proof of the full product loop. If the latter, rebaseline the date honestly and insert the reasoning slice. If the former, keep R8 focused and schedule the reasoning slice as a separate, explicitly authorized product milestone.

## 2. Findings C1–C9 against current main

| Finding | Review disposition | Current evidence and qualification |
|---|---|---|
| **C1 — Depth before breadth** | **Confirmed.** | core/models.py defines Signal and the team-experience/Control records, but no Thread, Hypothesis, ConfidenceChange, or SignalDisposition ORM models. EvidenceLink does exist, but migration 0012 constrains it to Evaluation subjects and Outcome/Signal sources; it does not yet provide the Hypothesis evidence path described by the architecture. The architecture and Task specs define the missing concepts; core/ingestion.py listing task names in an Event-scope whitelist does not implement their workers or persistence. R7-B lifecycle work is real and reusable, but the world-belief loop remains absent. |
| **C2 — No value measure** | **Partly confirmed; sharpen the claim.** | architecture.md lists operational observability metrics, including validation rejection rate and confidence-band distribution. Those are not a value harness demonstrating that a team gets better. The R8 delivery plan has scenario/safety acceptance criteria but no frozen quantitative measure for repeat-run improvement, predictive calibration, or useful retained-experience reuse. Some proposed metrics depend on the unbuilt belief layer. |
| **C3 — Proof follows code** | **Pattern confirmed, wording too absolute.** | B5.2 required supplemental concurrency, stale-binding, replay, and acceptance work after its first implementation review; the final acceptance record is in the B5 implementation plan. B4.4 and B5.4 also used separate regression slices. However, the B5.4 work is explicitly test-only and now merged in PR #122, so it is not accurate to say every proof is always deferred. The missing systemic control is a machine-checked requirement-to-test map, not the absence of tests or gates. |
| **C4 — Spec runs ahead of code** | **Confirmed.** | architecture.md and tasks.md define the Thread/Hypothesis model and F1–F3 flows, while the current ORM has no corresponding records and no update_thread worker was found. Some sections are clearly design contracts, but the distinction is not consistently visible at each entity/flow. |
| **C5 — Status drift** | **Confirmed, with a stronger current example.** | PR #122 is closed and merged at the current main commit `29c954f...`, but PLAN.md still says the next action is to sync PR #122 and complete its verification; the PR body also retains pre-merge pending language. PLAN.md contains older R7 narrative that still describes PR #113 as open and B4.4 closure as pending, despite the current summary saying B4.4 is closed. The uploaded Project source R8-Delivery-Plan.txt is older still: it says G5/G6 are outstanding and B4.4 closure is pending. The current repository copy, docs/development/r8-delivery-plan.md, is the canonical R8 plan; docs/documentation-guide.md explicitly says exported/copied R8 plans are convenience copies and must not be independently maintained. The repository plan's November 13 baseline records the then-open PR #113 as a dated historical checkpoint; that line is not itself a false claim when read as history. |
| **C6 — Too many PRs** | **Partly confirmed; do not optimize by merging every gate.** | B4.4 and B5.2 involved multiple planning, implementation, supplemental-proof, and closeout reviews. Some separation reflects genuine authorization and acceptance boundaries. The avoidable cost is repeating the same evidence narrative and status in multiple places, not the existence of separate PRs where scope or authority differs. |
| **C7 — Dates drive scope** | **Partly confirmed.** | R8 has a fixed November 23 target and a November 15 entry gate, while the reasoning loop is absent. But the R8 plan explicitly says the schedule does not authorize implementation and requires a separate entry decision. The deeper issue is the mismatch between the broad product vision and the narrower R8 acceptance contract, not simply the presence of a date. |
| **C8 — Hygiene left open** | **Partly confirmed; one item remains unverified.** | Current verification records still report 113 Alembic path_separator deprecation warnings. The R8 plan records a historical 36-failure run that did not reproduce in a later isolated full-suite run; its cause remains undetermined. The alleged migration filename/revision mismatches were not independently verified in this review. |
| **C9 — Claims outrun evidence** | **Confirmed as a process risk.** | The current PLAN/PR #122 mismatch demonstrates why a merge, CI run, local verification, and formal acceptance must be tied to exact SHAs and explicit decisions. The proposal's own self-correction is useful: reports should distinguish source-recorded, tool-verified, Operator-reported, and still-unconfirmed facts. |

### Important current-state corrections to the 2026-11-14 proposal

The proposal is valuable as a dated record, but some sequencing assumptions have already changed by the current main snapshot:

- B5.2 is no longer pending. Its final verification and technical acceptance are recorded in the R7-B B5 implementation plan.
- B5.3 is closed.
- B5.4 test/regression work was merged in PR #122 at `29c954fe8685e0a5ddb9b205277a28b1a158c57e`. The current PLAN.md next-action text has not been reconciled with that merge.
- Therefore, D1's instruction to park B5.4 is no longer actionable as written. Do not reopen or undo completed work. Decide only what future work remains necessary.
- B6 is now the next planned lifecycle track. Its Phase 1 read-only audit must resolve F8 from migration/data and implementation evidence before scope is frozen; the report raises a possibility, not a proven defect. R7-C remains separately gated.

## 3. The central product decision: what is R8?

The current R8 plan's own objective is to demonstrate shared Kernel/Control behavior across newsroom, development-team, and generalist scenarios; domain-knowledge separation; experience retention/reuse; safe transfer; and failure behavior. It says the objective is to test the existing architecture, not add another architectural layer.

That is a legitimate pressure test. It can establish whether the current Task, Outcome, Evaluation, KnowledgeItem, and retrieval foundations behave consistently across domains. It cannot establish that Watch has a working world model, because Threads, Hypotheses, evidence-linked confidence changes, and belief decay do not exist in the current implementation.

The Operator should choose one of two definitions before any schedule change:

1. **R8 validates the current platform.** Keep the R8 scope bounded to its existing three-domain acceptance criteria. Do not imply it proves the full reasoning vision. Put the reasoning loop into a new milestone after R8, with its own value harness and gate.
2. **R8 validates the Watch product vision.** Insert RW before the cross-domain pressure test. Rebaseline the November 23 target rather than compressing schema, validation, race, replay, and value proofs to fit the calendar.

Do not combine these definitions informally. Otherwise the team may pass R8 while the defining product loop is still absent, or expand R8 until its acceptance criteria become unmanageable.

## 4. Recommended approach to the reasoning loop

If the Operator chooses the full product loop before R8, use the proposed RW sequence but tighten the boundaries:

### RW-0 — decision and value definition only

- Confirm the current-main gaps with a small code/spec inventory.
- Define one vertical scenario on one real domain, including source, competing hypotheses, a prediction or falsifiable expectation, outcome, evaluation, lesson, and a second run.
- Freeze metrics and their measurement method before implementation.
- Decide D1–D10 explicitly. Record accepted, rejected, deferred, or revised; do not infer acceptance from a PR merge.
- Resolve the EvidenceLink subject/source contract through an ADR addendum before schema work if the accepted contract changes.
- Keep PLAN.md and phase dates untouched until the decisions are recorded.

### RW-1 — minimum durable belief schema

Build only the records needed for one Thread, multiple competing Hypotheses, evidence links, confidence changes, and immutable source references. Add SignalDisposition only if the chosen vertical slice genuinely needs triage. Preserve same-Team ownership, immutable Snapshot provenance, unique causes, and append-only history. Avoid building every future entity at once.

### RW-2 — deterministic commit path before model behavior

Implement the application validation and atomic commit service with deterministic proposals. Exercise rejection cases as well as success cases. This isolates the authority and data-integrity contract from model nondeterminism. The Operator path can be the first proposal producer only if its host-authentication boundary is already understood and remains within existing repository rules.

### RW-3 — model worker

Add the update_thread model worker behind the existing generation-provider/cost-accounting boundary. Use typed bounded proposals and stubbed providers for deterministic tests. Keep live-model smoke tests separate. Record rejection Events and reasons; do not add automatic repair/re-proposal until rejection data justifies it.

### RW-4 — minimum signal intake and context read path

Start with Operator-created Threads or a deliberately small deterministic triage rule. Make current Hypotheses available to Task context with strict Team scope and bounded context. Do not turn triage into a heuristic engine before the vertical slice demonstrates a need.

### RW-5 — decay

Treat scheduled decay as a separate, deterministic maintenance operation. It should never reject a Hypothesis or update last_touched_at. It can follow the initial reasoning loop if the first vertical slice can demonstrate useful evidence updates without it.

## 5. Make the value harness meaningful

The three measures in the proposal are a useful start, but they need operational definitions:

- **Validation diagnostics:** accepted/rejected proposal counts by rule and producer. This measures guardrail behavior, not team expertise. A lower rejection rate is not inherently better.
- **Retained-experience effect:** compare a repeat task with relevant prior KnowledgeItems against a controlled baseline using a fixed rubric and independently checked outcomes. Record whether the prior lesson was retrieved, actually used, and whether the result improved.
- **Belief calibration:** evaluate only registered, resolvable predictions with explicit deadlines and sufficient sample size. Report calibration by confidence band and show the sample count; do not claim predictive quality from a handful of examples.
- **Safe abstention:** include insufficient, contradictory, and irrelevant evidence cases. A system that declines to form a high-confidence belief when evidence is weak is demonstrating a core product property.

Freeze the task, rubric, comparison baseline, sample-size policy, and evidence source before the first milestone measurement. Do not let the model grade its own improvement without independent checks.

## 6. Delivery-process changes: what to adopt first

The proposal's process changes are directionally sound. Implement them in this order, each with a small independent change and explicit review:

1. **Two-SHA reporting and evidence links.** Cheap and immediately useful. Every PR says which code/test SHA was verified and which documentation-inclusive PR SHA is current, with exact CI run links and local evidence status.
2. **Proof matrix.** Start with a small declarative mapping from requirement IDs to collected pytest node IDs. CI must fail for missing or failing required proofs. Keep heuristic test-count alerts advisory until false-positive behavior is understood.
3. **Single current-status surface.** Keep the top of PLAN.md focused on the current gate and next action. Preserve historical evidence, but move detailed closed-phase narratives to appropriately named historical records only after verifying links and provenance. Do not delete history merely to shorten the file.
4. **Implementation markers.** Add yes/partial/no markers to high-value entities and flows. A checker must inspect more than ORM tables: migrations, services, Task handlers, provider wiring, and tests all matter. A table existing is not proof of an end-to-end flow.
5. **One slice, one integrated proof package.** Put the code, required tests, and documentation update in one reviewable PR set. Retain separate PRs where an independent authorization, technical acceptance, or risk boundary requires them.
6. **Complexity budget.** Every new entity/operation names the scenario or metric it enables. One feature slice in flight at a time.

Do not attempt all process automation in one large PR. Start with evidence traceability and the proof matrix; these address repeated problems without forcing a broad documentation rewrite.

## 7. Hygiene and code-structure work

Keep this separate from reasoning features:

- Confirm and fix the Alembic path_separator warning in a small configuration-only PR, then verify the warning count on an exact full-suite run.
- Investigate migration filename/revision mismatches only after listing the actual mismatches; document deliberate legacy naming rather than renaming migrations casually.
- Preserve the 36-failure incident as unresolved historical evidence unless new reproducible evidence explains it. A clean rerun does not explain the original failure.
- Split the very large experience-distiller test module only if test collection, fixture boundaries, and ownership remain clear; first make a behavior-preserving move with no test-body changes.
- Extract a race helper only where it makes tests shorter without hiding lock order, synchronization, or expected winner behavior.
- Refactor learning_commit branches only in a separate behavior-preserving PR with focused and full-suite evidence.

These are candidates for D10, not authorizations granted by this review.

## 8. Decisions still required

The remaining D1–D10 details are not all resolved. The Operator's selected sequencing and R8 start-date decisions are recorded in the dated addendum below; the remaining design decisions are preserved in [the proposal](reasoning-loop-and-delivery-redesign-proposal-2026-11-14.md) for RW-0.

Before implementation, record each decision with one of: Accepted, Rejected, Deferred, or Revised, plus rationale and date. At minimum, resolve the R8 objective/date and the EvidenceLink contract before schema work.

## 9. Documentation changes in this PR

This PR intentionally:

- adds docs/simple-explain.md as a plain-language orientation document;
- preserves the 2026-11-14 proposal as a decision input;
- adds this current-main review so future contributors do not treat the proposal's dated assumptions as current facts;
- links the orientation document from README.md, docs/documentation-guide.md, and CHANGE_MAP.md.

This PR does **not** change PLAN.md, the R8 delivery plan, architecture contracts, invariants, Task scopes, ADR decisions, source code, tests, migrations, or dependencies. That restraint is deliberate: the supplied proposal says D1–D10 must be recorded before those changes, and no such decision record has yet been made.

## 10. Review conclusion

The project should not abandon the rigor developed in R6/R7. It should redirect that rigor toward the missing product loop and measurable improvement. The immediate next step is a decision session, not a migration or model worker.

The most important correction is to stop treating a schedule as a product definition. First decide whether R8 proves the current platform or the complete Watch vision. Then define the smallest vertical scenario and its evidence. Only after that should the team authorize RW implementation and process automation.


---

## Operator roadmap decision and companion findings — 2026-11-15

The companion report *Watch — Project Review and Implementation Hints* (2026-11-14) is now available. Its F1–F9 findings are part of this review. The report is explicitly advisory and based on a static repository snapshot; it did not run tests and cannot establish Git or CI state.

### Current milestone corrections

- **B5.4 is complete and closed** by merged PR #122 at `29c954fe8685e0a5ddb9b205277a28b1a158c57e`. Earlier text in the proposal/review that treats B5.4 as unfinished or proposes parking it is historical and superseded. Do not reopen it without a demonstrated defect.
- **B6 is the next lifecycle track.** Use the [B6 delivery plan](r7-b-b6-legacy-lifecycle-hardening-plan.md). Phase 0 establishes the exact baseline; Phase 1 is read-only. B6 acceptance criteria must come from demonstrated defects or proof gaps. No implementation scope is assumed in advance.
- **F8 remains unresolved.** The audit must establish whether legacy-rooted items remain after B1 backfill and whether the current retirement path actually blocks them. Do not design a compatibility path until the condition is demonstrated.
- **R7-C remains separate.** RW-0 decides whether knowledge-use references or other R7-C capabilities are necessary for the value harness; do not combine R7-C with B6 by default.

### R8 and RW decision

The Operator has decided that all foundational Watch layers must be complete before R8 testing begins. The reasoning/world-memory loop is foundational, not a feature to add after or during the R8 pressure test.

The planned order is **B6 → RW-0 through RW-5 → foundation exit gate → R8**. R8 is planned to start on **November 23, 2026**; this is its start date, not its completion deadline. If the foundation exit gate has not passed, R8 does not start and the schedule is re-baselined.

RW-0 still owns the detailed design decisions, vertical slice, EvidenceLink contract, and value-harness definitions. This roadmap decision does not authorize RW implementation or resolve every D1–D10 item.

### Delivery-process implications

F1–F9 remain findings to act on selectively, not a blanket refactor authorization:

- Required proofs should be mapped to tests in the same implementation slice.
- PR reports should identify verified code/test SHA and current PR head, with exact CI evidence.
- Keep PLAN.md as the only current status authority and docs/testing.md as the verification evidence archive.
- Preserve independent authorization gates; do not collapse PRs merely to reduce their count.
- Treat F2/F3 refactors and hygiene work as separately scoped, behavior-preserving work unless the B6 audit demonstrates they are necessary.
