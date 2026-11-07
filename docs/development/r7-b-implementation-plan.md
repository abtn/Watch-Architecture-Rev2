# R7-B Agent Development Plan: KnowledgeItem Lifecycle (Revision 3 — repository-aligned)

**Audience:** the implementing agent.
**Sources:** Operator acceptance of the R7-B B0 decision review on 2026-11-05; ADR-0032 (original acceptance 2026-11-04 for R7-A, with the separately accepted R7-B design addendum below); INV-12/13; ADR-0029 D7; and the reviews of Revisions 1–3.
**Status (2026-11-07):** **B0 complete; B1 accepted and merged; B2 Step 0 complete; `legacy-opaque` amendment accepted; B2 implementation authorized; Step 1 and Step 2 accepted and merged; Step 3 correction implemented and corrected-head hosted CI passed; local re-verification and final review pending.** PR #43 merged at `d1a8b88fd930207142304fc9b0b7274de5de4992`; PR #45 merged at `18595356a3da93b47a8701c7e94fe7dbde098d55`; PR #46 merged at `669d2e8140036ea4db07cbc44b33f6baa2e2608d`. Step 3 is on PR [#48](https://github.com/abtn/Watch-Architecture-Rev2/pull/48), corrected code/test head `673de5f74e734e3a9fa6059b3f4333e93a055a99`. Corrected-head hosted CI [run 42382712672](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42382712672) passed fresh migration/single-head checks, Ruff, Mypy (32 source files), **738 tests**, and disposable-container cleanup. Operator-local exact-head verification passed on the prior head `326be859d36d82c042fe5b183e16a9168f7b3e4b`; local re-verification of the correction is pending. Full evidence is in `docs/testing.md`. Final technical review and explicit Operator acceptance remain pending. B3–B6 and R7-C remain unauthorized.



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

**B0 completion did not itself authorize B1. The Operator separately authorized B1 on 2026-11-05; B1 is accepted and merged. B2 was separately authorized on 2026-11-06. Step 1 and Step 2 are accepted and merged; B2 Step 3 is in progress within the accepted B2 sequence.** B3–B6 remain unauthorized; no later-phase Task registration, provider, active write scope or runtime change is authorized.

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

**Status:** B2 preplanning was finalized 2026-11-06 and the Operator separately authorized implementation on that date. Step 1 and Step 2 are accepted and merged; Step 3 correction is implemented and corrected-head hosted CI passed on PR #48; local re-verification, final review, and explicit acceptance remain pending. The sequence below remains binding.

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

