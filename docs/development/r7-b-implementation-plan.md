# R7-B Agent Development Plan: KnowledgeItem Lifecycle (Revision 3 — repository-aligned)

**Audience:** the implementing agent.
**Sources:** Operator acceptance of the R7-B B0 decision review on 2026-11-05; ADR-0032 (original acceptance 2026-11-04 for R7-A, with the separately accepted R7-B design addendum below); INV-12/13; ADR-0029 D7; and the reviews of Revisions 1–3.
**Status:** **B0 complete; B1 accepted by the Operator on 2026-11-06; final technical review and hosted CI passed.** PR #43 (`r7b-b1-snapshot-history-proof`) contains the B1 implementation and both final-review corrections. The migration requires create-root `version = 1`, `status = active`, and JSON `last_validated_at = null` before backfill. The live supersession validator requires a reciprocal predecessor to be retired, while preserving pending candidates whose predecessor has no reciprocal pointer. Operator-local exact-code-head verification passed at `ca498ecd43207e72082332c803a74eb30173d41c`: fresh disposable PostgreSQL migration to the single `0015_r7b_history` head, 33 focused migration tests, Ruff, Mypy (32 source files), and 690 full-suite tests. Hosted CI [run 42244001665](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42244001665) also passed on final PR head `9576b2adb87da9ade5891665dc343db9bdef9e91`, including fresh migrations, Ruff, Mypy, and 690 tests. The commits between those heads changed documentation only. Full evidence is in `docs/testing.md`. PR #43 remains open and draft pending a separate explicit Operator merge decision. **B2–B6 and R7-C remain unauthorized.**



**Baseline:** B0 PR #41 merged to `main` at `64d5fb19be541d80b3cb8941ce3359d4b69565c1`. Revision 3 is the accepted B0 design baseline. The local checkout remains independently subject to the read-only programmer preflight.

> Class, file, function and constraint names come from the review and ADR text. Verify each against the repository before relying on it. If a name or behavior differs, record the discrepancy in the PR and do not guess.

### Changes from Revision 2
- **Content hash redefined** over a stable content-state representation (Revision 2 required revalidation to preserve a hash that currently changes with `review_after`). Adds a hash-scheme version and a controlled projection transition (B0.3, B2).
- **Legacy snapshot decoder** for immutable historical create snapshots (B0.3, B1).
- **`ck_learning_changes_target_state`** updated alongside the operation constraint (B1).
- **Candidate creation guards** now require a D7-eligible predecessor and a valid non-NULL future `review_after` on the candidate (B0.1, B5).
- **Frozen contracts:** exact serialization and domain-separator literals; fuller approval fingerprint; stale defined as a derived disposition; Team-scoped lifecycle lock for graph changes (B0.3).
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

### B0.1 Accepted R7-B design decisions (Operator acceptance: 2026-11-05)

The Operator accepted all five B0 decisions and the R7-B D1/D5 design extensions. This acceptance freezes design only; it does not authorize B1 or any R7-B implementation.

**D5: reciprocal fields and pending-successor publication gate**

- Successor field: `supersedes_item_id` identifies the predecessor. It is set when the candidate is accepted through create and is immutable.
- Predecessor field: `superseded_by_id` identifies the accepted successor. It is set only by the predecessor's accepted supersede LearningChange.
- A candidate with non-NULL `supersedes_item_id` is an accepted KnowledgeItem with status `active`, but is withheld from retrieval and Context assembly until its predecessor is `retired` and `superseded_by_id` points back to it.
- The supersede LearningChange targets and modifies the predecessor only. It never writes the successor. Retrieval and Context assembly validate both directions against canonical state and D7 eligibility.
- Enforce same-Team ownership, no self-link, no cycles, at most one non-retired pending candidate per predecessor, and at most one committed successor. A retired candidate retains its immutable historical predecessor link but no longer occupies the pending-candidate slot.

**Candidate-creation guards** (create-with-`supersedes_item_id`; every guard is required at creation):

