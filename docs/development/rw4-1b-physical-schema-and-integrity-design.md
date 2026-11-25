# RW4-1B — SignalDisposition physical schema and relational-integrity design

**Status:** Proposed design for review; no physical design decisions accepted by this document.  
**Depends on:** accepted D3-A/B/C, D5.1–D5.4, D6.1–D6.6; completed RW4-1A source audit.  
**Design baseline:** RW4-1A audited main baseline d2a6f7d4f939a7c18ea00ad6c77574c7b1f63ec3; implementation must re-audit the actual merge base and current Alembic head.  
**Scope:** SignalDisposition row representation, database constraints, cross-record integrity strategy, immutable evidence, TaskRuntime transaction/replay seam, migration boundary, and a bounded PostgreSQL proof matrix.  
**Not in scope:** code, ORM, migration, SQL, test implementation, database execution, Task creation/dispatch, D2 Task identity migration, D4.1a canonical Team/hash arbitration, RW-5 locks/revision/writer retrofit, RW4-2 Stage B, RW4-3 matching, or RW4-5 reactivation.  
**Authorization:** This proposal does not authorize implementation.

## 1. Purpose and design rule

RW4-1 persists one immutable business disposition for a Team's intake of a Signal. It must not turn the global Signal model into a Team-owned record, infer canonical first-commit order from application timestamps, weaken accepted Task identity, or create a second Task lifecycle authority.

The physical design must distinguish row-local facts enforceable by PostgreSQL constraints, cross-record facts requiring a relational witness/trigger or transaction validation with a proved lock/isolation protocol, independent prerequisites that RW4-1 must not reimplement, and terminal atomicity owned by TaskRuntime.

The preferred solution is the smallest design that proves the accepted invariants. Do not add a generic integrity framework or a new TeamSignal registry merely to avoid specifying the actual relationship.

## 2. Accepted contract to preserve

- Exactly three dispositions: matched, duplicate, deferred.
- D5.2 reference matrix:
  - matched: thread_id required; duplicate_of_signal_id and reason_code NULL.
  - duplicate: duplicate_of_signal_id required; thread_id and reason_code NULL.
  - deferred: reason_code required; thread_id and duplicate_of_signal_id NULL.
  - decided_by_task_id required for all.
- Six accepted deferred reason codes only. Use the exact D5.3 vocabulary from the accepted specification; do not create aliases or add a seventh reason.
- One immutable disposition per Team/Signal pair.
- Deferred is a successful terminal business result; TaskRuntime completes the Task as done.
- Disposition, Task attribution/reason, one task_execution Outcome, Task terminal state/completion time, and one task_completed Event commit or roll back together.
- TaskRuntime alone owns Task lifecycle and terminal Event writes.
- Human-readable explanation and complete terminal result belong in immutable Task-attributed observation/Outcome evidence. The disposition row stores the stable machine-readable reason code. Outcome fields must agree exactly with the persisted disposition value, reason, and reference.
- Technical/integrity failures do not create a disposition.
- Dormant Thread matching does not reactivate in RW4-1. Until separately authorized and proven RW4-5, dormant would-be winner remains deferred with dormant_thread_requires_reactivation.
- No Signal status, Signal Team column, Thread timestamp mutation, new Thread, new Task creator, or TaskDispatcher expansion.

## 3. Proposed row shape

Recommended logical row (names illustrative until review):

| Column | Type / nullability | Purpose |
|---|---|---|
| id | UUID primary key | Stable disposition record identity. |
| team_id | UUID NOT NULL | Team whose intake is being decided. |
| signal_id | UUID NOT NULL | Global Signal being decided. |
| disposition | text/enum NOT NULL | One of the three accepted values. |
| thread_id | UUID NULL | Required only for matched. |
| duplicate_of_signal_id | UUID NULL | Required only for duplicate. |
| reason_code | text NULL | Required only for deferred; exact D5.3 values. |
| decided_by_task_id | UUID NOT NULL | Canonical triage Task attribution. |
| created_at | timestamptz NOT NULL | Database-assigned immutable creation timestamp. |

Recommended row-level constraints:

- Unique (team_id, signal_id).
- CHECK for the exact three disposition values.
- CHECK for the complete D5.2 nullability/reference matrix.
- CHECK rejecting duplicate_of_signal_id = signal_id.
- CHECK restricting deferred reason to the six accepted D5.3 codes and requiring NULL otherwise.
- FK team_id → teams.id.
- FK signal_id → signals.id; FK duplicate_of_signal_id → signals.id.
- Composite FK (thread_id, team_id) → threads(id, team_id).
- Composite FK (decided_by_task_id, team_id) → tasks(id, team_id).
- Restrictive delete behavior; no cascade deletion of immutable decision history.
- No updated_at.

