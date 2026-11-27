# RW4-1B — Current physical-design and proof review

**Status:** Read-only source/design review completed on 2026-11-27. The existing physical design remains a proposal; this review does not accept exact DDL, close F1–F4, authorize RW4-1 implementation, or enable any SignalDisposition writes.

**Baseline:** `main` at `3a1d897c989a181cfb7f4bf53e7766608dbd8578` (PR #219 merge). Hosted post-merge CI run [#2368](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/46010744787) passed role provisioning, migration as the dedicated migrator, Alembic head verification, Ruff, Mypy, and the full test suite.

**Reviewed sources:** RW4-1A source audit; RW4-1B physical design proposal; RW4-2 Stage A closure; `core/ingestion.py`, `core/task_runtime.py`, `core/models.py`, `core/knowledge_index.py`, `core/objectives.py`, `core/update_thread_context.py`, `core/world_memory.py`, `core/operator_application.py`; migrations `0017`, `0019`, `0020`; `migrations/env.py`; role bootstrap, role tests, CI workflow, Compose, disposable runner, and embedding smoke utility.

## 1. Sequenced review and closure work

| Step | Work | Acceptance / output | Current result |
|---|---|---|---|
| 1 | Pin the review baseline and migration head. Compare the old RW4-1A/1B source baselines with current `main`; inspect the actual Alembic chain. | Current commit and migration head recorded; old audit claims labelled historical. | **Done.** Current review baseline is PR #219 merge `3a1d897c...`; migration `0020_rw4_task_identity` follows `0019_rw1_world_memory`. |
| 2 | Reconcile role/credential evidence. Inspect provisioning, migration identity, role memberships, effective grants, CI setup, and runtime DSN consumers. | Separate bootstrap, owner, migrator, and runtime facts; identify what the role tests actually prove. | **Done.** Bootstrap/owner/migrator/read-only-runtime roles and CI proof exist; no host consumes runtime. |
| 3 | Re-audit intake provenance. Trace the Task → Team → Signal → Event path and each Signal reuse/replay branch. | Verify compatible lock modes and identify which Event records can become DB-attested provenance. | **Done at source level.** Existing ingestion locks Task `FOR UPDATE`, Team `FOR SHARE`; a new Event trigger can add Signal `FOR SHARE` without Team lock upgrade. The three existing-Signal reuse paths still need explicit fail-closed eligibility proof. |
| 4 | Review relational representation. Check row shape, D5.2 reference matrix, D5.3 reasons, unique pair, composite FKs, identity version, and FK-supporting indexes. | Exact PostgreSQL DDL and ORM mapping ready for independent review. | **Partially specified.** Logical shape and constraint/index names exist; exact SQL expressions, timestamp enforcement, ownership, and final migration code are not frozen. |
| 5 | Review provenance/immutability cutover. Check forward-only marker semantics, Event/Signal/Task/Team protected fields, TRUNCATE/CASCADE/partition controls, and migration rollback. | Exact trigger functions, grants, ACCESS EXCLUSIVE NOWAIT lock protocol, and PostgreSQL test cases. | **Design only.** No RW4-1 marker column or guard triggers exist. |
| 6 | Review Thread-domain and ORM freshness protocol. Check F3 trigger snapshot semantics, lock order, and F4 refresh behavior. | Two-session match-first/domain-first proof and stale-identity-map proof. | **Design only.** No Thread.domain guard or triage finalizer refresh implementation exists. |
| 7 | Review TaskRuntime atomicity and receipt dependency. Preserve one TaskRuntime owner, the separate D4.2 receipt transaction, atomic disposition/Outcome/Task/Event business finalization, and read-only replay. | Explicit dependency map; no duplicate lifecycle/replay authority. | **Contract specified; not implemented.** D4.2 receipt schema/recovery/fingerprint gates remain RW4-3 prerequisites. |
| 8 | Reconcile proof matrix and status documents. Distinguish current CI role proof from future RW4-1 PostgreSQL proofs and update current status authority. | No stale claims; explicit blockers and authorization boundary. | **This PR's documentation reconciliation.** |
| 9 | Independent review and Operator disposition. | Accept or revise physical design; only then request separate RW4-1 implementation authorization. | **Pending.** No implementation authorization is inferred. |

## 2. Current source findings

### 2.1 Role separation: partially delivered, not a working application runtime

Current repository evidence:

- `scripts/provision_database_roles.py` creates `watch_owner` (NOLOGIN), `watch_migrator` (LOGIN/NOINHERIT), and `watch_runtime` (LOGIN) on a fresh disposable database. It refuses the persistent database name `watch`, pre-existing cluster-global Watch roles, and a non-empty public schema.
- The ordinary online Alembic CLI path in `migrations/env.py` requires `session_user = 'watch_migrator'`, executes `SET ROLE watch_owner`, and verifies `current_user = 'watch_owner'`.
- CI provisions roles before running migrations. Run #2368 passed that path and the full suite on the exact merge commit.
- `tests/test_database_roles.py` checks role attributes/memberships, schema/database/table/sequence privileges, runtime login, and that the runtime cannot UPDATE/DELETE/TRUNCATE, create schema objects, SET ROLE owner, disable triggers, or set replication-role bypass.
- `watch_runtime` is intentionally SELECT-only. The tests do not prove the future application DML grant matrix or any RW4-1 trigger behavior.
- No checked-in host composition or runtime DSN consumer exists. The local Compose `watch` bootstrap remains a superuser and is not an application identity.
- The supplied-connection Alembic path bypasses the CLI identity assertion, but repository search found its use only in migration tests using an isolated administrative test connection. Keep that path test-only and documented.

**Disposition:** F1 is partially delivered. Do not mark it closed until the exact RW4-1 owner/runtime grants, trigger behavior, and runtime positive/negative DML proofs are implemented and run using distinct connections.

### 2.2 Local verification tooling has a migration-identity mismatch

Two stale developer instructions were found:

1. The pre-correction `scripts/test-disposable-postgres.ps1` used the bootstrap URL as `DATABASE_URL`, which the current Alembic CLI rejects because it requires `session_user = 'watch_migrator'`. The correction in this follow-up changes the runner to provision roles, use a migrator URL for `DATABASE_URL`, retain the administrative URL for `TEST_DATABASE_URL`, and restore all environment variables it changes.
2. The `core/embedding_smoke.py` usage docstring previously instructed users to set `DATABASE_URL = TEST_DATABASE_URL` with the bootstrap login. The correction in this follow-up documents the same fresh-database role bootstrap/migrator split used by CI.

**Verification status:** the source correction is included in this follow-up branch. It has not yet been executed on Windows; hosted Linux CI does not validate PowerShell runtime behavior. Do not mark local disposable verification complete until the script is run on Windows and its migration, test, cleanup, and environment-restoration results are recorded. Keep this tooling correction separate from production RW4-1 code.

### 2.3 Intake provenance and ingestion lock compatibility

Current `IngestionService._commit` locks the Task `FOR UPDATE`, then the Team `FOR SHARE`. For a new Signal it inserts the Signal and then the `signal_ingested` Event in the same transaction. Existing-Signal and ON CONFLICT winner paths write `fetch_no_change`; same-Task `prior_outcome` replay writes no new Event.

The proposed Event trigger's Task `FOR SHARE` → Team `FOR SHARE` → Signal `FOR SHARE` sequence is compatible with the existing Task/Team locks: reacquiring a weaker compatible lock held by the same transaction does not upgrade the Team lock. It must not request Team `FOR NO KEY UPDATE`, which would introduce SHARE-to-NO-KEY-UPDATE upgrade deadlock risk under concurrent same-Team ingestion.

Eligibility must distinguish:
- New post-cutover intake Events validated by the DB trigger and stamped with the marker.
- All pre-cutover Events, which remain NULL/untrusted and are never backfilled or retroactively attested.
- Same-Task replay of a legacy ingestion result, which may return its historical result but must not manufacture a marker or qualify the Signal for triage.
- The ordinary `fetch_no_change` path, ON CONFLICT winner path, and `prior_outcome` replay path, all of which require explicit cross-domain fail-closed eligibility proof.

The trigger can validate newly inserted Events and the referenced immutable fields. It cannot retroactively repair or validate legacy history. D4.1a Team/hash canonical arbitration remains separate; origin/hash uniqueness and application timestamps do not prove the first successfully committed Team/hash winner.

### 2.4 Relational integrity and TaskRuntime

The proposed row shape correctly separates:
- row-local D5.2 checks and D5.3 reason vocabulary;
- Team/Signal FKs;
- composite Thread/Team ownership;
- later D2-dependent Task/Team/Signal/identity-version composite FK;
- trusted-application checks for same-domain, active-at-decision, canonical provenance, and TaskRuntime transaction ownership.

The D2 migration `0020_rw4_task_identity` is already merged. The SignalDisposition composite Task FK remains a later, separately locked/preflighted migration. Runtime disposition INSERT must remain withheld until that FK is installed and verified.

TaskRuntime currently owns terminal Task/Outcome/Event commit, but has no triage-specific disposition seam or strict triage replay. The accepted D4.2 design adds a separately committed durable assessment receipt before business finalization. RW4-1 must not collapse that receipt into the disposition transaction or invent a second Outcome/replay system. The business disposition, Task execution Outcome, terminal Task state/time, and `task_completed` Event must remain one atomic TaskRuntime-owned transaction.

### 2.5 Thread-domain guard and ORM freshness

The F3 proposal is appropriately narrow: actual `Thread.domain` changes are rejected only after a matched disposition references the Thread; no-op domain assignments and later valid status transitions remain allowed. The guard must query matched references after PostgreSQL has locked the Thread row and must prove READ COMMITTED/volatile-trigger visibility after a concurrent wait.

The F4 rule is also necessary: SQLAlchemy row locking does not refresh stale identity-map scalar attributes. The eventual finalizer must re-select with `populate_existing=True` or call `Session.refresh()` after acquiring the Thread lock, then validate status/domain/Team/profile values in that same transaction.

Neither guard nor finalizer refresh exists today. Both require real two-session PostgreSQL/SQLAlchemy proof.

## 3. Blocking findings and disposition

| ID | Finding | Current status | Required closure |
|---|---|---|---|
| F1 | Role/owner boundary | **Partially delivered; open** | Extend current bootstrap to the RW4-1 protected-object/runtime DML contract; prove trigger behavior and effective privileges using actual runtime/migrator identities. |
| F2 | Thread writer ownership | **Open / blocking** | No host/runtime consumer or supported Thread lifecycle writer is implemented. Reconcile local untracked writers/credentials and implement the accepted Watch-owned writer path before write enablement. |
| F3 | Thread.domain DB guard | **Design only** | Exact trigger/function DDL and match-first/domain-first/no-op/non-matched PostgreSQL tests. |
| F4 | ORM locked-row freshness | **Design only** | Implement locked-row refresh and stale-identity-map two-session tests. |
| P1 | Local verification runner | **Code correction included in follow-up; Windows verification pending** | Execute the corrected PowerShell runner on Windows; verify role bootstrap, migrator CLI, admin test URL, full suite, cleanup, and exact environment restoration. |
| P2 | Exact physical DDL | **Not frozen** | Freeze exact CHECK expressions, FK actions, index predicates, timestamp assignment, trigger SQL, ownership/grants, and forward-only downgrade refusal. |
| P3 | All-outcome write gate | **Closed by accepted decision** | Keep matched/duplicate/deferred all disabled until every Decision 7 prerequisite is implemented and independently verified. |
| P4 | D4.1a / D4.2 / RW-5 dependencies | **Separate workstreams** | Do not implement them inside RW4-1; preserve their accepted sequencing and gates. |

## 4. Recommended implementation sequence after design acceptance

This is a proposed order, not an authorization:

1. **Tooling compatibility correction:** source correction is now prepared in the follow-up branch; run it on Windows and verify role bootstrap, migrator CLI, admin test URL, environment restoration, and the full disposable PostgreSQL suite before closing P1.
2. **Exact DDL freeze:** finalize table columns/types/defaults, row CHECKs, FKs/actions, minimal indexes, timestamp trigger/default, ownership, and downgrade refusal.
3. **Role/trigger cutover design:** freeze exact SECURITY DEFINER functions, safe search_path, PUBLIC EXECUTE revocation, protected-field guards, marker assignment, TRUNCATE/CASCADE/partition denial, and the role/connection cutover runbook.
4. **Migration proof design:** preserve the single ordered `LOCK TABLE tasks, teams, signals, events, threads IN ACCESS EXCLUSIVE MODE NOWAIT` statement; prove migration-first blocking, reader/writer-first immediate abort/retry, transactional rollback, and unchanged NULL legacy Events.
5. **Thread guard/ORM design:** freeze F3 trigger semantics and F4 refresh code location; include both race orders and no-op/status/replay cases.
6. **TaskRuntime integration design:** freeze the typed observation, exact terminal Event, one disposition/Outcome atomic transaction, strict read-only replay, and the D4.2 receipt/stale-receipt boundary without adding generic callbacks.
7. **Independent physical-design review:** resolve every P1/P2/F1–F4 finding and reconcile current status documents.
8. **Separate implementation authorization:** request RW4-1 implementation approval only after design acceptance. Do not infer it from this review.

## 5. Explicit boundaries

- No SignalDisposition ORM/table/migration/service or TaskRuntime code is implemented by this review.
- No D2 migration changes; the merged D2 schema remains unchanged.
- No D2-dependent SignalDisposition composite-FK migration is implemented.
- No D4.1a Team/hash arbitration, D4.2 receipt/matcher, RW-5 helper/revision/writer retrofit, RW4-2 Stage B creator, RW4-3 matching, RW4-4 Context, or RW4-5 reactivation is implemented.
- No live or persistent database was accessed. The CI evidence is for an ephemeral PostgreSQL service only.
- No disposition outcome or runtime write is enabled. Decision 7 remains binding.
- RW4-1 implementation still requires independent design acceptance and separate explicit Operator authorization.