- The predecessor is canonically valid and D7-eligible: `status=active`; `review_after` is timezone-aware UTC and later than the creation-time check; its current pointer and content hash validate; it belongs to the same Team; it has no committed successor and no non-retired pending candidate. A predecessor already in `needs_review` must be revalidated before a *new* candidate can be created.
- The candidate's own `review_after`, computed from its canonical commit time and the approval Task's pinned TeamPolicy, is non-NULL and in the future. If the pinned policy supplies no review interval, candidate creation is rejected. This prevents accepting an active candidate that can never pass the D7 publication gate.
- The predecessor/candidate relation is included in the LearningChange proposed-state hash. It is not part of the semantic content hash.

**Abandoned-candidate and edge-case rules**

| Situation | Accepted rule |
|---|---|
| Candidate abandoned | Retire it through an ordinary `LearningChange` with a retire-variant `KnowledgeLifecycleAssessment`. Preserve immutable `supersedes_item_id`. |
| Replacement candidate required | Permit only after the previous candidate is retired and only if the predecessor again passes every candidate-creation guard. |
| Predecessor revised or revalidated before supersession | Candidate remains withheld. The supersede proposal and assessment whose bound predecessor state changed are derived-stale and cannot be accepted. Create a new proposal and assessment bound to the new pointer/state. |
| Predecessor moved `active → needs_review` by scheduled `review_knowledge` while a candidate is pending | Candidate remains withheld. Any proposal/assessment bound to the former status is stale. A fresh supersede proposal and assessment may proceed from the predecessor's actual `needs_review` state only if every supersede-specific guard holds and the successor is accepted, active, canonical, and D7-eligible. This does not revalidate the predecessor. |
| Predecessor retired without supersession | Candidate remains permanently withheld. Retire it separately through the trusted path; never mutate it automatically. |
| Successor revised or revalidated before supersession | The old supersede proposal and assessment become stale because the successor binding changed. Re-propose and reassess against the exact new successor state. |
| Successor retired | The candidate can never become the committed replacement. Preserve its history and retire it separately if not already retired. |

**Supersession commit eligibility (D7-aware)**

At the actual supersede commit, all of the following must hold or the operation is blocked and the predecessor remains unchanged:

- The successor is accepted, canonical, and same-Team.
- The successor status is `active`.
- Its `review_after` is non-NULL, timezone-aware UTC, and later than the canonical commit-time check.
- Its current pointer, content version, content hash, and full-state binding still match the proposal and lifecycle assessment.
- The predecessor's exact current pointer, version, and actual status match its fresh proposal/assessment. The predecessor may be `active` or `needs_review`; a `needs_review` predecessor is retired by supersession, not revalidated.

A successor in `needs_review`, with NULL/due review date, or with stale binding blocks supersession. Refresh the proposal and assessment after any relevant state change.

**Visibility invariant:** predecessor and candidate are never both exposed. The predecessor is exposed only while its own D7 eligibility holds. If it becomes due or enters `needs_review` while a candidate remains pending, neither may be retrievable until the reciprocal supersession gate is satisfied. That temporary absence is acceptable.

**Graph concurrency:** candidate creation, supersede, and retirement of a candidate take a Team-scoped transaction lock before graph inspection or writes. Lock the Team row with `SELECT ... FOR UPDATE` first, then affected KnowledgeItem rows in ascending UUID order. Every graph-changing path uses this lock order; per-item operations also compare-and-set the exact current pointer and version. Retrieval and Context assembly validate reciprocity against one consistent canonical snapshot. Context's final validation must not rely on a previously returned retrieval result alone.

**Typed records and operation vocabulary**

- `KnowledgeRevalidationAssessment` and `KnowledgeLifecycleAssessment` (retire and supersede variants) are immutable, typed assessment records.
- The designed LearningChange operation vocabulary is `create / revise / revalidate / supersede / retire`.
- Assessment Tasks record only their own typed assessment and Task-attributed Events. They cannot write KnowledgeItem or LearningChange. The trusted Operator approval Task remains the sole lifecycle commit authority.

### B0.2 Frozen decision register and implementation-plan dispositions

The following decisions are accepted and closed for design. They are not reopened by B1 implementation unless source-level proof reveals a contradiction; any such contradiction stops the affected phase and returns to the Operator.

