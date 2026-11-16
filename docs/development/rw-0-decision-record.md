# RW-0 — Decision Record

**Recorded:** 2026-11-15
**Status:** decision record in progress; RW-0 execution remains after B6
**Authority:** Operator decisions are identified separately from accepted ADR constraints, recommendations, and unresolved questions.

This record is the decision index for the world-memory reasoning loop (RW). It does not authorize RW implementation. The required sequence remains **B6 → RW-0 through RW-5 → foundation exit gate → R8**.

## 1. Operator-confirmed decisions

| ID | Decision | Status |
|---|---|---|
| RW-D01 | Complete B6 before starting RW-0. B6 begins with baseline verification and a read-only audit; implementation scope requires evidence, a frozen acceptance checklist, and explicit approval. | Confirmed |
| RW-D02 | Complete the required RW foundation before R8. R8 is a pressure test of the integrated architecture, not the place to add a missing foundational layer. | Confirmed |
| RW-D03 | The intended order is B6 → RW-0 → RW-1 → RW-2 → RW-3 → RW-4 → RW-5 → foundation exit gate → R8. | Confirmed |
| RW-D04 | R8 is planned to start on November 23, 2026. This is not a completion deadline; no completion date is set. If the foundation gate has not passed, R8 does not start on that date. | Confirmed |
| RW-D05 | The first real-world value-harness domain is **newsroom**. | Confirmed |
| RW-D06 | This Checkpoint B work belongs on the existing documentation PR #123. It is documentation and contract definition only; it does not authorize production code, tests, migrations, schema changes, or RW implementation. | Confirmed |
| RW-D07 | The first newsroom demonstration should aim to establish all three distinct claims: relevant retained experience is available through retrieval, its use can be attributed to specific claims, and access to it improves later work under independent evaluation. These claims require separate evidence; a KnowledgeUseAssessment does not by itself establish causation. | Confirmed |
| RW-D08 | Include a minimal, typed KnowledgeUseAssessment capability in the RW foundation. It records an application-validated assessment against the exact knowledge version and LearningChange identity, the later Task's terminal Outcome, and immutable Context/TaskKnowledgeReference evidence. It grants no knowledge-mutation or decision authority and makes no causal claim. Defer any broader autonomous evaluation or learning loop. | Confirmed |
| RW-D09 | Retrieval-quality evaluation, label provenance, and small-sample reporting belong in the newsroom value-harness tooling, not as a new production capability or permanent Watch subsystem. The harness must still make retrieval relevance reproducible and report sample limitations honestly. | Confirmed |
| RW-D10 | Establish downstream benefit through a controlled newsroom comparison: control Tasks receive the same brief and source material without retained Watch experience; treatment Tasks receive retained experience through the normal retrieval and Context path; independent reviewers, blinded to group, score both against the same pre-agreed rubric. Report sample size, score differences, uncertainty, exclusions, and unresolved cases. Make no causal claim stronger than the design and evidence support. This is harness methodology, not a new autonomous evaluation capability in Watch. | Confirmed |

The exact newsroom beat, source corpus, task brief, and independent outcome set are not selected here. They must be frozen before the first scored harness run.

The Operator has confirmed the target product claims (RW-D07), the inclusion boundary for KnowledgeUseAssessment (RW-D08), the measurement boundary for retrieval evaluation (RW-D09), and the controlled comparison methodology for downstream benefit (RW-D10). Application-written, claim-level TaskKnowledgeReference and the minimal typed KnowledgeUseAssessment are therefore part of the proposed RW foundation scope. The assessment must validate exact knowledge-version and LearningChange identity, the later Task's terminal Outcome, and immutable Context evidence. It is an auditable use assessment, not a knowledge mutation, approval, decision, or causal finding. Any broader autonomous evaluation or learning loop remains deferred. Retrieval-quality evaluation, label provenance, small-sample reporting, and the blinded control/treatment comparison are harness methodology rather than production subsystems. Retrieval quality, exposure, claim-level attribution, and downstream benefit remain distinct measurements.

## 2. Accepted architecture constraints

These are existing accepted contracts, not new decisions made by this record.

### 2.1 EvidenceLink is one shared evidence model

