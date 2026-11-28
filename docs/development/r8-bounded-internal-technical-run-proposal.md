# R8 bounded internal technical-run proposal

**Status:** proposed preparation only; not execution-authorized.
**Development state:** Pre-R8-ready.
**Scope:** one independent CG-01 technical run and one independent C-01 technical run.
**Authority:** the accepted [result-recording protocol](r8-internal-test-result-recording-protocol.md) and [scope/proof freeze](r8-ready-internal-test-scope-and-proof-freeze.md).

## 1. Decision boundary

This proposal is for two separately recorded, bounded technical runs. It is not a campaign, product-value experiment, treatment comparison, RWN-01 run, or R8-ready transition.

No scenario may start until the Operator explicitly authorizes that scenario against the final exact source SHA, environment, and command. Authorization for CG-01 does not authorize C-01, and vice versa. Do not execute either scenario as part of PR validation.

## 2. Frozen technical-run baseline

The following revisions are the immutable baseline for preparing either bounded technical run. The source baseline is the exact current `main` commit after PR #226 merged.

| Baseline element | Exact revision | Meaning |
|---|---|---|
| **Source baseline / main** | `19a46fef615c5b4c1d18cd8092d6e70b7dbaa1b4` | Exact merged `main` SHA, including the frozen scenario tests, identity manifests, protocol, and runner. |
| **Scenario scope and proof contract** | PR #223 merge commit `634ffd24fbaaa1ee531c876ca4f529d89e4d49e2` | CG-01 + C-01 scope, expected proof, cardinality, limitations, and stop conditions. |
| **Result-recording protocol** | PR #224 merge commit `6c9732b41f3a701ecb11ce2b4bbab7a6e40badc4` | Run identity, authorization, evidence, dispositions, artifacts, checksums, and retry rules. |
| **Disposable PostgreSQL runner** | PR #225 merge commit `b5d6a79c85e30f0dd41ed40b5c86e3fb7a60e001` | Targeted pytest-node invocation, static checks, role/migration setup, and verified cleanup behavior. |
| **Scenario identity-manifest instrumentation** | PR #226 merge commit `19a46fef615c5b4c1d18cd8092d6e70b7dbaa1b4` | Test-only generated-identity and observed-cardinality output for both frozen scenario tests. |

The source baseline was verified against GitHub: `main` and the PR #226 merge commit are identical, with zero commits ahead or behind. The exact source SHA above is the required checkout for a run unless a later reviewed baseline is explicitly adopted.

The scenario contract, recording protocol, runner, and test instrumentation revisions are separately identified to make their responsibilities and provenance unambiguous. They are all included in the pinned source tree; the separate revision pins are traceability anchors, not instructions to mix files from different checkouts.

Any change to the source SHA, scenario contract, protocol, runner, test node, or command after authorization requires a fresh authorization decision.

## 3. Separate run definitions

### 3.1 CG-01

- Scenario: `CG-01`.
- Test node: `tests/test_world_memory.py::test_operator_update_creates_low_hypothesis_and_verified_evidence`.
- Run ID: assign immediately before execution using `R8IT-CG01-<UTC timestamp>-01`.
- Command, from repository root in PowerShell:

```powershell
.\scripts\test-disposable-postgres.ps1 -PytestArgs @("tests/test_world_memory.py::test_operator_update_creates_low_hypothesis_and_verified_evidence", "-s")
```

Expected evidence includes the isolated Team and pre-existing Thread/Signal/Snapshot fixture; authenticated Operator Task creation; one low-confidence active Hypothesis; one exact Snapshot-backed EvidenceLink; terminal Task/Outcome evidence; exact replay preserving Task/Outcome identity; no duplicate EvidenceLink or ConfidenceChange; and zero TeamExperienceChunk before, after success, and after replay.

This run does not test configured-source intake, Thread creation, retrieval/Context, retained-experience use, treatment, or scoring.

### 3.2 C-01

- Scenario: `C-01`.
- Test node: `tests/test_c01_intake_to_operator_update.py::test_c01_configured_source_intake_then_operator_update`.
- Run ID: assign immediately before execution using `R8IT-C01-<UTC timestamp>-01`.
- Command, from repository root in PowerShell:

```powershell
.\scripts\test-disposable-postgres.ps1 -PytestArgs @("tests/test_c01_intake_to_operator_update.py::test_c01_configured_source_intake_then_operator_update", "-s")
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

## 5. Identity-manifest capture

Both frozen scenario tests emit exactly one structured `R8_IDENTITY_MANIFEST=` JSON line after their assertions and replay checks. The line contains generated identifiers and observed cardinalities from that test execution; it is not a precomputed or reconstructed manifest.

The commands in §§3.1–3.2 include pytest's `-s` option so the manifest is written to the PowerShell transcript rather than being hidden by pytest output capture. Retain the complete line verbatim in the run record and preserve the raw transcript before producing any sanitized copy.

The manifest supplements, but does not replace, the expected-versus-observed evidence table, durable-state evidence, exact source/environment pins, or verified cleanup required by the accepted recording protocol. Do not infer unreported values or broaden database grants to fill an evidence gap.

## 6. Explicit authorization request

No execution is authorized by this proposal. Before either run, submit and obtain explicit authorization for:

- the selected scenario;
- its assigned Run ID;
- the frozen `main` source SHA and scenario-contract revision from §2;
- the exact command and immutable PostgreSQL image digest;
- the evidence-manifest approach in §5;
- the transcript/artifact location and cleanup procedure.

A correction after a failed run must be reviewed and authorized before a new attempt. Preserve the original run record unchanged.