The unique pair enforces at most one row per Team/Signal. A same Signal may have separate rows for different Teams. A FK to Signal alone proves existence only; it does not prove Team intake provenance, domain equality, or duplicate canonicality.

### 3.1 Deferred vocabulary source

The migration and tests must use the exact six accepted D5.3 reason codes from the accepted RW4-2 specification/decision record. This proposal intentionally does not restate or paraphrase their identifiers: a copied or stale list would create a second vocabulary authority. Before implementation, the physical design review must verify the exact literal set against the normative source and record it in the migration/test plan.

## 4. Cross-record integrity: options and recommendation

The hard relationships are: Team has an intake association to Signal; Signal and Team domains agree; matched Thread belongs to the same Team/domain and is eligible; duplicate target is the canonical same-Team/same-hash Signal; attributed Task is the canonical triage Task for this Signal.

### Option A — transaction validation against existing records

The TaskRuntime-owned persistence operation validates the existing Event/Task/Signal/Thread rows in the same transaction. It uses a defined lock order and isolation level, and revalidates all facts immediately before insert/terminal commit.

**Advantages:** smallest schema; no new ownership registry; keeps RW4-1 focused.

**Risks:** the existing Event payload is JSONB and does not have a typed Signal FK; Event mutability/deletion behavior and all concurrent writers must be audited. Without stable locks or immutable witness rows, a validation query can race with provenance changes. The accepted RW-5 canonical Team lock helper is not yet implemented, so RW4-1 cannot claim that protocol.

### Option B — relational intake-witness representation

Add typed relational columns or a dedicated Team/Signal intake-witness table with enforceable keys, populated by ingestion. This could make Team/Signal provenance and domain ownership more directly relational.

**Advantages:** stronger ordinary FK composition and queryability.

**Risks:** changes ingestion writes and schema, overlaps D4.1a canonical Team/hash arbitration, requires a migration and compatibility retrofit, and risks making a second source of truth for intake association. It is broader than a disposition-only slice.

### Recommendation — Option A only if race proof is real; otherwise stop and re-scope

Prefer Option A only if the design can prove that the existing Event witness is immutable/stable for the lifetime of the disposition and that all mutable referenced rows are protected against concurrent change under a concrete PostgreSQL lock/isolation protocol. The design must name the exact rows read/locked, lock modes, order, isolation level, and writers that can mutate/delete them.

If the current Event/Task/Signal model cannot provide that guarantee, do not paper over it with application validation. Return to review with a narrowly scoped relational-witness proposal and explicit sequencing impact. Do not silently implement Option B inside RW4-1.

For either option:
- Require the intake Event to be one of the accepted types and Task-attributed to the same Team.
- Validate Event Signal ID, origin, source type, content hash, and Snapshot reference against the persisted Signal and Snapshot provenance.
- Validate Signal.domain == Team.domain.
- Validate Thread.team_id == team_id, Thread.domain == Team.domain, and the status rule at commit. Active Thread is eligible; dormant can only be matched with the separately gated RW4-5 atomic reactivation path; resolved is ineligible.
- Do not accept caller-supplied provenance assertions.

## 5. Keep D4.1a duplicate canonicality outside this slice

A duplicate disposition requires more than a valid Signal FK and matching hash. It must point to the first successfully committed Signal for the same Team and exact raw content hash, regardless of origin.

The current Event timestamps, fetched_at, UUID order, and (origin_url, content_hash) uniqueness do not establish that winner.

Recommendation:
- Keep the duplicate_of_signal_id column and row constraint in the proposed shape.
- Do not enable duplicate disposition writes until D4.1a's separately reviewed database arbitration/stable-association mechanism and two-session PostgreSQL proof are complete.
- RW4-1 design must state this dependency explicitly. Do not create a partial canonical-hash registry, second winner algorithm, or surrogate timestamp ordering in this migration.
- The RW4-1 schema may reference the eventual canonical witness only if that dependency's exact interface is already accepted; otherwise keep canonical validation outside the frozen DDL and block duplicate execution.

## 6. Keep D2 Task identity outside this migration

The current Task schema lacks persisted signal_id and identity_version. The accepted D2 contract requires both plus unique (team_id, signal_id, identity_version), and recomputation of the canonical UUIDv5 Task ID from persisted request data.

