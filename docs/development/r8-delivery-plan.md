# Watch — R8 Delivery Plan

**R8-ready internal test start:** TBD; no start is authorized by this plan alone.
**Formal/scored R8 start:** TBD — the November 23, 2026 target was withdrawn on 2026-11-23.
**Completion date:** not set.

> **State and schedule clarification:** The former November 23 formal R8 start target is withdrawn. The project now distinguishes R8-ready internal testing from Full Design and formal/scored R8. A bounded R8-ready test may begin only after its own scope, prerequisites, and authorization are recorded in `PLAN.md`; it does not waive or close the full RW foundation gate. Formal/scored R8 remains gated on Full Design and the complete acceptance criteria below. No date grants permission to start.

## 1. Objective

Formal/scored R8 is the three-domain pressure test of the completed foundational Watch architecture. It begins only after the required layers—including the world-memory reasoning loop—are implemented, integrated, documented, and verified. The earlier R8-ready state is a separate, bounded internal-testing gate intended to expose problems before Full Design is complete.

R8-ready tests may reveal a missing foundational capability or a flawed design assumption. Pause the affected scenario, record the evidence, and return to design/implementation through a reviewed change; do not conceal the gap or continue scoring against an invalid baseline. Do not weaken formal R8 acceptance or treat exploratory results as scored results. See [R8 development states](r8-development-states.md).

The RW value harness uses **newsroom as its first real-world domain** (Operator-confirmed 2026-11-15). RW-0 decision groups 1–8 were approved on 2026-11-16, freezing the measurement methodology, rubric, thresholds, run design, and execution/reporting rules. The Operator selected **RWN-01**, the LEAP perovskite-additive study, as the newsroom story identity on 2026-11-16. Its source/experiment package remains a draft: the publisher PDF binary and Supplementary Material still require capture/review, and the corpus manifest, task brief, answer key, independent outcome set, story-specific scoring examples, reviewer calibration, and execution configuration must be frozen before scored runs. Any deferred pre-execution item must have a named owner and explicit acceptance gate. Story selection does not authorize scored runs or implementation.

Experiment A is a separate RW-3 representation experiment. Its merged canonical fixtures are an offline contract, not execution. The Operator has accepted the dependency rule recorded in the [Experiment A execution plan](experiment-a-execution-plan.md): its result informs RW4-4's model-facing evidence representation, but does not block RW4-0 through RW4-3 or RW-5. RW4-4 must use the result or record an explicit Operator-approved rationale and residual uncertainty before freezing its representation. Before foundation exit/R8, an accepted report or explicit inconclusive/not-required disposition must be recorded with limitations. This dependency decision is not provider authorization. RWN-01 remains the distinct newsroom retained-experience value-harness experiment. See [the newsroom value harness](rw-value-harness.md), [RWN-01 package draft](rw-newsroom-scenario-package-draft.md), and [RW-0 decision record](rw-0-decision-record.md).

R8 must demonstrate:

- Shared Kernel and Control behavior remains consistent across domains.
- Domain-specific knowledge remains outside the shared Kernel.
- Signals can be interpreted into durable, evidence-backed Threads and competing Hypotheses.
- Evidence and confidence changes have traceable, validated causes.
- Experience and beliefs persist beyond an individual model or Task.
- Relevant retained experience can be retrieved and used; irrelevant experience is rejected.
- Cross-domain transfer respects explicit applicability boundaries.
- Poor, conflicting, irrelevant, or insufficient evidence produces safe abstention or rejection rather than unsupported decisions or writes.
- A later run can demonstrate measurable benefit from retained experience under a predefined value harness.

## 2. Full Design path before formal/scored R8 acceptance

The active path is:

