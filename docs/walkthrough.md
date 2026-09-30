# docs/walkthrough.md

# Walkthrough

Three concrete traces of the operating loop, using only v1 entities, glossary terms, and the flows defined in `docs/architecture.md` §5. Every record shown is legal per the state machines in §4, and the invariant that guards each step is cited inline as `INV-NN`.

This document doubles as the spec for integration test fixtures: `tests/fixtures/` may reproduce these exact records.

**Conventions:** IDs are shortened for readability (`S-1041`, `TH-101`); production IDs are UUIDs. Timestamps are ISO-8601, abridged to the fields relevant at each step. Snapshot hashes are abridged (`sha256:9f21c…`). Quotes shown are illustrative; in tests, fixture snapshots contain the exact quoted substrings at the recorded offsets.

---

## Scenario A — Newsroom: the oil desk

The deep trace: ingestion → triage → update with rejections → decay → render with code-assembled citations → prediction registration and verification → evaluation → first learned playbook.

### A.1 Setup (2025-05-20)

This trace starts with an already-created and active Team TM-01. Team
creation/activation is a prerequisite to this scenario, not a write performed
by `seed_knowledge`. The Team record below is shown as prerequisite scenario
state. The Operator seeds the initial policy and KnowledgeItem via
`seed_knowledge` (TSK-001):

```json
{
  "id": "TM-01", "key": "oil-desk", "domain": "newsroom",
  "name": "Oil Desk",
  "mission": "Track OPEC+ supply policy and inventory dynamics; maintain an evidence-backed position on crude price direction through Q3 2025.",
  "status": "active"
}
```

TeamPolicy v1 (POL-01, activated by the same seed):

```json
{
  "routing": { "deferred_signals": "enqueue_update_thread" },
  "review": { "policy_changes": "operator", "learning_changes": "operator" },
  "knowledge_selection": { "max_items": 2, "kinds": ["practice", "playbook"] },
  "thresholds": { "render_briefing": "any hypothesis high AND >=3 verified evidence links" },
  "budgets": { "max_tasks_per_day": 40, "max_cost_usd_per_day": 8.00 },
  "preferences": { "artifact_types": ["briefing", "article", "daily_digest"] }
}
```

One KnowledgeItem is seeded (K-07, practice, v1):

> **Separate supply-side and demand-side explanations before raising confidence on price direction.** Inventory draws are consistent with both managed supply and demand shifts; never let one report move a price-direction hypothesis without attributing the mechanism.

### A.2 Day 1 — Ingestion (F1)

`ingest_source` TSK-201 polls the EIA weekly petroleum status report feed.

1. Content fetched; Snapshot stored first: `snap://signals/eia-wpsr-2025-06-04`, `sha256:9f21c…` (INV-03).
2. Signal committed:

```json
{
  "id": "S-1041", "domain": "newsroom", "source_type": "rss",
  "origin_url": "https://www.eia.gov/petroleum/supply/weekly/pdf/wpsrall.pdf",
  "fetched_at": "2025-06-04T15:02:11Z",
  "content_hash": "sha256:9f21c…",
  "extracted_summary": "Commercial crude inventories drew 4.2M bbl week ending May 30; fourth consecutive weekly draw; implied demand +2.1% y/y.",
  "embedding_model": "voyage-3"
}
```

3. A refetch at 16:00 returns byte-identical content → no new Signal; Event `fetch_no_change` (INV-03).

A second feed item the same day — a Reuters story syndicating the same report — becomes S-1042 (different origin, different hash: a new Signal, by design; dedup happens at triage, ADR-0017).

### A.3 Day 1 — Triage (F1)

`triage_signal` TSK-202 runs the newsroom `match_heuristics`:

- Entities normalized via the alias table: `organization: opec+`, `commodity: crude`, `metric: inventories`, `region: us`.
- Thread TH-101 ("OPEC+ voluntary cuts vs. seasonal demand recovery", `active`) shares 3 entities and has embedding similarity 0.83 ≥ threshold 0.75 → candidate.
- S-1042 vs S-1041: page-level cosine similarity 0.94 ≥ dedup threshold 0.90 within the 7-day lookback → `duplicate`.

