# RW4-0 — Evidence audit and closure recommendation

**Status:** Read-only source/spec audit; Operator decision required. This document does not accept D1–D6, close RW4-0, or authorize implementation.

**Audited baseline:** `main` at PR #174 squash merge `0d1e262c77bc79af7edf93c5f4c116cdb01475c2` (2026-11-23).

**Method:** Inspected the repository documentation and current ORM/application source at the audited commit. No code was changed; no tests, migrations, database queries, provider calls, or scored newsroom runs were performed.

## 1. Executive finding

RW4-0 is **not ready to close**. D1–D3 have identifiable existing contracts to reconcile, but D4–D6 still lack evidence needed to freeze a safe first implementation.

The central problem is not simply that triage is unimplemented. The current canonical records do not contain the inputs required by the target newsroom matching rules:

- `Signal` has no canonical title or normalized-entity field.
- `Thread` has no canonical entity set, embedding, or summary projection.
- The current Domain matching/dedup descriptions are target specifications, not executable configuration or source-backed rules.
- The decay specification uses Hypothesis `last_touched_at`; it does not define a Thread reactivation clock or a shared decay/triage lock order.

Consequently, no deterministic rule can currently justify the full set of `matched`, `new_thread`, `noise`, and near-duplicate `duplicate` outcomes without introducing or accepting additional source/representation contracts. An empty Thread-candidate set cannot be treated as evidence for `new_thread`.

**Recommendation:** keep RW4-0 open and implementation unauthorized. Do not solve the gaps by inventing a Thread embedding, an implicit title generator, a new Domain subsystem, or a decay timestamp. First decide whether to add a minimal canonical Signal/Thread matching representation, or explicitly narrow the first triage release to a smaller contract supported by existing data. The current source does not prove that either option has already been accepted.

## 2. Evidence by decision

### D1 — Trusted host invocation

**Evidence found**

- The accepted `update_thread` Task contract uses a narrow host-invoked application creator.
- The host authenticates the Operator and supplies a typed principal with an exact Team/action grant; Watch validates the grant against canonical Team/Thread state.
- The repository explicitly records that no production host composition root exists. Watch-side principal/grant validation is not end-to-end host authentication.
- `TaskDispatcher` remains the ingestion execution path; a Task-type string in an Event allow-list does not implement a creator or worker.

**Assessment:** the host-to-adapter trust boundary is a reusable design precedent, not a deployed integration. D1 can be accepted as an architectural boundary if the same limitation is carried forward. Do not claim production authentication or add a second scheduler/dispatcher.

### D2 — Canonical Task and disposition identity

**Evidence found**

- The `update_thread` contract demonstrates immutable request Events, request fingerprint validation, conflict-safe replay, TaskRuntime-owned lifecycle, and Team/Thread validation.
- That operation is keyed by a host idempotency UUID and target Thread. It does not prove the proposed one-Task-per-(Signal, Team) canonical identity or disposition uniqueness.
- PR #174 correctly requires database-enforced uniqueness for the triage canonical Task identity, atomic Task/request-Event insertion, and validation by a uniqueness loser.

**Assessment:** retain the D2 requirements as a proposal. The existing `update_thread` pattern is precedent for the transaction/replay shape only; its identity namespace and request semantics must not be copied. Before implementation, identify the actual persisted unique key and prove same-request replay, changed-policy conflict, independently authorized callers, and one request Event under concurrent creation.

### D3 — Terminal deferred

**Evidence found**

- The current Task write-scope matrix gives `update_thread` and `operator_update` SignalDisposition permission marked by footnote ³: “Refine `deferred` only.”
- The architecture SignalDisposition state table explicitly permits `deferred → matched | new_thread | noise | duplicate` through update/operator-update commits.
- PR #174 proposes that `deferred` is terminal in the first release and that no such refinement permission is retained.

**Assessment:** D3 is a real contract change, not a statement already reflected in the repository. If accepted, reconcile both the architecture lifecycle table and the Task/write-scope matrix: remove the deferred-refinement transition and the corresponding SignalDisposition write permission from `update_thread` and `operator_update`. Keep triage's own disposition write permission. No schema change is implied because SignalDisposition is not implemented.