- [ADR-0007](../decisions/architecture%20decision%20records%20%28ADR-0001%20-%20ADR-0019%29.md#adr-0007-generalized-evidence-links-with-deterministic-validation) defines polymorphic EvidenceLink subjects **hypothesis | evaluation** and sources **signal | outcome | artifact**. Quotes are validated deterministically against immutable hashed Snapshots; only **supports** and **challenges** can anchor ConfidenceChanges.
- [ADR-0020](../decisions/ADR-0020-consultations-waiting-happens-between-tasks.md) adds **consultation** as an EvidenceLink source. A Consultation answer is an immutable hashed Snapshot and can be cited using the same quote-validation rule.
- [ADR-0021](../decisions/ADR-0021-operator-update-path-human-as-first-class-worker.md) requires **operator_update** to use the same proposal and commit validation as **update_thread**. Human authorship is provenance, not a validation exemption.

RW must implement these accepted contracts through the existing EvidenceLink concept. A sibling evidence table or a human-only bypass is not the default design.

### 2.2 Current implementation is narrower than the accepted contract

At the code baseline audited for this checkpoint (**29c954fe8685e0a5ddb9b205277a28b1a158c57e**):

- **core/models.py** has an Evaluation-only EvidenceLink subject.
- Its supported source kinds are **signal** and **outcome**.
- It does not implement Hypothesis subjects, Artifact sources, or Consultation sources.
- **Thread**, **Hypothesis**, **ConfidenceChange**, and **SignalDisposition** are not ORM models in this baseline.
- The task names **triage_signal**, **update_thread**, **operator_update**, and **apply_decay** appear in specifications and an ingestion Event-scope allow-list; that allow-list is not an implementation of those Tasks.

This is an implementation gap against the accepted architecture, not a reason to replace the accepted model. Recheck the audit after B6 and immediately before RW-1.

### 2.3 Evidence-model implementation rule

The implementation plan should extend the existing **evidence_links** contract to the accepted subject/source vocabulary while preserving current Evaluation evidence, quote/hash validation, same-Team ownership, uniqueness, and rejection semantics.

The exact relational representation, foreign-key strategy, and migration sequence remain RW-1 engineering work. If the accepted polymorphic contract cannot be implemented without changing an accepted decision, stop and submit an ADR addendum for Operator review before coding. Do not silently narrow ADR-0007 or create a parallel evidence system.

Artifact source support may be staged until an Artifact entity exists, but the accepted target vocabulary must remain explicit. Consultation support is not optional in the accepted target: ADR-0020 already includes it. The order in which those source types become operational must be stated in the RW-1 migration plan.

## 3. RW-0 decisions still required after B6

The following items are not silently accepted by this record.

| Question | Current recommendation / known constraint | Decision still required |
|---|---|---|
| R7-C | Incorporate only the minimum capabilities required by RW-D07/RW-D08: application-written claim-level TaskKnowledgeReference and the minimal typed KnowledgeUseAssessment. Defer broader autonomous evaluation/learning-loop behavior. | The retrieval benchmark and blinded control/treatment comparison are newsroom harness methodology under RW-D09/RW-D10, not production capabilities. No permanent benchmark subsystem or autonomous evaluation loop is authorized. |
| Artifacts / rendered output | The first harness can measure evidence-grounded reasoning and retained experience without claiming a production publishing/delivery capability. | Decide whether R8's newsroom product claim requires persistent Artifacts/output before R8. |
| Consultations | The evidence source contract is accepted by ADR-0020, but the Consultation entity and Tasks are not implemented in the audited baseline. | Decide whether human consultation is required for the newsroom scenario or can remain deferred while the accepted evidence contract is staged. |
| Setup advisor / TeamDraft | Not required merely to prove the reasoning loop; a Team can be configured by an existing supported path or fixture. | Decide whether self-service Team setup is foundational to the R8 claim. |
| Expanded domain-pack machinery | Do not expand packs merely to make the first newsroom scenario work. | Decide whether current configured Team/generalist defaults are sufficient for the foundation and R8. |
| Exact newsroom scenario | Newsroom is confirmed as the first domain. | Select one bounded beat, fixed source corpus, task brief, outcome checks, and scoring rubric. |
| EvidenceLink migration details | One shared polymorphic model is the accepted target under ADR-0007 and ADR-0020. | Freeze exact database representation, constraints, compatibility/backfill behavior, and staged Artifact/Consultation support in RW-1. |
| Thread creation path | The current Task scope matrix gives `triage_signal` the scoped Thread-create permission (`new_thread`); `update_thread` and `operator_update` only refine the Thread summary/resolution. | Confirm `triage_signal` as the canonical Thread-creation path for the newsroom vertical slice. Use same-Team Thread fixtures for RW-2/RW-3 commit-path proofs; do not add Thread creation to `operator_update` implicitly. |
| operator_update sequence | ADR-0021 requires identical validation to update_thread; the proposal recommends a deterministic human path before the model worker. | Confirm RW-2 as the deterministic operator_update commit path before RW-3. |
| Proposal-batch atomicity | `docs/tasks.md` and `docs/architecture.md` currently specify that valid proposals commit atomically as one set, invalid proposals are rejected with Events, and a Task fails when all proposals fail. The original proposal's stronger whole-batch rejection wording may differ. | Confirm mixed valid/invalid batch behavior before RW-2. Preserve the current Task contract unless an explicit Operator decision changes it and the canonical specs are updated. |
| Model re-proposal after rejection | The proposal recommends no automatic repair loop in the first slice so the rejection rate remains measurable. | Confirm whether rejected proposals are terminal for the first RW-3 attempt. |
| Model-call test strategy | The proposal recommends deterministic stubbed-provider tests for proofs and a separate live smoke test. | Confirm the exact test split and provider boundary. |
| Evaluation/distillation linkage | Preserve existing R6/R7 Evaluation and distillation behavior unless RW evidence demonstrates a required change. | Decide whether Hypothesis evidence must be linked into Evaluation/distillation in the first RW release. |
| Value thresholds | Metric definitions are proposed in rw-value-harness.md; thresholds must be fixed before scored runs. | Operator freezes the scenario, rubric, run count, and thresholds during RW-0, before implementation and before any scored run; the R8 entry gate re-confirms that the frozen harness remains valid. |
| Process changes | The proposal recommends proof-matrix enforcement, two-SHA PR summaries, spec markers, and a small complexity budget. | Decide which process controls become mandatory, and whether hygiene/test-structure work remains separately authorized. |

## 4. Proposed RW delivery shape

The current planning proposal is:

1. **RW-1 — persistence:** add the durable world-memory records and reconcile the existing EvidenceLink table with accepted ADRs.
2. **RW-2 — deterministic commit:** implement the human operator_update path through the ordinary Task, proposal, validation, and commit gates.
3. **RW-3 — model update:** implement update_thread with bounded Context, typed proposals, existing generation/cost controls, and rejection Events.
4. **RW-4 — triage and read path:** add the smallest deterministic triage needed by the newsroom scenario and expose accepted active Hypotheses to bounded Task Context.
5. **RW-5 — decay:** implement the deterministic apply_decay contract without allowing decay to reject Hypotheses or refresh last_touched_at.

This is a proposed sequence for RW-0 to freeze. It is not implementation authorization.

## 5. RW-0 completion checklist

RW-0 is complete only when the Operator has explicitly accepted:

- the exact newsroom scenario, corpus, task brief, and independent outcome rubric;
- the minimum R7-C and capability set required by that scenario;
- the EvidenceLink relational/migration design and staged source support;
- the RW-1 through RW-5 slice boundaries and dependencies;
- the proof matrix and how each proof is enforced in CI;
- the value metrics, scoring rubric, and numeric or categorical acceptance thresholds;
- the model-provider test split and rejection/re-proposal behavior;
- the foundation exit gate and stop conditions.

Until then, unresolved rows remain open. No RW implementation starts merely because this document exists.

## 6. Authority and review

- PLAN.md remains the sole authority for current milestone status and authorization.
- This file records decisions and open questions; it does not override accepted ADRs.
- docs/development/rw-implementation-plan.md defines the proposed delivery/proof structure.
- docs/development/rw-value-harness.md defines the proposed newsroom measurement method.
- Re-audit implementation-state markers after B6; the code snapshot in this record is pre-B6.
