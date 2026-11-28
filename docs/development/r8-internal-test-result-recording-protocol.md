# R8 internal technical-test result-recording protocol

**Status:** accepted recording protocol; documentation only. Merged by PR [#224](https://github.com/abtn/Watch-Architecture-Rev2/pull/224) at `6c9732b41f3a701ecb11ce2b4bbab7a6e40badc4`.
**Development state:** Pre-R8-ready.
**Applies to:** the selected initial technical internal-test scenarios CG-01 and C-01 only.
**Authority:** `PLAN.md` and [the initial internal-test scope and proof freeze](r8-ready-internal-test-scope-and-proof-freeze.md).
**Execution boundary:** this protocol does not authorize a new test run, exploratory campaign, added test, production capability, persistent database, live provider, scoring, treatment comparison, or R8-ready transition.

## 1. Purpose and governing rules

This protocol defines how a future, separately authorized CG-01 or C-01 execution is identified, observed, classified, preserved, and closed. Its purpose is to make a result reproducible and auditable without turning the internal-test harness into a production subsystem.

Non-negotiable rules:

1. Record CG-01 and C-01 as separate scenario runs. Never combine their outcomes into one pass rate or treat one as a substitute for the other.
2. Preserve the exact code baseline and inputs. A result belongs to one exact source SHA, fixture/input set, environment, and command.
3. Separate pre-existing CI evidence from a new Operator-authorized exploratory run. CI is not silently relabeled as an exploratory run.
4. Record expected and observed behavior, including negative assertions and absence/cardinality checks. A green process exit alone is insufficient.
5. A run cannot be marked PASS until all required observations are supported by evidence and disposable-environment cleanup is verified.
6. Preserve raw evidence and classify failures before attempting a correction. Do not overwrite a failed run with a later passing run.
7. Do not infer product value, causal impact, treatment superiority, retained-experience use, or R8 readiness from these technical scenarios.

## 2. Run identity and immutable baseline

Create one record per scenario execution.

### 2.1 Required identity fields

- **Run ID:** unique, immutable identifier. Recommended form: `R8IT-<SCENARIO>-<UTC timestamp>-<short sequence>`, for example `R8IT-CG01-20261128T153000Z-01`.
- **Generated identity manifest:** retain the single test-output line prefixed `R8_IDENTITY_MANIFEST=` from the selected CG-01 or C-01 test. The suffix is one JSON object containing generated fixture/business identities and the test's observed cardinality/checkpoint values. Preserve it verbatim in the raw log and extract it unchanged into the run evidence artifact.
- **Scenario:** exactly `CG-01` or `C-01`.
- **Run type:** `existing-ci-evidence`, `authorized-local-technical-run`, or `authorized-hosted-technical-run`.
- **Authorization reference:** explicit Operator decision or instruction authorizing this specific execution; use `not applicable — historical CI evidence` only for already-existing CI records.
- **Repository and source SHA:** full immutable commit SHA actually tested; record branch and whether the SHA was on main or a PR head.
- **Scenario/proof contract version:** exact commit or document revision containing the frozen scenario and expected-evidence definition.
- **Harness/test identity:** exact test node ID(s), fixture names, and test command.
- **Run start/end:** UTC timestamps; preserve local timezone only as supplementary metadata.
- **Attempt number:** retries are new records linked to the prior Run ID; never replace the first attempt.

### 2.2 Source and fixture pinning

Record enough information to reconstruct the inputs without relying on mutable external resources:

- Team, Thread, Task, Signal, Snapshot and other generated fixture identities, using test identifiers only.
- Fixture factory names and fixture configuration/version.
- TeamPolicy version and relevant policy pins.
- For C-01: configured source origin, exact synthetic response bytes or an immutable artifact reference, content hash, response metadata used by the fake fetcher, and deterministic fetcher configuration.
- Any deterministic seed, clock/time override, generated UUID strategy, and relevant environment flags.
- Migration revision/head and the exact schema state used.
- Dependency lockfile or environment image/container identity where available.

Do not record credentials, tokens, passwords, private keys, connection strings containing secrets, or unnecessary personal data. Redact secrets at collection time; preserve the unredacted original only in an approved secret store, never in the run report or ordinary CI artifacts.

If an input cannot be pinned or reconstructed, mark that limitation explicitly. Do not claim exact reproducibility.

## 3. Environment and execution record

Record the environment before and after execution:

- Operating system and version; Python version; package/environment manager and locked dependency state.
- PostgreSQL server version and disposable container/image identity.
- Database name or disposable instance identifier (not credentials).
- Effective database identities: `session_user` and `current_user` for relevant connections, and the role used for Alembic. Never infer the effective role from a DSN label.
- Alembic current revision and head revision after migration.
- Exact command, working directory, relevant non-secret environment configuration, exit code, start/end timestamps, and elapsed duration.
- CI provider, workflow/run number, job names, attempt, and exact tested SHA for hosted runs.
- Whether the test used the existing disposable PostgreSQL runner. SQLite or in-memory substitutes do not satisfy PostgreSQL-specific proof obligations.

For a bounded scenario run, the runner accepts pytest selectors through `-PytestArgs`; each invocation creates a fresh disposable PostgreSQL instance and executes only the selected pytest node(s) after provisioning and migration. Example commands are recorded in the execution proposal. Omitting `-PytestArgs` retains the existing full-suite behavior. The runner still performs Ruff and Mypy unless `-SkipStaticChecks` is explicitly supplied.

The existing local disposable runner's bootstrap identity is for container/database setup and role provisioning; Alembic runs as `watch_migrator`. `watch_runtime` remains read-only. Do not invent or assume a production DML identity for these in-process scenarios.

## 4. Expected-versus-observed evidence

For every assertion group, record:

| Field | Required content |
|---|---|
| Evidence ID | Stable identifier within the Run ID |
| Contract reference | Scenario section, proof-matrix row, or exact test assertion |
| Expected | Exact state, count, identity, or safe-failure behavior |
| Observed | Actual state/count/identity, including zero where zero is expected |
| Evidence locator | Test output, CI job/step, sanitized log, query result, or artifact path/URL |
| Result | `pass`, `fail`, `not-observed`, or `not-applicable` with reason |
| Notes | Qualification, anomaly, or reason the evidence is insufficient |

Do not replace a zero-count assertion with a statement such as "nothing unexpected happened." Record the queried entity, scope, time/transaction boundary, and exact count.

### 4.1 CG-01 minimum evidence groups

Record each independently:

1. Fixture preconditions: isolated Team, pre-existing active Thread, same-Team Signal/Snapshot and source-attribution Task, and exact authenticated principal/action grant.
2. No Team Experience / no TeamExperienceChunk before the operation.
3. Operator request Task creation through Control Room and the expected request Event.
4. Successful commit: one expected low-confidence Hypothesis and one exact Snapshot-backed EvidenceLink, with expected quote/hash/offset identity.
5. TaskRuntime terminal evidence: expected Outcome, terminal Task state, and exactly the expected completion Event cardinality.
6. Exact replay: same logical request/Task identity and no duplicate Hypothesis, EvidenceLink, ConfidenceChange, request/commit/completion Event, or other business write.
7. No TeamExperienceChunk after first success and after exact replay.
8. Required failure/rollback assertions only where the frozen CG-01 proof contract explicitly includes them; distinguish component-level tests from the integrated CG-01 test.

CG-01 uses fixture-seeded Signal/Snapshot and a pre-existing active Thread. It does not prove configured-source intake, Thread creation, retrieval/Context, retained-experience use, treatment, or scoring.

### 4.2 C-01 minimum evidence groups

Record each independently:

1. Frozen cardinality: one Team, one TeamPolicy version, one configured origin, one Objective, one accepted Strategy proposal, one Plan, one PlanAction, one materialized `ingest_source` Task, one Signal/Snapshot, one pre-existing active Thread, and one Operator update request.
2. Plan/PlanAction source and policy pins; source Task identity and Control Room creation evidence.
3. FakeFetcher invocation count exactly one; exact synthetic bytes/hash; explicit confirmation that no live network request occurred.
4. Signal/Snapshot provenance: bytes/hash, origin, source type, Team/policy attribution, and source Task linkage.
5. Source Task Outcome, terminal Task state, exactly expected completion Event, and the existing evaluation follow-on identity/type.
6. Authenticated Operator Task, low-confidence Hypothesis, and exact quote/offset/hash EvidenceLink derived from the ingested Snapshot.
7. Operator request/commit/completion Event cardinality and terminal Task evidence.
8. Exact replay: identity convergence and unchanged business-write/Event cardinalities; no duplicate source fetch or business writes where asserted by the frozen contract.
9. No TeamExperienceChunk before/after/replay and no retrieval/Context invocation.
10. Required safe-failure/rollback evidence from existing component proofs; do not imply that every failure injection was run end-to-end.

C-01 uses one configured source and deterministic fake bytes. It does not prove cross-origin canonicalization, live-provider behavior, Thread creation, retrieval/Context, retained-experience use, triage/disposition, treatment, or scoring.

## 5. Durable-state evidence and cardinality

Where the frozen scenario requires durable-state inspection, record read-only evidence from the disposable PostgreSQL database:

- Entity/table or approved read-only query purpose.
- Team/scenario scoping predicate and relevant identity keys.
- Expected and observed row counts and identifiers.
- Event types and cardinalities, linked to their Task identities.
- Task status, Outcome identity/status, and terminal timestamp where relevant.
- Signal/Snapshot provenance and content hash where relevant.
- Hypothesis/EvidenceLink identities and their source Snapshot/quote/hash/offset association.
- TeamExperienceChunk count at each required checkpoint.
- Replay before/after cardinality comparison.

Prefer a small, reviewed, deterministic query set. Preserve query text and sanitized result output. Do not modify rows manually to make a test pass. Do not use database superuser/owner access as a substitute for the role boundary being tested. If a read-only evidence query cannot be executed under the available authorized test boundary, record the gap rather than broadening grants.

## 6. Failure classification

Assign one primary class and optional secondary tags. Preserve the original failure and supporting evidence.

| Class | Meaning | Required response |
|---|---|---|
| **ASSERTION / BEHAVIOR** | Implemented behavior contradicts the frozen expected result | Preserve failing output and exact SHA; isolate the smallest failing assertion; propose a separately reviewed correction |
| **FIXTURE / INPUT** | Fixture, synthetic bytes, policy pin, identity, or setup is invalid or differs from the frozen contract | Preserve the malformed input and setup trace; correct the fixture in a new attempt without rewriting the failed record |
| **ENVIRONMENT / FLAKINESS** | Timing, scheduling, resource pressure, or host-specific instability affects the result | Preserve timings, host details, retry history, and evidence distinguishing flakiness from a deterministic defect |
| **INFRASTRUCTURE** | PostgreSQL/container/CI service, network between test components, or runner provisioning failed independently of scenario behavior | Preserve infrastructure logs and exact failure boundary; do not mark the scenario PASS |
| **AUTHORITY / SCOPE** | Execution attempted an unapproved operation, role, provider, persistent database, or scenario expansion | Stop immediately; do not retry until the missing authorization is explicitly resolved |
| **ARCHITECTURE / GATE** | Required behavior depends on an absent or unaccepted contract, writer, migration, retrieval consumer, or other gated capability | Stop and return the concrete dependency; do not weaken assertions or invent a workaround |
| **EVIDENCE / OBSERVABILITY** | The operation may have completed, but required durable state, cardinality, logs, or cleanup cannot be established | Result is inconclusive; add no capability merely to conceal the evidence gap |

A failure may have more than one cause. Record the primary classification, secondary tags, confidence, evidence, and unresolved questions. Do not label a failure "flaky" solely because a retry passes.

## 7. Run disposition

Use exactly one final disposition:

- **PASS:** all applicable frozen expected assertions pass; exact SHA and inputs are pinned; required durable-state evidence is present; no scope/authority violation occurred; and disposable-environment cleanup is verified.
- **FAIL:** a required expected behavior is contradicted by observed evidence.
- **INCONCLUSIVE:** evidence is missing/ambiguous, environment instability prevents a reliable conclusion, or a required observation could not be made.
- **BLOCKED:** a scope, authority, architecture, or predecessor gate prevents an authorized execution.
- **ABORTED:** execution was stopped before the required observation set was completed. Include the stop reason; do not convert to PASS.

A test process exit code of zero is necessary but not sufficient for PASS. Any missing required assertion, unverified cleanup, unpinned source/input, or unexplained cardinality discrepancy prevents PASS.

## 8. Logs, artifacts, and evidence integrity

For each run, preserve:

- Full raw test/CI logs and a sanitized human-readable excerpt.
- The exact `R8_IDENTITY_MANIFEST=` JSON line emitted by the selected scenario test; do not manually reconstruct or edit generated identifiers.
- Exact command and environment manifest.
- Source SHA, scenario contract version, fixture/input manifest, and migration revision.
- Expected/observed evidence table and read-only query outputs.
- Failure traceback and relevant PostgreSQL/runner diagnostics, if any.
- Cleanup record and final disposition.
- SHA-256 checksums for retained log/artifact files when practical.

Use immutable artifact names containing Run ID and evidence ID. Do not edit raw logs; create a separate sanitized copy and record what was redacted. Do not put secrets in artifacts. Avoid retaining unrelated user or environment data.

## 9. Cleanup and closure

A run cannot be PASS until cleanup is verified:

1. Capture the container's attached volume names before cleanup; remove the container with `docker rm -fv`; then verify the container is absent and every captured anonymous volume name is absent from `docker volume ls`.
2. Confirm temporary database artifacts and generated files are removed or deliberately retained as named, non-sensitive evidence artifacts.
3. Confirm test-created background processes are stopped.
4. Confirm environment variables and process-local configuration are restored to their exact pre-run set/unset/value state where the runner promises restoration.
5. Confirm no persistent database or external provider was contacted.
6. Record cleanup command/output, container identity, and any cleanup exception.

If cleanup cannot be verified, classify the run INCONCLUSIVE or ABORTED as appropriate and report the residual resource. Never claim cleanup merely because the test command ended.

## 10. Baseline preservation, retries, and corrections

- Keep the original failed/inconclusive record immutable.
- Every retry receives a new Run ID and points to `retry_of` / `supersedes_for_comparison` fields; do not erase the prior result.
- A code correction creates a new source SHA. Re-run only after the correction is reviewed and separately authorized.
- Compare results only when scenario contract, fixture/input manifest, environment assumptions, and assertion set are compatible. Explain every difference.
- If the frozen scenario or expected evidence changes, version the protocol/scenario contract and obtain review before treating later runs as comparable.
- Never update historical CI records to make them appear to have tested a later SHA.

## 11. Reporting template

Copy one template per scenario run:

```yaml
run_id: R8IT-CG01-YYYYMMDDTHHMMSSZ-01
scenario: CG-01
run_type: authorized-local-technical-run
authorization_reference: "<explicit authorization reference>"
repository: abtn/Watch-Architecture-Rev2
source_sha: "<full SHA>"
branch: "<branch>"
scenario_contract_revision: "<commit or document revision>"
test_node_ids:
  - "<exact pytest node ID>"
command: "<exact command>"
started_at_utc: "<timestamp>"
finished_at_utc: "<timestamp>"
attempt: 1
retry_of: null

inputs:
  fixture_versions: {}
  policy_pins: {}
  generated_identity_manifest: "<artifact reference>"
  synthetic_input_manifest: "<artifact reference or not-applicable>"
  deterministic_seed: "<value or not-applicable>"

environment:
  os: "<name/version>"
  python: "<version>"
  postgres: "<version/image>"
  database_role:
    session_user: "<observed>"
    current_user: "<observed>"
    alembic_role: "<observed>"
  alembic_current: "<revision>"
  alembic_head: "<revision>"
  ci_run: null

evidence:
  - evidence_id: E01
    contract_reference: "<scenario assertion>"
    expected: "<exact expectation>"
    observed: "<exact observation>"
    locator: "<artifact/log/query reference>"
    result: pass

failure:
  primary_class: null
  secondary_tags: []
  explanation: null

cleanup:
  container_removed: null
  volumes_removed: null
  temporary_artifacts_removed_or_retained_by_reference: null
  environment_restored: null
  no_persistent_db_or_external_provider_contact: null
  evidence_locator: null

disposition: INCONCLUSIVE
limitations: []
reviewer: "<reviewer or pending>"
```

The template is a record format, not an executable test manifest. Replace placeholders with observed values; never leave a required field blank in a finalized record. Use the C-01 prefix in the Run ID and scenario field for C-01.

## 12. Authorization and scope boundary

This protocol is documentation only. Its acceptance establishes a consistent recording method; it does not authorize execution.

Before any new exploratory run or campaign:

1. Submit the exact scenario(s), Run ID plan, source SHA, commands, environment, fixture/input set, evidence queries, cleanup procedure, and expected output.
2. Identify whether the request is one bounded technical run or a campaign; do not infer campaign authorization from approval of one run.
3. Obtain explicit Operator authorization for the specific execution.
4. Stop if the run requires a live source/provider, persistent database, production credential, new test/capability, gated retrieval/Context, triage/disposition, scoring, or treatment comparison.
5. Keep the project state Pre-R8-ready unless the separate R8-ready entry gate is reviewed and explicitly accepted.

**Current disposition:** CG-01 + C-01 remain the selected initial technical scope. No new exploratory execution is authorized by this protocol or by its preparation.
