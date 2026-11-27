# RW4-2 Stage A — Creator request contract and evidence closure

**Status:** Documentation-only closure proposal, 2026-11-27. D1 existing-writer centralization and D2 Task identity schema are implemented and merged. The request Event v1 schema and fingerprint are frozen here for independent review. The RW4-2 triage creator/replay implementation remains unimplemented and unauthorized. Stage A is not declared closed until this record and its cross-document reconciliation are independently reviewed and merged.

**Baseline:** `main` at `2430a1412f6ac5400ec191ae74396d92fab37c6d`.

## 1. Delivery status — separate implementation from creator capability

| Area | Delivered evidence | Current status | What it does not prove |
|---|---|---|---|
| D1 existing Task writers | PR [#207](https://github.com/abtn/Watch-Architecture-Rev2/pull/207) (including #208 correction), merge commit `d03297c2b4e3522b0dc59ce001955cda130fd14f`; exact D1 CI #2326 passed | Ten existing production Task producers delegate to eight named operations in `core/control_room.py`; caller-owned Session/transaction and existing authorization/replay behavior are preserved | Does not implement or authorize the new `triage_signal` creator |
| D2 canonical Task identity schema | PR [#203](https://github.com/abtn/Watch-Architecture-Rev2/pull/203), merge commit `5d3370127718cee839834b6473b8b5883be95d0b`; migration `0020_rw4_task_identity.py` | Nullable `signal_id`/`identity_version`, triage identity CHECK/FK/uniqueness, composite support key, partial request-Event unique index, Team-lock insert trigger, immutable identity, locked zero-history preflight and fail-closed downgrade are merged | Does not create triage Tasks, validate request payloads at runtime, prove creator replay, or prove creator race/retry behavior |
| RW4-2 creator contract | This document and the Stage A specification | Request Event v1 shape, semantic fingerprint, replay-equivalence, lock paths, and retry ownership are frozen for review | No runtime creator, adapter, TaskDispatcher path, or production authentication integration exists |
| Creator PostgreSQL proof | Future RW4-2 Stage B | Mandatory, not yet delivered | Migration tests and D1 writer tests are not substitutes for creator concurrency/replay tests |

D1's ten producers are the three OperatorApplication/adapter producers, PlanService source-Task materialization, four TaskRuntime follow-on producers, KnowledgeRevalidationService, and KnowledgeLifecycleAssessmentService. The exact named-operation mapping remains in [the D1 implementation record](d1-control-room-writer-conformance-implementation.md).

## 2. Immutable `triage_signal_requested` Event v1 schema

The request Event payload is a strict JSON object with **exactly** the following keys. No optional or extension keys are accepted in schema version 1.

| Field | JSON type | Canonical form and validation |
|---|---|---|
| `schema_version` | integer | Exactly `1`; booleans are not integers for validation purposes |
| `task_id` | string | Canonical lowercase hyphenated UUID; equals Event envelope `task_id` and Task primary key |
| `team_id` | string | Canonical lowercase hyphenated UUID; equals Task `team_id` and the authorized grant Team |
| `signal_id` | string | Canonical lowercase hyphenated UUID; equals Task `signal_id` and the canonical Signal ID |
| `signal_snapshot_ref` | string | Non-empty exact stored `Signal.snapshot_ref`; no path/URL normalization |
| `signal_content_hash` | string | Exact stored Signal hash using the repository's `sha256:<64 lowercase hex>` representation |
| `as_of` | string | PostgreSQL `clock_timestamp()` serialized as UTC RFC 3339 with exactly six fractional digits and `Z`, e.g. `2026-11-27T13:24:15.123456Z`; never caller-supplied or application-clock-derived |
| `team_revision_watermark` | integer | Non-negative integer; booleans, floats, strings, and null are rejected |
| `policy_version` | integer | Positive integer; equals the immutable Task policy pin and the selected greatest-version TeamPolicy on first creation |
| `matcher_id` | string | Non-empty exact copy of `matching_pins.matcher_id` |
| `matcher_version` | string | Non-empty exact copy of `matching_pins.matcher_version` |
| `embedding_space_key` | string | Non-empty exact copy of `matching_pins.embedding_space_key` |
| `chunking_version` | string | Non-empty exact copy of `matching_pins.chunking_version` |
| `requested_by_principal` | string | Exact canonical issuer/subject identity returned by the existing `canonical_operator_identity` rule: compact sorted-key JSON `{"iss": issuer, "sub": subject}`, UTF-8, no surrounding whitespace; maximum 255 characters; no credential/token |
| `request_fingerprint` | string | `sha256:<64 lowercase hex>`; recomputed from the semantic preimage below |
| `matching_pins` | object | Strict schema described below; no unknown keys |
| `matching_pins_hash` | string | `sha256:<64 lowercase hex>`; SHA-256 of canonical UTF-8 JSON bytes of `matching_pins` |

The Event envelope remains authoritative for Event ID, Event type, Task attribution, and Event creation timestamp. The Event type must be exactly `triage_signal_requested`; envelope Task attribution must equal payload `task_id`. If an existing Event serializer duplicates any envelope field into payload, the duplicate must equal the envelope exactly; it does not create a second source of truth.

### 2.1 Matching-pin object v1

The object has exactly five keys:

```json
{
  "schema_version": 1,
  "matcher_id": "non-empty immutable identifier",
  "matcher_version": "non-empty immutable version",
  "embedding_space_key": "non-empty immutable key",
  "chunking_version": "non-empty immutable version"
}
```

`schema_version` is integer `1`; the other four values are non-empty strings. Unknown or missing keys, wrong types, empty strings, and booleans in integer positions fail closed. The four top-level pin fields must exactly equal the corresponding values in this object. Actual v1 values remain deferred to D4b and must be selected using the accepted fixture, matcher, and query-plan evidence; this contract does not invent placeholder values.

### 2.2 Canonical JSON and hashes

Use the repository's established canonical JSON convention:

```python
json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
```

Encode the resulting string as UTF-8. Reject values outside the declared JSON schema before serialization; do not allow NaN/Infinity, floats, implicit coercion, or implementation-dependent object representations.

Both hashes use the lowercase hexadecimal SHA-256 digest prefixed with `sha256:`.

- `matching_pins_hash = "sha256:" + sha256(canonical_json(matching_pins).encode("utf-8")).hexdigest()`
- The request fingerprint is computed from this exact semantic preimage object, with no extra keys:

```json
{
  "domain": "watch.rw4.triage-signal-request.v1",
  "schema_version": 1,
  "operation": "triage_signal",
  "task_type": "triage_signal",
  "identity_version": "triage_identity_v1",
  "task_id": "<canonical UUID>",
  "team_id": "<canonical UUID>",
  "signal_id": "<canonical UUID>",
  "signal_snapshot_ref": "<exact stored snapshot reference>",
  "signal_content_hash": "sha256:<64 lowercase hex>",
  "policy_version": 1,
  "matching_pins": {
    "schema_version": 1,
    "matcher_id": "<exact immutable value>",
    "matcher_version": "<exact immutable value>",
    "embedding_space_key": "<exact immutable value>",
    "chunking_version": "<exact immutable value>"
  },
  "matching_pins_hash": "sha256:<64 lowercase hex>"
}
```

The fingerprint is `"sha256:" + sha256(canonical_json(preimage).encode("utf-8")).hexdigest()`. The `policy_version` shown as `1` is illustrative; the actual positive pinned version is used. UUID strings use canonical lowercase hyphenated form. The domain string and field names are fixed for v1; any semantic change requires an explicit request-schema version change and review, not an additive unknown key.

### 2.3 Replay equivalence and first-writer metadata

Replay equivalence is defined by the canonical Task identity plus the exact semantic preimage above. Therefore it includes Task/Team/Signal identity, identity version, Task type, snapshot reference, Signal content hash, policy version, and all matching pins.

The following are deliberately excluded from semantic equivalence and the request fingerprint:

- `requested_by_principal`: each replay caller is independently authorized; the first requester's attribution remains immutable and is returned unchanged.
- `as_of`: the first-writer PostgreSQL cutoff remains immutable and is returned unchanged.
- `team_revision_watermark`: the first-writer serialized cutoff remains immutable and is returned unchanged.

Exclusion from the fingerprint does **not** mean omission from validation. On every replay/load, validate the stored principal's canonical representation, the stored timestamp's exact format and UTC meaning, the non-negative watermark, the full payload shape, all Task/Event/envelope equality constraints, and both hashes. Never replace first-writer metadata with values from a later caller. A changed policy, snapshot/content identity, or matching pin under the same canonical Task identity is a conflict, not a second Task.

## 3. Lock, transaction, and retry ownership cross-check

The Stage A creator contract is aligned with [RW-5 shared contract §4.6](rw-5-shared-contract-proposal.md). The canonical RW-5 helper is the only supported lock implementation; RW4-2 must not introduce a temporary or bespoke helper.

| Path | Required order | Required behavior |
|---|---|---|
| Every invocation | Caller-owned active transaction; `SHOW transaction_isolation` before application-data reads/locks/writes | Require PostgreSQL READ COMMITTED exactly; reject REPEATABLE READ/SERIALIZABLE before probing Task existence |
| First creation | Non-locking Task-ID probe → Team `FOR NO KEY UPDATE` → protected Task recheck | If still absent, revalidate Team/Signal/source/current greatest-version policy/pins; capture `clock_timestamp()` and Team revision; insert Task and one request Event atomically |
| First-create race | Team lock → protected Task recheck finds winner | Return only typed retry-required; do not acquire Task after Team and do not disclose the winner in that transaction |
| Replay | Non-locking probe → Task `FOR UPDATE` → Team `FOR NO KEY UPDATE` → reload/validate | Reauthorize caller; require Team exactly active; validate canonical identity and complete stored Event; read-only replay of original Task/policy/cutoff/provenance |
| Final Task-PK conflict after protected recheck | No follow-up Task read under Team | Terminal protocol/integrity failure; not retryable and no request Event |

The Control Room operation receives the caller's active SQLAlchemy Session and does not create a Session, begin/commit/rollback the transaction, or retry internally. The **outer workflow/transaction owner** owns rollback and bounded reinvocation. Only the protected post-Team-lock recheck outcome is retryable: rollback the entire transaction and retry with a fresh Session/transaction, at most three total invocations. A third retry-required result is terminal retry exhaustion. The final Task-PK conflict is a distinct terminal integrity failure. Do not retry validation, authorization, inactive-Team, or semantic-pin conflicts.

The D2 migration trigger is a Team-lock participation guard for triage INSERTs. It does not authenticate, authorize, attest Control Room origin, validate request payloads, or make out-of-band SQL writers supported. The trusted-application-code boundary and operational exclusion of unsupported writers remain explicit. Do not grant broad Team UPDATE privileges merely to make the trigger lock work; any SECURITY DEFINER choice requires a separately reviewed owner/grant/search_path design.

## 4. Requirement-to-proof status

| Requirement | Status | Evidence / remaining proof |
|---|---|---|
| Ten existing Task producers delegate to Control Room | **Implemented** | PR #207/#208; D1 exact-head CI #2326; ten-producer matrix in D1 implementation record |
| D2 Task identity schema and migration preflight | **Implemented** | PR #203; migration `0020_rw4_task_identity.py`; migration/constraint/lock tests recorded in PR #203 |
| Request Event v1 field validation and fingerprint | **Specified; not implemented** | This document freezes the contract; Stage B must implement and test exact shape, canonical serialization, both hashes, and fail-closed malformed/unknown-field handling |
| Caller authorization before create and replay | **Specified; not implemented for triage creator** | Existing principal/grant pattern is precedent only; Stage B must test wrong/missing/multiple grants and prove no existence disclosure |
| First-create/replay lock paths and bounded retry owner | **Specified; not implemented for triage creator** | Stage B must use the canonical RW-5 helper and prove both paths on real PostgreSQL sessions |
| Creator exact replay, semantic conflict, and no duplicate request Event | **Not proven** | Stage B tests required; the migration partial unique index proves at-most-one only, not existence or payload validity |
| Creator concurrency, post-lock recheck, final-PK-conflict behavior, retry exhaustion | **Not proven** | Mandatory two-session PostgreSQL tests in Stage B hosted CI |
| D4b actual matching-pin values | **Deferred** | Must be selected/measured before RW4-3; no placeholders or `latest` aliases |
| Production host authentication/composition | **External prerequisite** | No production host composition root exists; required before production use |
| SignalDisposition persistence, matching, Context, decay, reactivation | **Out of this stage** | Remain in their separately sequenced and authorized slices |

## 5. Stage A exit and downstream gate

Stage A may be closed only after an independent review confirms that:

1. The ten-producer D1 inventory and merged D1 evidence are accurate.
2. D2 migration and schema claims match PR #203 and migration `0020`.
3. The Event payload schema, matching-pin object, canonical serializer, hash preimages, and replay-equivalence rules are internally consistent and contain no unspecified v1 fields.
4. The creator lock/retry contract agrees with RW-5 §4.6 and clearly assigns transaction rollback/retry to the outer owner.
5. Every requirement-to-proof row distinguishes delivered D1/D2 evidence from future creator proofs.
6. The affected status documents identify the current branch baseline and preserve the serial sequence.

After Stage A closure, the next serial implementation candidate is RW4-1 SignalDisposition persistence, but only after its physical design, cross-record integrity strategy, migration/preflight/rollback proof subset, independent review, and separate explicit implementation authorization. The following RW-5 helper/Team-revision/writer-retrofit slice also requires separate authorization and PostgreSQL interleaving proof before RW4-2 Stage B can be considered.

This document does not authorize RW4-1, RW-5, RW4-2 Stage B, RW4-3, RW4-4, RW4-5, production host integration, persistent-database operations, formal R8, or scored runs.
