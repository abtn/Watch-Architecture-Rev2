# Decisions — Index

This is a navigation index, not a replacement for the full ADRs. Open the linked ADR before changing behavior governed by it. An ADR marked **Proposed** is not accepted authority.

| ADR | Decision | Practical consequence |
|---|---|---|
| [0001–0019 history](decisions/architecture%20decision%20records%20(ADR-0001%20-%20ADR-0019).md) | Original Watch decisions: Team, memory, learning, policy, evidence, commit, Tasks, projections, domain packs, and agent-facing documentation. | Consult the full history only when the task touches an original decision not superseded by Revision 2. |
| [0020](decisions/ADR-0020-consultations-waiting-happens-between-tasks.md) | Consultations wait between Tasks. | Do not create a blocking in-Task consultation path. |
| [0021](decisions/ADR-0021-operator-update-path-human-as-first-class-worker.md) | Operator update path. | Human updates use explicit Task/validation boundaries. |
| [0022](decisions/ADR-0022-generalist-pack-and-setup-advisor.md) | Generalist pack and setup advisor. | Generalist support remains within the pack/kernel boundary. |
| [0023](decisions/ADR-0023-control-layer.md) | Explicit Control layer. **Status: Accepted 2026-10-20.** | Strategy intent is separate from Task execution. |
| [0024](decisions/ADR-0024-strategy-is-not-team-policy.md) | Strategy is not TeamPolicy. **Status: Accepted 2026-10-20.** | Contextual strategic intent cannot rewrite general policy. |
| [0025](decisions/ADR-0025-plan-is-derived-execution-state.md) | Plan is derived execution state. **Status: Accepted 2026-10-25.** | Plan stores intended work; Tasks/Events describe actual execution. |
| [0026](decisions/ADR-0026-dual-entry-execution-model.md) | Dual-entry execution model. **Status: Accepted 2026-10-25.** | Reactive and deliberative entry paths converge on the same Task runtime. |
| [0027](decisions/ADR-0027-team-policy-daily-task-quota.md) | TeamPolicy daily Task-start quota. **Status: Proposed.** | Existing quota semantics remain documented; this G0 decision set does not accept ADR-0027 or broaden quota behavior. |
| [0028](decisions/ADR-0028-rag-backed-knowledge-cores.md) | RAG-backed Knowledge Cores. **Accepted 2026-10-25.** | Initial canonical inputs, hybrid PostgreSQL retrieval, scoped access, immutable Context provenance, and projection freshness/rebuild rules are recorded; embedding choice is staged to R6-D. |
| [0029](decisions/ADR-0029-llm-assisted-experience-distillation.md) | LLM-assisted Experience Distillation. **Accepted 2026-10-25; D7 review semantics resolved 2026-11-02.** | Evidence-linked LearningChange proposals, Operator commit, versioning, TeamPolicy-controlled review scheduling, fail-closed retrieval eligibility, and publication are defined; model output cannot commit Team memory or policy. |
| [0030](decisions/ADR-0030-r6-bounded-execution-source-safety-outcome.md) | R6 bounded execution, recovery, source safety, and Outcome contract. **Accepted 2026-10-25.** | One lifecycle authority, bounded recovery/retry, restricted configured-source fetch, and an atomic terminal Outcome contract. |
| [0031](decisions/ADR-0031-cloudflare-workers-ai-generation.md) | Initial Cloudflare Workers AI generation provider. **Accepted 2026-10-30.** | The first R6-E hosted model is `@cf/meta/llama-3.1-8b-instruct-fp8`; output remains an untrusted JSON proposal validated by Watch. |
| [0032](decisions/ADR-0032-knowledge-quality-evaluation-and-lifecycle.md) | Knowledge quality evaluation and lifecycle. **Original architecture accepted 2026-11-04 for R7-A; R7-B B0 design addendum accepted 2026-11-05.** | R7-A is complete. B0 freezes R7-B content/snapshot hashes, confidence behavior, evidence freshness, trusted-identity fingerprint binding, typed assessments, and D5 reciprocal successor/publication gating with D7-aware candidate/abandonment rules. B3.2–B3.6 are implemented and merged; B3.7's full regression matrix is mapped; B3.8 exact-head verification passed on hosted/local tested SHA `6b624310d4d3ae53153dba1b9f47e949564de079` (946 full-suite tests); B3.9 formal B3 exit was accepted and closed on 2026-11-10. The Markdown-only cumulative diff-check qualification is recorded in `docs/testing.md`. The approval allowlist remains exactly `create`; B4–B6 and R7-C remain separately gated and unauthorized. |

## Reading rule

Start with the row relevant to the task. Read the complete ADR when changing its behavior, reviewing a rejected alternative, changing durable schema/semantics, or resolving an authority question. Do not load all ADRs for every task.
