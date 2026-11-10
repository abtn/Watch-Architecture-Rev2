# Watch — Persistent Team Experience

Watch is a framework for building teams of AI-assisted workers that can carry out useful work and retain lessons from experience.

AI workers can suggest what to do, but they do not make decisions on their own. The system checks proposals against its rules, and trusted people remain responsible for important decisions. Work, results, and accepted lessons are recorded so future tasks can build on what came before.

> **Model intelligence is temporary. Team experience is persistent.**

## Completed foundations

- **K0:** established the project's development tools and database foundation.
- **K1:** created the first safe path for recording completed work.
- **R0:** defined the main ideas and boundaries of the system.
- **R1:** checked that the design fits the existing system.
- **R2:** introduced goals and how they are managed.
- **R3:** added a consistent way to assess the system's state.
- **R4 (closed 2026-10-20):** established how the system turns goals into structured strategies.
- **R5 (closed 2026-10-24):** added durable plans and their lifecycle.
- **R6-G0:** agreed how Watch should learn from evidence and retain useful team knowledge.
- **R6-A:** added reliable task outcomes, retries, and recovery.
- **R6-B:** added the first end-to-end path for carrying out configured source work.
- **R6-C:** added a way to review how work was carried out without changing its records.
- **R6-D:** added the ability to index and search approved source material.
- **R6-E:** gave tasks useful background information and allowed AI to suggest next steps within set limits.
- **R6-F:** enabled reviewed experience to become reusable team knowledge.
- **R6-G (closed 2026-11-04):** completed the process for reviewing past work and reusing lessons in future tasks.

## Work in progress

- **R7:** work is focused on checking the quality of saved lessons and how saved knowledge should be validated and evolve. B2 is closed with its accepted residual verification gaps recorded. B3.2–B3.6 assessment persistence, revalidation/lifecycle assessment, TaskRuntime integration, and approval-time binding are implemented and merged (PRs #60, #62, #64, #66, #68). B3.6 merged at `4735b93c74025ddee3bd099ef6d5e64cbac34719`; its exact PR head passed hosted and Operator-local verification (908 full-suite tests, 113 existing Alembic warnings). B3.7 integrated regression implementation is authorized and underway in [PR #69](https://github.com/abtn/Watch-Architecture-Rev2/pull/69), using the matrix at [`docs/development/r7-b-b3-7-integrated-regression-matrix.md`](docs/development/r7-b-b3-7-integrated-regression-matrix.md). Initial integrated revalidation and supersede tests pass hosted CI on code head `303bc28149ab580a9406fde007a156d5d0e6d67a` (909 tests, 113 existing Alembic warnings). Operator-local B3.8 verification is not claimed. B3.8 exact-head verification and B3.9 closeout remain gated. The approval allowlist remains exactly `create`; no lifecycle commit, candidate creation, automatic TaskDispatcher activation, B4–B6, or R7-C work is authorized.

## Future plan

- **R8:** test the same approach across different kinds of teams and work.
- **R9:** make the development and review process more repeatable and reliable.

## Project documentation

- [PLAN.md](PLAN.md) — current project status and next steps.
- [Architecture overview](docs/architecture.md) — how the system is structured.
- [Architecture decisions](docs/decisions.md) — the decisions that guide the project.
- [Contributor instructions](AGENTS.md) — how to work safely in this repository.