### D4 — Deduplication, Thread matching, and new-Thread eligibility

**Canonical source evidence**

- `Signal` currently stores `domain`, `source_type`, `origin_url`, `fetched_at`, `content_hash`, and `snapshot_ref`. It has no title or normalized-entity field.
- Signal ingestion derives `Signal.domain` from `Team.domain`, stores immutable Snapshot bytes, and enforces uniqueness on `(origin_url, content_hash)`.
- Signal embeddings, where indexed, are stored on `KnowledgeChunk` projections with chunk/source Snapshot and embedding-space metadata. They are not a canonical Signal-level matching contract.
- `Thread` currently stores Team, domain, title, status, `created_at`, and `last_updated_at`. It has no entity set, embedding, or summary.
- `docs/domains.md` describes newsroom entity overlap, Thread embedding similarity, and near-duplicate similarity thresholds. It does not supply executable versioned configuration or actual values for those rules. Its newsroom entity-overlap rule also has no current canonical Signal/Thread entity fields to consume.
- The generalist pack's exact-origin dedup is already substantially handled at ingestion by `(origin_url, content_hash)`; the selected first value-harness domain is newsroom, whose target rule is different.

**Assessment:** no source-backed deterministic Thread matcher or newsroom near-duplicate policy exists at this baseline. Signal chunk embeddings cannot be compared to a Thread representation that does not exist. Exact same-origin duplicate ingestion does not create a second Signal to triage. Cross-origin exact-hash handling is technically derivable from current fields, but it is not the documented newsroom policy and has no approved canonical-winner/lookback contract; do not silently substitute it.

**Required decision:** either (a) design and approve the smallest canonical, versioned inputs needed for the newsroom matcher and dedup rule, including provenance/rebuild behavior, or (b) explicitly narrow the first release and its disposition vocabulary to a case that can be proven from current canonical records. Until that choice is made, D4 remains open. Do not add Thread embeddings or a Domain ORM/configuration subsystem by default.

### D5 — Disposition matrix and Thread creation

**Evidence found**

- Team and Signal domains are available and ingestion sets Signal.domain from Team.domain. Existing source and ORM contracts support validating equality; they do not support caller/model selection of Team/domain.
- The current Thread ORM requires a non-empty title of at most 500 characters and has a database default status of `active`.
- The Signal ORM has no title/headline field. Its Snapshot is immutable source content, but the current ingestion contract does not extract and persist a canonical title or a deterministic title-normalization rule.
- Thread creation provenance can be represented by a Task-attributed Event under the proposed triage scope, but no SignalDisposition or triage commit implementation currently exists.

**Assessment:** Team/domain derivation is supportable. Initial `active` is consistent with the current ORM default and status constraint, subject to explicit acceptance in the design. A deterministic descriptive title source is not established. A URL-derived title would be deterministic but is not demonstrated to be a valid newsroom Thread title; it should not be adopted merely because `origin_url` exists.

**Recommendation:** exclude `new_thread` from the first release unless a canonical non-model title source and normalization rule are demonstrated and accepted. This does not by itself resolve D4's existing-Thread matching requirement. Do not create placeholder or model-generated titles.

### D6 — Reactivation and RW-5 decay interaction

**Evidence found**

- The current decay contract selects active Hypotheses using `Hypothesis.last_touched_at` and the effective decay window.
- `last_touched_at` changes only when evidence is accepted; decay itself must never change it.
- A Thread becomes dormant when all its active Hypotheses have been low for one window.
- `Thread.last_updated_at` exists in the ORM and has an index, but the current decay contract does not identify it as the decay clock or define how triage changes it.
- Triage's proposed `dormant → active` transition is documented, but no RW-5 decay implementation or shared triage/decay lock-order contract exists at this baseline.

