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

## Work in progress

- **RW-0 — next foundation track:** settle the remaining reasoning-loop decisions and freeze the newsroom value-harness scenario before RW implementation. The [RW-0 decision record](docs/development/rw-0-decision-record.md) tracks the open decisions and authorization boundary.
- **R7-C** remains separately gated; B6 closure does not authorize it. RW-0 will determine whether any R7-C capability is necessary for the reasoning value harness.

The active checkpoint, exact status, authorization, and verification evidence are maintained in [PLAN.md](PLAN.md) and [docs/testing.md](docs/testing.md).

## Future plan

- **RW — world-memory reasoning loop:** complete RW-0 through RW-5 and pass the foundation exit gate before cross-domain testing.
- **R8 (planned start: November 23, 2026):** pressure-test the completed architecture across newsroom, development-team, and generalist domains. November 23 is a planned start, not a completion deadline; R8 waits for the foundation exit gate. See the [R8 delivery plan](docs/development/r8-delivery-plan.md).
- **R9:** make the development and review process more repeatable and reliable.

## Project documentation

- [PLAN.md](PLAN.md) — current project status and next steps.
- [Plain-language overview](docs/simple-explain.md) — the whole Watch concept in one read; orientation only.
- [Architecture overview](docs/architecture.md) — how the system is structured.
- [Architecture decisions](docs/decisions.md) — the decisions that guide the project.
- [Contributor instructions](AGENTS.md) — how to work safely in this repository.
- [Documentation guide](docs/documentation-guide.md) — document authority, active reading order, and historical-record policy.
