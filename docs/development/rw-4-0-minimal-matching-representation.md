# RW4-0 — Minimal Signal/Thread matching representation

**Status:** Supporting design/evidence artifact reconciled to the accepted D4.1/D4.1a/D4.2/D4.3, D5.1–D5.4, and D6.1–D6.6 decisions (2026-11-25). Numeric thresholds, winner margin, score serialization, candidate/evidence bounds, fixture results, canonical Team/hash persistence design, query-cost evidence, and actual matching-pin values remain open. D5 disposition semantics and D6 reactivation contract are accepted; physical persistence and reactivation implementation remain separately gated. No implementation is authorized.

**Baseline:** PR #174 merge `0d1e262c77bc79af7edf93c5f4c116cdb01475c2`.

**Evidence audit:** [PR #175](https://github.com/abtn/Watch-Architecture-Rev2/pull/175), whose read-only source audit is based on the same baseline.

## 1. Accepted D4 direction and remaining evidence

The Operator accepted this narrow first matching representation on 2026-11-25, with the following decision boundaries:

- Reuse canonical `Signal`, immutable Snapshot, `EvidenceLink`, `Hypothesis`, `Thread`, and the existing rebuildable `KnowledgeChunk` projection.
- Derive each Thread's matching evidence set from its existing Signal-backed EvidenceLinks. Do not persist a Thread embedding, entity table, alias subsystem, or separate Domain ORM.
- Use exact raw-content hash for duplicate detection in the Team's own Signal intake history. Do not classify near-duplicates in the first slice.
- Use same-embedding-space Signal chunk similarity to find a unique existing Thread candidate. No model call or re-embedding occurs during triage.
- Restrict automatic first-release outcomes to `matched`, `duplicate`, and terminal `deferred`. Do not create Threads, automatically label `noise`, or refine deferred dispositions in this slice.

The representation and outcome boundaries are accepted; this is not a frozen numeric algorithm. The threshold, winner margin, score serialization, candidate/evidence bounds, fixture evidence, canonical Team/hash persistence design, and RW-5-dependent dormant reactivation remain explicit gates.

## 2. Why this is the smallest representation

The audited source already contains the necessary provenance chain:

### Incoming Signal

1. A trusted `ingest_source` Task belongs to a Team.
2. Its `signal_ingested` or `fetch_no_change` Event identifies the canonical Signal.
3. `Signal` identifies its Domain, source, origin URL, fetch time, raw content hash, and immutable Snapshot reference.
4. `KnowledgeChunk` rows are rebuildable projections of that Signal Snapshot. Each row records source Snapshot/hash, chunk hash/index/version, embedding vector, and the complete embedding-space identity.

The Task's `team_id` plus its ingestion Event provides the Team association. `Signal.domain` alone is not a Team identity and must never be used to cross Team boundaries.

### Existing Thread evidence

1. `EvidenceLink` identifies a Team-scoped Signal source and a Hypothesis subject.
2. `Hypothesis` identifies its canonical Thread and Team.
3. `Thread` identifies its Team, Domain, title, and lifecycle status.

Therefore, the existing relation

`EvidenceLink(subject_kind=hypothesis, source_kind=signal) → Hypothesis → Thread`

already defines which canonical Signals have been used as evidence in a Thread. It is a provenance-backed Thread evidence profile; no Thread embedding needs to be stored.

The matcher reads this relationship and the existing Signal chunk projections. It creates no canonical entity and no new persistent matching projection.

## 3. Proposed read model

The matcher constructs two bounded, ephemeral read models. They are not ORM entities and are not independently persisted.

### 3.1 Incoming Signal profile

| Field | Source | Validation |
|---|---|---|
| `team_id` | immutable triage Task | trusted host admission; active Team |
| `signal_id` | immutable Task request | canonical Signal exists |
| `domain` | Team and Signal | exact equality required |
| `snapshot_ref`, `content_hash` | Signal | Snapshot exists and hash pair is consistent |
| `embedding_space_key` | current Signal KnowledgeChunk rows | one consistent space; matches Task pin |
| `chunking_version` | KnowledgeChunk rows | one supported version, matches Task pin |
| `chunks` | KnowledgeChunk rows | ordered by chunk index; each row matches current Signal Snapshot/hash |

The incoming Signal must have a Team association through an `ingest_source` Task Event of type `signal_ingested` or `fetch_no_change`. The Event's Task must belong to the requested Team, and its payload's Signal ID, Snapshot reference, and content hash must match the canonical Signal. Missing or inconsistent association fails closed.

The Task creator must find and validate a current Signal projection before admitting the Task, then pin its `embedding_space_key` and `chunking_version` in the immutable request. If no valid incoming Signal projection exists at admission, do not create the Task; return a host-side admission failure so indexing can complete first. After admission, distinguish three cases:

- **The immutable matcher pins are no longer supported by the running implementation:** the queued Task is terminally superseded through TaskRuntime using the accepted mapping (`failed`, `terminal_failure`, reason `matching_pins_superseded`), with no retry or replacement.
- **A candidate Thread's otherwise-valid evidence profile lacks a compatible projection:** that candidate is unmatchable and is excluded deterministically. If no eligible candidate remains, or the remaining evidence is otherwise insufficient/ambiguous, the assessment may produce the applicable valid terminal `deferred` business outcome.
- **A required incoming projection or other required projection becomes unavailable, stale, or inconsistent after admission while the immutable pins themselves remain supported:** this is not, by itself, the accepted stale-pin supersession case, and it must not be converted into a successful `deferred` disposition. Fail closed through TaskRuntime technical-failure/recovery handling; the exact reason mapping for this distinct condition is not defined by the accepted D3 decision and must not be invented here.

The matcher never calls an embedding provider or substitutes a different model space.

### 3.2 Thread evidence profile

For one Team, derive candidate Threads from:

- `EvidenceLink.team_id = Team.id`
- `EvidenceLink.subject_kind = 'hypothesis'`
- `EvidenceLink.source_kind = 'signal'`
- `EvidenceLink.stance IN ('supports', 'challenges')`
- `EvidenceLink.hypothesis_id → Hypothesis.id`
- `Hypothesis.team_id = Team.id`
- `Hypothesis.thread_id → Thread.id`
- `Thread.team_id = Team.id`
- `Thread.domain = Team.domain`
- `Thread.status IN ('active', 'dormant')`

Include supporting/challenging Signal-backed EvidenceLinks across Hypothesis lifecycle states. A committed EvidenceLink remains part of the Thread's evidence history even if its Hypothesis is later superseded or rejected. Exclude `mentions` links from the first profile because a mention alone is too weak to establish Thread identity. Do not include Outcome-backed EvidenceLinks in this Signal-to-Signal matcher.

For every contributing Signal, validate a same-Team intake association, not just Domain equality: there must be an `ingest_source` Task Event of type `signal_ingested` or `fetch_no_change` whose Task belongs to this exact Team and whose payload identifies this exact Signal and its canonical Snapshot reference/content hash. This matters because `Signal` itself is not Team-owned and the current EvidenceLink foreign key to Signal does not enforce that the EvidenceLink's Team matches the Team that ingested the Signal. A matching Domain is insufficient: reject cross-Team evidence even when both Teams share the same Domain. Also validate that the Signal's chunk projection still points to its canonical Snapshot/hash. In addition, validate the provenance recorded on each contributing EvidenceLink:

- If `snapshot_ref` and `snapshot_hash` are both present, they must exactly match the referenced Signal's canonical Snapshot reference and content hash.
- If both are absent, the EvidenceLink is not eligible for semantic matching in this first slice. Do not silently substitute the Signal's current Snapshot as though the EvidenceLink had cited it.
- A partial pair (which the current database check should reject) or a pair that disagrees with the Signal is an integrity failure. Do not omit the corrupt link and continue ranking a potentially incomplete Thread profile, and do not record it as `deferred`. Fail closed through TaskRuntime technical-failure/recovery handling. The absent-pair case is different and is excluded deterministically.

This check is necessary because the EvidenceLink model permits both snapshot fields to be absent and only enforces pair consistency when they are present; it does not itself guarantee that the pair matches the referenced Signal. The matcher must not erase that provenance distinction.

A Thread with no eligible Signal-backed EvidenceLink, no compatible chunk projection, or no common embedding space has no usable profile in this matcher. It is **unmatchable**, not evidence that a new Thread should be created.

Resolved Threads are excluded. Active and dormant Threads are both candidates; the dormant transition is handled separately under D6/RW-5.

## 4. Three separate decisions

### 4.1 Exact duplicate Signal

Run exact duplicate detection before Thread matching.

- Scope: Signals already associated with the same Team through `ingest_source` Events of type `signal_ingested` or `fetch_no_change`.
- Rule: another Signal with exactly the same raw `content_hash` is an exact duplicate.
- Canonical duplicate: the first Signal successfully committed into the Team's intake history for that exact content hash. PostgreSQL must arbitrate concurrent first arrivals and the Team/hash association must remain stable. Do not select by Event `created_at`, application timestamps, caller-supplied `fetched_at`, Signal UUID, or origin ordering.
- Exclude the incoming Signal itself.
- The duplicate disposition references the canonical Signal and makes no Thread mutation.

The existing unique constraint on `(origin_url, content_hash)` prevents a second Signal for the same origin/content pair, but it does not implement the accepted Team-wide, cross-origin canonical association. Signal is not Team-owned; Team membership is derived from ingestion Events. The persistence mechanism that serializes and preserves the first committed Team/hash association is still a design gate and requires a two-session disposable-PostgreSQL proof.

This does **not** detect whitespace/markup changes, paraphrases, syndicated edits, or other near-duplicates. Those remain outside the first slice. Similarity must not be repurposed as a duplicate rule without separate labeled evidence and acceptance.

### 4.2 Existing Thread match

For each eligible Thread, compare the incoming Signal's chunks with the chunks of Signals in that Thread's evidence profile, restricted to the same embedding space and chunking version.

Proposed simple score:

`thread_score(T) = max cosine_similarity(incoming_chunk, evidence_chunk)`

over all eligible chunk pairs where the evidence chunk belongs to a Signal linked to Thread `T`.

The evidence for a candidate is the best-scoring pair: incoming chunk and historical evidence chunk, including their Signal IDs, chunk indexes/hashes, source Snapshot refs/hashes, and embedding-space key.

A Thread is selected only if:

1. its score reaches a fixture-calibrated minimum threshold;
2. it is the unique best candidate by the frozen winner-margin rule; and
3. its Team, Domain, and current status are revalidated at commit.

If no candidate reaches the threshold, multiple Threads tie, the best/second-best margin is insufficient, required evidence is missing, or candidate ranking is ambiguous, return `deferred`. With exactly one eligible candidate, the minimum threshold is sufficient; apply the winner-margin rule only when a runner-up exists. If the bounded candidate/evidence scan would truncate the eligible set, return `deferred` rather than selecting from a partial set. UUID ordering may stabilize evidence serialization but must never break a semantic score tie.

No recency bonus is proposed initially. `Thread.last_updated_at` is not currently established as a matching clock, and adding it without a lifecycle contract would make the score depend on an unproven timestamp meaning.

**Accepted limitation:** maximum pairwise chunk similarity is the accepted experimental baseline heuristic, not a proven production score and not proof that two Signals describe the same event. A single highly similar chunk can dominate even when the rest of the incoming Signal is unrelated. It is also biased toward Threads with larger evidence profiles because they offer more chunk pairs. Its threshold and margin must be calibrated against labeled positive and hard-negative newsroom fixtures that vary Thread profile size. If that evidence does not support an explicitly accepted false-positive tolerance, reject this heuristic or keep the matcher deferred; do not lower the threshold or add complexity by intuition. The fixture report must expose per-case false positives and false negatives, not only aggregate accuracy.

**Performance limitation:** migration `0010_knowledge_chunk_projection` creates the embedding-space/Signal B-tree index and lexical GIN index, but no pgvector ANN index. The existing vector retrieval orders by cosine distance; the source does not prove its latency at realistic Team evidence volumes. Before RW4-3 implementation, measure the eligible candidate/evidence cardinalities and inspect the query plan on a disposable fixture database. The first version must have a hard evidence-scan bound and defer when that bound is exceeded. Do not add HNSW/IVFFlat or another index speculatively; require measured need and a separate schema decision.

### 4.3 New Thread eligibility

Not supported in this first slice.

The current Signal record has no canonical title/headline, and the Snapshot ingestion path does not persist a deterministic title extraction. The Thread title is required and non-empty. A URL-derived title is not accepted as a newsroom title source, and model-generated titles are outside this deterministic triage boundary.

Therefore:

- no existing Thread match does not imply `new_thread`;
- this matcher never creates a Thread;
- absence of a candidate, insufficient evidence, or an unmatchable Thread set results in `deferred`;
- `new_thread` remains disabled for v1; any later automatic Thread creation requires a separate source-backed design and Operator decision, not title extraction alone.

## 5. First-slice disposition vocabulary

| Result | Required durable reference | Side effect |
|---|---|---|
| `duplicate` | canonical same-Team duplicate Signal | disposition only |
| `matched` | one existing same-Team/domain active Thread; under accepted D6, a dormant Thread only when the same TaskRuntime transaction reactivates it and records `thread_reactivated` | disposition only for active Thread; atomic lifecycle transition/Event/TaskRuntime commit for dormant Thread. Until separately authorized and proven RW4-5, dormant would-be matches remain deferred |
| `deferred` | explicit reason code | disposition only |

The first slice does not automatically emit:

- new Thread creation: excluded by accepted D4.3; a future capability needs a separate design and Operator decision;
- `noise`: no deterministic, source-backed noise classifier is established;
- near-duplicate `duplicate`: no validated near-duplicate policy or numeric threshold.

Deferred is terminal in this release, consistent with accepted D3. No `update_thread` or `operator_update` SignalDisposition refinement is introduced.

D4.3's no-automatic-Thread-creation rule was accepted by the Operator on 2026-11-25. This changes the target disposition coverage and must remain consistent in the architecture state table and Task/write-scope matrix before any schema or implementation work.

## 6. Versioning, Task pinning, and durable assessment

The matcher is application-owned deterministic code, not a model or mutable Domain subsystem.

The immutable triage Task request should bind:

- Team and Signal IDs;
- Signal Snapshot reference and content hash;
- TeamPolicy version already pinned by the Task;
- matcher identifier and version;
- incoming `embedding_space_key`;
- `chunking_version`.

The matcher identifier/version owns the scoring rule, threshold, winner margin, candidate bound, and tie semantics. Do not put matching configuration into arbitrary TeamPolicy JSON or invent a Domain configuration table for this first slice.

Before the business commit, persist one immutable, versioned Task-attributed match-assessment Event. It should contain:

- the exact input Signal/Snapshot identity and matcher version;
- embedding-space and chunking identities;
- disposition result and reason;
- bounded, deterministically ordered candidate Thread evidence;
- for each retained candidate, the supporting evidence Signal/Snapshot identity, chunk index/hash, and score;
- the selected Thread or canonical duplicate Signal reference, if any;
- a canonical assessment fingerprint.

Persist scores as canonical decimal strings with a specified precision/rounding rule. Candidate bounds and payload size must be frozen before implementation.

#### Assessment receipt identity and recovery contract

The assessment Event is an immutable, versioned recovery receipt, not merely an informational log entry. Before implementation, freeze all of the following:

1. **One receipt per Task.** The first slice produces at most one canonical assessment for a triage Task. The receipt identity is derived from the Task ID and a fixed assessment kind/version; it is not keyed only by attempt number. Retries of the same immutable Task must resolve the same receipt.
2. **Database-enforced uniqueness.** Enforce uniqueness for that canonical identity in the database. An application-side existence check is not sufficient under concurrent attempts. If two attempts race, the losing transaction loads the winning receipt and verifies its Task ID, request fingerprint, schema version, and canonical assessment fingerprint. It may reuse the winner only when those values agree; a mismatch is an integrity failure, never an invitation to overwrite or append a second competing receipt.
3. **Durable-before-business transaction boundary.** Receipt insertion and its canonical identity must be committed atomically in a transaction that completes before the separate business-commit transaction begins. This ordering is required by the recovery claim: after the receipt transaction commits, a crash before business commit must leave the receipt durable for exact replay. If receipt and business mutation share one transaction, the receipt is not durable independently and cannot serve as the promised pre-commit recovery receipt; that alternative is therefore not supported by this proposal. The implementation must define how a Task remains recoverable between these two commits and how a failed business commit is retried from the receipt. Do not describe an uncommitted Event as a durable recovery receipt.
4. **Kernel authorization.** Define the exact Task type / Kernel write scope and the single authorized Kernel path for this Event. Do not widen a generic Event allow-list without an explicit scope decision. TaskRuntime continues to own attempts, interruption, recovery, and terminal outcomes.
5. **Recovery states.** No receipt means assessment has not durably completed and recovery follows the Task's existing retry/recovery policy. One valid receipt means replay that exact assessment without rerunning similarity. A corrupt receipt, multiple receipts, or a receipt whose request/fingerprint does not match the immutable Task is an integrity failure and must fail closed. A receipt already committed to a business disposition returns the original result without a second disposition, Thread transition, or business Event.
6. **No attempt-specific semantic drift.** A new Task attempt cannot change matcher version, projection identity, or candidate result. Those are pinned by the immutable request and receipt. If canonical references are no longer valid at commit, fail closed; do not rerun matching or choose a replacement candidate.

The document does not prescribe a particular Event table migration or invent a generic idempotency framework. The exact Event type, schema version, unique key representation, transaction boundary, and recovery tests are implementation prerequisites and remain open for review.

The matcher must not store vectors or copy full source text into Event payloads. Snapshot references, hashes, chunk identities, and scores provide bounded provenance.

## 7. Commit and concurrency boundary

Candidate search is read-only. It cannot create dispositions, mutate Threads, change Hypotheses, or enqueue `update_thread` Tasks.

The existing Kernel commit boundary remains responsible for atomically committing the disposition, any permitted dormant-to-active Thread transition, and the Task-attributed business Event. Task admission, attempts, retries, recovery, and terminal outcomes remain TaskRuntime-owned.

At commit, validate again:

- Task and immutable request fingerprint;
- Signal/Snapshot/hash and same-Team ingestion Event association for the incoming Signal and every contributing evidence Signal;
- for every selected evidence link, EvidenceLink snapshot pair exactly matches its canonical Signal Snapshot/hash; absent or mismatched provenance is not silently repaired;
- Team active status and exact Domain equality;
- disposition uniqueness for `(signal_id, team_id)`;
- selected Thread belongs to the same Team and Domain and is not resolved;
- selected duplicate Signal is canonical and belongs to the same Team's intake history;
- assessment Event belongs to the same Task and has not already been committed.

A replay of an already committed assessment returns the original business result and emits no second disposition, transition, or Event.

**D6.1–D6.6 are accepted; RW4-5 implementation remains gated.** A dormant Thread may receive a `matched` disposition only when the same valid triage Task atomically reactivates it, records exactly one immutable Task-attributed `thread_reactivated` Event, preserves `Thread.last_updated_at`, increments Team `world_memory_revision`, and commits the disposition plus TaskRuntime terminal evidence in the same transaction. Use the accepted RW-5 canonical lock order; do not invent a second helper or lock path. Until separately authorized and proven RW4-5 implementation, a dormant would-be winner remains terminal deferred with `dormant_thread_requires_reactivation`. Do not mutate Hypothesis `last_touched_at`.

## 8. Required fixture evidence before D4 can close

Create a deterministic, offline newsroom fixture set. It is separate from Experiment A and RWN-01; neither is a substitute for matching evaluation.

At minimum include:

1. Exact same-origin/same-content ingestion replay (one canonical Signal).
2. Exact same bytes at different origins within one Team (duplicate).
3. Same bytes ingested by different Teams (not cross-Team duplicate).
4. Near-duplicate syndicated copy with changed markup/whitespace (not exact duplicate; not auto-duplicate in v1).
5. A clear update to one existing Thread with multiple historical evidence Signals.
6. Two unrelated Threads sharing broad topic vocabulary (hard negative).
7. One Signal with two plausible Thread candidates (must defer unless calibrated winner margin is met).
8. A dormant Thread with strong supporting/challenging matching evidence (candidate only; reactivation remains gated by D6).
9. A Thread represented only by `mentions` EvidenceLinks (not a candidate in v1).
10. A resolved Thread with otherwise strong evidence (excluded).
11. Thread with no eligible Signal-backed EvidenceLinks (unmatchable; must not cause new Thread creation).
12. No valid incoming KnowledgeChunk projection at Task admission (Task creator rejects without creating Task); queued Task whose immutable matcher pins are no longer supported (terminal `matching_pins_superseded`, no retry/replacement); candidate profile lacking a compatible projection (candidate excluded and may contribute to a valid deferred result); and required projection loss after admission while pins remain supported (TaskRuntime technical-failure/recovery path, not deferred or stale-pin supersession; exact reason mapping remains unresolved).
13. Mismatched embedding-space key or chunking version.
14. Corrupt or mismatched Signal Snapshot/hash (integrity failure; fail closed through TaskRuntime, never deferred).
15. Domain mismatch and cross-Team evidence attempts, including an EvidenceLink owned by Team A that references a Signal ingested only by Team B with the same Domain.
16. Candidate/evidence scan exceeds its bound (defer; never choose from a truncated set).
17. Scores exactly at threshold and winner-margin boundaries.
18. One-candidate case (threshold applies; no runner-up margin).
19. Small and large Thread evidence profiles (measure max-score size bias and query cost).
20. Evidence profile at and above the scan bound (above bound defers).
21. One high-scoring outlier chunk among otherwise unrelated incoming chunks (must expose whether max-pairwise scoring produces a false match).
22. Several distinct Hypotheses/subtopics represented in one Thread, with evidence spread across different numbers of Signals.
23. The same relevant evidence distributed across differently sized profiles, to measure profile-size bias.
24. EvidenceLinks whose snapshot pair is absent, disagrees with the canonical Signal Snapshot, or matches it exactly; only the exact-match case may contribute. Separately verify that the database rejects a partially populated snapshot pair.
25. Supporting and challenging links attached to active, superseded, and rejected Hypotheses, with independent labels to determine whether historical lifecycle states improve or degrade Thread identity.

The fixture must label the intended Thread or duplicate identity independently of the matcher. Report false-positive and false-negative cases, not just aggregate accuracy. Report the max-score outlier cases and stratify results by evidence-profile size and Hypothesis lifecycle state. Numeric threshold, margin, candidate/evidence bounds, score precision, and acceptable query cost remain open until this evidence is reviewed. D4's decision shape is accepted; if no defensible threshold or cost bound exists, the affected matching cases remain deferred and RW4-3 cannot enable them.

The operational scan bound must be defined separately for candidate Threads, evidence Signals, and evidence chunks. Specify how the query detects that a bound is exceeded without first loading an unbounded eligible set; document the relevant query plan and measured cardinalities on a disposable fixture database. The matcher must never rank a truncated candidate set as though it were complete. If the bound cannot be checked within the accepted query-cost budget, defer rather than scan or select from a partial result.

## 9. Consequences and explicit non-goals

**Benefits**

- No new canonical table or column for matching.
- No Thread embedding or summary projection.
- No model/provider call during triage.
- Existing immutable Snapshots and rebuildable chunk projections retain their established roles.
- Thread identity is grounded in accepted, Team-scoped world-memory evidence rather than an invented profile.
- Exact duplicate detection is transparent and independently testable.

**Limitations**

- Threads without Signal-backed EvidenceLinks cannot be matched automatically.
- Embedding-space migration/rebuild can temporarily make a Signal or Thread profile unmatchable.
- Maximum pairwise similarity can produce false positives and requires fixture calibration.
- Exact-hash dedup misses near-duplicates.
- The first slice cannot create new Threads or classify noise.
- The Team association for incoming Signals depends on valid ingestion Events; a missing/corrupt Event fails closed.

Explicitly excluded: entity extraction/alias tables, Thread embeddings, new Domain ORM/configuration, near-duplicate classification, model triage, Thread creation, automatic noise classification, deferred refinement, Hypothesis/EvidenceLink mutation, Task scheduling/dispatcher expansion, RW4-4 Context assembly, RW4-KU, and RW-5 implementation.

## 10. Remaining decisions and closure gates

| Gate | Proposed resolution | Still required |
|---|---|---|
| D4 representation | Reuse EvidenceLink-derived Thread evidence profile + Signal KnowledgeChunk vectors | Accepted 2026-11-25; numeric/operational evidence remains open |
| D4 exact dedup | Exact raw content hash within one Team regardless of origin; first committed Team/hash Signal is canonical | Accepted 2026-11-25; persistence design and PostgreSQL concurrency proof remain open |
| D4 semantic match | Max pairwise chunk cosine score is an experimental baseline only | D4.2 shape accepted 2026-11-25; labeled fixture, outlier/profile-size evaluation, numeric calibration, bounded candidate query, score serialization, actual pins, and query-cost proof remain open |
| D4 near duplicate | Exclude from first slice | Accepted 2026-11-25 |
| D4.3 new Thread | Disable automatic creation in v1; no match becomes terminal deferred | Accepted 2026-11-25; any later capability needs a separate design/decision |
| D5.1–D5.4 disposition | Exactly `matched`, `duplicate`, `deferred`; accepted reference matrix and reason vocabulary | Accepted 2026-11-25; physical persistence remains gated |
| D3 deferred lifecycle | Deferred is immutable/terminal and successful (`done`); technical/integrity failures are not deferred | Accepted; RW4-1 atomic persistence proof remains gated |
| D6 reactivation | Matched-only dormant reactivation; preserve Thread timestamp; Team revision increment; atomic TaskRuntime commit and immutable Event under canonical RW-5 locks | Accepted 2026-11-25; RW4-5 implementation, DB uniqueness, race/recovery proof, and separate authorization remain required |
| Task/recovery | Pin matcher + projection identity; persist assessment receipt | Exact Event schema, canonical one-per-Task identity, database uniqueness, transaction boundary, bounds, and recovery tests |
| Evidence provenance | Require same-Team Signal intake association and matching EvidenceLink snapshot pair | Cross-Team same-Domain and absent/mismatched-pair fixtures |
| Scoring heuristic | Max pairwise score remains experimental only | Outlier, profile-size, lifecycle-state fixtures and accepted false-positive tolerance |
| Query bounds | Bound Thread, Signal, and chunk scans separately | Bounded overflow detection, query plan, and measured cost |
| RW3.4 gate | Formal acceptance still deferred | Acceptance or explicit sequencing exception before RW4 implementation |

No implementation or schema work begins from this supporting artifact alone. D3–D6 decision contracts are accepted, but RW4-1 physical persistence, RW4-3 matcher evidence closure, RW4-5 reactivation implementation, the Task envelope/assessment-receipt proof, and each slice's explicit authorization remain separate prerequisites. RW3.4 may proceed only under its recorded sequencing exception; formal acceptance remains deferred.

## 11. Selected design options for the next review

The Operator selected the following options for this proposal. These selections settle the direction of the design document; they do not freeze a production algorithm or authorize implementation.

### A1 — Hypothesis lifecycle evidence

Use active, superseded, and rejected Hypotheses as the **experimental baseline** for the Thread evidence profile. Preserve lifecycle state and EvidenceLink stance in the assessment evidence, and report matching outcomes separately by lifecycle state. The fixture set must reveal both beneficial historical evidence and false matches caused by stale or rejected evidence. Do not assume the three states are equally reliable. Their eventual production eligibility remains subject to fixture results and explicit Operator acceptance.

### B1 — Maximum pairwise similarity

Retain maximum pairwise chunk cosine similarity as the **experimental baseline heuristic only**. Evaluate high-scoring outlier chunks, Thread profile-size bias, multiple Hypotheses/subtopics, and false-positive/false-negative rates. It is not an accepted final scoring rule. If the evidence does not establish an acceptable false-positive tolerance, reject the heuristic or keep matching deferred.

### C1 — Assessment receipt durability

Use a separately committed assessment-receipt transaction before the distinct Kernel business-commit transaction. Receipt uniqueness is database-enforced and canonical per Task; retries reuse and validate the durable receipt. The implementation must prove recovery across the boundary between those transactions. A shared receipt/business transaction is not an equivalent substitute for this guarantee.

### D1 — Documentation scope

Keep this PR limited to the matching-representation proposal. Reconcile the architecture implementation-state table's stale EvidenceLink description in a separate, small documentation change after this proposal is reviewed. Do not expand this PR to include that unrelated correction.

### Preserved boundaries

The D4, D5, and D6 decisions now accepted by the Operator supersede the former open-decision wording in this historical proposal. They do not close the remaining RW4-0 evidence gates, settle numeric thresholds or scan budgets, satisfy the RW3.4 sequencing gate, or authorize application code, tests, schema, migrations, database operations, provider calls, or scored experiments.