| Decision | Accepted contract | Consequence |
|---|---|---|
| 1. Confidence and content hashing | Include `confidence` in the semantic content hash. A confidence-only revise is content-changing. | Increment content version, change content hash, clear `last_validated_at`, and stale/republish the projection. Revalidation preserves confidence, version, and content hash. |
| 2. Revalidation evidence freshness | Verified re-examination of existing canonical evidence may qualify only while that evidence remains temporally relevant and source-valid for the claim. | Rebuild and hash-verify the evidence basis at assessment time against current content version/hash. Time-sensitive/current-condition claims, expired/changed sources, or material newer/contradictory evidence require new observations. A timestamp alone is insufficient. |
| 3. Trusted Operator identity | Retain host-supplied canonical issuer/subject identity in the immutable approval-request fingerprint and decision record. | Expand the fingerprint to the complete expected target, evidence, assessment, policy, and successor binding. Reuse of an idempotency key with a different principal conflicts. |
| 4. Domain separators | Snapshot: `watch.r7b.knowledge-item-state.v1`; content: `watch.r7b.knowledge-content.v2`. | Freeze exact SHA-256 input framing and preserve legacy verification under the scheme that produced each historical record. |
| 5. Candidate lifecycle | Accept the B0.1 candidate guards, abandoned-candidate rules, complete edge table, and fresh supersession from a `needs_review` predecessor under its operation-specific guards. | Enforce reciprocal publication gating, immutable candidate history, Team-scoped graph serialization, and the never-both-exposed invariant. |

**Snapshot-first history disposition:** accept conditionally. B1 must prove complete reconstruction from immutable LearningChange snapshots, the validated current pointer, and the explicitly authorized D7 review overlay. B1 tests must prove root/chain continuity, no forks or missing parents, exact final-state match, legacy Event placement, and replay after later commits. If any required case cannot be proven, stop and propose the smallest append-only history record; do not add one unilaterally.

Other previously reviewed dispositions remain frozen: revalidation assessment is a separate immutable type; revise preserves `needs_review`; lifecycle assessment is deterministic and operation-specific; stale is a derived application disposition; Team Experience projection pins and Context manifest v3 are mandatory; and the Team-scoped graph lock is required.
### B0.3 Freeze these contracts in writing

1. **Content hash redefinition (blocking fix).**
   - *Problem:* the current `knowledge_item_content_hash` derives from the commit service's item state, which includes `review_after`; the helper strips `status` and `last_validated_at` but not `review_after`. Revalidation changes `review_after`, so today the hash would change although the content did not.
   - *Verified field inventory:* the current `_knowledge_item_state` represents `kind`, `title`, `statement`, `body`, `applicability`, `preconditions`, `assumptions`, `limitations`, `non_applicability`, `failure_modes`, `known_counterexamples`, `missing_information`, `uncertainty`, and `confidence`. It also includes row identity, Team identity, status, version, validation/review dates and origin pointer; these are not all content.
   - *Accepted rule:* define the new hash over exactly these semantic fields: `kind`, `title`, `statement`, `body`, `applicability`, `preconditions`, `assumptions`, `limitations`, `non_applicability`, `failure_modes`, `known_counterexamples`, `missing_information`, `uncertainty`, and `confidence`. Exclude `id`, `team_id`, `status`, `version`, `last_validated_at`, `review_after`, `origin_learning_change_id`, `current_learning_change_id`, `supersedes_item_id` and `superseded_by_id`.
   - All current KnowledgeItem arrays preserve their stored semantic order. No array is treated as a set or reordered in this version; any future set-like normalization requires a separately specified field and sort key.
   - *Scheme identity:* new LearningChange snapshots, Team Experience projection records and Context manifest v3 carry `content_hash_scheme`. Existing projection rows have no scheme marker and are classified as legacy by the migration; v1/v2 Context manifests imply the legacy scheme. Neither is rewritten. Old hashes are recomputed/verified with the legacy algorithm that produced them; no legacy hash is interpreted as a new-scheme hash.
   - *Confidence and version (accepted):* a revise increments the content version and may change confidence; revalidation preserves both exactly. Confidence participates in the content hash. A confidence-only revise therefore changes the hash, is content-changing, and clears `last_validated_at`.
   - *Scheme versioning (accepted):* introduce a `content_hash_scheme` value for new records. The new scheme identifier is `watch.r7b.knowledge-content.v2`. Existing projection rows have no marker; migration assigns the explicit legacy marker (`legacy-current-state-v1`) and they remain ineligible until republished. Historical manifest v1/v2 imply that legacy scheme because their immutable payload has no scheme field. Historical LearningChange snapshots are decoded/verified with the original snapshot/hash semantics, never rewritten.
   - *Projection transition:* existing projection rows used the old semantics and must not remain eligible by accident. Define a controlled **stale-and-republish/rebuild** path: rows lacking the new scheme version are ineligible until republished against the current item version, content hash (new scheme) and current pointer.
   - The full-state snapshot hash (item 2) is separate and keeps the mutable lifecycle fields.