A composite FK to (tasks.id, tasks.team_id) proves same-Team Task ownership, not that this is the canonical Task for this Signal.

Recommendation:
- Do not add D2 columns/indexes in the RW4-1 migration.
- Do not weaken Task attribution to caller-provided IDs or a task-type-only check.
- Make the D2 Task identity migration a hard prerequisite for disposition writes unless a reviewed, equally strong persisted identity proof exists beforehand.
- At disposition insert and replay, recompute and verify canonical Task ID, Team, Signal, operation, identity version, and exactly-one valid request Event from persisted data.
- If this requires D2 fields, RW4-1 disposition writes must wait for that migration to land. This creates a sequencing question because the accepted serial plan places RW4-1 before RW-5 and RW4-2 Stage B, while the D2 Task identity migration has not yet been implemented. This proposal does not reorder those slices. The Operator must decide whether to schedule the already-accepted D2 migration as a narrowly bounded prerequisite before enabling RW4-1 writes, or accept a separately reviewed transitional proof that is equally strong without those fields. Do not proceed on an assumed workaround.

## 7. Immutability and timestamp

**Recommended immutability:** a narrow PostgreSQL trigger that rejects UPDATE and DELETE on the disposition table. A role/privilege solution is acceptable only if the actual production runtime role model is inspected and shown to prevent mutation by every supported writer. Do not assume that model.

**Recommended timestamp:** created_at TIMESTAMPTZ NOT NULL with a PostgreSQL-controlled insertion-time assignment using clock_timestamp(). A DEFAULT alone is insufficient because a caller can explicitly supply a value; use an insert trigger that overwrites the supplied value or a proven column-privilege boundary. The exact mechanism and repository convention must be confirmed during design review. This records database insertion time, not commit order. It is not the D2 immutable Task as_of, the D4.1a first-commit arbitration key, or the RW-5 Team revision watermark.

No cascading deletes. If a referenced Signal, Team, Thread, or Task is subject to deletion, restrictive FK behavior should prevent destroying immutable disposition history. Verify the actual deletion policies and migration conventions before freezing the exact FK actions.

## 8. TaskRuntime integration proposal

Do not open a second transaction and do not add a generic callback framework.

Proposed narrow flow inside existing TaskRuntime.finalize transaction:

1. Lock and validate the Task/attempt using the existing TaskRuntime path.
2. For a triage success only, validate canonical Task identity and the exactly-one request Event.
3. Validate persisted Signal/Team intake provenance and domain; validate the selected Thread or duplicate reference according to the outcome.
4. Insert the disposition row using the active Session, or on committed replay load and validate the exact existing disposition.
5. Build/validate the typed terminal observation and task_execution Outcome so disposition value, reason code, reference, and human explanation agree.
6. Insert exactly one task_completed Event and set Task done plus completed_at.
7. Commit all database writes together.

Technical failure before successful disposition validation produces no disposition and follows existing TaskRuntime retry/recovery/failure semantics. Deferred is a successful business outcome, not a technical failure.

Replay must validate the complete bundle: canonical Task/request Event, disposition row, Task-attributed observation/Outcome, terminal Event, Task status, and completion timestamp. Exact replay is read-only. Any mismatch fails closed; do not repair, synthesize, overwrite, or create replacement history.

The immutable observation Snapshot is stored outside PostgreSQL as in current TaskRuntime. A failed DB transaction may leave an unreferenced immutable file; no disposition, Outcome, terminal Event, or terminal Task state may survive independently.

## 9. Migration boundary

- The migration must follow the actual Alembic head on its implementation base; the audit's 0019 head is a historical source observation, not a promise that no later migration exists.
- One linear Alembic head only. No historical migration edits.
- Transactional DDL; no concurrent index build unless the repository's migration/rollback contract is explicitly redesigned.
- Fresh install, upgrade from current head, downgrade policy, injected failure rollback, and post-migration schema inspection are part of proof.
- No data backfill is expected from the source audit; no deployed database rows were inspected. Recheck live schema/data assumptions in the implementation preflight.
- Do not combine with D2 Task identity, D4.1a canonical association, RW-5 Team revision/lock helper, or RW4-5 Thread reactivation migrations.

## 10. Bounded PostgreSQL proof matrix

