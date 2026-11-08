# R7-B Agent Development Plan: KnowledgeItem Lifecycle (Revision 3 — repository-aligned)

**Audience:** the implementing agent.
**Sources:** Operator acceptance of the R7-B B0 decision review on 2026-11-05; ADR-0032 (original acceptance 2026-11-04 for R7-A, with the separately accepted R7-B design addendum below); INV-12/13; ADR-0029 D7; and the reviews of Revisions 1–3.
**Status (updated 2026-11-08):** **B0 complete; B1 accepted and merged; B2 formally closed with accepted residual verification gaps; B3.2 merged by PR #60; exact-merge Operator-local verification passed; formal Checkpoint 4 closeout pending.** PR #60 merged to `main` at `31be3a25cf7f52ca81eab65cc10280a855738c3d`; final PR head `0eecefedbc4ef6e4b60cbd8c3eacf31e1256f362` passed hosted CI run [42496681657](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42496681657): fresh PostgreSQL migration/single-head, Ruff, Mypy, and 823 tests (95 warnings). Operator-local verification passed on the exact merge SHA: migration/single-head at `0017_r7b_assessments`, 9 model tests, 8 migration tests, Ruff, Mypy (33 files), 823 full-suite tests (95 warnings, 123.45s), and both diff checks. The disposable container was removed and database environment values restored; detailed evidence is in `docs/testing.md`. B3.3 has not started; its implementation remains gated on formal Checkpoint 4 closeout and separate written Operator authorization. The active approval allowlist remains exactly `create`; B4–B6 and R7-C remain unauthorized.



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
4. Historical data and replay stay valid: Context manifest v1/v2 replay, historical review Events, historical `LearningChange` snapshots and their recorded hashes are never rewritten. Historical snapshot hashes retain their snapshot-specific verification. Existing Team Experience projection hashes remain unchanged but must not be assigned a content-hash scheme that the row does not prove.
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
| State/hash helpers | The pre-B1 content hash used the pre-B1 21-field state representation; the post-B1 helper uses the normalized 24-field B1 state, including current-pointer and supersession fields. No projection-row field identifies which historical calculation produced its digest. | The current helper is not a safe universal verifier for every historical projection. B2 introduces the v2 semantic hash; the Operator accepted the `legacy-opaque` projection disposition recorded below. |
| Canonicality | `knowledge_item_committed_state_matches` deliberately omits status and last_validated_at; `_accepted_learning_change_is_canonical` requires the origin create. | B1 adds explicit history and D7-overlay proofs; B2 makes consumers current-pointer aware. |
| Review Event | `knowledge_items_reviewed` records item ID, version, review_after and origin pointer, but not current pointer. | New Events add current pointer; legacy Events use unique provenance matching and fail closed when ambiguous. |
| Team Experience projection | `TeamExperienceChunk` and `TeamExperienceIndexState` pin origin pointer, item version and content hash; neither pins current pointer or hash-scheme identity. | B2 adds both pins and blocks `legacy-opaque` rows until republished. |
| Context | The assembler currently emits `r6e-context-manifest-v2` and supports v1/v2 replay; included Team Experience provenance has origin but not current LearningChange identity. | B2 emits v3 while preserving the existing immutable v1/v2 replay path. Manifest version alone does not prove which legacy content-hash calculation produced an included projection digest. |
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
| 4. Domain separators | Snapshot: `watch.r7b.knowledge-item-state.v1`; content: `watch.r7b.knowledge-content.v2`. | Freeze exact SHA-256 input framing; preserve historical LearningChange snapshot verification, and treat pre-existing Team Experience projection hashes as `legacy-opaque` rather than assuming a universal legacy verifier. |
| 5. Candidate lifecycle | Accept the B0.1 candidate guards, abandoned-candidate rules, complete edge table, and fresh supersession from a `needs_review` predecessor under its operation-specific guards. | Enforce reciprocal publication gating, immutable candidate history, Team-scoped graph serialization, and the never-both-exposed invariant. |

**Snapshot-first history disposition:** accept conditionally. B1 must prove complete reconstruction from immutable LearningChange snapshots, the validated current pointer, and the explicitly authorized D7 review overlay. B1 tests must prove root/chain continuity, no forks or missing parents, exact final-state match, legacy Event placement, and replay after later commits. If any required case cannot be proven, stop and propose the smallest append-only history record; do not add one unilaterally.

Other previously reviewed dispositions remain frozen: revalidation assessment is a separate immutable type; revise preserves `needs_review`; lifecycle assessment is deterministic and operation-specific; stale is a derived application disposition; Team Experience projection pins and Context manifest v3 are mandatory; and the Team-scoped graph lock is required.
### B0.3 Freeze these contracts in writing

1. **Content hash redefinition (blocking fix).**
   - *Problem:* the current `knowledge_item_content_hash` derives from the commit service's item state, which includes `review_after`; the helper strips `status` and `last_validated_at` but not `review_after`. Revalidation changes `review_after`, so today the hash would change although the content did not.
   - *Verified field inventory:* the current `_knowledge_item_state` represents `kind`, `title`, `statement`, `body`, `applicability`, `preconditions`, `assumptions`, `limitations`, `non_applicability`, `failure_modes`, `known_counterexamples`, `missing_information`, `uncertainty`, and `confidence`. It also includes row identity, Team identity, status, version, validation/review dates and origin pointer; these are not all content.
   - *Accepted rule:* define the new hash over exactly these semantic fields: `kind`, `title`, `statement`, `body`, `applicability`, `preconditions`, `assumptions`, `limitations`, `non_applicability`, `failure_modes`, `known_counterexamples`, `missing_information`, `uncertainty`, and `confidence`. Exclude `id`, `team_id`, `status`, `version`, `last_validated_at`, `review_after`, `origin_learning_change_id`, `current_learning_change_id`, `supersedes_item_id` and `superseded_by_id`.
   - All current KnowledgeItem arrays preserve their stored semantic order. No array is treated as a set or reordered in this version; any future set-like normalization requires a separately specified field and sort key.
   - *Scheme identity:* new Team Experience projection records and Context manifest v3 carry `content_hash_scheme`; the new scheme identifier is `watch.r7b.knowledge-content.v2`. By the accepted migration rule, pre-existing projections must receive the `legacy-opaque` storage disposition, never be treated as v2, and remain ineligible until republished. Context v1/v2 manifests do not establish a legacy content-hash scheme: their existing replay path validates immutable historical Context data without recalculating KnowledgeItem content hashes. Neither projections nor historical Context records are rewritten. Historical LearningChange snapshot hashes retain their separate snapshot-version/decoder rules.
   - *Confidence and version (accepted):* a revise increments the content version and may change confidence; revalidation preserves both exactly. Confidence participates in the content hash. A confidence-only revise therefore changes the hash, is content-changing, and clears `last_validated_at`.
   - *Scheme versioning (amended and accepted 2026-11-06):* the new scheme identifier is `watch.r7b.knowledge-content.v2`. The original B0.3 label `legacy-current-state-v1` is superseded for pre-existing Team Experience projections by `legacy-opaque`, a non-verifiable storage disposition accepted by the Operator. Historical Context manifest v1/v2 retain their exact replay behavior and do not imply or require any KnowledgeItem content-hash scheme. Historical LearningChange snapshots retain their separate original snapshot/hash semantics and are never rewritten.
   - *Projection transition:* existing projection rows must not remain eligible by accident. The accepted **stale-and-republish/rebuild** path assigns `legacy-opaque`, keeps the current-pointer pin NULL, and marks index state stale; all existing hashes and embedding data remain byte-for-byte unchanged, and only a normal successful republish creates v2 rows.
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

10. **Context manifest v3.** Origin and current `LearningChange` identity per included Team Experience passage, plus the content-hash scheme version. The existing v1/v2 replay path remains immutable and unchanged; it verifies historical Context snapshot/Event integrity without recalculating KnowledgeItem content hashes. Any embedded legacy passage hash remains opaque historical data.

11. **Legal transition table and test matrix** (see Reference).

### B0 acceptance

B0 design acceptance was explicitly granted by the Operator on **2026-11-05** for all five decisions, the R7-B D1 assessment extension, and the D5 reciprocal-successor/publication-gate amendment.

