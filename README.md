# Watch — Persistent Team Experience

Watch is a framework for building teams of AI-assisted workers that can carry out useful work and retain lessons from experience.

AI workers can suggest what to do, but they do not make decisions on their own. The system checks proposals against its rules, and trusted people remain responsible for important decisions. Work, results, and accepted lessons are recorded so future tasks can build on what came before.

> **Model intelligence is temporary. Team experience is persistent.**

## Completed foundations

- **K0–K1:** established the development and database foundation, then proved the safe proposal → validation → atomic Kernel commit → Event path.
- **R0–R3:** established Revision 2 architecture boundaries, compatibility with the existing Kernel and Task model, durable Objectives, and deterministic StateAssessment.
- **R4:** established the StrategyProposal boundary and deterministic strategy validation.
- **R5:** introduced durable Plan materialization and lifecycle.
- **R6:** completed the source → Evaluation → distillation → Operator → Team Experience path, including task outcomes and recovery, source execution, review, indexing, retrieval, and reusable experience.
- **R7-0:** completed the architecture decisions and entry gate for knowledge quality and lifecycle.
- **R7-A:** added evidence-lineage classification and immutable knowledge-quality assessment.
- **R7-B0:** froze the canonical KnowledgeItem lifecycle design and cross-document contracts.
- **R7-B1:** added current-pointer history and snapshot-based lifecycle reconstruction.
- **R7-B2:** completed versioned content hashing and canonicality, projection, and Context-manifest updates.
- **R7-B3:** added immutable lifecycle assessments and their narrow assessment Tasks.
- **R7-B4:** implemented the trusted revise/revalidate commit path and completed the integrated G1–G6 regression proofs.
- **R7-B5.0–B5.4:** implemented candidate creation, supersession, and retirement, then completed the integrated lifecycle verification and formal closeout.
- **R7-B6:** completed the legacy lifecycle reconstruction and trusted-retirement regression proofs; test-only PR [#124](https://github.com/abtn/Watch-Architecture-Rev2/pull/124) merged on 2026-11-16. See the [B6 closeout](docs/development/r7-b-b6-legacy-lifecycle-hardening-plan.md).
- **RW-0:** closed the reasoning-loop decision phase and established the handoff into the world-memory foundation track; documentation closeout PR [#126](https://github.com/abtn/Watch-Architecture-Rev2/pull/126) was squash-merged.

## Work in progress

- **RW-1 — implementation merged; formal acceptance pending:** the accepted Thread, Hypothesis, ConfidenceChange, and shared EvidenceLink physical design is documented in the [RW-1 physical design proposal](docs/development/rw-1-physical-design-proposal.md). All six D132 decisions were accepted on 2026-11-16. Design/planning PR [#127](https://github.com/abtn/Watch-Architecture-Rev2/pull/127) and implementation PR [#128](https://github.com/abtn/Watch-Architecture-Rev2/pull/128) are merged. Test-only schema-negative follow-up PR [#132](https://github.com/abtn/Watch-Architecture-Rev2/pull/132) passed hosted and Operator-local exact-head verification (**1,029 passed**); documentation reconciliation is tracked in draft PR [#131](https://github.com/abtn/Watch-Architecture-Rev2/pull/131). These checks close the identified schema-level test gap, not the RW-1 milestone. Formal RW-1 acceptance remains pending.
- **RW-1 through RW-5:** these are the remaining world-memory reasoning-loop foundation slices. Implementation will proceed in bounded, separately authorized steps, followed by the foundation exit gate.
- **R7-C** remains separately gated. Neither R7-B6 nor RW-0 closeout authorizes R7-C implementation.
- **RWN-01 newsroom scenario preparation:** source capture, corpus freeze, reviewer materials, and final harness/test configuration are deferred from the immediate foundation critical path. They remain required before newsroom scored runs and the foundation exit/R8 gate; no scored runs are currently authorized.
- **Experiment A canonical fixtures — offline research artifact:** draft PR [#133](https://github.com/abtn/Watch-Architecture-Rev2/pull/133) adds canonical schemas, two renderers, Invariant #7 equivalence checks, and RW3-03/RW3-13/SP-01 fixtures. Hosted CI and Operator-local verification passed on exact head 51c24c0d4d29229ead57e8f06f6edd04a457d7be (**1,057 passed**). This does not authorize Experiment A execution, scored RWN-01 runs, or RW-2/RW-3 implementation.

The active checkpoint, exact status, authorization, and verification evidence are maintained in [PLAN.md](PLAN.md) and [docs/testing.md](docs/testing.md). Programmer-side Windows PowerShell sync and test scripts follow the [local sync/test script guide](docs/development/powershell-local-sync-test-script-guide.md).