| Proof group | Required cases | Expected result |
|---|---|---|
| Migration | Fresh disposable DB; upgrade from current head; one head/current; injected DDL failure | Correct schema; rollback leaves no partial objects; linear history. |
| Row checks | Every valid D5 matrix row; every invalid/null combination; unknown disposition/reason; self-duplicate | Valid rows accepted; invalid rows rejected by PostgreSQL. |
| Uniqueness | Same Team/Signal twice; same Signal in two Teams; concurrent same-pair insert | One row per pair; cross-Team rows independent; exactly one concurrent winner. |
| FK ownership | Missing Signal/Team/Thread/Task; cross-Team Thread/Task | FK rejection; no cascading history deletion. |
| Provenance | Missing/malformed intake Event; wrong Task Team; Signal/Snapshot/hash mismatch; domain mismatch | Fail closed; no disposition. |
| Ingestion reuse regression | fetch_no_change, ON CONFLICT winner, and prior_outcome replay with cross-domain Signal reuse | All three rejected for RW4-1 eligibility; ingestion correction, if any, remains separately scoped. |
| Thread | Wrong Team/domain; resolved; active; dormant without RW4-5 | Invalid candidates rejected; active allowed; dormant defers without reactivation. |
| Duplicate | Cross-Team target; different hash; noncanonical target; same hash but D4.1a winner unavailable | No duplicate disposition until canonical proof is available. |
| Task identity | Wrong Task type/Team/Signal/identity; malformed or duplicate request Event; canonical UUID mismatch | Fail closed; D2 migration is prerequisite for persisted identity check. |
| Immutability | UPDATE and DELETE under actual runtime role; privileged path if applicable | Mutation rejected by selected DB enforcement. |
| Timestamp | Omitted timestamp; explicit caller timestamp; repeat read | PostgreSQL assigns stable timestamp; caller-supplied value is ignored/rejected by the selected enforcement mechanism. |
| Atomic success | Matched and deferred paths; duplicate only after D4.1a gate | Disposition + Outcome + Task + terminal Event commit together. |
| Atomic rollback | Inject failure after disposition insert and before Outcome/Event/Task terminalization | No DB row from terminal bundle survives. |
| Replay | Exact replay; corrupt/missing disposition; corrupt Outcome/Event/Task state | Exact replay read-only; inconsistency fails closed. |
| Concurrency | Concurrent disposition inserts and relevant provenance mutation race | Unique winner; no stale/mismatched provenance commit. Use real PostgreSQL sessions. |
| Boundaries | No Signal/Thread/EvidenceLink mutation; no new Task/dispatcher path; no RW-5/RW4-5 behavior | No out-of-scope writes. |

All constraint, concurrency, lock, trigger, and transaction claims require disposable PostgreSQL. SQLite/in-memory substitutes are not accepted for those proofs. Record PostgreSQL version, Alembic head, exact tested SHA, isolation level, session count, and observed blocking/commit outcomes.

## 11. Decisions requested from the Operator

This proposal intentionally separates recommendations from accepted decisions. Review the following:

1. Row shape: accept or amend the proposed one-row-per-(team_id, signal_id) shape and D5.2 reference matrix.
2. Cross-record enforcement: accept Option A only if its lock/isolation proof is feasible; otherwise authorize a separate relational-witness scope. Do not accept application validation without a concrete race proof.
3. Duplicate gate: accept that duplicate disposition writes remain disabled until D4.1a canonical arbitration is implemented and proven.
4. Task identity and sequencing gate: accept D2 migration as a hard prerequisite for disposition writes/replay, and decide whether its implementation must precede RW4-1 or whether a separately reviewed equivalent persisted proof is possible without reordering the accepted serial plan.
5. Immutability/timestamp: accept trigger-based UPDATE/DELETE rejection and database-assigned clock_timestamp(), subject to runtime-role and repository convention verification.
6. TaskRuntime seam: accept a narrow explicit triage-specific in-session finalization/replay path, with no generic callback abstraction.
7. Proof matrix: accept the bounded disposable-PostgreSQL cases in §10, with any additions/removals stated explicitly.

No response to this proposal is inferred. Until the Operator accepts the design and separately authorizes implementation, no ORM, SQL, migration, TaskRuntime, ingestion, or test changes may be made.

## 12. Explicit non-authorization

RW4-1B is a design proposal only. It does not authorize:
- SignalDisposition model/table/migration/service implementation;
- TaskRuntime or ingestion code changes;
- D2 Task identity migration;
- D4.1a canonical Team/hash arbitration;
- RW-5 locks, Team revision, decay, or writer retrofit;
- RW4-2 Stage B creator implementation;
- RW4-3 matching/commit;
- RW4-5 dormant Thread reactivation.
