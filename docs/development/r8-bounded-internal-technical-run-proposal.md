# R8 bounded internal technical-run proposal

**Status:** proposed preparation only; not execution-authorized.
**Development state:** Pre-R8-ready.
**Scope:** one independent CG-01 technical run and one independent C-01 technical run.
**Authority:** the accepted [result-recording protocol](r8-internal-test-result-recording-protocol.md) and [scope/proof freeze](r8-ready-internal-test-scope-and-proof-freeze.md).

## 1. Decision boundary

This proposal is for two separately recorded, bounded technical runs. It is not a campaign, product-value experiment, treatment comparison, RWN-01 run, or R8-ready transition.

No scenario may start until the Operator explicitly authorizes that scenario against the final exact source SHA, environment, and command. Authorization for CG-01 does not authorize C-01, and vice versa. Do not execute either scenario as part of PR validation.

## 2. Source baseline

- Repository: `abtn/Watch-Architecture-Rev2`.
- Required branch at execution: `main`.
- The exact full source SHA is intentionally **not yet frozen**. It must be copied from `main` after the targeted-runner correction in PR [#225](https://github.com/abtn/Watch-Architecture-Rev2/pull/225) is accepted and merged.
- The scenario contract revision must be the same merged source baseline, including the accepted result-recording protocol.
- Any change to source SHA, test node, scenario contract, or runner command after authorization requires a fresh authorization decision.

## 3. Separate run definitions

### 3.1 CG-01

- Scenario: `CG-01`.
- Test node: `tests/test_world_memory.py::test_operator_update_creates_low_hypothesis_and_verified_evidence`.
- Run ID: assign immediately before execution using `R8IT-CG01-<UTC timestamp>-01`.
- Command, from repository root in PowerShell:

```powershell
.\scripts\test-disposable-postgres.ps1 -PytestArgs "tests/test_world_memory.py::test_operator_update_creates_low_hypothesis_and_verified_evidence"
```

Expected evidence includes the isolated Team and pre-existing Thread/Signal/Snapshot fixture; authenticated Operator Task creation; one low-confidence active Hypothesis; one exact Snapshot-backed EvidenceLink; terminal Task/Outcome evidence; exact replay preserving Task/Outcome identity; no duplicate EvidenceLink or ConfidenceChange; and zero TeamExperienceChunk before, after success, and after replay.

This run does not test configured-source intake, Thread creation, retrieval/Context, retained-experience use, treatment, or scoring.

### 3.2 C-01

- Scenario: `C-01`.
- Test node: `tests/test_c01_intake_to_operator_update.py::test_c01_configured_source_intake_then_operator_update`.
- Run ID: assign immediately before execution using `R8IT-C01-<UTC timestamp>-01`.
- Command, from repository root in PowerShell:

```powershell
.\scripts\test-disposable-postgres.ps1 -PytestArgs "tests/test_c01_intake_to_operator_update.py::test_c01_configured_source_intake_then_operator_update"
```

Expected evidence includes the frozen one-Team/one-policy/one-source cardinality; accepted Strategy proposal and Plan/PlanAction; one Plan-materialized `ingest_source` Task; exactly one FakeFetcher request with the fixed synthetic bytes; one Signal/Snapshot with exact source provenance and hash; one source-attributed intake Event and one source Task completion Event; the existing evaluation follow-on; one authenticated Operator update Task; one low-confidence Hypothesis and exact Snapshot-backed EvidenceLink; exactly one request/commit/completion Event for the Operator Task; exact replay preserving Task/Outcome identity and business-write cardinality; and zero TeamExperienceChunk at all required checkpoints.

This run does not test live network/provider behavior, Thread creation, retrieval/Context, retained-experience use, cross-origin canonicalization, triage/disposition, treatment, or scoring.

## 4. Shared environment and execution controls

For each invocation independently:

1. Start a new PowerShell transcript at a non-repository evidence location whose filename includes the Run ID. Stop the transcript in a `finally` block.
2. Record OS and PowerShell versions, Python/uv versions, Docker Engine version, PostgreSQL image digest, repository SHA, working directory, exact command, and UTC start/end times.
3. Resolve the configured PostgreSQL image to an immutable digest and pass that digest through `-Image`; record the digest in the run manifest. Do not rely only on the mutable `pgvector/pgvector:pg16` tag.
4. Let the runner provision roles and apply migrations. Record the sole Alembic head/current revision and the observed database identities; do not infer runtime identity from a DSN label.
5. Keep static checks enabled. Each invocation runs Ruff, Mypy, migrations, and only its selected pytest node.
6. Verify the runner's final cleanup output: container absent, every captured anonymous volume absent, and tracked environment variables restored exactly.
7. Preserve the raw transcript, sanitized copy, SHA-256 checksum, and per-scenario expected/observed evidence record. Never put credentials or connection strings in artifacts.

Do not run both selectors in one invocation: each scenario requires its own fresh disposable database and independent Run ID/disposition.

## 5. Evidence readiness gap

The current scenario tests use generated UUIDs and assert the resulting relationships in-process, but the test output does not currently emit a generated-identity manifest. The accepted protocol asks the run record to retain generated fixture identities.

Before a run can be claimed PASS, resolve this gap by one of the following, with explicit review:
- add minimal test-only structured identity output to the two existing scenario tests (without adding a new scenario or changing production behavior); or
- demonstrate an existing, approved way to capture the generated identities and durable-state observations from the same run.

Do not silently omit the manifest, invent identifiers, or broaden database grants. Until this is resolved, a test may complete but its recording disposition cannot be PASS under the accepted protocol.

## 6. Explicit authorization request

No execution is authorized by this proposal. Before either run, submit and obtain explicit authorization for:
- the selected scenario;
- its assigned Run ID;
- the final merged `main` source SHA and scenario-contract revision;
- the exact command and immutable PostgreSQL image digest;
- the evidence-manifest approach resolving §5;
- the transcript/artifact location and cleanup procedure.

A correction after a failed run must be reviewed and authorized before a new attempt. Preserve the original run record unchanged.