1. **R7-B B4.4 — complete and closed.** G1–G6, exact-head verification, documentation reconciliation, and explicit Operator acceptance were completed on 2026-11-13.
2. **R7-B B5.4 — complete and closed.** Do not reopen it without a demonstrated defect.
3. **R7-B B6 — complete and formally closed on 2026-11-16.** Test-only PR #124 merged at `419312bc678901e2d22179313e6285086bee42da`; exact-head local and hosted verification are recorded in `docs/testing.md` and the [B6 delivery/closeout record](r7-b-b6-legacy-lifecycle-hardening-plan.md). Do not treat B6 as outstanding R8 work.
4. **RW-0 — reasoning-loop decision freeze and value harness.** Reconcile the approved RW-0 decision record, implementation plan/proof matrix, value harness, and this R8 plan; freeze the newsroom measurement methodology and capability boundaries; and prepare the actual experiment package (selected completed story, source corpus/manifest, scored brief, answer key, independent outcome reference, story-specific scoring examples, and execution configuration) or explicitly track each remaining pre-execution deliverable with a named owner and acceptance gate. RW-0 freezes the EvidenceLink architectural contract; the exact physical relational/migration design is a separately accepted RW-1 pre-implementation gate under D132. RW-0 decision approval does not authorize implementation.
5. **RW-1 — minimum durable world-memory model.** Implement only the accepted Thread, competing Hypothesis, evidence, confidence-change, and immutable source-reference contract. Add SignalDisposition only if the vertical slice requires it.
6. **RW-2 — deterministic Operator update and commit path.** Prove provenance, confidence, cause, rival-preservation, atomicity, replay, and concurrency rules without model nondeterminism.
7. **RW-3 — model reasoning worker.** Add `update_thread` behind the existing generation-provider and cost-accounting boundaries. Model output remains an untrusted proposal.
8. **RW-4 — signal triage and reasoning retrieval.** Implement the minimum accepted signal-intake path and expose current, relevant Hypotheses to bounded Task Context with Team isolation.
9. **RW-5 — confidence decay.** Implement the accepted deterministic decay behavior and its proofs before the foundation exit gate.
10. **Foundation exit gate.** Verify all required layers end-to-end, including the value harness, migrations, tests, docs, exact-head local verification, and hosted CI. Record explicit Operator acceptance.

RW-D99 freezes only the minimum R7-C capabilities required for auditable claim-level attribution: immutable TaskKnowledgeReference and minimal typed KnowledgeUseAssessment. Under D133, the implementation plan must map each capability to a named RW slice and proof obligations before authorizing any slice that implements it. This does not authorize the separate R7-C milestone or a broader evaluation/learning loop. RW-D11–D15 and D100 retain the exclusions for persistent Artifacts/publishing, operational Consultation workflows, self-service setup, and expanded domain-pack machinery unless the frozen product claim demonstrates a necessary dependency and the Operator explicitly approves a scope change. Do not treat every specified future feature as an automatic prerequisite.

The F8 legacy-snapshot retirement question was resolved during the completed B6 audit and closeout; it is not an outstanding R8 entry task. The B6 closeout record documents the test-only proof and confirms that no production, schema, or migration change was required. Do not reopen B6 or introduce speculative schema/lifecycle refactoring without a demonstrated defect and separate authorization.

## 3. Formal/scored R8 entry gate — schedule-independent acceptance

Freeze and record:

- Exact `main` baseline SHA and Alembic migration head.
- B6 acceptance and merge evidence.
- RW-0 decisions and accepted architecture contracts.
- RW-1 through RW-5 implementation, test, and verification evidence.
- The three domain scenarios and their domain-pack inputs.
- The common Control and Task execution path.
- Evidence, confidence, provenance, replay, concurrency, and safe-abstention proofs.
- Experience retention/reuse measures, comparison baseline, rubric, and sample-size policy.
- Cross-domain transfer restrictions.
- Explicit exclusions and unresolved non-critical risks.

**Entry rule:** all foundational exit criteria must pass before the first formal/scored R8 scenario is run. R8-ready exploratory testing uses the separate entry criteria in [R8 development states](r8-development-states.md) and must be explicitly authorized in `PLAN.md`. The formal start date remains TBD until RW-4/RW-5 estimates, the accepted Experiment A result/residual-risk disposition, newsroom package readiness, and the foundation exit forecast are evidence-based. No date grants permission for formal R8 with incomplete foundations.

## 4. R8 pressure-test domains

### Domain 1 — Newsroom

Exercise source intake, evidence interpretation, competing explanations, confidence updates, Task execution, outcomes, and retained experience. Include unsupported quotations, conflicting sources, stale information, and insufficient evidence.

