# Watch — R8 Delivery Plan

**Planned start:** Monday, November 23, 2026.
**Completion date:** not set. November 23 is the day R8 starts, not a deadline to finish R8.

## 1. Objective

R8 is the three-domain pressure test of the completed foundational Watch architecture. It begins only after the required layers—including the world-memory reasoning loop—are implemented, integrated, documented, and verified.

R8 tests the architecture that exists at its entry baseline. It must not be used to add a missing fundamental layer. If a foundational dependency is incomplete on November 23, R8 does not start; the schedule is re-baselined rather than weakening the entry gate or compressing unfinished architecture into the test phase.

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

## 2. Required path before R8

The active path is:

1. **R7-B B5.4 — complete and closed.** Do not reopen it without a demonstrated defect.
2. **R7-B B6 — legacy lifecycle hardening.** Follow [the B6 delivery plan](r7-b-b6-legacy-lifecycle-hardening-plan.md): verified baseline, read-only audit, frozen scope, minimal implementation if justified, integrated verification, hosted/local verification, and explicit acceptance.
3. **RW-0 — reasoning-loop decisions and value harness.** Confirm the current code/spec gap inventory, settle the remaining D1–D10 decisions, define one vertical scenario and operational measures, and resolve the EvidenceLink contract before schema work if required.
4. **RW-1 — minimum durable world-memory model.** Implement only the accepted Thread, competing Hypothesis, evidence, confidence-change, and immutable source-reference contract. Add SignalDisposition only if the vertical slice requires it.
5. **RW-2 — deterministic Operator update and commit path.** Prove provenance, confidence, cause, rival-preservation, atomicity, replay, and concurrency rules without model nondeterminism.
6. **RW-3 — model reasoning worker.** Add `update_thread` behind the existing generation-provider and cost-accounting boundaries. Model output remains an untrusted proposal.
7. **RW-4 — signal triage and reasoning retrieval.** Implement the minimum accepted signal-intake path and expose current, relevant Hypotheses to bounded Task Context with Team isolation.
8. **RW-5 — confidence decay.** Implement the accepted deterministic decay behavior and its proofs before the foundation exit gate.
9. **Foundation exit gate.** Verify all required layers end-to-end, including the value harness, migrations, tests, docs, exact-head local verification, and hosted CI. Record explicit Operator acceptance.

RW-0 must decide whether R7-C knowledge-use references or other existing milestones are required to measure retained-experience effects. R7-C is not silently merged into B6 or RW; any required work receives an explicit scope and authorization.

The B6 audit must resolve the F8 legacy-snapshot retirement question before any B6 implementation contract is frozen. B6 is not an excuse for speculative schema or lifecycle refactoring.

## 3. R8 entry gate — November 23 target

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

**Entry rule:** all foundational exit criteria must pass before the first R8 scenario is run. November 23 is a planned start date, not permission to start with incomplete foundations.

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
- Whether relevant prior experience was retrieved and actually used.
- Whether a controlled second run improves against the fixed rubric and baseline.
- Prediction calibration only where predictions are registered, resolvable, and numerous enough to support honest reporting.
- Safe-abstention behavior under insufficient, contradictory, and irrelevant evidence.

Do not let a model grade its own improvement without independent checks. Report sample sizes and limitations.

## 7. Completion and acceptance

R8 has no preassigned completion date. Its completion gate is defined by evidence, not by the November 23 start date.

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
6. No foundational architecture is added after R8 starts. A newly discovered fundamental gap stops the pressure test and requires a separately authorized re-plan.
7. Use exact SHAs for local and hosted verification; distinguish code/test SHA from documentation-inclusive PR head.
8. Use disposable PostgreSQL only, dynamic ports, and verified cleanup/environment restoration.
