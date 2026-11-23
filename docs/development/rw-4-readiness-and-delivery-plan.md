# RW-4 Readiness and Delivery Plan

**Status:** Active planning baseline; documentation only. RW-4 production implementation is not authorized.
**Planning baseline:** `main` at `de0528bd2db1da0f172e4b629963dea08ea52889` (PR #176 merge).
**Status authority:** `PLAN.md` remains the only authority for milestone status and authorization. This document owns the dependency-aware RW-4 readiness checklist and delivery sequence.
**Scope:** Reconcile the evidence audit in PR #175, the bounded RW4-0 proposal in PR #174, the minimal matching proposal in PR #176, the RW-4 design plan, Task specifications, and architecture.

## 1. Executive decision

RW-4 is **not ready for production implementation**. RW4-0 remains open. PR #176 is a merged design proposal, not acceptance of its experimental matcher or closure of D1–D6. PR #175 remains an open audit branch based on an obsolete main SHA; its findings are reconciled here, so do not treat that branch as the current baseline without rebasing and review.

The delivery path has four work classes:

1. **Mandatory pre-implementation gates:** RW3.4 disposition, RW4-0 decisions, matching evidence, Task/write-scope reconciliation, shared decay/reactivation contract, Context-consumer definition, and a requirement-to-test matrix.
2. **Independent parallel work:** RW-5 decay design/implementation and Experiment A preparation within their accepted boundaries.
3. **RW-4 implementation:** persistence, Task boundary, deterministic triage/commit, and world-memory Context retrieval.
4. **Foundation exit:** RW4/RW5 integration, RW4-KU disposition, Experiment A disposition/report, RWN-01 readiness, and explicit acceptance before R8.

Do not make all of RW-5 a prerequisite to starting RW-4. RW-5 can proceed independently. The shared timestamp, revalidation, and concurrency contract is required before RW4 implements dormant-Thread reactivation; both slices are required for integrated proof.

## 2. Current evidence baseline

- **PR #174** records bounded D1–D6 proposals; it did not close RW4-0 or authorize implementation.
- **PR #175** found: D1 host-invoked Task-creator precedent but no production host composition/authentication; D2 canonical Task identity needs DB uniqueness and is not the existing `update_thread` identity; D3 conflict between deferred-refinement prose and the proposed terminal-deferred contract; D4 matching inputs are not source-ready; D5 no safe canonical Signal title for Thread creation; D6 no shared RW-5 timestamp/lock contract.
- **PR #176** proposes a minimal representation: derive Thread evidence from EvidenceLink → Hypothesis → Thread; require same-Team ingestion provenance and matching Snapshot provenance; exact-hash duplicate detection within one Team; reuse KnowledgeChunk projections; keep maximum-pairwise cosine experimental only; first-slice outcomes `matched`, `duplicate`, `deferred`; disable `new_thread` and automatic `noise`; and require a separately committed canonical assessment receipt before the Kernel business commit.
- **RW3.4** implementation and corrective proofs are merged, but formal acceptance is deferred. The ledger remains 28 PASS / 7 PARTIAL / 0 OPEN. The bounded residual proof work and external integration limitations remain as recorded in `PLAN.md`.
- **RW-5** is independently implementable. Its integration with triage is blocked on D6 timestamp and concurrency decisions, not on all RW-5 work.
- **Experiment A** informs RW4-4 representation only. Its canonical fixtures are offline artifacts; the experiment has not been executed. It does not block RW4-0 through RW4-3 or RW-5.
- **RWN-01** is a separate newsroom value-harness package and is not a substitute for matching fixtures or Experiment A.

## 3. Staged readiness gates and authorization

RW4-0 is the umbrella design-closure milestone: it closes only when D1–D6 and the cross-cutting contracts are reconciled, evidence-backed, and explicitly accepted. **That does not mean every D1–D6 deliverable blocks every implementation slice.** A slice may begin under its own narrower gate while RW4-0 remains open, provided the overall RW3.4 gate and that slice's prerequisites have been satisfied and the Operator explicitly authorizes that slice.

### Gate A — RW3.4 formal disposition

Current disposition: **deferred**, not accepted.

Complete only the bounded work already identified:
1. Resolve the Context identity tuple/recovery-state coverage gap, or present an explicit residual-risk decision.
2. Add targeted duplicate/future commit and rejection-marker tests only where existing guards require them.
3. Resolve the mismatched in-session attempt question against the supported runtime contract.

Do not build an exhaustive Cartesian recovery matrix or reopen merged production code without a demonstrated defect. Keep all seven PARTIAL rows visible. `RW-REQ-01` (production host authentication/composition) and `RW-POL-01` (production TeamPolicy publisher/lock serialization) remain external integration boundaries; do not fabricate either integration. The local PR #169 environment-restoration assertion failure remains a qualification; do not rerun the 1,296-test suite solely for that script defect.

**Exit:** either formal RW3.4 acceptance, or an explicit Operator sequencing exception that retains the deferred status and all residual qualifications. This is a hard gate before RW-4 production implementation, not a requirement to redo RW3.4.

### Gate B — RW4-0 decision closure

RW4-0 closes only after D1–D6 are reconciled, evidence-backed, and explicitly accepted. PR #174 and #176 preserve proposals; neither substitutes for this gate. The staged slice gates below allow bounded implementation to proceed before umbrella RW4-0 closure only where explicitly stated; they do not imply that the remaining decisions are accepted.

#### D1 — Trusted host invocation and authority

Freeze an explicit trusted host-invoked operation for one Signal and one Team. Define trusted principal fields and the exact Team/action grant checked by Watch. The caller cannot select a Team from untrusted payload data. Every caller is independently authorized, including a caller resolving an existing Task.

No automatic `ingest_source → triage_signal` Task creation, scheduler, or TaskDispatcher expansion in the first slice. The production host composition/authentication boundary remains external; Watch-side grant validation is not proof of deployed host authentication.

### D2 — Canonical Task and disposition identity

Keep three identities distinct: (a) business identity `(signal_id, team_id)`; (b) one deterministic Task identity derived from canonical Team, Signal, and `triage_signal` operation under a dedicated, versioned identity namespace/domain tag (database-enforced uniqueness, unless that canonical identity is deliberately the Task primary key); and (c) immutable request provenance/fingerprint. Freeze atomic Task/request-Event creation, same-request replay, and conflicting-request behavior. The losing concurrent request loads and validates the winning Task/Event; it does not create a second Event. Requester identity is provenance, not semantic equivalence, as recorded in the PR #174 correction.

Separately freeze SignalDisposition uniqueness for `(signal_id, team_id)`, its canonical persisted identity, Task attribution, reason, timestamp fields, and database constraints. The immutable Task request must pin Team ID, Signal ID, canonical Signal Snapshot reference and hash, TeamPolicy version, matcher identifier/version, embedding-space key, and chunking version. Same-request replay requires the complete immutable fingerprint to match; a changed pin or other immutable request content conflicts. The existing `update_thread` idempotency namespace is precedent for transaction/replay shape only; it must not be reused as triage identity.

### D3 — Deferred lifecycle and Task write-scope reconciliation

The proposed first release makes `deferred` terminal. The current architecture lifecycle table still permits `deferred → matched/new_thread/noise/duplicate` through `update_thread` or `operator_update`, and the Task matrix still grants those Task types SignalDisposition writes. This is a real contract conflict, not a documentation detail.

If terminal deferred is accepted, reconcile the architecture lifecycle table, F1 narrative, Task specification, and Task/write-scope matrix together: remove deferred-refinement transitions and the corresponding SignalDisposition write permission from `update_thread` and `operator_update`; define triage's exact SignalDisposition and permitted Thread effects. Do not implement against contradictory authority documents. This plan does not silently accept terminal deferred.

### D4 — Minimal matching representation and evidence

Use the PR #176 representation as the bounded experimental candidate:
- derive Thread evidence profiles at read time through Team-scoped EvidenceLink → Hypothesis → Thread;
- preserve Hypothesis lifecycle state and EvidenceLink stance for analysis;
- validate every incoming and historical Signal's same-Team ingestion Event and exact Signal/Snapshot/hash association;
- validate EvidenceLink Snapshot reference/hash against its canonical Signal Snapshot; absent provenance is excluded, partial/corrupt/conflicting provenance fails closed;
- detect exact raw content-hash duplicates only within the Team's own intake history, with a deterministic canonical winner;
- use current KnowledgeChunk projections with pinned embedding-space and chunking identities;
- do not introduce Thread embeddings, summary projections, entity/alias tables, or a general Domain subsystem.

Maximum pairwise chunk cosine similarity is an **experimental heuristic only**. It is vulnerable to high-scoring outlier chunks and larger-profile bias. Do not accept a numeric threshold or margin without labeled fixture evidence.

Required offline fixtures: same-origin replay; cross-origin exact bytes within one Team; same hash across Teams; near-duplicate syndicated copy; clear match; broad-topic hard negative; multiple candidates/ties; dormant and resolved Threads; mentions-only and no-evidence Threads; active/superseded/rejected Hypotheses; supporting/challenging stances; missing/stale/mismatched/corrupt projections and Snapshots; same-Domain cross-Team provenance; candidate/evidence scan overflow; threshold/margin boundaries; high-scoring outlier chunks; multiple Hypotheses/subtopics; and differently sized evidence profiles.

Labels must be independent of the matcher. Report false positives and false negatives by case, lifecycle state, and profile size. Measure eligible candidate/evidence cardinalities, bounded overflow detection, query plan, and cost on a disposable PostgreSQL fixture database. Never rank a truncated set as complete. If acceptable false-positive tolerance or query cost cannot be demonstrated, keep matching deferred or narrow the first slice; do not tune by intuition.

### D5 — Disposition vocabulary and Thread-creation eligibility

The PR #176 first-slice proposal is:
- `matched`: one existing same-Team/domain Thread;
- `duplicate`: one canonical exact-content duplicate in the same Team's intake history;
- `deferred`: explicit reason and terminal in this release.

`new_thread` is disabled because no safe canonical title source exists. Automatic `noise` is disabled because no deterministic source-backed classifier exists. Near-duplicate classification is excluded. The exact duplicate canonical-winner rule, intake-history scope, and valid reference combinations still require explicit acceptance.

Freeze every disposition/reference combination and its Task-attributed Event semantics. No disposition may mutate Hypothesis, EvidenceLink, ConfidenceChange, TeamPolicy, or enqueue follow-up Tasks. If a later release wants `new_thread` or `noise`, it needs a separate source-backed rule and design decision.

### D6 — Dormant Thread reactivation and RW-5 contract

Agree before RW4 reactivation implementation:
- whether matching/reactivation changes a Thread-level timestamp;
- which timestamp is authoritative, if any;
- whether a reactivated Thread can immediately become dormant under unchanged Hypothesis touch times;
- exact rows/records locked by triage and decay;
- common lock order and under-lock revalidation;
- decay-first and triage-first outcomes;
- replay behavior and at-most-one reactivation Event.

Decay uses Hypothesis `last_touched_at`; accepted evidence is the only operation that updates it. Decay does not update it. Triage must not use it as a proxy for Thread activity. RW-5 implementation itself remains independent; the shared contract is required before RW4 implements reactivation and before integrated proof.

### Cross-cutting gate — Assessment receipt and recovery

Freeze the PR #176 C1 contract before code:
- one canonical assessment receipt per Task, identity derived from Task plus fixed assessment kind/version and explicitly **independent of Task attempt** (retries/attempts reuse the same receipt identity);
- database-enforced uniqueness on the canonical `(task_id, assessment_kind, assessment_version)` identity, not application pre-check only;
- concurrent losing attempts load and validate the winning receipt;
- request/schema/assessment fingerprints are validated;
- receipt and identity commit in a transaction that completes **before** the distinct Kernel business-commit transaction begins;
- TaskRuntime remains the only attempt, retry, interruption, and recovery authority;
- valid receipt replays exactly without rerunning matching;
- absent receipt follows existing retry/recovery policy; corrupt, duplicate, or mismatched receipt fails closed;
- committed business result replays without a second disposition, Thread transition, or Event.

Define the exact Event schema, unique identity, Task type/write scope, Kernel path, transaction ownership, and recovery proofs. A shared receipt/business transaction is not equivalent to durable-before-business ordering.

### Cross-cutting gate — Later Task Context consumer and representation

Name the later Task type that consumes world-memory Context and the existing assembler to extend. Define Team/Thread scope, eligible active Hypotheses and EvidenceLinks, source/Snapshot/hash/quote validation, interaction with Domain Knowledge and Team Experience, deterministic order, count/character/token bounds, overflow behavior, immutable Context Snapshot/manifest Event/hash, and replay.

Do not broaden RW-3's target-Thread Context or create a parallel Context subsystem. Experiment A informs only the RW4-4 model-facing evidence representation. Before RW4-4 freezes it, use an accepted result or an explicit Operator disposition with rationale and residual uncertainty.

### Gate C — Requirement-to-test matrix and implementation authorization

Before each production RW-4 slice, freeze and independently review that slice's requirement-to-test subset. Maintain the complete RW-4 matrix as the umbrella proof plan; exact test node IDs and tested SHAs are added as each slice is implemented. The complete integration matrix must be frozen before RW4-5.

At minimum map:
- host authority, Team grant, canonical Task identity, race, replay, conflict;
- Signal/Team ownership and disposition uniqueness;
- Signal and EvidenceLink Snapshot/hash provenance;
- each allowed and prohibited disposition/reference combination;
- duplicate canonicalization and matching thresholds/ties/overflow;
- receipt uniqueness, separate transaction durability, and recovery;
- atomic disposition/Thread/Event commit and rollback;
- dormant reactivation and decay races;
- Context membership, provenance, ordering, bounds, and replay;
- no direct Task lifecycle writes, unapproved follow-up Task creation, or dispatcher expansion;
- disposable-PostgreSQL migration/constraint proofs.

**Overall project gate before any RW-4 production implementation:** RW3.4 formal acceptance or an explicit sequencing exception, with residuals retained.

**Staged slice gates (each also requires a reviewed requirement-to-test subset and explicit Operator authorization):**

| Slice | Required decisions/evidence before that slice |
|---|---|
| **RW4-1 — persistence** | D3 terminal-deferred lifecycle and Task/write-scope reconciliation accepted; D5 disposition vocabulary, reference matrix, uniqueness scope, and physical constraints accepted. No matching algorithm, D6 decay contract, receipt, or Context decision is required for this persistence-only slice. |
| **RW4-2 — Task boundary** | D1 trusted host invocation/authority boundary and D2 versioned canonical Task identity, immutable request pins, DB uniqueness, request Event, concurrency/replay/conflict contract accepted; TaskRuntime envelope and write scope reconciled. RW4-1 schema contract must be stable. |
| **RW4-3 — matching and commit** | D4 matching/duplicate evidence and measured query cost accepted, or a narrower deterministic subset explicitly accepted; C1 receipt/recovery contract accepted; D6 shared decay/reactivation timestamp, lock order, and revalidation contract accepted before any reactivation implementation. If reactivation is explicitly deferred from the slice, the D6 gate applies before adding it, not to unrelated matching/commit work. |
| **RW4-4 — Context** | Named later Task consumer, existing assembler, eligible records, provenance, bounds, overflow, snapshot/manifest and replay contract accepted; Experiment A result or explicit Operator disposition recorded before representation freeze. |
| **RW4-5 — integration** | RW4-1 through RW4-4 accepted as applicable, RW-5 decay implementation available, and integrated race/post-decay retrieval proof completed. |

RW4-0 umbrella closure remains a separate milestone requiring D1–D6 and cross-cutting contracts to be fully reconciled and accepted. A staged implementation does not close RW4-0 by implication.

## 4. Parallel work that does not block RW4-0..2

### RW-5 — deterministic decay

RW-5 design and implementation may proceed independently of RW4-0, RW4-1, and RW4-2. Its planned work is:
1. deterministic `apply_decay` Task through existing TaskRuntime;
2. effective Team/Domain decay-policy selection;
3. confidence reduction with exactly one valid decay Task cause;
4. never reject Hypotheses and never mutate `last_touched_at`;
5. Thread dormancy when all active Hypotheses meet the accepted low-confidence/window condition;
6. boundary-time, repeated-run idempotency, concurrency, and recovery proofs.

The shared D6 timestamp/lock contract must be delivered before RW4 implements reactivation. RW-5 must not invent a second runtime or scheduler.

### Experiment A

Preparation and offline protocol work may proceed independently. Its scope is limited to informing RW4-4 representation. The merged canonical fixture package is not an executed experiment. Provider/model execution requires separate explicit authorization. Before RW4-4 representation freeze, record either the accepted experiment result or an explicit Operator rationale and residual uncertainty. Before foundation exit/R8, retain an accepted report or explicit inconclusive/not-required disposition with limitations.

### RWN-01

RWN-01 is the separate newsroom value-harness scenario. Freeze publisher PDF and Supplementary Material review, corpus manifest, task brief, answer key, independent outcome set, scoring examples, reviewer calibration, and execution configuration before scored runs. It is not a prerequisite to starting RW-4 and is not a substitute for matching fixtures or Experiment A.

## 5. RW-4 implementation sequence

Each stage has its own reviewed scope, acceptance evidence, and explicit authorization.

### RW4-1 — SignalDisposition persistence

Implement the accepted physical representation only: ORM, migration, one row per Signal/Team, Team-isolation and reference constraints, Task attribution, reason, timestamps, indexes.

Proof: fresh disposable PostgreSQL migration; uniqueness/FK/check violations; cross-Team/domain rejection; all valid/invalid reference combinations; upgrade compatibility; no unapproved changes to Signal, Thread, or EvidenceLink semantics.

### RW4-2 — Triage Task boundary

Implement the explicit trusted host-invoked creator and TaskRuntime-owned execution boundary: canonical Task identity, immutable request, Team/Signal validation, policy pin, atomic Task/request Event, DB uniqueness/race behavior, fingerprint/replay/conflict rules, exact Task envelope and write scope, admission/failure/recovery.

Keep TaskDispatcher unchanged. Do not add automatic post-ingestion enqueueing.

### RW4-3 — Deterministic triage and commit

Implement only the evidence-approved duplicate/matching rules: bounded candidate/evidence retrieval; same-Team ingestion and Snapshot provenance; deterministic result/reason; canonical durable assessment receipt; separate receipt transaction; Kernel-authorized business commit; and atomic disposition/Event commit. Matched active-Thread handling may proceed under the accepted D4/C1/D5 contracts. **Dormant-Thread reactivation is a separately gated addition:** until D6 is accepted, dormant candidates must not be reactivated or receive a `matched` disposition that implies reactivation; resolve them only through the accepted terminal `deferred` disposition with an explicit D5-approved reason. Do not change Thread status/activity timestamps or emit a reactivation Event in this variant.

Proof for the non-reactivation slice: positive/negative fixtures, threshold/tie/overflow, duplicate and concurrent request replay, receipt recovery across the two transactions, rollback, no Hypothesis/EvidenceLink/ConfidenceChange mutation, and no automatic `update_thread` Task. Add decay-first/triage-first races, under-lock revalidation, and at-most-one reactivation Event only in the separately authorized D6 reactivation slice.

### RW4-4 — World-memory Context retrieval

Extend the selected existing Task Context path. Implement same-Team active Hypothesis and eligible EvidenceLink selection, canonical source/Snapshot/hash/quote validation, deterministic serialization/order, explicit bounds and fail-closed overflow, immutable Context Snapshot/manifest Event/hash, exact replay, and stale-reference rejection.

Experiment A result or explicit Operator disposition is required before representation freeze. Prove only eligible verified current records reach the model and existing retrieval behavior remains intact.

### RW4-KU — claim-level attribution (separate gate)

Keep immutable application-written `TaskKnowledgeReference` and typed application-validated `KnowledgeUseAssessment` separately gated. Decide whether required for RW-4 acceptance or only the foundation/value-harness gate. Do not broaden into a general learning/evaluation subsystem.

### RW4-5 — integrated verification and acceptance

Prove the full path:

`canonical Signal → authorized Team triage → durable disposition/Thread → later Task Context`

Include RW-5 integration: matched Signal reactivates the correct dormant Thread; decay and triage cannot overwrite stale decisions; retrieval sees canonical post-decay state; only eligible active Hypotheses and verified EvidenceLinks reach the later Task.

Close with exact-head local verification, exact-head hosted CI, disposable PostgreSQL evidence, requirement-to-test matrix, docs/CHANGE_MAP reconciliation, residual-risk ledger, and explicit Operator acceptance.

## 6. Explicit non-goals

Do not build these merely to unblock RW-4:
- Thread embeddings or summaries;
- new Domain ORM/configuration subsystem;
- entity extraction/alias infrastructure;
- near-duplicate detection without validated rules;
- model-based triage or model-generated Thread titles;
- automatic noise classification;
- automatic triage after ingestion;
- second scheduler/runtime or TaskDispatcher expansion;
- deferred refinement through RW-2/RW-3 Task types without an accepted scope change;
- parallel Context subsystem;
- live provider calls or scored newsroom runs.

Reconsider only when a concrete scenario and evidence justify a separate design and authorization.

## 7. Brief execution sequence

1. **Reconcile docs and evidence:** bring PR #175 findings onto current main; update architecture, Task matrix, PLAN, README, CHANGE_MAP, and historical labels.
2. **Settle the overall RW3.4 gate:** complete bounded residual proof and formally accept RW3.4, or record an explicit sequencing exception with all seven PARTIAL rows and external integration boundaries retained. This gate applies before any RW-4 production slice.
3. **Advance RW-5 independently:** design/implement decay and prove its invariants. The shared D6 timestamp/lock/revalidation contract is required before RW4 dormant-Thread reactivation, but does not block unrelated RW-4 slices.
4. **Authorize and implement ready slices:** freeze and independently review each slice's proof-matrix subset, then obtain explicit authorization for that slice. RW4-1 persistence requires its D3/D5 gate; RW4-2 Task boundary requires D1/D2 and a stable RW4-1 schema. These slices may proceed while umbrella RW4-0 remains open.
5. **Close umbrella RW4-0:** reconcile and explicitly accept all D1–D6 and cross-cutting contracts, including matching evidence/query cost, receipt/recovery, and Context representation. This is a separate design-closure milestone; it does not retroactively authorize implementation.
6. **Implement RW4-3 and RW4-4 when their own gates are met:** RW4-3 matching/commit requires D4 and C1; dormant reactivation is a separately gated addition requiring D6. RW4-4 requires its named Context consumer/contracts and an accepted Experiment A result or explicit Operator disposition before representation freeze.
7. **Integrate and accept:** complete RW4-5 with RW-5 race and post-decay retrieval proofs; decide RW4-KU; complete foundation-exit evidence and explicit acceptance.

## 8. Readiness checklist

- [ ] RW3.4 accepted, or explicit sequencing exception recorded with residuals retained.
- [ ] D1 trusted invocation/authority accepted before RW4-2.
- [ ] D2 versioned canonical Task identity, complete immutable request pins, DB uniqueness, and replay/conflict contract accepted before RW4-2.
- [ ] D3 terminal-deferred lifecycle and Task/write-scope reconciliation accepted.
- [ ] D4 matching and duplicate representation supported by independent fixtures and measured query cost before RW4-3.
- [ ] D5 disposition vocabulary/reference matrix and new-Thread/noise exclusions accepted.
- [ ] D6 shared decay/reactivation timestamp, lock order, and race outcomes accepted before reactivation and integrated proof.
- [ ] Assessment receipt transaction/recovery accepted before RW4-3; later Task Context consumer/bounds accepted before RW4-4.
- [ ] Architecture lifecycle and Task/write-scope matrix reconciled.
- [ ] Requirement-to-test matrix independently reviewed.
- [ ] Slice-specific prerequisite checklist and proof-matrix subset reviewed before each implementation PR.
- [ ] First bounded implementation PR explicitly authorized.

No R8 date is assigned here. R8 remains TBD until RW-0 through RW-5 and the formal foundation exit gate are complete and accepted.