B0 closes when:
- The accepted decisions and D1/D5 design are recorded consistently in ADR-0032, this plan, PLAN.md, the R7 entry gate, Task contracts, the decision index, CHANGE_MAP, CONTEXT, and README.
- Documentation validation passes: the diff is docs-only; phase names, status statements, task scopes, and authority rules agree; changed-file references and anchors resolve; no proposed design is represented as implemented or active; and the Operator's acceptance is recorded.
- The documentation-only integration is merged and the B0 closeout is recorded in PLAN.md.

**B0 completion did not itself authorize B1. The Operator separately authorized B1 on 2026-11-05; B1 is accepted and merged. B2 was separately authorized on 2026-11-06. Steps 1–3 are accepted and merged; Step 4 requirement gap analysis is complete, with only final provider-space revalidation and direct migrated-legacy-row rebuild regression coverage remaining. Sequence 1 documentation closeout is in progress; Sequence 4 has not begun.** B3–B6 remain unauthorized; no later-phase Task registration, provider, active write scope or runtime change is authorized.

---

## Phase B1: Schema, create-pointer rollout, legacy decoder, chain reconstruction and D7 overlay

**Implementation and acceptance status (2026-11-06):** B1 was separately authorized on 2026-11-05, accepted on 2026-11-06, and merged through PR [#43](https://github.com/abtn/Watch-Architecture-Rev2/pull/43) at `d1a8b88fd930207142304fc9b0b7274de5de4992`. The final-review corrections are complete: migration backfill rejects any create root whose version is not 1, status is not active, or `last_validated_at` is not JSON null; live supersession reconstruction rejects reciprocal links from non-retired predecessors. Regression coverage proves the valid unlinked pending-candidate case remains accepted. Operator-local verification passed at exact code head `ca498ecd43207e72082332c803a74eb30173d41c`: disposable PostgreSQL migration to the single `0015_r7b_history` head, 33 focused migration tests, Ruff, Mypy (32 source files), and 690 full-suite tests. Final PR-head hosted CI [run 42246346103](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42246346103) passed on `a7c6d4a7de5529ea9fb4faff5c9ab17bbbc51fd8`: fresh PostgreSQL migration/single-head checks, Ruff, Mypy, 690 tests, and container cleanup. B1 is complete.



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

**Goal:** define and implement the stable semantic content-hash contract, invalidate and safely republish old Team Experience projections, and make indexing, retrieval, and Context assembly validate the B1 current-learning-change chain. B2 must complete before B4 because revalidation depends on a hash that does not change when review metadata changes.

**Status (2026-11-08):** B2 implementation was separately authorized on 2026-11-06 and is formally closed by explicit Operator instruction on 2026-11-08. Steps 1–8 are accepted and merged through PR #57. Hosted and Operator-local exact-code-head verification passed on `027b9f1cb0bbd5faaaf8d6d7cc44c8359af49b31`: fresh migration/single-head, Ruff, Mypy, and 806 tests (77 warnings). Closure retains three uncompleted checks as residuals: no separate focused regression run, no recorded `git diff --check`, and no complete line-by-line final diff review. The local-before-documentation-PR sequence deviation remains recorded. B3 planning/preflight is documented; implementation still requires separate written Operator authorization. B4–B6 and R7-C remain unauthorized.

### Frozen compatibility contract

- **New hash scheme:** `watch.r7b.knowledge-content.v2`, using the exact semantic fields frozen in ADR-0032 §B0.3: `kind`, `title`, `statement`, `body`, `applicability`, `preconditions`, `assumptions`, `limitations`, `non_applicability`, `failure_modes`, `known_counterexamples`, `missing_information`, `uncertainty`, and `confidence`.
- Exclude KnowledgeItem/Team identity, status, content version, `last_validated_at`, `review_after`, origin/current LearningChange pointers, and both supersession links. Preserve the stored order of every array; do not normalize arrays as sets. Confidence is semantic: changing only confidence changes the hash.
- Normalize values according to the accepted ADR contract and serialize with `core.state_assessment._canonical_json`. Compute SHA-256 over UTF-8 domain-separator bytes, one NUL byte, and canonical JSON bytes. Persist `sha256:<64 lowercase hex>`. The scheme identifier and its domain separator are the exact accepted literal above.
- **Accepted legacy disposition:** B0.3 originally proposed `legacy-current-state-v1` for all pre-existing projections. Step 0 established that the pre-B1 21-field calculation and post-B1 normalized 24-field calculation are distinct, while projection rows persist no scheme discriminator. The persistent `watch` database was not inspected, so the actual distribution is unknown; no row may be assigned an algorithm from its current KnowledgeItem state, ID, timestamp, or digest. The Operator accepted `legacy-opaque` on 2026-11-06 as the fail-closed storage disposition; it is not a hash algorithm and has no verifier.
- **Context v1/v2 replay:** preserve the current immutable replay behavior exactly. It validates the stored Context snapshot bytes/hash and associated Event/task metadata; it does not recompute a KnowledgeItem content hash. Do not infer a content-hash scheme from manifest version, add retroactive scheme fields, or rewrite historical Context payloads. Any included old `content_hash` remains an opaque value inside the immutable record.
- **Accepted projection transition:** classify every pre-existing projection row with `content_hash_scheme = 'legacy-opaque'`, leave `current_learning_change_id` NULL, and mark its index-state record `stale`. Preserve all existing item hashes, chunk text/hashes, embeddings, and embedding metadata unchanged. Fail closed for retrieval regardless of the stored digest. A successful ordinary republish writes the v2 digest and current-pointer pin. Do not implement separate legacy verifiers: no persisted discriminator was found to assign every historical projection to an exact algorithm.
- A hash value without its scheme is ambiguous and cannot be treated as current. Scheme identity travels with every new Team Experience projection and every Team Experience entry in a new Context manifest.
- Existing create behavior remains the only enabled lifecycle commit. B2 prepares consumers to use the current pointer; it does not enable revise, revalidate, supersede, or retire.

### Implementation sequence (B2 authorization recorded 2026-11-06; execute in sequence)

**Step 0 — Exact-head preflight and consumer inventory**

1. Start from the then-current `main`, verify the B1 merge is an ancestor, and confirm a clean worktree. At this planning baseline, B1 is merge commit `d1a8b88fd930207142304fc9b0b7274de5de4992`.
2. Confirm Alembic has one head at `0015_r7b_history`; use only a fresh disposable PostgreSQL database for migration and database-backed tests. Never point either test URL at the persistent `watch` database.
3. Recheck the current implementation rather than relying on line numbers: `knowledge_item_content_hash`, `_accepted_learning_change_is_canonical`, `TeamExperienceIndexer`, `HybridKnowledgeRetriever`, `RetrievedPassage`, Context manifest replay/build/validation, `OperatorApplicationAdapter`, `LearningCommitService`, and TaskRuntime approval admission/finalization.
4. Record the current legacy hash calculation, projection row shape in fixtures, current Context v1/v2 replay behavior, and every hard-coded create-only guard. Do not modify code during this inventory.

**Operator preflight evidence:** clean worktree on local `main`, HEAD `d1a8b88fd930207142304fc9b0b7274de5de4992`, B1 confirmed as an ancestor of HEAD; `python -m alembic heads` returned exactly `0015_r7b_history (head)`. The persistent `watch` database was not inspected.

**Step 0 findings and accepted ruling (2026-11-06) — COMPLETE**

- The pre-B1 content-hash implementation used the pre-B1 21-field KnowledgeItem state representation and its historical timestamp serialization. The post-B1 helper uses the normalized 24-field `learning_history.knowledge_item_state` representation, including current-pointer and supersession fields. The current migration-era projection models persist no scheme identifier, so an old row cannot prove which calculation produced its `item_content_hash`.
- The inventory did not inspect the persistent `watch` database. It establishes that more than one historical algorithm exists in repository history, not that any particular production database contains rows from both generations.
- The current Context v1/v2 replay path verifies immutable Context snapshot bytes/hash and associated Event/task metadata; it does not recalculate KnowledgeItem content hashes. Therefore preserving v1/v2 replay does not require a legacy KnowledgeItem content-hash verifier. Any embedded old passage hash remains part of the immutable historical payload.
- This was a design conflict with the B0.3 compatibility assumption that all existing projections could be assigned `legacy-current-state-v1` and that Context v1/v2 implied the same scheme; the Operator resolved it by accepting the opaque projection disposition and retaining the existing v1/v2 replay behavior.
- **Operator decision:** the Operator explicitly accepted this disposition on 2026-11-06. Under the accepted B2 migration rule, all pre-existing Team Experience projection rows must be classified as `legacy-opaque` (a non-retrievable storage disposition, not a claim about the digest algorithm), their current-pointer pin must remain NULL, and their index state must be marked stale. Existing hash strings, chunks, embeddings, and metadata must be preserved byte-for-byte. A normal successful republish writes the v2 hash and current pointer. Context v1/v2 replay remains exactly as implemented, without content-hash recalculation.
- This is an accepted amendment to the original B0.3 compatibility wording, recorded in ADR-0032. The Operator separately authorized B2 implementation on 2026-11-06. Step 1 and Step 2 are accepted and merged. Step 2's final documentation-head CI passed run `42350516648`; exact implementation-head hosted and Operator-local verification is recorded in `docs/testing.md`.

**Step 1 — Implement and prove the versioned semantic content hash**

**Status (2026-11-07):** Step 1 merged through PR [#45](https://github.com/abtn/Watch-Architecture-Rev2/pull/45) at `18595356a3da93b47a8701c7e94fe7dbde098d55`. Exact PR head `cd2426e64d86f32916be28f639ada19574f8607e` passed hosted CI run [42286427354](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42286427354) (fresh migration/single-head checks, Ruff, Mypy 32 files, 732 tests, cleanup). Operator-local exact-head verification also passed: 42 focused tests, Ruff, and Mypy across 32 source files. Step 1 is accepted as the prerequisite for Step 2.

1. Introduce one explicit v2 hash implementation. Do not implement a legacy projection-hash verifier: pre-existing projection hashes are opaque historical values and fail closed through the `legacy-opaque` marker/stale state until republished.
2. Make the v2 projection contain exactly the frozen semantic fields. Keep the full-state snapshot hash and content hash separate: the former still binds lifecycle identity/state; the latter represents semantic content only.
3. Apply the accepted `legacy-opaque` disposition. No old projection digest is recomputed or verified; it is preserved unchanged and made ineligible until v2 republish.
4. Add table-driven tests proving determinism; every semantic field affects the hash; confidence-only changes the hash; array order matters; and changes only to status, validation/review dates, version, identity, Team, pointers, or supersession links do not change v2. Test preservation and ineligibility of historical projection digests under `legacy-opaque`; do not invent legacy hash verifiers or universal legacy vectors.

**Step 2 — Add projection provenance fields with a fail-closed migration**

**Status (2026-11-07):** accepted and merged through PR [#46](https://github.com/abtn/Watch-Architecture-Rev2/pull/46) at `669d2e8140036ea4db07cbc44b33f6baa2e2608d`. Hosted implementation CI run [42347539252](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42347539252) and final documentation-head CI run [42350516648](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42350516648) passed. Operator-local exact implementation-head verification passed, including a fresh-disposable-PostgreSQL full suite (**735 passed, 0 failed**). Full evidence is in `docs/testing.md`.

1. Add `current_learning_change_id` and `content_hash_scheme` to both `TeamExperienceChunk` and `TeamExperienceIndexState`. New publications must populate both fields.
2. Use one additive Alembic revision after `0015_r7b_history` (`0016_team_exp_history_pins`; the identifier is deliberately under Alembic's 32-character version-column limit). Preserve one Alembic head.
3. Set existing projection rows to `content_hash_scheme = 'legacy-opaque'`, leave `current_learning_change_id` NULL, and mark existing index-state records `stale`. Do not copy the KnowledgeItem's current pointer into old rows: that would falsely claim the pointer was captured when the old projection was published.
4. Keep existing `item_content_hash`, chunk text, chunk hashes, embeddings, and embedding metadata unchanged during migration. Do not mass-re-embed inside Alembic. Add same-Team referential integrity for non-NULL current pointers and a constraint for the supported scheme identifiers.
5. Migration tests must prove old rows remain present but are not publishable/retrievable under `legacy-opaque`, all historical hash strings and embedding data are unchanged, failed migration rolls back cleanly, and a fresh database reaches exactly one head.

**Step 3 — Make canonicality follow the B1 current pointer**

**Status (accepted and merged 2026-11-07):** Step 3 merged through PR [#48](https://github.com/abtn/Watch-Architecture-Rev2/pull/48) at merge commit `1ba9f38ec2fa0b7c4a748181bce4096d8f65b356`; PR head `fcb9f4bd9b56b2353299828a7db39619a4650604`. The canonicality helper resolves the current pointer and delegates complete chain/D7 verification to `reconstruct_knowledge_item_history`; retrieval SQL/verifier and Context validation enforce current-pointer and v2 hash-scheme pins. A pointer-only accepted-revalidation regression proves old projections are rejected until republished. Corrected-head hosted CI run [42383223932](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42383223932) and Operator-local exact-head verification both passed; local verification included the full suite (**738 passed**), Ruff, Mypy (32 source files), migration head `0016_team_exp_history_pins`, environment restoration, and disposable-container cleanup. Actual lifecycle commits remain create-only.

1. Replace the origin-create-only assumption in `_accepted_learning_change_is_canonical`. Load the current change through `KnowledgeItem.current_learning_change_id`, not through `origin_learning_change_id`.
2. Validate that the pointer resolves to an accepted same-Team `LearningChange`; validate operation-specific target semantics (create has NULL target and creates this item; a later transition targets this exact item); validate the approval Task, pinned TeamPolicy, trusted decision Event, and committed timestamp.
3. Use B1's `reconstruct_knowledge_item_history` as the history authority. Do not introduce a second, weaker chain reconstruction implementation. The final reconstructed state must match the live canonical KnowledgeItem, including the D7 review overlay and current pointer.
4. During B2, real accepted lifecycle commits remain create-only. Add synthetic history fixtures where useful to prove a non-origin current pointer is understood by readers, without adding a live revise/revalidate approval path. Malformed, missing, cross-Team, unaccepted, wrong-target, wrong-pointer, or inconsistent snapshots fail closed.

**Step 4 — Publish current-pointer and hash-scheme pins**

**Implementation and merge status (2026-11-08):** Step 4 was implemented and merged through PR [#50](https://github.com/abtn/Watch-Architecture-Rev2/pull/50) at `96447318484d539ffa240745b9adc95b8b510871` (head `6b15a55478c2ec6b0e933201aa5f250adb38b449`). Hosted CI passed on the exact PR head (run `42389377578`) and merge commit (run `42389752995`). Operator-local exact merged-head verification passed 740 tests, Ruff, Mypy, migration/head checks, `git diff --check`, environment restoration and disposable-container cleanup. The legacy rebuild regression simulates the post-0016 `legacy-opaque`/stale state; it does not run Alembic migration and rebuild in one integrated fixture.

**Requirement gap analysis (Sequences 2–3; 2026-11-07):** inspected the exact merged `main` baseline `1ba9f38ec2fa0b7c4a748181bce4096d8f65b356`, including `core/knowledge_index.py`, `tests/test_team_experience.py`, `migrations/versions/0016_team_experience_history_pins.py`, and `tests/test_team_experience_projection_migration.py`. The findings below distinguish implementation from test evidence; no source/test changes were made.

| Requirement | Existing code | Existing tests | Disposition |
|---|---|---|---|
| 1. Bind current LearningChange ID and v2 content-hash scheme in each chunk and index-state row; compare in `_projection_matches` and preserve consistency through publication. | Implemented: row construction writes both pins; `_upsert_index_state` writes the same values; `_projection_matches` checks state and every chunk. Final transaction locks/reloads the KnowledgeItem and checks current pointer, origin, version and semantic hash before it inserts rows derived from the same source snapshot. | `test_separate_team_experience_projection_is_idempotent_and_retrievable` asserts chunk/state pins; `test_revalidation_pointer_only_transition_invalidates_old_projection` proves pointer-only change invalidates the old projection. | **Satisfied; no implementation change identified.** |
| 2. Recheck item ID/Team, pointer, version/hash, scheme, status, D7 eligibility, canonical history and embedding-space identity immediately before publication. | Final transaction checks the item by ID under `FOR UPDATE`; `_accepted_learning_change_is_canonical` validates the current chain; `_review_date_is_eligible` checks active status and future timezone-aware UTC review date; `_upsert_index_state` rechecks Team/version/origin/current pointer/content hash and writes the v2 scheme. However, provider-space identity is checked only after `embed()` and before row construction/final transaction. It is not revalidated at the final publication boundary. | Canonicality/current-pointer and D7 tests cover the item/history/eligibility dimensions. No test changes provider space after the post-embedding check and before publication. | **One confirmed narrow implementation gap:** provider-space final-boundary validation. No evidence of cross-space retrieval was found; retrieval requires query/chunk/state embedding identities to match, so the demonstrated consequence is a potentially stale `published` marker, not demonstrated mixed-space retrieval. |
| 3. Mark required refresh stale before provider call; publish replacement chunks and matching index state atomically. | `_record_index_state(status='stale')` commits before `embed()`. The final transaction deletes old chunks, inserts replacements, flushes, and upserts `published` state in one transaction. Retrieval requires `st.status = 'published'`. | `test_failed_publication_records_staleness_and_rebuilds` proves provider failure leaves old chunks undiscoverable and a later rebuild succeeds. | **Satisfied; no implementation change identified.** |
| 4. `rebuild_all` discovers legacy-opaque/stale rows for normal republish. | `rebuild_all()` unions IDs from active eligible KnowledgeItems, `TeamExperienceChunk` rows, and `TeamExperienceIndexState` rows. A migrated legacy row remains discoverable through both projection tables and is sent through the ordinary indexer. | `test_0016_preserves_legacy_projection_bytes_and_marks_them_opaque_and_stale` proves migration preserves rows and marks state stale; `test_failed_publication_records_staleness_and_rebuilds` proves ordinary stale-row rebuild. Neither directly runs `rebuild_all()` against a migrated `legacy-opaque` row. | **Implementation present; direct regression coverage missing.** |

**Step 4 disposition:** requirements 1 and 3 are satisfied; requirement 2 needs only the final embedding-space revalidation behavior; requirement 4 needs a direct legacy-migration-to-rebuild regression test, not a new discovery algorithm. Keep the original four requirements as the acceptance contract. Do not expand into Step 5 retrieval, Step 6 Context manifest v3, Step 7 approval refactoring, lifecycle commits, or any B3–B6/R7-C work. Actual lifecycle commits remain create-only. Sequence 4 has not started.

1. Extend the indexer, `_upsert_index_state`, `_projection_matches`, and final publication transaction to bind the exact current LearningChange ID and v2 content-hash scheme in both index state and each chunk.
2. Recheck the item ID/Team, current pointer, content version/hash, scheme, status, D7 eligibility, canonical history, and embedding-space identity immediately before publication. The state row and chunk rows must describe the same canonical version.
3. Keep the existing stale-before-embedding behavior: once a refresh is required, old rows must become undiscoverable before a provider call can fail. Publish replacement chunks and the matching index-state record atomically after all final checks.
4. Make `rebuild_all` discover `legacy-opaque`/stale rows so they can be republished through the normal indexer. Rebuild is an ordinary projection operation, not a canonical KnowledgeItem write.

**Step 5 — Enforce chain and publication gates in retrieval**

**Status (accepted and merged 2026-11-08):** PR [#52](https://github.com/abtn/Watch-Architecture-Rev2/pull/52) merged at `bc0d71e20fbe3ed01ef13493099a80367d8a5a42` (head `a9f72979c4da8b5c02705ca812760ed4386a40ba`). Hosted CI run [42462369436](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42462369436) passed on the exact PR head. Local exact-head verification was skipped at the Operator's direction; no local test count is claimed. The implementation excludes predecessors with committed successors and validates candidate reciprocity against canonical predecessor history in the retriever's consistent snapshot; D7 eligibility remains in force.

1. Extend candidate SQL and result validation to require matching Team, item version, semantic content hash, origin ID, current LearningChange ID, hash scheme, embedding space, and a `published` index-state record.
2. Resolve and validate the current LearningChange and full B1 chain in application code; SQL joins and similarity scores are candidate selection only, never canonical authority.
3. Apply D7 eligibility at read time: item must be active, have a timezone-aware UTC `review_after`, and be strictly before its review deadline. Missing, due, or malformed review dates fail closed.
4. Apply the accepted D5 reciprocal-successor visibility gate against a consistent canonical snapshot: a candidate with `supersedes_item_id` stays hidden until its predecessor is retired and `superseded_by_id` points back to it; a predecessor with a committed successor is hidden. The predecessor and candidate are never both exposed. If a pending candidate exists while the predecessor becomes due or `needs_review`, neither is exposed until the reciprocal gate is satisfied.
5. B2 implements only the read/publication guard. Candidate creation and the actual supersede commit remain B5 work.

**Step 6 — Introduce Context manifest v3 without changing historical replay**

**Status (accepted and merged 2026-11-08):** PR [#53](https://github.com/abtn/Watch-Architecture-Rev2/pull/53) merged at `70ee2217aa7dc20e32b263a597af9b1b37261e29` (head `f0efbbb79f827fd48b9862262adccba15eabd2e9`). Hosted CI run [42464991372](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42464991372) passed on the exact PR head. Local exact-head verification was skipped at the Operator's direction; no local test count is claimed. New manifest v3 records current LearningChange identity and hash scheme, and final Context validation independently checks canonical history and reciprocal visibility. Manifest v1/v2 replay remains immutable and byte-exact; the outer Task Context schema remains v2.

1. New Context assembly emits `r6e-context-manifest-v3`. Add each included Team Experience passage's `current_learning_change_id` and `content_hash_scheme` alongside its existing item ID, version, content hash, and origin ID in both the selected manifest entry and the immutable Context document.
2. Carry these fields from projection rows through `RetrievedPassage` and final Context validation. The final Context validation independently reloads and verifies canonical history and reciprocal visibility; it must not trust an earlier retrieval result alone.
3. Keep Context manifest v1/v2 replay version-aware, byte-exact, and behavior-identical to the current implementation. Do not recalculate embedded KnowledgeItem content hashes or infer their scheme from manifest version. Do not rewrite historical snapshots or Events, reinterpret old manifests as v3, or require old passages to contain fields they never recorded.
4. Do not bump the outer Task Context document schema unless implementation demonstrates a separately necessary change; B2's accepted requirement is manifest v3.

**Step 7 — Refactor approval validation without enabling new operations**

**Implementation and verification status (2026-11-08):** Step 7 implementation was merged through PR #55 at `47aad564ac0496f4ff984bc4d937355922d36c77`. Hosted CI run `42468214569` and Operator-local exact implementation-head verification passed on `534a7fad6b6cb3cfa3fd7381bcdb0d8ecdb1b8e2` (793 tests in each environment). The implementation remains bounded by the accepted B2 create-only authority.

**Current enforcement inventory (verified on merged main after PR #53):**

- `OperatorApplicationAdapter.request_learning_change_decision` rejects anything other than `target_kind=knowledge_item`, `operation=create`, and `target_id=NULL` before creating the approval Task/request Event. It also binds the host-supplied principal, Team grant, acceptance assessment, idempotency key and request fingerprint.
- `TaskRuntime._validate_operator_admission` validates approval Task shape/write scope/budget, the unique request Event and its fingerprint, same-Team target, create operation/NULL target, and the recorded quality-assessment binding. It is called by admission and re-used by commit/finalization validation.
- `LearningCommitService.decide` independently checks Task type/attempt/scope/budget, request Event, principal identity and Team grant, Team and pinned policy, proposed status, create/NULL-target semantics, evidence reconstruction, and the atomic LearningChange decision/Event transaction.
- `TaskRuntime._validate_learning_change_decision_result` validates the committed create-only state and exact decision Event before terminalizing the Task. `_committed_operator_decision_observation` and recovery/replay paths must preserve the same create-only interpretation.

**Refactoring contract:**

1. Separate common approval-request integrity validation from create-specific eligibility and commit validation. Common integrity includes the request Event envelope/schema, decision/rejection-reason shape, canonical Operator identity binding, host-side Team-grant validation where the trusted principal is available (and persisted identity/fingerprint validation downstream), idempotency binding, request fingerprint, Task identity/type/attempt/scope/budget, and immutable assessment ID/hash binding where present.
2. Keep operation-specific checks explicit and fail-closed at each authority boundary: request creation, TaskRuntime admission, canonical commit, terminal finalization, and interrupted recovery/replay. The only currently eligible operation is `create`, with `target_kind=knowledge_item` and `target_id=NULL`; acceptance still requires the recorded completed `KnowledgeQualityAssessment` and the existing evidence/proposal validation.
3. Preserve independent enforcement at each boundary. Shared pure parsing/normalization/fingerprint helpers may be reused where dependency-safe, but do not move transaction-owned database checks out of their owning service, introduce circular imports, or make one layer trust an earlier layer's validation result.
4. Keep the active application approval allowlist exactly `{create}`. The wider LearningChange schema vocabulary is not an authorization grant. `revise`, `revalidate`, `supersede`, and `retire` must remain rejected at every entry/commit/finalization path.
5. Preserve existing stable rejection categories, including `only_knowledge_item_create_is_supported`, `operator_task_request_target_invalid`, and `learning_change_decision_state_mismatch`, unless a separately reviewed compatibility reason requires a change. Do not silently normalize distinct failure categories.
6. Preserve the existing Task write scope `["LearningChange", "KnowledgeItem"]`, Task type, host-authenticated typed principal, request/decision Event contracts, idempotency behavior, retry/attempt fencing, competing-approval conflict handling, interrupted recovery, and atomicity boundary: LearningChange decision + decision Event commit together; Task terminal Outcome/Events remain TaskRuntime-owned.

**Required regression coverage:**

- A table-driven operation matrix proves only `create` is admitted; each of `revise`, `revalidate`, `supersede`, and `retire` is rejected by request creation, direct TaskRuntime admission validation, direct `LearningCommitService.decide`, finalization validation, and recovery/replay validation as applicable.
- Rejected requests create no approval Task/request Event and no LearningChange/KnowledgeItem mutation. Tampered persisted request Events or committed states fail closed at the downstream boundary even if an earlier layer was bypassed.
- Common-integrity regressions cover malformed/duplicate request Events, invalid decision/rejection reason, non-canonical or mismatched Operator identity, missing Team grant, cross-Team target, altered idempotency key/fingerprint, mismatched assessment ID/hash, stale TeamPolicy pin, wrong Task shape/write scope/budget, and stale attempt.
- Existing create accept/reject behavior remains intact: accepted create binds the recorded quality assessment and creates one canonical KnowledgeItem; rejection creates none; decision Event and canonical mutation remain atomic.
- Existing same-key replay, conflicting-key behavior, concurrent competing approval Tasks, lost-response replay, interrupted recovery, and TaskRuntime terminal finalization remain covered and unchanged.

**Step 7 acceptance:** all common-integrity and create-specific checks are separated without weakening any boundary; the active allowlist is exactly `{create}`; all four later lifecycle operations fail closed with stable reasons at every applicable layer; no Task/schema/write-scope/runtime/provider/auth changes are introduced; focused tests, Ruff, Mypy and the full suite pass. Step 7 completion did not close B2: Step 8 integrated fixtures and Step 9 final B2 exit were still required.

**Implementation authorization and boundary:** Step 7 was explicitly authorized on 2026-11-08 and merged through PR #55. That authorization did not widen the active operation allowlist; only `knowledge_item/create/NULL target` is eligible.

**Step 8 — Integrated regression fixtures (ACCEPTED AND MERGED — PRs #56 and #57)**

**Closeout (2026-11-08):** Step 8 documentation/inspection PR #56 merged at `58d88bafdf33e8ce1af2f5a7ba9af11bfd84cb32`; integrated test fixtures PR #57 merged at `027b9f1cb0bbd5faaaf8d6d7cc44c8359af49b31`. PR #57 exact implementation head `114a6311534cd116190e3c2f4143fdfb1a2c979b` passed hosted CI run [42478536427](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42478536427): fresh PostgreSQL migration and single Alembic head, Ruff, Mypy, and **806 tests passed, 77 warnings**. The warnings were non-failing Alembic `path_separator` deprecations. Step 8 changed only three test files; no production source, migration, schema, runtime, provider, authentication, or database configuration changed. Operator-local exact-head verification on the Step 8 code head is not yet recorded and is required in Step 9.

**Delivered integrated coverage:**

- Accepted create → canonical LearningChange/current pointer → v2 hash → Team Experience projection → retrieval → Context manifest v3.
- Real Alembic `0016` migration → legacy-opaque/stale projection blocked from retrieval → application `rebuild_all()` → republished v2/current-pointer pins → retrieval restored.
- Failed publication → stale/undiscoverable projection → successful rebuild → repeated rebuild returns unchanged without another embedding publication.
- Canonicality/projection tampering matrix across current pointer, Team, target, status, committed snapshot, hash scheme, stale state, and chunk hash; rejected data remains absent from retrieval and Context.
- Offset-aware D7 boundary behavior; before-boundary eligibility and exact-boundary ineligibility.
- Context v1/v2 replay remains byte-exact without reassembling or recalculating the KnowledgeItem hash.
- Database-enforced cross-Team projection integrity is asserted separately because the composite constraint rejects the mutation before retrieval.
- Existing D5 focused matrix and Step 7 create-only approval matrix remain intact; no redundant D5 test expansion or approval-authority change was introduced.

**Step 8 boundary:** the integrated regression implementation is complete and merged. The create-only allowlist remains exactly `{create}`. Step 8 completion does not constitute B2 exit; Step 9 exit review and explicit Operator acceptance remain required. B3 planning/preflight is documented only; B3 implementation remains unauthorized. B4–B6 and R7-C remain unauthorized.

**Step 9 — Exact-head verification and formal B2 exit gate (Operator-closed 2026-11-08 with accepted residuals)**

**Execution record (2026-11-08):** the exact merged implementation commit under test was `027b9f1cb0bbd5faaaf8d6d7cc44c8359af49b31`. Hosted run [42479112563](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42479112563) and Operator-local verification both passed on this same commit. PR #57's exact head `114a6311534cd116190e3c2f4143fdfb1a2c979b` also passed hosted run [42478536427](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42478536427); it is retained as PR-head evidence, not confused with the merge-commit exact-SHA run. Full local evidence and outstanding checks are recorded in `docs/testing.md`.

**Preflight and identity — PASS:** local checkout was repository root, branch `main`, HEAD `027b9f1cb0bbd5faaaf8d6d7cc44c8359af49b31`, equal to `origin/main`; worktree clean before and after. `uv sync --locked` passed. No code changed during verification.

**Database and migration — PASS:** a fresh disposable PostgreSQL container `watch-b2-step9-clean-d8f56de433`, database `watch_b2_step9_clean`, dynamically assigned loopback port `10891`; full Alembic chain from empty DB; current revision `0016_team_exp_history_pins`; exactly one head. Container was subsequently confirmed absent. Persistent `watch` and port `5432` were not targeted.

**Static and full verification — PASS:** Ruff; Mypy (33 source files); full pytest suite once, without preceding focused tests: **806 passed, 77 warnings in 136.25s**. Warning counts: 65 in `tests/test_r7b_history_migration.py` and 12 in `tests/test_team_experience_projection_migration.py`, including the Alembic `path_separator` deprecation warning. Hosted run 42479112563 passed the corresponding migration/static/full-suite job on the same implementation SHA (806 tests, 77 warnings).

**Not yet evidenced as separate Step 9 checks:** focused regression groups were not separately invoked on the local run; `git diff --check` was not recorded; and a complete line-by-line final diff/scope review remains outstanding. The full-suite pass is not represented as a separate focused-run pass. The changed-file inventory and key create-only approval guards have been reviewed; no scope expansion was identified in those reviewed surfaces.

**Sequence deviation:** Operator-local verification occurred while this Step 9 planning PR (#58) was still open and unmerged, although this plan originally specified merging the planning checkpoint before execution. This deviation is recorded transparently. It does not create a code-SHA mismatch: hosted and local verification both tested the unchanged implementation commit `027b9f1cb0bbd5faaaf8d6d7cc44c8359af49b31`. PR #58 is documentation-only; its later documentation commits do not alter the implementation code tree under test.

**Scope boundary:** the reviewed B2 implementation remains limited to hash/history/projection/retrieval/Context and create-only approval behavior. The active approval allowlist remains exactly `{create}`. No B3 assessment Tasks/models, B4 revise/revalidate writes, B5 candidate creation/supersede/retire writes, B6 expansion, R7-C reference/use/benchmark, new runtime/dispatcher/scheduler/public API/auth stack, or production provider is authorized or included in this documentation update.

**B2 exit disposition (2026-11-08): CLOSED BY EXPLICIT OPERATOR INSTRUCTION.** The Operator instructed “Close B2.” The exact-code-head hosted/local technical evidence is positive, and the Operator accepted closure while retaining these residual verification gaps: (1) prescribed focused groups were not separately run; (2) `git diff --check` was not recorded; (3) complete line-by-line final diff review was not completed. These are accepted residuals, not passed checks. The local verification preceded merge of the Step 9 documentation PR; this sequence deviation remains explicit. The active approval allowlist remains exactly `{create}`. B3 planning/preflight may proceed; B3 implementation requires separate written authorization. B4–B6 and R7-C remain unauthorized.

**Documentation boundary:** this PR updates project status and verification records only. It does not change source, tests, migrations, schema, runtime, provider, authentication, Task grants, or database configuration.

### B2 acceptance criteria

- V2 hash follows the exact ADR field list, separator, normalization, and serialization. Historical projection rows carry `legacy-opaque`, remain stale and cannot be retrieved before v2 republish; no legacy projection-hash verifier is assumed.
- Revalidation-only lifecycle metadata changes do not affect v2 content hash; confidence changes do.
- Existing projection rows are explicitly legacy and stale, are never treated as v2, and cannot be retrieved before republishing.
- New chunks and index-state records pin the exact current LearningChange ID and hash scheme; publication is atomic and rechecks canonical state.
- Indexing, retrieval, and Context assembly validate the B1 current-pointer chain, policy/Team provenance, D7 eligibility, and D5 reciprocal visibility.
- New Context uses manifest v3; historical v1/v2 replay is immutable and unchanged.
- The active approval allowlist is exactly `{create}` at request creation, TaskRuntime admission/finalization/recovery, and LearningCommitService; all later lifecycle operations remain rejected with stable tested reasons.
- Fresh migration, focused regressions, Ruff, Mypy, full suite, diff check, and exact-head hosted CI pass.

### B2 stop conditions and explicit non-goals

Stop and report a design discrepancy before implementing a workaround if: any historical projection might remain retrievable after migration; current-pointer history cannot be proven; D5 reciprocity cannot be checked against a consistent snapshot; Context v1/v2 replay changes; or the create-only approval boundary cannot be preserved.

B2 does **not** implement KnowledgeRevalidationAssessment or KnowledgeLifecycleAssessment (B3); revise/revalidate writes (B4); candidate creation, supersede, or retire writes (B5); repeated legacy lifecycle hardening assigned to B6; TaskKnowledgeReference/KnowledgeUseAssessment or retrieval benchmarking (R7-C); a new runtime, dispatcher, scheduler, public API/auth stack, production evaluator/provider, or second commit path.

**B2 exit criterion:** either the full B2 acceptance matrix is green on the exact PR head with synchronized implementation/verification records, or the Operator explicitly accepts closure with any uncompleted checks recorded as residuals rather than passes. B2 was closed through the latter disposition on 2026-11-08. B3 implementation remains separately gated.



## Phase B3: Typed assessments and recording Tasks

**B2 closeout reference:** B2 is formally closed by explicit Operator instruction on 2026-11-08. The three retained residual verification gaps are recorded in `PLAN.md` and `docs/testing.md`; none is represented as passed. This does not expand B2's create-only authority.


**Status:** B3.2 schema/migration/immutability implementation is merged through PR #60. Checkpoint 4 is the post-merge review and exact-merge local verification gate; it is not yet closed. The final PR head passed hosted CI, while Operator-local verification on the exact merge commit remains pending. B3.3 is the next planned stage but has not started. This document update records the current implementation state; it does not authorize B3.3 or widen any Task/approval authority.

**Goal:** add immutable, operation-specific assessment records and narrow recording Tasks. These assessments supply validated evidence to the existing trusted Operator approval path; they do not authorize or commit lifecycle transitions.

**Frozen B3 boundaries**

- Add only `KnowledgeRevalidationAssessment` and `KnowledgeLifecycleAssessment`, with the operation-specific variants defined below. Do not reuse `KnowledgeQualityAssessment`.
- Add only the narrow assessment Tasks `assess_knowledge_revalidation` and `assess_knowledge_lifecycle`.
- The revalidation assessment is bound to the exact current item state and a freshly rebuilt, verified evidence basis. A timestamp alone never establishes freshness.
- Lifecycle assessment is deterministic and operation-specific. It records structured Operator rationale, evidence references, and findings; no model scoring.
- Evaluator/assessor implementations are injected behind a narrow boundary. Tests use deterministic fakes. No production provider or model is selected.
- Each assessment Task may record only its own typed assessment and Task-attributed Events. It cannot write `LearningChange` or `KnowledgeItem`.
- Approval-time validation binds the assessment to the exact proposal, target state, evidence, policy pin, Task scope, and host-supplied Operator identity/fingerprint required by B0.3.
- The active lifecycle approval allowlist remains exactly `create` throughout B3. B3 does not enable revise, revalidate, supersede, or retire commits.
- Reuse the existing TaskRuntime, Task admission/finalization/recovery, Event, and immutable-record patterns. No second runtime, dispatcher, scheduler, auth stack, or autonomous approval.

### B3 sequence — planning may start now; implementation requires the entry gate

#### B3.0 — Entry gate and exact-head preflight

**Agent / coding side**
1. Read the current `PLAN.md`, this B3 section, ADR-0032 B0.1–B0.3, the accepted B1/B2 implementation, `docs/tasks.md`, and the existing R7-A quality-assessment implementation.
2. Trace the actual code paths for assessment persistence, Task creation/admission, TaskRuntime finalization/recovery, Task-attributed Events, immutable-row enforcement, approval request fingerprints, and create-only lifecycle guards. Verify every symbol against current `main`; do not rely on stale line numbers or assume the earlier R7-A pattern is identical.
3. Produce a read-only inventory: files/classes/functions to extend, migration head, constraints/triggers available, existing event/outcome semantics, current assessment replay/idempotency behavior, and every guard that must remain create-only.
4. Report discrepancies between this plan and code. Stop on any conflict with B0.3 or the authority boundary; do not invent a workaround.

**Operator / local side**
1. Confirm the B2 closure record and understand its accepted residuals; do not relabel those residuals as passed checks.
2. Run the read-only local preflight: repository root, branch, HEAD, clean/dirty worktree, `origin/main` relation, Python/uv environment, and current Alembic head. Do not discard or stash local changes.
3. Give the agent the exact observed base SHA and preflight report. Do not let the agent infer the local checkout state.
4. Do not run migrations or database-backed tests in this read-only planning step. When implementation is later authorized, use only a fresh disposable PostgreSQL database/container and a dynamically assigned loopback port; do not inspect or target persistent `watch` or host port 5432.
5. Before B3.2, verify that B2 formal exit is recorded in `PLAN.md`, its documentation PR is merged, and separate written B3 implementation authorization exists.

**Expected output:** a read-only B3 inventory and a recorded preflight report. No code, migration, database mutation, Task registration, or authority change.

#### B3.1 — Freeze the typed assessment contracts

**Agent / coding side**
1. Define the immutable `KnowledgeRevalidationAssessment` contract. It must bind:
   - KnowledgeItem ID and Team ID;
   - exact current `LearningChange` pointer;
   - expected content version and v2 content hash/scheme;
   - rebuilt evidence-basis hash and canonical evidence references;
   - evaluator identity and revision;
   - typed findings/disposition and the complete assessment payload hash;
   - creating Task identity and the provenance needed to verify the recorded assessment.
2. Define the immutable `KnowledgeLifecycleAssessment` envelope and strict discriminated payloads:
   - **retire variant:** exact target state, operation, structured Operator rationale/reason, evidence references, deterministic findings;
   - **supersede variant:** all required predecessor bindings plus exact successor ID, Team, current pointer, version, content hash, status, `review_after`, and the evidence/rationale for the replacement relationship.
3. Bind each assessment to the exact proposed `LearningChange` and its proposal/proposed-state hashes. A lifecycle assessment must not be reusable for another operation, target, proposal, or successor state.
4. Specify canonical serialization and payload-hash inputs using the accepted B0.3 rules and existing repository canonicalization helpers. Preserve array order where the contract requires it; do not introduce unreviewed normalization.
5. Define stable validation failure categories for missing, stale, malformed, cross-Team, wrong-operation, and hash-mismatched assessments.
6. Do not add fields, status values, uniqueness rules, or new authority semantics that are not required by B0.3 or proven necessary by the existing persistence/idempotency contract. Surface any unresolved schema decision for Operator review before implementation.

**Operator review point:** review the field/binding matrix and the exact distinction between revalidation and lifecycle variants before schema work begins.

**Expected output:** a reviewed contract table, serialization/hash specification, and negative-case matrix. No code yet.

**Implementation authorization gate:** B3.2 and every later implementation stage require both (a) formal B2 exit recorded in `PLAN.md` after the required checks are completed or explicitly dispositioned, and (b) separate written Operator authorization for B3 implementation. If either is absent, stop after B3.0/B3.1 planning.

#### B3.2 — Schema, migration, and immutability

**Agent / coding side**
1. Recheck the actual current migration head and model conventions. Select the next migration revision only after the exact base is confirmed; never guess or reuse a revision identifier.
2. Add separate persistence models/tables for the two typed assessment records. Enforce Team ownership and same-Team relationships to the target, proposal, and creating Task using the strongest supported database constraints.
3. Encode operation-specific payload shape so a retire assessment cannot carry supersede-only fields and a supersede assessment cannot omit its successor binding.
4. Add database-level immutability protection consistent with existing immutable assessment/history records. Updates and deletes must be rejected; ordinary creation and required Task/Event attribution must remain possible.
5. Add migration upgrade/downgrade tests and positive/negative constraint tests. Preserve all existing records and historical replay bytes.
6. Do not change `KnowledgeItem`, `LearningChange`, their commit constraints, the create-only approval allowlist, or any projection/retrieval schema in B3.

**Operator / local side**
1. Review the migration plan and exact schema diff before running it.
2. Verify the migration on a fresh disposable database and confirm one Alembic head.
3. Never run migration experiments against persistent `watch`.

**Expected output:** two typed immutable persistence contracts, migration and DB-level rejection tests; no lifecycle commit capability.

#### B3.2 Checkpoint 4 — Post-merge contract review and exact-merge verification

**Status:** exact-merge local verification passed on 2026-11-08; formal Checkpoint 4 acceptance/closeout remains pending.

**Merged implementation and hosted evidence**
- PR [#60](https://github.com/abtn/Watch-Architecture-Rev2/pull/60) merged to `main` at `31be3a25cf7f52ca81eab65cc10280a855738c3d`.
- Final PR head: `0eecefedbc4ef6e4b60cbd8c3eacf31e1256f362`.
- Hosted CI [run 42496681657](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42496681657) passed on the exact PR head: fresh PostgreSQL migration and single-head checks, Ruff, Mypy, and 823 tests (95 warnings).

**Contract review findings**
1. The migration creates separate `knowledge_revalidation_assessments` and `knowledge_lifecycle_assessments` tables, plus immutable `learning_change_operator_provenance`.
2. Composite constraints bind assessment Team, Task, exact proposal operation, proposal target, KnowledgeItem, request/recorded Events, and lifecycle successor to the required same-Team/Task relationships. The proposal's target reference remains target-bound.
3. The historical `current_learning_change_id` references are intentionally Team-bound rather than target-bound: B1 backfills the historical current pointer to the original create LearningChange, whose `target_id` is NULL. This exception does not weaken the target-bound FK from the proposed LearningChange to the exact KnowledgeItem. The successor current pointer follows the same historical-pointer rule.
4. Assessment identity, Task/idempotency, request Event, and recorded Event uniqueness are database-enforced. Hash format, operation vocabulary, positive versions/attempts, JSON array shape, and retire/supersede variant shape have database checks.
5. Row UPDATE/DELETE and statement TRUNCATE are rejected for both assessment tables and Operator provenance. Downgrade refuses to remove persisted assessment/provenance history; empty-schema downgrade is covered separately. No application database role existed to receive a narrower privilege boundary, so no role was invented or altered; privileged superuser/replication bypass remains an operational boundary.
6. The final PR corrections align ORM and migration checks for whitespace-only provenance/evaluator/idempotency values and retain negative PostgreSQL tests for cross-Team references, invalid proposal operation, Event/Task attribution, duplicate identity, invalid retire/supersede shapes, and successor deletion.
7. No assessment Task registration, worker write grant, assessment service, lifecycle commit, or approval expansion is included in B3.2. The active approval allowlist remains exactly `create`.

**Earlier Operator-local evidence — not exact-merge evidence**
- The earlier local run was on `02913493f1c82bda25aaa8e843097b9f4c2a7c52`, before the final PR fixes. It reached `0017_r7b_assessments`, verified one Alembic head, passed Ruff/Mypy, 13 focused tests, 819 full-suite tests (87 warnings), and `git diff --check`.
- Because the final PR head added the whitespace-only identity corrections and additional PostgreSQL regression coverage, this earlier local result must not be reported as verification of merge commit `31be3a25cf7f52ca81eab65cc10280a855738c3d`.

**Operator-local exact-merge verification — PASSED (2026-11-08)**

- Tested SHA: `31be3a25cf7f52ca81eab65cc10280a855738c3d`; local `main` was fast-forwarded to the exact `origin/main` merge commit after a clean-worktree preflight.
- `uv sync --locked` passed.
- Fresh disposable PostgreSQL container `watch-r7b-b3c4-15bc377052`, database `watch_r7b_b3c4_15bc377052`, dynamically assigned loopback port `29544`.
- `uv run alembic upgrade head` passed; database revision and sole Alembic head: `0017_r7b_assessments`.
- Focused tests: `uv run pytest tests/test_r7b_assessment_models.py -q` → **9 passed**; `uv run pytest tests/test_r7b_assessment_migration.py -q` → **8 passed, 18 warnings**.
- `uv run ruff check core tests migrations` passed.
- `uv run mypy core` passed (33 source files).
- `uv run pytest -q` → **823 passed, 95 warnings in 123.45s**.
- Both `git diff --check 31be3a25cf7f52ca81eab65cc10280a855738c3d^ 31be3a25cf7f52ca81eab65cc10280a855738c3d` and worktree `git diff --check` passed.
- Original `DATABASE_URL` and `TEST_DATABASE_URL` values were restored. The runner removed only its disposable container; removal was confirmed. Persistent `watch` and host port 5432 were not targeted.
- All 95 warnings were Alembic `path_separator` deprecation warnings: 18 from assessment migration tests, 65 from `tests/test_r7b_history_migration.py`, and 12 from `tests/test_team_experience_projection_migration.py`. They did not fail tests or checks.

This is exact-merge local evidence, not a result on the PR head or the earlier pre-final-fix commit.

**Checkpoint 4 acceptance boundary:** B3.2 may be recorded closed only after the schema/contract review and exact-merge local verification are accepted and documented. B3.3 remains the next stage, but this closeout does not itself authorize its implementation. The create-only approval allowlist and all B3 authority boundaries remain unchanged.

#### B3.3 — Revalidation assessment service and Task

**Agent / coding side**
1. Implement a narrow evidence-basis builder that reconstructs the basis from canonical Outcomes, recorded Evaluations, Events, EvidenceLinks, immutable Snapshots, and other explicitly permitted canonical references. Do not treat retrieved chunks, similarity ranks, transcripts, or model assertions as canonical evidence.
2. At assessment time, revalidate reference existence, Team ownership, canonical IDs, snapshot/source hashes, provenance and quote constraints, and the exact current item pointer/version/content hash.
3. Apply the B0 freshness rule: existing canonical observations may qualify only while temporally relevant and source-valid. Time-sensitive/current-condition claims, expired or changed sources, and material newer or contradictory evidence require new observations. A timestamp alone is insufficient.
4. Place the evaluator behind an injected protocol that returns an untrusted typed draft. Validate the draft and all bindings in application code before persisting the immutable assessment. Tests use deterministic fakes; no production evaluator is wired.
5. Implement `assess_knowledge_revalidation` as an ordinary Task on the existing TaskRuntime. Its exact write scope is only `KnowledgeRevalidationAssessment` plus Task-attributed Events through the established runtime mechanism.
6. Make retries, idempotency, replay, interrupted-task recovery, and terminal outcomes consistent with the verified R7-A Task pattern. Replaying a completed Task must return the same recorded assessment, not call the evaluator again or create a second assessment.
7. Fail closed when the item pointer/version/hash changes during assessment or evidence reconstruction; the result must not be accepted as current.

**Operator review point:** inspect the evidence freshness truth table and the allowed canonical evidence sources before accepting the implementation.

**Expected output:** deterministic tests for fresh/adequate evidence, stale or changed sources, new-observation-required cases, cross-Team references, pointer races, malformed evaluator drafts, retry and replay.

#### B3.4 — Lifecycle assessment service and Task

**Agent / coding side**
1. Implement deterministic, operation-specific assessment validation for `retire` and `supersede`. Do not use model scoring or a production evaluator.
2. Require structured Operator rationale, evidence references, and deterministic findings for each variant.
3. For retire, bind the exact target ID, Team, current pointer, version, status, content hash, and full-state snapshot expected by the proposal.
4. For supersede, additionally bind the exact successor's ID, Team, current pointer, version, content hash, status, and `review_after`; bind the predecessor's actual current state and the explicit replacement rationale/evidence.
5. Enforce strict discriminated payload validation. Wrong-operation fields, missing successor fields, stale target/successor bindings, and cross-Team relationships fail closed.
6. Implement `assess_knowledge_lifecycle` as an ordinary Task on the existing TaskRuntime. Its exact write scope is only `KnowledgeLifecycleAssessment` plus Task-attributed Events through the established runtime mechanism.
7. Ensure replay returns the same immutable assessment and never silently reassesses a completed Task against newer state.

**Operator review point:** review the retire/supersede payload examples and confirm they match the frozen B0.1 candidate and graph rules. B3 assessment does not create candidates or commit supersession.

**Expected output:** deterministic retire/supersede contract tests, stale-binding tests, cross-Team rejection, Task scope, replay and immutability coverage.

#### B3.5 — TaskRuntime, recovery, and Event integration

**Agent / coding side**
1. Register both Task types only through the existing Task registry/admission path and only after their exact request-event and Task-shape validators are implemented.
2. Verify exact `allowed_writes`, budget, attempts, deadline, and Task linkage against the actual repository conventions. Do not copy values blindly from R7-A.
3. Ensure TaskRuntime admission, finalization, interrupted-task recovery, retry fencing, and committed-observation replay recognize each assessment Task without broadening unrelated Task types.
4. Record the required request/recorded Events with Task attribution and immutable payload hashes. Event replay must prove the same Task, assessment ID, Team, and proposal binding.
5. Confirm neither assessment Task can pass admission/finalization/recovery with `KnowledgeItem` or `LearningChange` in its write scope or mutate either table through a side path.
6. Test missing/corrupt Events, duplicate recording, retry after partial failure, terminal replay, and conflicting idempotency keys.

**Expected output:** narrow TaskRuntime integration and explicit proof that the existing runtime remains the only execution path.

#### B3.6 — Approval-time assessment binding

**Agent / coding side**
1. Extend the existing approval validation path to load and independently verify the required assessment for the requested operation. Do not trust an assessment ID or Task status alone.
2. Recompute/verify the assessment payload hash and validate the full target/proposal/evidence binding, Team ownership, current pointer/version/content hash, evaluator identity/revision, pinned TeamPolicy version, and Task write scope.
3. For supersede, revalidate the complete successor binding, including `review_after`, against current canonical state at approval time.
4. Include assessment payload hashes—not only assessment IDs—in the immutable approval-request fingerprint and committed decision record, together with the host-supplied canonical Operator identity as required by B0.3.
5. Reuse of an idempotency key with a different principal, assessment payload, proposal, target state, or successor state must conflict. Stale or mismatched assessments cannot be accepted; a new proposal and assessment are required.
6. Keep the active approval allowlist exactly `create`. Add validation infrastructure only; do not admit `revalidate`, `supersede`, or `retire` commits in B3. `revise` remains B4 scope.

**Operator review point:** inspect the final fingerprint field matrix and prove that B3 has not widened the approval allowlist.

**Expected output:** approval-gate tests for missing, duplicate, stale, tampered, wrong-operation, cross-Team, wrong-principal, and successor-mismatch assessments, while all non-create commits remain rejected.

#### B3.7 — Integrated regression matrix

Add end-to-end tests that traverse the real persistence, TaskRuntime, Event, assessment, and approval-validation boundaries. At minimum cover:

- valid revalidation assessment bound to a fresh current evidence basis;
- evidence freshness failures: expired/changed source, time-sensitive claim without new observations, material contradiction, missing canonical reference, invalid provenance;
- pointer/version/content-hash drift before and during assessment and again before approval;
- cross-Team target, evidence, proposal, Task, and successor references;
- immutable assessment update/delete rejection at the database boundary;
- malformed and cross-operation lifecycle payloads;
- retire target binding and full-state mismatch;
- supersede successor ID/pointer/version/hash/status/`review_after` mismatch;
- evaluator identity/revision mismatch and malformed/untrusted evaluator draft;
- exact Task write-scope rejection for `KnowledgeItem` and `LearningChange`;
- request/recorded Event integrity, idempotency conflicts, retry, interrupted recovery, and byte/ID-stable terminal replay;
- approval fingerprint binds the full assessment payload and host principal;
- all non-create lifecycle approval attempts remain rejected, including admission, finalization, recovery, and commit-service boundaries.

Tests must assert both the intended assessment record and the absence of unauthorized canonical writes. Do not rely solely on unit tests that bypass TaskRuntime, database constraints, or approval validation.

#### B3.8 — Exact-head verification and exit review

**Agent / coding side**
1. Run the prescribed focused groups independently before the full suite; record exact commands and results.
2. Run Ruff, Mypy, and `git diff --check`.
3. Review the complete diff against the B3 changed-file allowlist and this phase boundary. Report every changed file and explain any necessary support change outside the core assessment paths.
4. Verify no production provider, new runtime/dispatcher/scheduler, authentication stack, direct KnowledgeItem/LearningChange write, or non-create approval grant was introduced.
5. Ensure hosted CI passes on the exact final PR head.

**Operator / local side**
1. Preflight the exact PR head and clean worktree before syncing/testing.
2. Run migrations and the full suite against a fresh disposable PostgreSQL instance on a dynamically assigned loopback port.
3. Run the same focused groups, Ruff, Mypy, and diff check locally; record the exact tested SHA.
4. Confirm the disposable container is removed and both database environment variables are restored; do not touch persistent `watch` or host port 5432.
5. Compare hosted and local tested code SHAs; investigate any mismatch rather than calling it exact-head verification.

**Expected output:** reproducible hosted/local evidence on one exact code SHA, complete diff/scope review, and a B3 exit recommendation.

#### B3.9 — Documentation closeout and separate gate

1. Update `PLAN.md`, this implementation plan, `docs/testing.md`, ADR-0032 progression, Task documentation, CHANGE_MAP, README, and CONTEXT so that status, task names, write scopes, and authority boundaries agree.
2. Record actual merged commit, exact hosted/local tested SHA, focused/full test counts, warnings, migration head, static checks, diff review, and any deviations. Do not turn unrun checks into passes.
3. Obtain explicit Operator acceptance of B3 exit before marking B3 complete.
4. Keep B4–B6 and R7-C separately gated. B3 exit does not authorize any lifecycle commit path.

### B3 acceptance criteria

- Both assessment types are immutable and operation-specific, with canonical payload hashes and complete target/proposal/evidence bindings.
- Revalidation freshness follows B0.2/B0.3; canonical evidence references and source hashes are revalidated at assessment time.
- Lifecycle assessment is deterministic, contains structured Operator rationale/evidence/findings, and strictly separates retire from supersede.
- Both assessment Tasks use the existing TaskRuntime, exact narrow write scopes, attributable Events, idempotency, recovery, and stable replay.
- Approval-time validation independently verifies the exact assessment payload and all B0.3 fingerprint bindings.
- The active approval allowlist remains exactly `create`; B3 introduces no lifecycle commit capability.
- Focused and full tests, fresh migration/single-head, Ruff, Mypy, `git diff --check`, complete scope review, and hosted/local exact-head verification pass.
- No production evaluator/provider, new runtime/dispatcher/scheduler/auth stack, direct canonical writes, or R7-C work is introduced.

**B3 stop conditions:** stop and return to the Operator if the frozen contracts cannot be represented without changing B0.3, if canonical evidence freshness cannot be verified, if assessment immutability or exact Task scope cannot be enforced, if the approval fingerprint cannot bind all required data, or if implementation would require widening the create-only allowlist. Do not proceed into B4 to work around a B3 blocker.

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
- Content hash: unchanged across revalidation, supersede and retire; changes on content revise (and confidence revise per decision). Historical projection hashes remain unchanged and ineligible until republished; historical LearningChange snapshot hashes continue to follow their separate snapshot decoder/verification rules.
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