Committed dispositions (INV-09 — one row per signal per team, never implicit):

```json
{ "signal_id": "S-1041", "team_id": "TM-01", "thread_id": "TH-101",
  "disposition": "matched", "reason": "3 entity overlap; emb 0.83", "decided_by_task_id": "TSK-202" }
{ "signal_id": "S-1042", "team_id": "TM-01", "duplicate_of_signal_id": "S-1041",
  "disposition": "duplicate", "reason": "syndicated copy of S-1041", "decided_by_task_id": "TSK-202" }
```

Cross-team note: the rates desk (TM-02) dispositioned S-1041 as `noise` the same hour — signals are unowned; relevance is per-team (ADR-0012).

An `update_thread` task is enqueued for the matched thread.

### A.4 Day 1 — Update (F2)

`update_thread` TSK-203, budget 8 tool calls / $0.50 / 180 s. Context loaded from entities only (INV-01): TH-101, its three active hypotheses, dispositions, policy POL-01, and — bounded by `knowledge_selection` — K-07 (1 of max 2 items).

Current hypotheses: **H-101a** (moderate) "OPEC+ extends voluntary cuts into H2; draws continue under managed supply"; **H-101b** (moderate) "Inventory builds reflect weak demand; OPEC+ unwinds cuts"; **H-101c** (low) "Refinery maintenance, not OPEC policy, explains the draws".

The model returns five proposals. Deterministic validation runs per proposal (INV-02); the accepted set then commits atomically (INV-13):

| # | Proposal | Validation | Result |
|---|---|---|---|
| 1 | EvidenceLink E-01: S-1041 → H-101a, `supports`, quote "Commercial crude inventories drew 4.2 million barrels in the week ending May 30, the fourth consecutive weekly draw." @ [318, 401] | hash matches snapshot; exact substring at offsets | **accepted** |
| 2 | EvidenceLink E-02: S-1041 → H-101b, `challenges`, quote "Implied demand rose 2.1 percent year over year." @ [512, 556] | passes | **accepted** |
| 3a | EvidenceLink E-03: S-1043 (analyst note) → H-101a, `mentions` | quote passes | **accepted** (context only) |
| 3b | ConfidenceChange on H-101a, cause = E-03 | `stance="mentions"` may never anchor confidence (INV-06) | **rejected** |
| 4 | ConfidenceChange CC-01: H-101a moderate → `high`, cause = E-01 | evidence cause, supporting stance, cause pairing complete (INV-05) | **accepted** |
| 5 | Reject H-101c, reason "Two consecutive reports contradict the maintenance explanation; maintenance season ended 2025-05-25" | terminal transition with reason + Event (INV-07) | **accepted** |

One more proposal — EvidenceLink E-04 with offsets [88, 210] on S-1043 — fails: the substring at those offsets is not the quoted text (INV-04). **Rejected** with Event `proposal_rejected {reason: "quote_offset_mismatch"}`. Nothing about the rejection is silent; it also feeds the validation-rejection-rate metric (architecture §11).

Commit (single transaction): E-01, E-02, E-03, CC-01, H-101c → `rejected`. Events: `evidence_link_added` ×3, `confidence_changed`, `hypothesis_rejected`, `proposal_rejected` ×2. `last_touched_at` bumped on H-101a and H-101b only (accepted evidence); never by decay later. Thread summary regenerated with `summary_basis: ["H-101a", "H-101b"]` — a projection, never read as authority (INV-11).

The team did **not** converge to one verdict: H-101a `high`, H-101b `low`, H-101c `rejected`, all auditable.

### A.5 Days 3–12 — compressed