### Domain 2 — Development team

Exercise technical evidence, competing diagnoses or hypotheses, implementation Tasks, outcomes, and retained experience through the same shared architecture. Include contradictory test results, unsupported claims, and stale project knowledge.

### Domain 3 — Generalist

Exercise a materially different generalist scenario without relying on newsroom or development-specific assumptions. Verify that shared reasoning and Control behavior do not depend on either specialized domain.

### Cross-domain integration

Run the domains against the same shared architecture. Verify Team and domain isolation, applicability checks, and that knowledge from one domain cannot silently become an authoritative belief or canonical write in another.

## 5. Required failure behavior

For each applicable domain, test:

- Fabricated or misquoted evidence.
- A weak relation such as “mentions” being used to justify a confidence increase.
- Confidence changes without one valid cause.
- A new Hypothesis deleting or silently overwriting a rival.
- Insufficient, irrelevant, stale, or contradictory evidence.
- Replayed and concurrent updates.
- Invalid cross-Team or cross-domain references.
- Failure and recovery at supported Task/runtime boundaries.

Rejected proposals must not create partial canonical writes, duplicate Events/Outcomes, or corrupt existing evidence and beliefs. Safe abstention is a valid result.

## 6. Value harness

Freeze the task, rubric, comparison baseline, sample-size policy, and evidence source before measuring R8 outcomes.

At minimum, report:

- Validation outcomes by rule and producer; rejection rate is diagnostic, not a success metric by itself.
- Whether relevant prior experience was retrieved and entered the later Task Context; claim direct use only where a validated knowledge-use reference or equivalent accepted mechanism is in scope (otherwise report the controlled outcome effect without asserting direct use).
- Whether a controlled second run improves against the fixed rubric and baseline.
- Prediction calibration only where predictions are registered, resolvable, and numerous enough to support honest reporting.
- Safe-abstention behavior under insufficient, contradictory, and irrelevant evidence.

Do not let a model grade its own improvement without independent checks. Report sample sizes and limitations.

## 7. Completion and acceptance

R8 has neither a scheduled start nor a preassigned completion date. Its start and completion gates are defined by evidence, not by the withdrawn November 23 target.

Acceptance requires:

- [ ] All three domain scenarios pass.
- [ ] Shared Kernel/Control behavior remains invariant across domains.
- [ ] Domain knowledge and Team memory remain properly isolated.
- [ ] Threads, competing Hypotheses, evidence links, and confidence changes work through the governed path.
- [ ] Evidence provenance and immutable source references are verified.
- [ ] Replay, concurrency, and atomicity proofs pass.
- [ ] Relevant experience is retained, reconstructed, and used.
- [ ] Irrelevant experience and invalid transfer are rejected.
- [ ] Insufficient, poor, and conflicting evidence produces safe behavior.
- [ ] The predefined value harness is reported with sample sizes and limitations.
- [ ] Full regression suite and exact-final-head hosted CI pass.
- [ ] Documentation and implementation status are reconciled.
- [ ] No unresolved critical defects remain.
- [ ] Explicit Operator acceptance is recorded.

If any criterion fails, R8 remains open with the failed criterion, evidence, severity, and next action recorded. Do not weaken the acceptance bar to claim completion.

## 8. Architectural and delivery constraints

1. No second commit path; proposals use the existing controlled validation and commit boundaries.
2. Model output never becomes authority for durable state.
3. Domain-specific policy remains outside the shared Kernel.
4. Evidence, confidence, and lifecycle changes have immutable provenance and valid causes.
5. Team and domain boundaries are enforced at every read and write.
6. Do not make unreviewed architectural changes during a test run. A newly discovered fundamental gap pauses the affected scenario; record the evidence, reassess the design, obtain the required decision/authorization, implement the smallest correction, and rerun affected proofs before resuming. Preserve the original baseline and distinguish exploratory from scored results.
7. Use exact SHAs for local and hosted verification; distinguish code/test SHA from documentation-inclusive PR head.
8. Use disposable PostgreSQL only, dynamic ports, and verified cleanup/environment restoration.