**Status (2026-11-07):** the final-review correction is implemented on PR [#48](https://github.com/abtn/Watch-Architecture-Rev2/pull/48), corrected code/test head `673de5f74e734e3a9fa6059b3f4333e93a055a99`, based on accepted Step 2 merge commit `669d2e8140036ea4db07cbc44b33f6baa2e2608d`. The canonicality helper resolves the current pointer and delegates complete chain/D7 verification to `reconstruct_knowledge_item_history`; retrieval SQL/verifier and Context validation now enforce Step 2's current-pointer and v2 hash-scheme pins. A pointer-only accepted-revalidation regression proves old projections are rejected until republished. Corrected-head hosted CI [run 42382712672](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42382712672) passed migration/single-head checks, Ruff, Mypy (32 source files), **738 tests**, and disposable-container cleanup. Operator-local verification passed on prior head `326be859d36d82c042fe5b183e16a9168f7b3e4b`; local re-verification of the correction is pending. See `docs/testing.md` for exact details. Final technical review and explicit Operator acceptance remain pending. Actual lifecycle commits remain create-only.

1. Replace the origin-create-only assumption in `_accepted_learning_change_is_canonical`. Load the current change through `KnowledgeItem.current_learning_change_id`, not through `origin_learning_change_id`.
2. Validate that the pointer resolves to an accepted same-Team `LearningChange`; validate operation-specific target semantics (create has NULL target and creates this item; a later transition targets this exact item); validate the approval Task, pinned TeamPolicy, trusted decision Event, and committed timestamp.
3. Use B1's `reconstruct_knowledge_item_history` as the history authority. Do not introduce a second, weaker chain reconstruction implementation. The final reconstructed state must match the live canonical KnowledgeItem, including the D7 review overlay and current pointer.
4. During B2, real accepted lifecycle commits remain create-only. Add synthetic history fixtures where useful to prove a non-origin current pointer is understood by readers, without adding a live revise/revalidate approval path. Malformed, missing, cross-Team, unaccepted, wrong-target, wrong-pointer, or inconsistent snapshots fail closed.

**Step 4 — Publish current-pointer and hash-scheme pins**

1. Extend the indexer, `_upsert_index_state`, `_projection_matches`, and final publication transaction to bind the exact current LearningChange ID and v2 content-hash scheme in both index state and each chunk.
2. Recheck the item ID/Team, current pointer, content version/hash, scheme, status, D7 eligibility, canonical history, and embedding-space identity immediately before publication. The state row and chunk rows must describe the same canonical version.
3. Keep the existing stale-before-embedding behavior: once a refresh is required, old rows must become undiscoverable before a provider call can fail. Publish replacement chunks and the matching index-state record atomically after all final checks.
4. Make `rebuild_all` discover `legacy-opaque`/stale rows so they can be republished through the normal indexer. Rebuild is an ordinary projection operation, not a canonical KnowledgeItem write.

**Step 5 — Enforce chain and publication gates in retrieval**

1. Extend candidate SQL and result validation to require matching Team, item version, semantic content hash, origin ID, current LearningChange ID, hash scheme, embedding space, and a `published` index-state record.
2. Resolve and validate the current LearningChange and full B1 chain in application code; SQL joins and similarity scores are candidate selection only, never canonical authority.
3. Apply D7 eligibility at read time: item must be active, have a timezone-aware UTC `review_after`, and be strictly before its review deadline. Missing, due, or malformed review dates fail closed.
4. Apply the accepted D5 reciprocal-successor visibility gate against a consistent canonical snapshot: a candidate with `supersedes_item_id` stays hidden until its predecessor is retired and `superseded_by_id` points back to it; a predecessor with a committed successor is hidden. The predecessor and candidate are never both exposed. If a pending candidate exists while the predecessor becomes due or `needs_review`, neither is exposed until the reciprocal gate is satisfied.
5. B2 implements only the read/publication guard. Candidate creation and the actual supersede commit remain B5 work.

**Step 6 — Introduce Context manifest v3 without changing historical replay**

1. New Context assembly emits `r6e-context-manifest-v3`. Add each included Team Experience passage's `current_learning_change_id` and `content_hash_scheme` alongside its existing item ID, version, content hash, and origin ID in both the selected manifest entry and the immutable Context document.
2. Carry these fields from projection rows through `RetrievedPassage` and final Context validation. The final Context validation independently reloads and verifies canonical history and reciprocal visibility; it must not trust an earlier retrieval result alone.
3. Keep Context manifest v1/v2 replay version-aware, byte-exact, and behavior-identical to the current implementation. Do not recalculate embedded KnowledgeItem content hashes or infer their scheme from manifest version. Do not rewrite historical snapshots or Events, reinterpret old manifests as v3, or require old passages to contain fields they never recorded.
4. Do not bump the outer Task Context document schema unless implementation demonstrates a separately necessary change; B2's accepted requirement is manifest v3.

**Step 7 — Refactor approval validation without enabling new operations**

1. Separate common approval-request integrity checks from the operation-specific eligibility/commit checks in `OperatorApplicationAdapter`, `LearningCommitService`, and TaskRuntime approval admission/finalization.
2. Keep the active approval allowlist exactly `create`. Revise, revalidate, supersede, and retire must remain rejected with stable, tested reasons until their later authorized phases.
3. Do not add Task types, Task registrations, worker capabilities, new write scopes, autonomous approval, or a second commit path. Preserve trusted host Operator identity, idempotency, request fingerprints, retry/recovery, and atomic decision/Event behavior.

**Step 8 — Add integrated regression fixtures**

Cover the whole read path, not only helpers:

- New create → accepted LearningChange → current pointer → v2 hash → projection publication → retrieval → Context v3.
- Existing projection with unknown historical hash → `legacy-opaque` marker and stale state → no retrieval → explicit successful republish → v2 projection and retrieval.
- Republish failure after stale marking → old chunks remain undiscoverable; retry/rebuild succeeds idempotently.
- Current-pointer mismatch, wrong Team, wrong target, wrong status, invalid snapshot, broken chain, wrong scheme, or tampered chunk/state → no passage and no Context inclusion.
- D7 due/NULL/non-UTC/needs_review cases and the full D5 pending/reciprocal successor visibility matrix.
- Context v1/v2 replay remains exact under its existing snapshot/Event validation, without requiring legacy KnowledgeItem content-hash recalculation; new Context v3 records origin/current IDs and the v2 hash scheme.
- Operator approval, TaskRuntime admission/finalization, idempotency and recovery continue to accept create only and reject every not-yet-authorized lifecycle operation.

**Step 9 — Exact-head verification and B2 exit gate**

1. Run focused hash, migration, Team Experience, retrieval, Context, Operator adapter, LearningCommit, and TaskRuntime tests.
2. Against disposable PostgreSQL, upgrade from the merged `0015_r7b_history` head to the single new head; verify old rows, stale gating, republish, and rollback behavior.
3. Run Ruff, Mypy, the full test suite, `git diff --check`, and hosted CI on the exact final PR head. Record local operator evidence separately from hosted CI.
4. Review the changed-file list and PR diff: only the B2 hash/projection/consumer/Context/approval-guard scope is allowed. Confirm no B3 assessment models/Tasks, B4 revise/revalidate writes, B5 create-with-successor/supersede/retire writes, or R7-C work slipped in.

### B2 acceptance criteria

- V2 hash follows the exact ADR field list, separator, normalization, and serialization. Historical projection rows carry `legacy-opaque`, remain stale and cannot be retrieved before v2 republish; no legacy projection-hash verifier is assumed.
- Revalidation-only lifecycle metadata changes do not affect v2 content hash; confidence changes do.
- Existing projection rows are explicitly legacy and stale, are never treated as v2, and cannot be retrieved before republishing.
- New chunks and index-state records pin the exact current LearningChange ID and hash scheme; publication is atomic and rechecks canonical state.
- Indexing, retrieval, and Context assembly validate the B1 current-pointer chain, policy/Team provenance, D7 eligibility, and D5 reciprocal visibility.
- New Context uses manifest v3; historical v1/v2 replay is immutable and unchanged.
- The approval path remains create-only; all later lifecycle operations remain rejected.
- Fresh migration, focused regressions, Ruff, Mypy, full suite, diff check, and exact-head hosted CI pass.

### B2 stop conditions and explicit non-goals

Stop and report a design discrepancy before implementing a workaround if: any historical projection might remain retrievable after migration; current-pointer history cannot be proven; D5 reciprocity cannot be checked against a consistent snapshot; Context v1/v2 replay changes; or the create-only approval boundary cannot be preserved.

B2 does **not** implement KnowledgeRevalidationAssessment or KnowledgeLifecycleAssessment (B3); revise/revalidate writes (B4); candidate creation, supersede, or retire writes (B5); repeated legacy lifecycle hardening assigned to B6; TaskKnowledgeReference/KnowledgeUseAssessment or retrieval benchmarking (R7-C); a new runtime, dispatcher, scheduler, public API/auth stack, production evaluator/provider, or second commit path.

**B2 exit:** the full B2 acceptance matrix is green on the exact PR head, no stop condition is open, the implementation and verification record is synchronized, and the Operator explicitly accepts the B2 exit. B3 remains separately gated.



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