2. **Snapshot format, serialization and hash.**
   - Versioned canonical state envelope containing *all* semantic fields, including both pointers (`origin_learning_change_id`, `current_learning_change_id`), both supersession links, and `snapshot_version`. Every field is always present; NULL is serialized as JSON `null`, never omitted.
   - Serialization: adopt `core.state_assessment._canonical_json` (verified in the current repository): sorted keys, ASCII escaping, compact separators, and rejection of non-finite numbers. Normalize before serialization: UUIDs as lowercase hyphenated strings; `Decimal` as fixed-point strings without exponents, never JSON floats; timestamps as timezone-aware UTC ISO-8601 strings with `Z` and exactly six fractional digits (naive timestamps rejected). NULL is explicit JSON `null`. All current arrays preserve their stored order; no set-like arrays are defined for this snapshot version.
   - Field normalization is exactly as specified in the preceding serialization bullet. All arrays in the current KnowledgeItem contract preserve stored semantic order; this snapshot version defines no set-like array fields and performs no array sorting.
   - Hash (accepted): SHA-256 over UTF-8 `domain_separator` bytes, one NUL byte (`0x00`), then UTF-8 canonical JSON bytes; exclude the hash field itself. Store as `sha256:<64 lowercase hex characters>`. The immutable exact literals are snapshot hash `watch.r7b.knowledge-item-state.v1` and content hash `watch.r7b.knowledge-content.v2`.

3. **Legacy snapshot compatibility (blocking fix).** Historical create snapshots are immutable and lack `snapshot_version`, `current_learning_change_id`, `supersedes_item_id` and `superseded_by_id`.
   - Define a **legacy decoder** (legacy snapshot version) that recognizes the exact existing create snapshot shape. It interprets fields absent from that historical payload as reconstructed values: `current_learning_change_id` = the accepted create `LearningChange` (established by the validated backfill), `supersedes_item_id` = NULL, `superseded_by_id` = NULL. Existing `origin_learning_change_id` remains the recorded origin value. The validator marks each reconstructed value as legacy-derived; it never claims those values were present in the original snapshot.
   - The validator must mark these as **reconstructed legacy values**, distinct from fields actually recorded in newer snapshots. It must never present them as written data.
   - New lifecycle snapshots use the versioned envelope. Old records are validated only via the legacy rule.

4. **Approval-request contract and fingerprint (accepted).** Bind: Team, target ID, expected current pointer, expected content version, expected status, operation, proposal hash, proposed-state hash, pinned TeamPolicy version, evidence references and the LearningChange evidence-basis hash, assessment payload hashes (not just IDs), the target's expected content hash and full-state snapshot hash, and, for supersede, the exact successor state (ID, pointer, version, content hash, status, and `review_after`). Canonical host-supplied Operator issuer/subject identity is included in the immutable approval-request fingerprint and decision record. The existing in-repository adapter receives the typed principal before creating the request Event; identity binding therefore remains in the request fingerprint as well as the committed decision. Reusing the same host idempotency key with a different principal conflicts. The Operator identity is decision metadata, never KnowledgeItem content identity.

5. **Stale-proposal semantics.** There is no `invalidated` status (`LearningChange` is only `proposed / accepted / rejected`). **Stale** is a derived application disposition, not a mutation:
   - The old proposal and assessment remain immutable.
   - Their expected pointer/state no longer matches canonical state, so they cannot be accepted.
   - A new proposal and assessment must be created.
   - Cleanup of a stale proposal uses the existing trusted decision path (rejection), never an autonomous assessment Task.
   Use "stale" consistently in plan prose; do not describe a stale proposal or assessment as having a new persisted status.

