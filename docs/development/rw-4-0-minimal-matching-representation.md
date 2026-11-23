# RW4-0 — Minimal Signal/Thread matching representation

**Status:** Design proposal for Operator review. This document does not accept D4/D5/D6, close RW4-0, or authorize implementation.

**Baseline:** PR #174 merge `0d1e262c77bc79af7edf93c5f4c116cdb01475c2`.

**Evidence audit:** [PR #175](https://github.com/abtn/Watch-Architecture-Rev2/pull/175), whose read-only source audit is based on the same baseline.

## 1. Decision sought

Approve or amend a deliberately narrow first matching representation:

- Reuse canonical `Signal`, immutable Snapshot, `EvidenceLink`, `Hypothesis`, `Thread`, and the existing rebuildable `KnowledgeChunk` projection.
- Derive each Thread's matching evidence set from its existing Signal-backed EvidenceLinks. Do not persist a Thread embedding, entity table, alias subsystem, or separate Domain ORM.
- Use exact raw-content hash for duplicate detection in the Team's own Signal intake history. Do not classify near-duplicates in the first slice.
- Use same-embedding-space Signal chunk similarity to find a unique existing Thread candidate. No model call or re-embedding occurs during triage.
- Restrict automatic first-release outcomes to `matched`, `duplicate`, and terminal `deferred`. Do not create Threads, automatically label `noise`, or refine deferred dispositions in this slice.

This is a proposal, not a frozen algorithm. The numeric similarity threshold, winner margin, candidate bound, fixture evidence, and RW-5 concurrency contract remain explicit gates.

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

The incoming Signal must have a Team association through an `ingest_source` Task Event of type `signal_ingested` or `fetch_no_change`. The Event's Task must belong to the requested Team and identify the same Signal. Missing or inconsistent association fails closed.

The matcher does not call an embedding provider. If the Signal is not indexed, its projection is stale, or the pinned embedding space is unavailable, the result is `deferred` with a precise reason. It must not silently invoke a provider or substitute a different model space.

### 3.2 Thread evidence profile

For one Team, derive candidate Threads from:

- `EvidenceLink.team_id = Team.id`
- `EvidenceLink.subject_kind = 'hypothesis'`
- `EvidenceLink.source_kind = 'signal'`
- `EvidenceLink.hypothesis_id → Hypothesis.id`
- `Hypothesis.team_id = Team.id`
- `Hypothesis.thread_id → Thread.id`
- `Thread.team_id = Team.id`
- `Thread.domain = Team.domain`
- `Thread.status IN ('active', 'dormant')`

Include Signal-backed EvidenceLinks across Hypothesis lifecycle states. An accepted EvidenceLink remains part of the Thread's evidence history even if its Hypothesis is later superseded or rejected. Do not include Outcome-backed EvidenceLinks in this Signal-to-Signal matcher.

For every contributing Signal, validate that its Domain matches the Team and that its chunk projection still points to its canonical Snapshot/hash. Only chunks with the incoming Signal's exact `embedding_space_key` and supported `chunking_version` are comparable.

A Thread with no eligible Signal-backed EvidenceLink, no compatible chunk projection, or no common embedding space has no usable profile in this matcher. It is **unmatchable**, not evidence that a new Thread should be created.

Resolved Threads are excluded. Active and dormant Threads are both candidates; the dormant transition is handled separately under D6/RW-5.

## 4. Three separate decisions

### 4.1 Exact duplicate Signal

Run exact duplicate detection before Thread matching.

- Scope: Signals already associated with the same Team through `ingest_source` Events of type `signal_ingested` or `fetch_no_change`.
- Rule: another Signal with exactly the same raw `content_hash` is an exact duplicate.
- Canonical duplicate: earliest Team-association Event `created_at`, then Signal UUID ascending as a stable tie-break.
- Exclude the incoming Signal itself.
- The duplicate disposition references the canonical Signal and makes no Thread mutation.

The existing unique constraint on `(origin_url, content_hash)` already prevents a second Signal for the same origin/content pair. This rule adds only cross-origin exact-byte detection inside the Team's own intake history.

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

If no candidate reaches the threshold, multiple Threads tie, the best/second-best margin is insufficient, required evidence is missing, or candidate ranking is ambiguous, return `deferred`. UUID ordering may stabilize evidence serialization but must never break a semantic score tie.

No recency bonus is proposed initially. `Thread.last_updated_at` is not currently established as a matching clock, and adding it without a lifecycle contract would make the score depend on an unproven timestamp meaning.

**Important limitation:** maximum pairwise chunk similarity is intentionally a small candidate heuristic, not proof that two Signals describe the same event. Its threshold and margin must be calibrated against labeled positive and hard-negative newsroom fixtures. If that evidence does not support acceptable precision, the matcher must remain deferred or the representation must be reconsidered; it must not be made more permissive by intuition.

### 4.3 New Thread eligibility

Not supported in this first slice.

The current Signal record has no canonical title/headline, and the Snapshot ingestion path does not persist a deterministic title extraction. The Thread title is required and non-empty. A URL-derived title is not accepted as a newsroom title source, and model-generated titles are outside this deterministic triage boundary.

Therefore:

- no existing Thread match does not imply `new_thread`;
- this matcher never creates a Thread;
- absence of a candidate, insufficient evidence, or an unmatchable Thread set results in `deferred`;
- `new_thread` remains disabled until a separate canonical title source and eligibility rule are demonstrated and accepted.

## 5. First-slice disposition vocabulary

| Result | Required durable reference | Side effect |
|---|---|---|
| `duplicate` | canonical same-Team duplicate Signal | disposition only |
| `matched` | one existing same-Team/domain Thread | disposition; dormant reactivation only if D6/RW-5 contract is accepted |
| `deferred` | explicit reason code | disposition only |

The first slice does not automatically emit:

- `new_thread`: no safe title source or strong new-Thread rule;
- `noise`: no deterministic, source-backed noise classifier is established;
- near-duplicate `duplicate`: no validated near-duplicate policy or numeric threshold.

Deferred is terminal in this release, consistent with D3's proposal. No `update_thread` or `operator_update` SignalDisposition refinement is introduced.

This narrowing is a proposal for Operator acceptance. It changes the target disposition coverage and must be reflected consistently in the architecture state table and Task/write-scope matrix before any schema or implementation work.

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

The assessment Event is the recovery receipt. If a Task crashes after assessment but before business commit, recovery reuses that exact assessment and does not rerun similarity against a potentially rebuilt projection. Commit still revalidates canonical Signal/Team/Thread references and the current Thread state. If that revalidation fails, fail closed; do not silently select a different Thread during replay.

The matcher must not store vectors or copy full source text into Event payloads. Snapshot references, hashes, chunk identities, and scores provide bounded provenance.

## 7. Commit and concurrency boundary

Candidate search is read-only. It cannot create dispositions, mutate Threads, change Hypotheses, or enqueue `update_thread` Tasks.

The existing Kernel commit boundary remains responsible for atomically committing the disposition, any permitted dormant-to-active Thread transition, and the Task-attributed business Event. Task admission, attempts, retries, recovery, and terminal outcomes remain TaskRuntime-owned.

At commit, validate again:

- Task and immutable request fingerprint;
- Signal/Snapshot/hash and Team association;
- Team active status and exact Domain equality;
- disposition uniqueness for `(signal_id, team_id)`;
- selected Thread belongs to the same Team and Domain and is not resolved;
- selected duplicate Signal is canonical and belongs to the same Team's intake history;
- assessment Event belongs to the same Task and has not already been committed.

A replay of an already committed assessment returns the original business result and emits no second disposition, transition, or Event.

**D6 remains open.** The matcher may identify a dormant Thread, but it does not decide whether matching resets any decay clock. It must not mutate Hypothesis `last_touched_at`. The authoritative Thread timestamp, triage/decay lock order, and decay-first/triage-first outcomes must be agreed with RW-5 before reactivation can be implemented. No lock order is invented in this document.

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
8. A dormant Thread with strong matching evidence (candidate only; reactivation remains gated by D6).
9. A resolved Thread with otherwise strong evidence (excluded).
10. Thread with no Signal-backed EvidenceLinks (unmatchable; must not cause new Thread creation).
11. Missing/stale KnowledgeChunk projection.
12. Mismatched embedding-space key or chunking version.
13. Corrupt or mismatched Snapshot/hash.
14. Domain mismatch and cross-Team evidence attempts.
15. Scores exactly at threshold and winner-margin boundaries.

The fixture must label the intended Thread or duplicate identity independently of the matcher. Report false-positive and false-negative cases, not just aggregate accuracy. Numeric threshold, margin, candidate bound, and score precision are not accepted until this evidence is reviewed. If no defensible threshold exists, D4 remains open.

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
| D4 representation | Reuse EvidenceLink-derived Thread evidence profile + Signal KnowledgeChunk vectors | Operator acceptance of this representation |
| D4 exact dedup | Team-scoped exact content hash only | Confirm canonical Team-association Event query and fixture proof |
| D4 semantic match | Max pairwise chunk cosine score; unique threshold + margin | Labeled fixture, numeric calibration, bounded candidate query |
| D4 near duplicate | Exclude from first slice | Explicitly accept the reduced coverage |
| D5 new Thread | Disable | Separate title-source/eligibility proposal if later required |
| D5 noise | Disable automatic classification | Separate deterministic rule if later required |
| D3 deferred | Terminal | Reconcile architecture lifecycle and Task write-scope matrix |
| D6 reactivation | Matching may identify dormant Thread only | RW-5 timestamp and shared lock-order decision |
| Task/recovery | Pin matcher + projection identity; persist assessment receipt | Exact Event schema, bounds, uniqueness, and recovery tests |
| RW3.4 gate | Formal acceptance still deferred | Acceptance or explicit sequencing exception before RW4 implementation |

No implementation or schema work begins until the representation, narrowed outcomes, fixture results, Task envelope, assessment receipt, D3 reconciliation, D6/RW-5 contract, and RW3.4 sequencing gate are reviewed and explicitly accepted.

## 11. Operator decision requested

Please review these specific choices:

1. Accept a Thread's matching representation as the set of its existing Team-scoped Signal-backed EvidenceLinks, with no persisted Thread embedding.
2. Accept exact-content-hash duplicate detection only; defer near-duplicate detection.
3. Accept same-space Signal chunk similarity as a candidate heuristic, with numeric threshold and winner margin left open until fixture evidence.
4. Narrow first-release outcomes to `matched`, `duplicate`, and terminal `deferred`; disable `new_thread` and automatic `noise`.
5. Keep D6 reactivation blocked on RW-5's timestamp and lock-order contract.

This document is a design proposal only. It does not accept D4/D5/D6, close RW4-0, or authorize application code, tests, schema, migrations, database operations, provider calls, or scored experiments.