- **06-06:** S-1047 (OPEC+ meeting outcome) confirms extension → H-101a holds `high` (E-05). H-101d ("OPEC+ will deepen cuts") proposed and then **superseded by H-101a** with reason + Event — the merge-as-supersession path (INV-07).
- **06-06:** scheduled `apply_decay` TSK-214: H-101b `last_touched_at` is >72 h old → moderate → `low`, ConfidenceChange with `cause_kind="decay"`, `decay_task_id=TSK-214` (INV-05, INV-08). H-101a is still `high`, so TH-101 stays `active`. A one-proposal learning change (LC-009, from an older weak evaluation) is **rejected by the Operator** — learning stays conservative (INV-12).
- **06-14:** threshold Trigger TRG-02 fires ("any hypothesis high AND ≥3 verified evidence links") → `render_output` TSK-219. Triggers create Tasks; they never publish directly.

### A.6 Day 12 — Render (F4)

The evidence pack is assembled **by code** from verified EvidenceLinks E-01, E-05, E-06. The model drafts prose against the pack only — it never sees or writes citation metadata (INV-10). Code appends the footer:

```text
Sources
[1] EIA Weekly Petroleum Status Report, week ending 2025-05-30. eia.gov/petroleum/supply/weekly/
    snapshot sha256:9f21c… — supports "OPEC+ extends voluntary cuts…" ("Commercial crude
    inventories drew 4.2 million barrels…")
[2] OPEC+ meeting communiqué, 2025-06-06. opec.org/…
    snapshot sha256:44be7… — supports (voluntary cuts extended through Q3)
[3] EIA Weekly Petroleum Status Report, week ending 2025-06-06.
    snapshot sha256:c81a2… — supports (fifth consecutive weekly draw)
```

Deterministic post-check: no URL/link patterns in the body (the footer is code-appended and exempt) → pass. Artifact committed:

```json
{ "id": "A-009", "team_id": "TM-01", "task_id": "TSK-219", "artifact_type": "briefing",
  "title": "Crude draws continue under extended OPEC+ cuts",
  "snapshot_ref": "snap://artifacts/a-009", "content_hash": "sha256:7d3e1…", "status": "draft" }
```

The Operator delivers it; A-009 → `delivered`, and `record_outcome` TSK-221 logs Outcome O-013 (`delivery`).

### A.7 Day 12 — Register the prediction

The briefing's central claim is falsifiable, so the Operator registers it **before** knowing the result, via `record_outcome` TSK-230. This is the registration half of a prediction check (ADR-0013): an Outcome with no observation yet.

```json
{ "id": "O-021", "team_id": "TM-01", "subject_kind": "hypothesis", "subject_id": "H-101a",
  "outcome_type": "prediction_registered",
  "expected": {
    "resolution_condition": "EIA weekly reports for the four weeks ending 2025-07-18 show net commercial crude draws while OPEC+ voluntary cuts remain in force",
    "check_by": "2025-07-25T00:00:00Z",
    "predicted_band": "high" },
  "observation_snapshot_ref": null, "observation_hash": null }
```

### A.8 Day 30 — Observe

`record_outcome` TSK-238 records the observation against the same subject, type `prediction_check`, `expected.registered_outcome_id = "O-021"`. Observation Snapshot: the four EIA weekly reports compiled; `observed_at: 2025-07-22`. Result: cumulative draws of 11.8M bbl; cuts extended through Q3 on 2025-07-01.

The scheduler's overdue scan would have flagged O-021 had `check_by` passed with no recorded check (architecture §5 F5).

### A.9 Day 31 — Evaluate (F5)

`evaluate_outcome` TSK-240 (model evaluator) reads O-022, O-021, H-101a, and the evidence, then proposes:

```json
{ "id": "EV-006", "team_id": "TM-01", "outcome_id": "O-022",
  "subject_kind": "hypothesis", "subject_id": "H-101a", "conclusion": "mixed",
  "findings": {
    "direction": "correct — cumulative draws of 11.8M bbl under extended cuts",
    "resolution_quality": "weak — the registered condition was qualitative; a 1M bbl cumulative draw would also have passed",
    "improvement": "register numeric magnitude and direction for quantity-bearing hypotheses",
    "notes": "one subsidiary claim (implied demand +2.1% y/y) was not re-verified" },
  "evaluator_kind": "model", "status": "proposed" }
```