6. **Graph concurrency rule.** Cycle and uniqueness checks are insufficient under concurrent transactions. Freeze a **Team-scoped lifecycle lock** taken before checking and committing any supersession-graph change: candidate creation, supersede, and retirement of a candidate. Proposed concrete implementation: lock the Team row with `SELECT ... FOR UPDATE` first, then lock affected KnowledgeItem rows in ascending UUID order. Per-item operations retain atomic compare-and-set on exact current pointer + content version. The same lock order must be used by every graph-changing code path.

7. **Lifecycle assessment recording path.** A narrow deterministic `assess_knowledge_lifecycle` Task, analogous in scope to `assess_knowledge_revalidation`. It records structured Operator rationale, evidence references and deterministic findings. It cannot write `KnowledgeItem` or `LearningChange`. The trusted approval Task remains the sole commit authority. No model scoring.

8. **Revalidation evidence freshness (accepted).** A timestamp alone never establishes freshness. Verified re-examination of existing canonical evidence may qualify only where the observations remain temporally relevant and source-valid for the claim. Rebuild the evidence basis at assessment time; re-verify canonical references, Team ownership, source snapshot hashes and applicable provenance/quote constraints; then evaluate it against the current content version and new-scheme content hash. Time-sensitive or present-condition claims, expired/changed sources, and material newer or contradictory evidence require new source observations. This decision does not impose a universal new-observation requirement for claims whose existing canonical basis remains adequate.

9. **Review Event shape.** New `knowledge_items_reviewed` Events carry the current `LearningChange` pointer. Legacy placement rules are in B1.

10. **Context manifest v3.** Origin and current `LearningChange` identity per included Team Experience passage, plus the content-hash scheme version. v1/v2 replay is preserved and verified under the scheme that produced them.

11. **Legal transition table and test matrix** (see Reference).

### B0 acceptance

B0 design acceptance was explicitly granted by the Operator on **2026-11-05** for all five decisions, the R7-B D1 assessment extension, and the D5 reciprocal-successor/publication-gate amendment.

B0 closes when:
- The accepted decisions and D1/D5 design are recorded consistently in ADR-0032, this plan, PLAN.md, the R7 entry gate, Task contracts, the decision index, CHANGE_MAP, CONTEXT, and README.
- Documentation validation passes: the diff is docs-only; phase names, status statements, task scopes, and authority rules agree; changed-file references and anchors resolve; no proposed design is represented as implemented or active; and the Operator's acceptance is recorded.
- The documentation-only integration is merged and the B0 closeout is recorded in PLAN.md.

**B0 completion did not itself authorize B1. The Operator separately authorized B1 on 2026-11-05 after B0 closeout.** That authorization is limited to the B1 scope below. B2–B6 remain unauthorized; no later-phase Task registration, provider, active write scope or runtime change is authorized.

---

## Phase B1: Schema, create-pointer rollout, legacy decoder, chain reconstruction and D7 overlay

**Implementation and acceptance status (2026-11-06):** The Operator separately authorized B1 on 2026-11-05 and accepted the B1 phase on 2026-11-06. Implementation is in draft PR [#43](https://github.com/abtn/Watch-Architecture-Rev2/pull/43). The final-review corrections are complete: migration backfill rejects any create root whose version is not 1, status is not active, or `last_validated_at` is not JSON null; live supersession reconstruction rejects reciprocal links from non-retired predecessors. Regression coverage proves the valid unlinked pending-candidate case remains accepted. Operator-local verification passed at exact code head `ca498ecd43207e72082332c803a74eb30173d41c`: disposable PostgreSQL migration to the single `0015_r7b_history` head, 33 focused migration tests, Ruff, Mypy (32 source files), and 690 full-suite tests. Hosted CI [run 42244001665](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42244001665) passed on final PR head `9576b2adb87da9ade5891665dc343db9bdef9e91`, including fresh migrations, Ruff, Mypy, and 690 tests. The commits between those heads changed documentation only. Historical create snapshots and review Events remain unchanged in storage. PR #43 remains open and draft pending separate explicit Operator merge authorization. **B2–B6 and R7-C remain unauthorized.**



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
- Stale (not "stale") proposals cannot be accepted; stale proposal cleanup goes through the trusted rejection path.
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
