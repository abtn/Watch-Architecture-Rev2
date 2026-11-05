# R7-B Agent Development Plan: KnowledgeItem Lifecycle (Revision 3 — repository-aligned)

**Audience:** the implementing agent.
**Sources:** "R7-B decision review" (PR #40), ADR-0032 (accepted 2026-11-04, R7-A only), INV-12/13, ADR-0029 D7, and the reviews of Revisions 1 and 2.
**Status:** conditional approval, pending B0 freeze. **Implementation is NOT authorized.** B0 is documentation-only. B1 onward start only after the Operator accepts the B0 outputs and gives separate written authorization.

**Initial review baseline:** when Revision 3 was supplied, PR #40 was open and unmerged at `a2e713c`, based on the R7-A merge. This integration adds the D5 publication-gate amendment as a proposed, non-effective B0 addendum; the original ADR acceptance remains R7-A-only.

> Class, file, function and constraint names come from the review and ADR text. Verify each against the repository before relying on it. If a name or behavior differs, record the discrepancy in the PR and do not guess.

### Changes from Revision 2
- **Content hash redefined** over a stable content-state representation (Revision 2 required revalidation to preserve a hash that currently changes with `review_after`). Adds a hash-scheme version and a controlled projection transition (B0.3, B2).
- **Legacy snapshot decoder** for immutable historical create snapshots (B0.3, B1).
- **`ck_learning_changes_target_state`** updated alongside the operation constraint (B1).
- **Candidate creation guards** now require a D7-eligible predecessor and a valid non-NULL future `review_after` on the candidate (B0.1, B5).
- **Frozen contracts:** exact serialization and domain-separator literals; fuller approval fingerprint; "invalidated" defined as a derived disposition; Team-scoped lifecycle lock for graph changes (B0.3).
- **New edge rule** for a scheduled review of the predecessor while a candidate is pending; B5 acceptance wording corrected.
- **B1/B2 rollout:** B1 updates the create commit to set the current pointer atomically (no NULL-pointer intermediate state).

---

## 0. Ground rules (apply to every phase)

1. One write path only: proposed `LearningChange` → application validation → trusted Operator approval via the host adapter. No direct `KnowledgeItem` writes by any Task, worker, model, indexer or retrieval path.
2. Everything runs as ordinary Tasks with exact write scopes on the existing TaskRuntime. No new runtime, scheduler, dispatcher, auth stack or autonomous approval.
3. No production evaluator provider is selected or inherited (D8). Evaluators sit behind an injectable boundary, and tests are deterministic.
4. Historical data and replay stay valid: Context manifest v1/v2 replay, historical review Events, historical `LearningChange` snapshots and their recorded hashes are never rewritten. Old records are verified under the scheme that produced them.
5. Canonical state is authority. Projection rows and similarity ranks are never authority. Stale projections become ineligible immediately on any canonical transition.
6. `KnowledgeItem.confidence` changes only via an accepted `revise`. Revalidate, supersede, retire, review scheduling and all assessments leave it unchanged.
7. Never use timestamps or "latest row" ordering to decide the current version or to place a historical Event in the chain. Ambiguity fails closed.
8. **Exit criteria:** B0 exits on documentation validation (diff limited to docs, internal consistency, authority and cross-reference checks, Operator acceptance recorded). B1–B6 exit on the full existing suite green plus new tests for that phase.
9. Each phase stays within its scope. **Stop and ask the Operator** if an acceptance criterion cannot be met as written or a decision below proves wrong against the code.

---


## Verified repository baseline (2026-11-05)

The following discrepancies were checked against the R7-A `main` baseline at `75122a7b34c15e2445b81a2a719020667b55bf06`. Recheck them at B1 preflight; they are planning facts, not implementation authorization.

| Area | Verified current behavior | R7-B consequence |
|---|---|---|
| `KnowledgeItem` | Has immutable `origin_learning_change_id` only; no current pointer or supersession fields. | B1 adds the current pointer and both reciprocal supersession fields. |
| `LearningChange` | `ck_learning_changes_operation` allows `create/revise/retire`; `ck_learning_changes_target_state` allows NULL target only for create and requires a target for revise/retire. | B1 updates both constraints for revalidate/supersede and the target rule in the Reference table. |
| State/hash helpers | `_knowledge_item_state` includes item/team identity, all content fields, confidence, status, version, validation/review dates and origin pointer. `knowledge_item_content_hash` removes status and last_validated_at, but retains review_after, version and origin/identity fields. | The existing hash is not a stable content-only hash. B0.3 defines a new scheme; B2 retains legacy verification and transitions projections. |
| Canonicality | `knowledge_item_committed_state_matches` deliberately omits status and last_validated_at; `_accepted_learning_change_is_canonical` requires the origin create. | B1 adds explicit history and D7-overlay proofs; B2 makes consumers current-pointer aware. |
| Review Event | `knowledge_items_reviewed` records item ID, version, review_after and origin pointer, but not current pointer. | New Events add current pointer; legacy Events use unique provenance matching and fail closed when ambiguous. |
| Team Experience projection | `TeamExperienceChunk` and `TeamExperienceIndexState` pin origin pointer, item version and content hash; neither pins current pointer or hash-scheme identity. | B2 adds both pins and blocks old-scheme rows until republished. |
| Context | The assembler currently emits `r6e-context-manifest-v2` and supports v1/v2 replay; included Team Experience provenance has origin but not current LearningChange identity. | B2 emits v3 while preserving v1/v2 replay under their historical hash semantics. |
| Task authority | `assess_knowledge_quality` is active from R7-A. No R7-B revalidation/lifecycle assessment Task is active. | Proposed R7-B assessment Tasks remain non-active until their separately authorized implementation is merged. |
| Canonical serializer | `core.state_assessment._canonical_json` exists and uses sorted keys, ASCII escaping, compact separators and rejection of non-finite values. | B0.3 adopts it after explicit value normalization. |

## Phase B0: Design freeze (documentation only, no code)

**Goal:** settle every open design item so B1+ never reopens settled architecture.

### B0.1 Amend ADR-0032 (Operator acceptance required)

**D5: reciprocal fields and pending-successor publication gate**
- Two fields, both required:
  - Successor: `supersedes_item_id` (identifies the predecessor), set at creation, **immutable**.
  - Predecessor: `superseded_by_id` (identifies the accepted successor), set only by the supersede commit.
- A successor with `supersedes_item_id` is `accepted` and `active` but **ineligible for retrieval and Context assembly** until its predecessor is `retired` with `superseded_by_id` pointing back to it.
- The supersede commit changes only the predecessor. It never writes the successor.
- Retrieval and Context assembly validate reciprocity against canonical state at read time.
- Constraints: same Team only; no self-link; no cycles; `superseded_by_id` unique.

**Candidate creation guards** (create-with-`supersedes_item_id`; all must hold at creation, else reject):
- Predecessor is canonically valid and **D7-eligible**: `status=active`; `review_after` is timezone-aware UTC and later than the creation-time check; its current pointer and content hash validate; same-Team; it has no committed successor and no non-retired pending candidate. A predecessor needing review must be revalidated first.
- The candidate's own `review_after`, computed from its canonical commit time and pinned TeamPolicy, must be **non-NULL and in the future**. If the policy supplies no review interval, candidate creation is rejected. (Otherwise an active candidate with NULL `review_after` could never pass the gate: scheduled review skips NULL dates and revalidation applies only to `needs_review`.)
- The relation is part of the proposed-state hash.

**Abandoned-supersession and edge-case rules** (immutable links, no dead ends; recommended disposition for Operator acceptance):

| Situation | Rule |
|---|---|
| Candidate abandoned | Retire it through an ordinary `LearningChange` with a retirement assessment. Its immutable `supersedes_item_id` is preserved as history. |
| A replacement candidate is needed | Allowed only after the previous candidate is retired, and only if the predecessor passes the creation guards above (D7-eligible, no committed successor). |
| Predecessor revised or revalidated first | Candidate stays withheld. The pending supersede proposal and assessment become **stale** (see "Invalidation" in B0.3). New ones must bind the predecessor's new pointer and state. |
| Predecessor moved `active → needs_review` by scheduled `review_knowledge` while a candidate is pending | Candidate stays withheld. Any assessment that bound the predecessor's former status is stale; a fresh one must bind its actual current state. Supersession may proceed from `needs_review` only if all operation-specific guards hold and the successor passes the D7 gate. This is an acceptable fail-closed state. |
| Predecessor retired without supersession | Candidate stays permanently withheld. Retire it separately. It is never mutated automatically. |
| Successor revised or revalidated first | The pending supersede proposal and assessment are stale (successor binding changed). Re-propose and reassess. |
| Successor retired | Candidate is cancelled and can never become the accepted replacement. |

Uniqueness model: historical `supersedes_item_id` references may include retired attempts. Enforce **at most one non-retired pending candidate per predecessor** and **at most one committed successor**. Canonical reciprocity validation ignores retired abandoned candidates.

**Supersession commit eligibility (D7-aware).** At the actual supersede commit, all must hold, else supersession is **blocked** and the predecessor stays unchanged under its own eligibility:
- Successor is accepted, canonical and same-Team.
- Successor status is `active`.
- Successor `review_after` is non-NULL and later than the canonical commit time.
- Successor's current pointer, content version and content hash still match the proposal and assessment.

A successor in `needs_review` must first be revalidated; the supersede proposal and assessment are then refreshed.

**Visibility invariant.** The invariant is that the predecessor and its candidate are **never both exposed**. It is *not* that the predecessor is always eligible until the instant of supersession. If the predecessor becomes due, neither item may be retrievable for a period. That is acceptable.

**New typed records and vocabulary**
- Add `KnowledgeRevalidationAssessment` and `KnowledgeLifecycleAssessment` (retire and supersede variants) to D1.
- Operation vocabulary: `create / revise / revalidate / supersede / retire`, with matching DB constraint changes (B1).

### B0.2 Update the R7-B implementation plan
- Remove from the open-decision list: manifest/projection pins, approval request contract, review dates (settled by ADR-0032, INV-12/13, ADR-0029 D7).
- Merge "snapshot-chain sufficiency" and "history snapshot shape" into one decision.
- Record dispositions: snapshot-first (accept, conditional on proof), revalidation assessment (accept), revise-preserves-`needs_review` (accept), lifecycle assessment (accept, revised), publication gate (accept pending amendment), content-hash redefinition (accept pending B0.3).

### B0.3 Freeze these contracts in writing

1. **Content hash redefinition (blocking fix).**
   - *Problem:* the current `knowledge_item_content_hash` derives from the commit service's item state, which includes `review_after`; the helper strips `status` and `last_validated_at` but not `review_after`. Revalidation changes `review_after`, so today the hash would change although the content did not.
   - *Verified field inventory:* the current `_knowledge_item_state` represents `kind`, `title`, `statement`, `body`, `applicability`, `preconditions`, `assumptions`, `limitations`, `non_applicability`, `failure_modes`, `known_counterexamples`, `missing_information`, `uncertainty`, and `confidence`. It also includes row identity, Team identity, status, version, validation/review dates and origin pointer; these are not all content.
   - *Rule:* define the new hash over a stable content-state object containing only the semantic fields `kind/title/statement/body/applicability/preconditions/assumptions/limitations/non_applicability/failure_modes/known_counterexamples/missing_information/uncertainty`. Include `confidence` only if the Operator accepts that choice below. Exclude `id`, `team_id`, `status`, `version`, `last_validated_at`, `review_after`, `origin_learning_change_id`, `current_learning_change_id`, `supersedes_item_id` and `superseded_by_id`.
   - All current KnowledgeItem arrays preserve their stored semantic order. No array is treated as a set or reordered in this version; any future set-like normalization requires a separately specified field and sort key.
   - *Scheme identity:* new LearningChange snapshots, Team Experience projection records and Context manifest v3 carry `content_hash_scheme`. Existing projection rows have no scheme marker and are classified as legacy by the migration; v1/v2 Context manifests imply the legacy scheme. Neither is rewritten. Old hashes are recomputed/verified with the legacy algorithm that produced them; no legacy hash is interpreted as a new-scheme hash.
   - *Confidence and version:* a revise increments the content version and may change confidence; revalidation preserves both. **Operator decision to flag:** whether confidence is inside the content hash. Recommendation: include it, so a confidence-only revise changes the hash and counts as content-changing (clears `last_validated_at`).
   - *Scheme versioning:* introduce a `content_hash_scheme` value for new records. The new scheme identifier is the proposed `watch.r7b.knowledge-content.v2` domain separator. Existing projection rows have no marker; migration assigns an explicit legacy marker (`legacy-current-state-v1`) and they remain ineligible until republished. Historical manifest v1/v2 imply that legacy scheme because their immutable payload has no scheme field. Historical LearningChange snapshots are decoded/verified with the original snapshot/hash semantics, never rewritten.
   - *Projection transition:* existing projection rows used the old semantics and must not remain eligible by accident. Define a controlled **stale-and-republish/rebuild** path: rows lacking the new scheme version are ineligible until republished against the current item version, content hash (new scheme) and current pointer.
   - The full-state snapshot hash (item 2) is separate and keeps the mutable lifecycle fields.

2. **Snapshot format, serialization and hash.**
   - Versioned canonical state envelope containing *all* semantic fields, including both pointers (`origin_learning_change_id`, `current_learning_change_id`), both supersession links, and `snapshot_version`. Every field is always present; NULL is serialized as JSON `null`, never omitted.
   - Serialization: adopt `core.state_assessment._canonical_json` (verified in the current repository): sorted keys, ASCII escaping, compact separators, and rejection of non-finite numbers. Normalize before serialization: UUIDs as lowercase hyphenated strings; `Decimal` as fixed-point strings without exponents, never JSON floats; timestamps as timezone-aware UTC ISO-8601 strings with `Z` and exactly six fractional digits (naive timestamps rejected). NULL is explicit JSON `null`. All current arrays preserve their stored order; no set-like arrays are defined for this snapshot version.
   - Field normalization is exactly as specified in the preceding serialization bullet. All arrays in the current KnowledgeItem contract preserve stored semantic order; this snapshot version defines no set-like array fields and performs no array sorting.
   - Hash: SHA-256 over UTF-8 `domain_separator` bytes, one NUL byte (`0x00`), then UTF-8 canonical JSON bytes; exclude the hash field itself. Store as `sha256:<64 lowercase hex characters>`. **Proposed exact literals** (freeze in B0; immutable once frozen): snapshot hash `watch.r7b.knowledge-item-state.v1`; content hash `watch.r7b.knowledge-content.v2`.

3. **Legacy snapshot compatibility (blocking fix).** Historical create snapshots are immutable and lack `snapshot_version`, `current_learning_change_id`, `supersedes_item_id` and `superseded_by_id`.
   - Define a **legacy decoder** (legacy snapshot version) that recognizes the exact existing create snapshot shape. It interprets fields absent from that historical payload as reconstructed values: `current_learning_change_id` = the accepted create `LearningChange` (established by the validated backfill), `supersedes_item_id` = NULL, `superseded_by_id` = NULL. Existing `origin_learning_change_id` remains the recorded origin value. The validator marks each reconstructed value as legacy-derived; it never claims those values were present in the original snapshot.
   - The validator must mark these as **reconstructed legacy values**, distinct from fields actually recorded in newer snapshots. It must never present them as written data.
   - New lifecycle snapshots use the versioned envelope. Old records are validated only via the legacy rule.

4. **Approval-request contract and fingerprint.** Bind: Team, target ID, expected current pointer, expected content version, expected status, operation, proposal hash, proposed-state hash, pinned TeamPolicy version, evidence references **and the LearningChange evidence-basis hash**, assessment payload hashes (not just IDs), the target's expected **content hash and full-state snapshot hash**, and, for supersede, the exact successor state (ID, pointer, version, content hash, status, `review_after`). The trusted Operator identity (host-supplied) is bound to the decision record against this fingerprint. Proposed default: because the principal may not be known when the approval request Event is created, bind it in the decision fingerprint/idempotency key, alongside the immutable request fingerprint. This placement remains an Operator decision to confirm in B0.

5. **Stale-proposal semantics.** There is no `invalidated` status (`LearningChange` is only `proposed / accepted / rejected`). **Stale** is a derived application disposition, not a mutation:
   - The old proposal and assessment remain immutable.
   - Their expected pointer/state no longer matches canonical state, so they cannot be accepted.
   - A new proposal and assessment must be created.
   - Cleanup of a stale proposal uses the existing trusted decision path (rejection), never an autonomous assessment Task.
   Use "stale" consistently in plan prose; do not describe a stale proposal or assessment as having a new persisted status.

6. **Graph concurrency rule.** Cycle and uniqueness checks are insufficient under concurrent transactions. Freeze a **Team-scoped lifecycle lock** taken before checking and committing any supersession-graph change: candidate creation, supersede, and retirement of a candidate. Proposed concrete implementation: lock the Team row with `SELECT ... FOR UPDATE` first, then lock affected KnowledgeItem rows in ascending UUID order. Per-item operations retain atomic compare-and-set on exact current pointer + content version. The same lock order must be used by every graph-changing code path.

7. **Lifecycle assessment recording path.** A narrow deterministic `assess_knowledge_lifecycle` Task, analogous in scope to `assess_knowledge_revalidation`. It records structured Operator rationale, evidence references and deterministic findings. It cannot write `KnowledgeItem` or `LearningChange`. The trusted approval Task remains the sole commit authority. No model scoring.

8. **Revalidation evidence freshness.** A timestamp alone never establishes freshness. *Recommendation:* verified re-examination of existing canonical evidence qualifies if the evidence basis is rebuilt at assessment time, re-verified by hash, and evaluated against the *current* content version and (new-scheme) content hash. Whether new source observations are additionally required is an **Operator decision**. Flag it explicitly.

9. **Review Event shape.** New `knowledge_items_reviewed` Events carry the current `LearningChange` pointer. Legacy placement rules are in B1.

10. **Context manifest v3.** Origin and current `LearningChange` identity per included Team Experience passage, plus the content-hash scheme version. v1/v2 replay is preserved and verified under the scheme that produced them.

11. **Legal transition table and test matrix** (see Reference).

### B0 acceptance
- ADR-0032 R7-B addendum and updated R7-B plan are integrated into PR #40 (or its successor), with Operator acceptance explicitly recorded; every item flagged "Operator decision" is resolved.
- Documentation validation passes: changed-file scope is docs-only, phase names and task scopes are consistent, all internal links/anchors resolve, and the authority chain agrees.
- Written, separate Operator authorization for B1 exists. **No code before this.**

---

## Phase B1: Schema, create-pointer rollout, legacy decoder, chain reconstruction and D7 overlay

**Goal:** prove lifecycle history is reconstructable from existing snapshots plus the current pointer, with the authorized D7 overlay, before committing to any history table.

**Tasks**
1. Migration: add `KnowledgeItem.current_learning_change_id` (FK, same-Team). Keep `origin_learning_change_id` immutable.
2. **Create-pointer rollout (no NULL intermediate state):** in the same phase, update the existing create commit in `LearningCommitService` to set `current_learning_change_id` (= origin) atomically for every new item. Then enforce non-nullability after the backfill. This is the only create-path change allowed in B1.
3. Migration: add `supersedes_item_id` **and** `superseded_by_id` (verify first whether either already exists). Each is a same-Team self-reference with a no-self-link check. Enforce B0.1 uniqueness: unique `superseded_by_id`; partial uniqueness so at most one non-retired candidate per predecessor. Acyclicity is enforced in application validation under the B0.3 lock and tested.
4. Migration: update **both** `LearningChange` constraints.
   - `ck_learning_changes_operation`: add `revalidate` and `supersede`.
   - `ck_learning_changes_target_state` must express: `create` → `target_id` NULL; `revise`, `revalidate`, `supersede`, `retire` → `target_id` NOT NULL.
   - Positive and negative DB-constraint tests for every operation/target combination.
5. Backfill: `current_learning_change_id = origin_learning_change_id`, after validating the origin is an accepted create and the Team relationship holds. Fail loudly on any violation. Do **not** rewrite historic snapshots.
6. Implement the **legacy snapshot decoder** (B0.3 item 3) and the versioned envelope for new snapshots.
7. Chain reconstruction function:
   - Root is the accepted create (decoded via the legacy decoder if legacy).
   - Each later accepted change targets the same item; its `previous_state` identifies the prior current pointer and its `committed_state` identifies the new accepted change.
   - The item's current pointer is the final node.
   - Both supersession links are validated along the chain. Reconstructed legacy values are marked as such.
8. **D7-overlay-aware validator** (do not just ignore `status`/`last_validated_at`):
   - A verified `knowledge_items_reviewed` Event is the sole authority for `active → needs_review` without a pointer advance.
   - `needs_review → active` only via an accepted revalidation change.
   - `retired` only via retire/supersede changes.
   - `last_validated_at` set only by revalidation, cleared only by a content-changing revise.
   - **Legacy review Events** (no current pointer) are accepted only on a unique match via durable Task/Event provenance and recorded item state. If unplaceable, **fail closed**. Never infer position from the latest timestamp.
9. Rejection cases: missing parents, forks, duplicate transitions from one predecessor, cross-Team references, mismatched snapshots, unauthorized status or date mutation.
10. Replay-after-later-commit: replaying an original create approval after a later revision returns the original result. The validator checks the original is a valid historical node, not that it equals the live row.

**Decision gate:** if the proof fails on any required case, **stop**. Propose the smallest append-only version-history table to the Operator. Do not add one unilaterally.

**Acceptance:** all rejection cases tested; constraint tests green; backfill tested on a populated fixture; new creates have a non-NULL current pointer; legacy decoder tested; replay and legacy-Event fail-closed tests green; create semantics otherwise unchanged.

---

## Phase B2: Content-hash scheme, projection transition and chain-aware consumers

**Goal:** land the hash redefinition and make every consumer chain-aware while only create is exercised. This phase **must complete before B4** (revalidation depends on a stable content hash).

**Compatibility requirement (semantic):** existing create semantics, authorization, idempotency and canonical outcomes remain unchanged. New projection records include the current pointer and the content-hash scheme version, and newly assembled Context uses manifest v3. Historical manifest v1/v2 replay remains unchanged.

**Tasks**
1. Implement the new content hash (B0.3 item 1) with a scheme version. Keep old-scheme verification for historical records, manifests and projections.
2. Implement the controlled **stale-and-republish** path: old-scheme projection rows are ineligible until republished. Test that none remains eligible by accident.
3. Update the canonicality helper used by Team Experience indexing/retrieval and Context assembly to validate: current pointer resolves to an accepted same-Team `LearningChange`; exact target; committed state matches the current canonical row (B1 overlay-aware rules); policy pin; same-Team ownership.
4. Update `OperatorApplicationAdapter`, `LearningCommitService` and TaskRuntime approval-Task request/finalization so they no longer hard-code `operation=create`. Make validation operation-specific, but enable only create.
5. Implement publication-gate reciprocity checks (including D7 eligibility) in retrieval and Context assembly, tested with fixtures. The real create-with-`supersedes_item_id` path comes in B5.
6. Projection publication records current `LearningChange` identity. Ship manifest v3.

**Acceptance:** create semantics unchanged per the requirement above; revalidation fixture shows the content hash unchanged when only `review_after`/`last_validated_at`/status change; stale projection rows ineligible immediately after a simulated canonical transition; old-scheme rows ineligible until republished; v1/v2 replay passes; v3 generated for new Context.

---

## Phase B3: Assessments

**Goal:** the typed assessment records and their recording paths.

1. `KnowledgeRevalidationAssessment` (immutable). Binds item ID, Team, current `LearningChange`, content version, content hash (new scheme), fresh evidence-basis hash and references (per the B0 freshness rule), evaluator identity/revision, typed findings. Narrow `assess_knowledge_revalidation` Task writes only this and Task-attributed Events. Do not reuse `KnowledgeQualityAssessment`.
2. `KnowledgeLifecycleAssessment` (immutable), strict operation-specific payloads, bound to the exact `LearningChange` proposal, recorded by the narrow deterministic `assess_knowledge_lifecycle` Task:
   - *retire:* exact target state, reason, evidence references, findings.
   - *supersede:* the above plus successor ID, pointer, version, content hash, status, `review_after`, the predecessor's actual current status/state, and evidence/rationale for the replacement relationship.
3. Injectable evaluator boundary with deterministic test evaluators. No production provider.
4. Application validation of every assessment at approval time: ownership, hashes, evaluator identity/revision, pointer/version match, policy pin, Task scope, and the full fingerprint binding (B0.3 item 4).

**Acceptance:** each assessment rejects mismatched pointer/version/hash, cross-Team references and wrong-operation payloads; assessments are immutable; assessment Tasks cannot write `LearningChange` or `KnowledgeItem`.

---

## Phase B4: Revise and revalidate

**Revise** (uses existing `KnowledgeQualityAssessment`)
- Same item ID; content version +1; origin preserved; current pointer advanced atomically (compare-and-set on exact pointer + expected version).
- `active` stays `active`; `needs_review` stays `needs_review`. Revise never reactivates.
- Content-changing revise (per the B0 definition, including a confidence change if so decided) clears `last_validated_at`.
- `review_after` recomputed from the approval Task's pinned TeamPolicy and canonical commit time. A missing interval yields NULL.
- Only revise may change confidence.
- Revising a pending candidate or its predecessor makes the pending supersede proposal/assessment stale (B0.1).

**Revalidate**
- `needs_review → active` only, via an accepted `LearningChange` with a `KnowledgeRevalidationAssessment` bound to the *current* content version/hash (never a pre-revise assessment).
- Preserve content, **content hash (new scheme)**, content version and **confidence exactly**.
- Set `last_validated_at`; recompute `review_after` from commit time and pinned policy. A missing interval yields NULL, so the item stays ineligible.
- Advance the current pointer. Because the content hash is unchanged, republish keys on the new current pointer and item state. A fresh projection republish is still required before retrieval exposes the item.
- No scheduler-only reactivation.

**Acceptance:** tests for every case above, including revise-on-`needs_review`, confidence-only revise, revalidation attempting to change confidence (must fail), stale-assessment revalidation (must fail), content hash unchanged across revalidation, and concurrent compare-and-set races.

---

## Phase B5: Supersede, retire and create-with-successor

**Create-with-`supersedes_item_id`** (explicit deliverable)
- Implement candidate creation under the **Team-scoped lifecycle lock**, enforcing all candidate creation guards in B0.1 (D7-eligible predecessor, candidate non-NULL future `review_after`, no committed successor or other pending candidate, no cycle, same-Team). Bind the relation into the proposal and proposed-state hash.
- The candidate is accepted and active but withheld by the publication gate.

**Retire**
- `retired`, no successor link, terminal. Requires `KnowledgeLifecycleAssessment` (retire), exact pointer/version, Operator decision. Retiring a candidate cancels it and frees the predecessor's candidate slot per B0.1 (graph change, so under the lifecycle lock).

**Supersede**
- `LearningChange` targets the **predecessor only**, under the lifecycle lock. Predecessor becomes `retired` with `superseded_by_id` set atomically with its pointer update. The successor row is not modified.
- Guards: exact predecessor pointer/version/status; successor same-Team, accepted, and `supersedes_item_id` equals the predecessor; no self-link or cycle; **D7-aware successor eligibility at commit (B0.1)**; successor pointer/version/hash match the proposal and assessment.
- On commit, the successor becomes eligible through reciprocity validation alone.
- Implement every edge rule in the B0.1 table, including the scheduled-review-of-predecessor case.

**Acceptance (corrected):** the predecessor and its candidate are **never both retrievable**. Before supersession the candidate is withheld and the predecessor is exposed only while its own D7 eligibility holds. After supersession the successor is exposed and the predecessor is not. A blocked supersession (successor `needs_review`, NULL/due `review_after`, stale binding) leaves the predecessor unchanged. All edge rules and concurrency cases tested.

---

## Phase B6: Legacy compatibility and hardening

**Goal:** complete historical compatibility and regression work on top of the B1 validator.

1. Repeated review/revalidation sequences (active → needs_review → active → needs_review …) validate correctly.
2. Legacy review Events without pointers: unique-match placement succeeds, ambiguous placement fails closed, never timestamp-guessed.
3. Legacy create snapshots validate through the decoder across every later transition type.
4. Unauthorized status or date mutations are rejected by history validation.
5. Run the full regression matrix and the end-to-end flow: create → review → revise → revalidate → create-with-successor → supersede/retire, with replay of each original approval after later transitions.

**Acceptance:** full matrix green; no arbitrary `last_validated_at` or status drift accepted.

---

## Reference

### Legal transitions

| Operation | From | Effect | Content version | Confidence | Content hash | Pointer |
|---|---|---|---|---|---|---|
| create | none | new `active` item, v1; optional `supersedes_item_id` (candidate withheld; requires non-NULL future `review_after`) | 1 | initial value | computed | origin = current = create change |
| revise | active / needs_review | status preserved, content changed, `last_validated_at` cleared, `review_after` recomputed | +1 | **may change** | changes | advances |
| revalidate | needs_review | to `active`, `last_validated_at` set, `review_after` recomputed | unchanged | unchanged | **unchanged** | advances |
| supersede | active / needs_review (predecessor) | predecessor `retired` + `superseded_by_id`; successor untouched; blocked unless successor active with future `review_after` | unchanged | unchanged | unchanged | advances (predecessor) |
| retire | active / needs_review | `retired`, no successor, terminal | unchanged | unchanged | unchanged | advances |
| review_knowledge (Task) | active | to `needs_review` only | unchanged | unchanged | unchanged | **does not advance** (Event records current pointer) |

### Target constraint

| Operation | `target_id` |
|---|---|
| create | NULL |
| revise / revalidate / supersede / retire | NOT NULL |

### Regression test matrix (minimum)
- Replay of create, revise, revalidate, supersede and retire approvals **after later transitions**, each returning the original result.
- Reconstruction rejection: missing parent, fork, duplicate transition, cross-Team reference, mismatched snapshot, timestamp-ordering attempts.
- Legacy decoder: legacy create root accepted with reconstructed fields marked; never treated as recorded data.
- DB constraints: every operation/target combination, positive and negative.
- Content hash: unchanged across revalidation, supersede and retire; changes on content revise (and confidence revise per decision); old-scheme records still verify; old-scheme projection rows ineligible until republished.
- Snapshot hash: stable across serialization; changes with any semantic field (both pointers, both supersession links); distinct from content hash; UUID/Decimal/timestamp normalization cases; NULL never omitted.
- Approval fingerprint changes when any bound element changes (assessment payload hash, successor state, policy version, expected status, target content/snapshot hash, evidence-basis hash, Operator identity).
- Stale (not "invalidated") proposals cannot be accepted; stale proposal cleanup goes through the trusted rejection path.
- Revise on `needs_review` stays `needs_review`; revise clears `last_validated_at`; stale-assessment revalidation fails.
- Revalidate/supersede/retire cannot alter confidence, content or content version.
- Candidate creation rejected when: predecessor `needs_review`/NULL or due `review_after`/retired/has successor/has other pending candidate; candidate has NULL or past `review_after`; self-link, cycle, cross-Team.
- Concurrent candidate creation and supersession cannot produce a cycle or duplicate candidate/successor (lifecycle lock).
- Publication gate: withheld candidate, flip on supersession, never both exposed; predecessor due while candidate pending (neither exposed) is allowed.
- Edge table: each row, including scheduled review of the predecessor, replacement after retirement, and candidate permanently withheld after non-supersede predecessor retirement.
- Supersession blocked for successor in `needs_review`, NULL/due `review_after`, or stale pointer/version/hash.
- Stale projection ineligible immediately after each transition; revalidated item requires republish.
- Manifest v1/v2 replay and v3 generation.
- Legacy review Events: unique-match accepted, ambiguous fails closed; new Events carry the pointer.
- Concurrent compare-and-set on the same item.

### Operator decisions required in B0
1. Is confidence part of the content hash (recommended yes) and is a confidence-only revise content-changing?
2. Revalidation freshness: is re-examination of existing evidence sufficient, or are new observations required?
3. Where the Operator identity is bound in the approval fingerprint/decision.
4. Final literals for the two domain separators.
5. Acceptance of the abandoned-supersession edge table and the candidate creation guards.

### Non-goals
Multi-Team sharing; LLM scoring for retire/supersede; a production evaluator provider; automatic TeamPolicy changes; a new scheduler/runtime; a separate vector store or reranker; any R7-C work (TaskKnowledgeReference, KnowledgeUseAssessment, retrieval benchmark).

### Definition of done for R7-B
All phases B0–B6 accepted, full regression matrix green, no open design dispositions, ADR-0032 and the R7-B plan consistent with the code, and the Operator's written sign-off recorded. R7-C remains separately gated.