Validation passes (same team; conclusion vocabulary; the EvidenceLink subject_kind="evaluation" citing O-022's observation snapshot with a checked quote — INV-04). **Recorded.** The evaluation is a proposal with provenance, not an oracle (ADR-0003).

### A.10 Day 33 — Learn (F6)

`propose_learning_change` TSK-244 reads EV-006 and proposes:

```json
{ "id": "LC-014", "team_id": "TM-01", "basis_kind": "evaluation", "basis_id": "EV-006",
  "target_kind": "knowledge_item", "target_id": null, "operation": "create",
  "proposed_state": {
    "kind": "playbook",
    "title": "Register numeric resolution conditions for quantity-bearing hypotheses",
    "statement": "When a hypothesis implies a measurable quantity — inventories, prices, poll share — prediction registrations must state magnitude and direction, not direction alone.",
    "confidence": "moderate", "review_after": "2025-10-31T00:00:00Z" },
  "status": "proposed" }
```

The Operator approves via `approve_learning_change` TSK-245. The commit service verifies, in order: basis Evaluation is recorded and belongs to TM-01 ✓; supporting evidence exists ✓; target version unchanged (create — no target) ✓; proposed state matches the operation and schema ✓; task scope ✓; Operator approval identity recorded in the Event payload ✓ (INV-12). **K-12 created, v1, active.**

Note what was *not* learned: nothing became a playbook from the successful direction call — the lesson came from the **mixed** quality of the check. That is the design working (ADR-0003).

### A.11 Day 34 — The loop closes

The next `update_thread` TSK-250 loads context; `knowledge_selection` retrieves K-07 and K-12 (2 of max 2, by embedding relevance). The playbook written on day 33 now constrains how day-34 evidence is handled. No code path special-cased this — retrieval is policy-driven.

### A.12 The month, as the README defines "working"

| Records created (30 days) | |
|---|---|
| Signals / Dispositions | 41 / 41 (+ per-team noise from TM-02) |
| Threads | 2 active, 1 dormant (set by decay) |
| Hypotheses | 5 created; 1 rejected, 1 superseded — both explicit, both with Events |
| ConfidenceChanges | 6 (4 evidence, 2 decay) — every one has a cause |
| Artifacts | 3 (1 briefing, 2 digests), citations code-assembled |
| Outcomes | 5 (1 delivery, 1 registered prediction, 1 check, 2 feedback) |
| Evaluations | 3 (worked / mixed / inconclusive) |
| LearningChanges | 2 (1 accepted → K-12; 1 rejected for weak basis) |

Checklist against `README.md` → "What working looks like": hypotheses supported, challenged, superseded, rejected ✓; every confidence change explained ✓; stale assessment (H-101b) lost confidence on schedule ✓; summary traceable via `summary_basis` ✓; outcome recorded, evaluated, and converted into exactly one conservative, evidence-backed practice ✓.

---

## Scenario B — Devteam scout: the same loop, a different kind of work

Shorter trace with a different center of gravity: here the failure is in the team's **method**, not its world model, and the learning is a **revision** of an existing practice rather than a creation.

### B.1 Setup

Team TM-11 `dev-scout` (domain `devteam`), `decay_window` 14 days. Among its seeded knowledge: **K-003** (practice, v1):

> **Deduplicate syndicated reposts against recent signals using page-level embedding similarity (threshold 0.90).** Announcement reposts otherwise inflate adoption evidence.

### B.2 Signals and dedup

Over May: S-3011 (GitHub release notes, DuckDB v1.1.3, canonical origin), plus two reposts → `duplicate` of S-3011 (dedup working as intended). Thread TH-301 "DuckDB for in-process analytics" accumulates: H-301a "Production-ready for single-writer embedded analytics" (`high`), H-301b "Unsuitable for multi-writer ingestion workloads" (`moderate`, supported by a postmortem quote).

### B.3 Memo

On a manual Trigger (Operator request), `render_output` TSK-317 produces A-301, a `recommendation_memo`: **adopt** for single-writer analytics; **avoid** for multi-writer ingestion. Citations assembled by code from consumed EvidenceLinks (INV-10). Delivered; delivery Outcome recorded.

### B.4 Implementation outcomes

- **O-321** (`implementation_result`, subject A-301): batch-pipeline adoption on v1.1.3 works. Supports the adopt position.
- **O-322**: another squad's multi-writer ingestion attempt fails on v1.1.3. Supports H-301b.
- **06-20:** S-3030 — the DuckDB v1.2 release notes, announcing improved concurrent-write support — is ingested, but a blog repost (S-3029) had been ingested first, and page-level similarity 0.91 got S-3030 dispositioned **`duplicate` of S-3029**, whose text lacked the concurrency item. The one signal that falsified H-301b was never seen by an update task. Dispositions are immutable history; the system does not rewrite them (see §4 note on triage refinement).
- **07-08:** **O-323** (`implementation_result`): the multi-writer retry on v1.2 succeeds.

### B.5 Evaluation — the method failure surfaces

`evaluate_outcome` TSK-341 evaluates O-323 against A-301 and H-301b:

```json
{ "id": "EV-331", "conclusion": "mixed",
  "findings": {
    "adopt_position": "further validated by O-321 and O-323",
    "avoid_position": "falsified as of v1.2 — the memo's evidence was stale at decision time",
    "root_cause": "S-3030 (canonical v1.2 release notes) was dispositioned duplicate of repost S-3029; the concurrency item existed only in the canonical text",
    "class": "method failure — dedup policy, not world model" },
  "evaluator_kind": "model", "status": "recorded" }
```

EvidenceLinks with subject_kind="evaluation" cite O-323's observation snapshot and the disposition record's events. Recorded.

### B.6 Learning — revise, don't append

`propose_learning_change` TSK-348 proposes a **revise** of K-003 (not a new item — the practice exists and is wrong at the edges):

```json
{ "id": "LC-902", "basis_kind": "evaluation", "basis_id": "EV-331",
  "target_kind": "knowledge_item", "target_id": "K-003", "operation": "revise",
  "proposed_state": {
    "version": 2,
    "statement": "Deduplicate reposts only against canonical-origin signals (the publisher of record). A repost must never absorb a canonical source's disposition; when similarity is high but authority differs, disposition deferred and let an update task decide." },
  "previous_state": { "version": 1, "statement": "Deduplicate syndicated reposts against recent signals using page-level embedding similarity (threshold 0.90)." },
  "status": "proposed" }
```

The Operator approves; the commit service's optimistic check confirms K-003 is still at v1 (INV-13); **K-003 v2 becomes active, v1 archived in `previous_state`** — auditable, never overwritten (INV-12).

### B.7 What Scenario B shows that A does not

- The **revise path** of team memory: versioned practice change with `previous_state` preserved.
- Evaluation catching a **method failure** (how the team watches) rather than a world-model failure (what it believes) — the two-memory split paying off.
- A real cost of dedup policy, and why `dedup_policy` is a first-class, learnable part of the domain contract rather than a fixed constant.
- Why dispositions being immutable is correct: the record of the mistake is the evidence that justifies the fix.

---

## Scenario C — Crypto desk: numeric evidence and an honest miss

A third kind of proof: here the subject is fast, noisy, and **partly numeric**. What C adds that A and B do not have: market data entering world memory as deterministic text snapshots (so the quote machinery applies to a funding rate exactly as it does to a wire quote), a prediction registered with a *numeric* resolution condition, and a **missed** prediction feeding back into world memory as challenging evidence — the negative-verification path.

### C.1 Setup (2025-06-18)

Team TM-21 `crypto-desk` — newsroom domain, crypto configuration — seeded by the Operator: TeamPolicy v1 (POL-21) with `sources` (three RSS feeds + one free market-data API), `thresholds`, `budgets`, and a `decay` override of 48 hours (this subject moves faster than the 72-hour newsroom default). Two practices seeded via `seed_knowledge` (both operator-carried, `manual_seed` — in v1 lessons travel between teams through humans; cross-team sharing is deferred):

> **K-C01** (playbook): *Register numeric resolution conditions for price predictions — a level and a deadline, never a direction alone.*
> **K-C02** (practice): *Deduplicate syndicated reposts only against canonical-origin signals; a repost must never absorb a canonical source's disposition.*

(K-C02 is the devteam desk's hard-won lesson, carried in deliberately — Scenario B.6's K-003 v2 semantics, seeded here from day one because crypto press is the most syndicated beat there is.)

One Thread: **TH-501** "BTC regime after the cycle peak", three active hypotheses: **H-501a** (moderate) "structural demand: sustained spot-ETF inflows grind price higher"; **H-501b** (moderate) "leverage overshoot: funding/OI build-up precedes a long-squeeze reversal"; **H-501c** (low) "distribution range: early buyers exit into ETF demand".

### C.2 Numeric signals and dedup (2025-06-19)

The market-data connector fetches the daily snapshot; the canonical-text normalizer renders it deterministically. Snapshot `snap://signals/mkt-2025-06-19`:

```text
BTC-USD daily 2025-06-19 | close 67412 | chg24h +2.3% | funding_rate 0.0125 | open_interest 18.4B | spot_etf_net_flow +214M | etf_flow_7d_avg +480M | exchange_outages none
```

Same inputs tomorrow → byte-identical text → same hash → no new Signal (INV-03 applies to rendered numerics exactly as to prose). Signal S-5010 committed. Triage (TSK-502): 3 entity overlap with TH-501 → `matched`. A wire repost of the day's ETF story (S-5011) → `duplicate` of its The Block original (S-5012) per K-C02 — the B.4 failure mode, pre-empted.

### C.3 Update commit (2025-06-19)

`update_thread` TSK-503. Context loaded from entities only (INV-01); policy-bounded knowledge retrieval returns K-C01 and K-C02. Model proposals, deterministic validation:

| # | Proposal | Result |
|---|---|---|
| 1 | E-501: S-5010 → H-501b, `supports`, quote "funding_rate 0.0125 \| open_interest 18.4B" @ [44, 79] — verified against the rendered snapshot (INV-04) | accepted |
| 2 | CC: H-501b moderate → `high`, cause E-501 | accepted (INV-05/06: supports stance, paired cause) |
| 3 | E-502: S-5010 → H-501a, `challenges`, quote "spot_etf_net_flow +214M \| etf_flow_7d_avg +480M" @ [84, 126] — flow deceleration argues against structural demand | accepted; CC: H-501a moderate → `low` |
| 4 | E-503: S-5012 → H-501c, `mentions` | accepted as context; **cannot** anchor confidence (INV-06) |
| 5 | E-504: S-5012 → H-501a, quote with offsets [30, 96] | **rejected** — substring mismatch at offsets (INV-04); Event `proposal_rejected` with reason |

Per-proposal commit: 4 accepted as one atomic set, 2 rejections recorded with reasons. `summary_basis: ["H-501a", "H-501b"]`.

### C.4 Register the prediction (2025-06-20)

The desk's highest-band hypothesis implies a falsifiable claim. K-C01 forces the numeric form. `record_outcome` TSK-506 — registration **before** the result is known (ADR-0013):

```json
{ "id": "O-510", "team_id": "TM-21", "subject_kind": "hypothesis", "subject_id": "H-501b",
  "outcome_type": "prediction_registered",
  "expected": {
    "resolution_condition": "Any BTC daily close below 62,000 USD between 2025-06-20 and 2025-07-04 (long-squeeze reversal)",
    "check_by": "2025-07-05T00:00:00Z",
    "predicted_band": "high" },
  "observation_snapshot_ref": null, "observation_hash": null }
```

### C.5 Reality: the miss, fed back (2025-07-05)

Fourteen sessions pass; BTC chops between 65,100 and 69,900; no close below 62,000. `record_outcome` TSK-511 commits **O-511** (`prediction_check`, `expected.registered_outcome_id = "O-510"`), observation snapshot: the fourteen canonical daily renders compiled; hash stored; `observed_at: 2025-07-05`.

The scheduler's overdue scan would have flagged O-510 had no check arrived.

Now the step that neither A nor B demonstrated: **the checked miss enters world memory as evidence.** `update_thread` TSK-512 proposes E-506: O-511 → H-501b, `challenges`, quote from the compiled observation snapshot ("No daily close below 62,000 USD in the window 2025-06-20 through 2025-07-04; minimum close 65,100 on 2025-06-27."), verified against the outcome snapshot's hash. Accepted. ConfidenceChange: H-501b `high → low`, cause E-506 (INV-05). The desk reversed its own highest-confidence belief in one auditable step, and the reason chain — registration, deadline, observation, quote, band change — is reconstructible forever.

### C.6 Evaluation and learning (2025-07-07 to 07-09)

`evaluate_outcome` TSK-514 (model) evaluates O-511:

```json
{ "id": "EV-510", "conclusion": "worked",
  "findings": {
    "prediction": "missed — condition not met; H-501b corrected by evidence within one day of resolution",
    "registration_quality": "high — numeric level and deadline, resolved cleanly, no ambiguity (K-C01 honored)",
    "root_cause": "funding/OI elevation was read as reversal timing; it is a persistence signal without a corroborating trigger",
    "notes": "decay alone did not correct H-501b in time; the check did" },
  "evaluator_kind": "model", "status": "recorded" }
```

Note the semantics: the *prediction* failed and the *evaluation* is `worked` — what is being judged is the method's accountability, and it functioned. `propose_learning_change` TSK-516 proposes (create path):

> **K-C03** (playbook): *Treat funding/OI extremes as regime indicators, not reversal timers — register reversal-timing predictions only with a corroborating trigger (ETF-flow flip, spot selloff, or exchange outflow spike).*

Operator approves (TSK-517); the F6 commit-service checklist passes; K-C03 v1 active. The next update task retrieves K-C03 with its context — the desk that mis-timed one reversal is less likely to mis-time the next one.

### C.7 What Scenario C shows that A and B do not

- **Numeric evidence through the same gates:** a funding rate earns confidence only via a verified quote against a deterministic rendered snapshot — no special numeric path, no exception (INV-04 is format-blind).
- **The negative-verification path:** A's check passed direction; B's outcomes were implementation results. C shows a *missed* prediction becoming challenging evidence that drops the desk's own `high` band — the calibration loop closing in the painful direction, which is the direction that builds trust.
- **`worked` on a missed prediction:** Evaluation judges method accountability, not correctness — the distinction that lets a system get better without lying to itself about hit rates.
- **Lessons traveling through humans:** K-C02 carried in by the Operator from another desk's hard experience (v1 has no cross-team knowledge path — by design, and it worked).

## 4. Spec amendments required by this walkthrough

Writing these traces forced two clarifications. Apply before M0:

1. **`tasks.md` §1, bullet 5** currently reads "if any proposal fails validation, nothing from that Task commits." Replace with: *"Per-proposal validation: valid proposals commit atomically as one set; invalid proposals are rejected with Events carrying reasons; a Task whose proposals all fail is marked failed."* (The update-thread card and architecture F2 already describe exactly this; the §1 bullet is the outlier.)
2. **Prediction registration.** `architecture.md` §3 (`Outcome`) and §5 (F5), plus the `record_outcome` card in `tasks.md`: prediction checks are recorded in two Outcomes — `prediction_registered` (expected filled; `observation_snapshot_ref`/`observation_hash`/`observed_at` nullable **only** for this outcome_type) and `prediction_check` (observation filled; `expected.registered_outcome_id` names the registration). Overdue detection scans for registrations past `check_by` with no subsequent check. No schema migration required (`outcome_type` and nullability only).

## 5. Fixture notes

- IDs in this document are stable fixture identifiers; integration tests may assert against them directly.
- Every rejected proposal shown corresponds to a named invariant test (`tests/invariants/`): quote mismatch → INV-04; mentions-anchored confidence → INV-06; both must appear in fixture form.
- All timestamps in Scenario A are internally consistent with the 72-hour newsroom decay window and daily decay schedule; reuse them when testing decay ordering.