**Assessment:** one timestamp question can be answered from existing contracts: triage reactivation must not change Hypothesis `last_touched_at` merely to reset decay; that field is reserved for accepted evidence. But this exposes a substantive unresolved behavior: after triage reactivates a dormant Thread without accepted evidence, a subsequent decay pass may still find its Hypotheses eligible under the unchanged `last_touched_at` values. The current specification does not say whether that is intended or whether Thread-level activity should affect dormancy.

**Required decision:** RW-5 must explicitly define whether a matched Signal counts as fresh Thread activity for decay eligibility. If yes, define the authoritative Thread-level activity timestamp and its update events; if no, document that reactivation can be temporary until accepted evidence changes Hypothesis touch state. Then define one lock order shared by triage and decay, with under-lock revalidation and deterministic decay-first/triage-first outcomes. The existing `update_thread` Team→Thread locking precedent is useful but does not prove the RW-5 batch lock set. D6 remains open until this is agreed.

## 3. Cross-cutting Task/write-scope reconciliation

The current matrix says:

- `triage_signal`: SignalDisposition write; Thread create/reactivation; Task and Event Kernel effects.
- `update_thread` and `operator_update`: SignalDisposition refinement of deferred only (footnote ³).
- `apply_decay`: Thread `active → dormant` and ConfidenceChange decay writes.

The D3 proposal requires removing the deferred-refinement grant from the two existing update Task types. D5/D6 must also preserve the narrow triage Thread effects and must not grant triage writes to Hypothesis, EvidenceLink, ConfidenceChange, TeamPolicy, or follow-up Tasks. Event attribution and the disposition/Thread commit remain atomic under the existing Kernel boundary.

The exact triage Task envelope is not yet frozen in the current Task specification: canonical request fields, policy pin, `allowed_writes`, Task identity, creator admission, and the mapping between deterministic application effects and the matrix's W/C labels must be reconciled before implementation.

## 4. Evidence-backed closure status

| Item | Result at audited baseline | Closure status |
|---|---|---|
| D1 host boundary | Reusable host-invoked pattern exists; production host composition absent | Acceptable as an explicit external integration boundary |
| D2 identity/replay | Existing creator provides partial precedent; triage pair identity still needs its own unique key and tests | Proposal retained; implementation contract not yet proven |
| D3 terminal deferred | Conflicts with architecture transition and Task matrix | Requires accepted documentation reconciliation |
| D4 matching/dedup | Required canonical inputs/configuration absent | Open blocker |
| D5 new Thread | Team/domain and active status supported; canonical title source absent | Disable new_thread unless a source is approved |
| D6 reactivation/decay | Hypothesis decay clock known; Thread activity semantics and shared lock order absent | Open RW-5 agreement blocker |
| Task/write-scope | Deferred-refinement permission remains; triage envelope not exact | Requires reconciliation before implementation |
| Requirement-to-test matrix | PR #174 lists proof obligations but exact test nodes cannot yet be named for unresolved algorithms | Freeze after D4–D6 decisions |

## 5. Recommended Operator disposition

1. Accept D1 only as a host integration contract, with the production composition limitation explicit.
2. Retain D2's database-enforced uniqueness and atomic Task/request-Event requirements; do not claim the existing `update_thread` key is interchangeable.
3. If D3 is accepted, update the architecture transition table and remove deferred-refinement SignalDisposition write permission from `update_thread` and `operator_update`.
4. Keep D4 open until a source-backed newsroom matching/dedup representation and algorithm are selected. Do not substitute exact-origin ingestion dedup or Signal-only vector similarity for Thread matching.
5. Exclude `new_thread` from the first release unless a stable canonical title source is demonstrated. Active initial status and Team/domain derivation can be specified from current ORM/source evidence.
6. Keep D6 open until RW-5 decides whether a matched Signal resets Thread dormancy and both operations share a proven lock/revalidation contract. Triage must not mutate Hypothesis `last_touched_at`.
7. Do not authorize RW4-1 schema work or RW4-2/RW4-3 implementation until the disposition contract, exact Task envelope/write scope, and the above blockers are resolved.

This audit is evidence for Operator decisions. It does not itself accept these recommendations, amend the accepted architecture/Task contracts, close RW4-0, or authorize code, schema, migration, provider, or database work.
