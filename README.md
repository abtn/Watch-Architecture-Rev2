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

- **R7:** B3 is formally closed. B4.1 proposal/assessment contracts, B4.2 revise commit, and B4.3 revalidate commit are merged. B4.4 G1–G5 are complete and merged (PRs [#103](https://github.com/abtn/Watch-Architecture-Rev2/pull/103), [#105](https://github.com/abtn/Watch-Architecture-Rev2/pull/105), [#107](https://github.com/abtn/Watch-Architecture-Rev2/pull/107), [#109](https://github.com/abtn/Watch-Architecture-Rev2/pull/109), and [#111](https://github.com/abtn/Watch-Architecture-Rev2/pull/111)). G6 implementation is authorized and in progress in PR [#113](https://github.com/abtn/Watch-Architecture-Rev2/pull/113); exact-head hosted CI passed (956 passed, 113 warnings), while Operator-local verification remains pending. B5, B6, and R7-C remain unauthorized. See [PLAN.md](PLAN.md), [the B4.4 regression audit](docs/development/r7-b-b4-4-integrated-regression-audit.md), [the G6 plan](docs/development/r7-b-b4-4-g6-needs-review-revise-plan.md), and [testing evidence](docs/testing.md).

## Future plan

- **R8 (target: November 23, 2026):** test the same shared architecture across newsroom, development-team, and generalist scenarios. Entry is gated by B4.4 closure and the November 15 acceptance gate; see the [R8 delivery plan](docs/development/r8-delivery-plan.md).
- **R9:** make the development and review process more repeatable and reliable.

## Project documentation

- [PLAN.md](PLAN.md) — current project status and next steps.
- [Architecture overview](docs/architecture.md) — how the system is structured.
- [Architecture decisions](docs/decisions.md) — the decisions that guide the project.
- [Contributor instructions](AGENTS.md) — how to work safely in this repository.
