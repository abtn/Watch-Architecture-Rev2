# Experiment A — Execution Plan and RW Dependency Proposal

**Status:** planning proposal; no model/provider execution is authorized.
**Planning baseline:** main at 792f7fcecf75e285aad3d15eb8ba17d67cef2569 (2026-11-23).
**Artifact baseline:** Experiment A canonical-fixture contract merged by PR #133 at 77337f8a68454078ab154596228946acdd148fb8; exact tested PR head 82d5d618174c54d7f9946ebeda3b279b89f851b1.
**Decision authority:** Operator. PLAN.md remains the authority for current milestone status and authorization.

## 1. Purpose and research question

Experiment A is a bounded RW-3 research experiment:

> Given exactly the same underlying world-memory case information, does presenting the evidence in a flat representation or a decision-structured representation change a reasoning worker's evidence assessment and proposed update?

The experiment is about representation, not whether the underlying evidence is true and not whether Watch's complete architecture improves newsroom output.

The research motivation is methodological. Published cognitive-grounding work suggests that explicit decision guidance and structured context can affect LLM behavior in some settings. It does not establish that Watch's structured representation is better for scientific reasoning. Experiment A must test that question directly and report its narrow limits.

## 2. Existing artifact and current evidence

PR #133 supplies an offline package containing:

- RW3-03: a completed measurement supports the stated Hypothesis under all specified conditions; evaluator expectation is a supporting EvidenceLink and confidence increase.
- RW3-13: a requested measurement remains pending; evaluator expectation is to hold confidence and not invent a result or ConfidenceChange.
- SP-01: a separate StrategyProposer single-source diagnostic. It is not an RW-3 update case and must not be pooled into the primary Experiment A comparison.
- Flat and decision-structured renderers for the RW-3 cases.
- Representation Invariant #7, which checks that both renderings preserve the same record multiset.
- Closed model-facing evidence-assessment and RW-3 proposal-output schemas.

The fixtures, schemas, renderers, and Invariant #7 tests are an offline contract only. They do not show that a model was run, that either representation performs better, or that the renderers are safe production Context assemblers.

Important limitations already recorded in research/experiment_a/README.md:

1. The scientific fixture payload is intentionally extensible in selected locations; the model-facing schemas are closed.
2. The flat and structured renderer outputs do not have their own dedicated JSON Schema.
3. The current renderer package does not implement the production allowlisted projection that would be required before provider exposure.
4. Evaluator-only expected answers are excluded from the model-visible fixture hash and must never enter model input.
5. Fixture semantic validation and model-contract validation prove different properties.

Do not silently turn these research renderers into a production request format.

## 3. Scope

### Included

- Compare flat versus structured representations for RW3-03 and RW3-13.
- Keep the underlying case facts, task instructions, model/provider configuration, output schema, and evaluation criteria constant.
- Measure evidence-assessment correctness, proposed-update correctness, unsupported assertions, and output-contract validity.
- Preserve exact inputs, renderer versions, prompts, model configuration, raw outputs, scoring, and protocol deviations.
- Produce a bounded report that informs the RW-4 Context representation decision.

### Excluded

- SP-01 from the primary RW-3 comparison; it may remain a separate smoke/diagnostic check.
- RWN-01 and the newsroom retained-experience comparison.
- Retrieval relevance, multi-Thread retrieval, TaskKnowledgeReference, KnowledgeUseAssessment, causal claims, and the RW-D27 newsroom treatment/control design.
- RW-4 Signal triage, SignalDisposition persistence, Thread matching, or production Context integration.
- RW-5 confidence decay.
- Production provider integration, database access, migrations, persistent Watch state, or scored newsroom runs.
- Claims that a small fixture experiment validates the full RW-3 architecture or general model reasoning ability.

## 4. Proposed experimental design

This section is a proposal to freeze before execution, not a record of an approved run.

### 4.1 Conditions and pairing

For each primary fixture, prepare a matched pair:

- Condition F: flat rendering.
- Condition S: decision-structured rendering.

Each pair uses the same canonical fixture bytes, the same model-facing task instructions, the same output schema, and the same model/provider configuration. Only the representation of the case information changes.

Randomize the order of F/S within each pair. Each call starts in a fresh isolated conversation/session. No output, critique, correction, or evaluator feedback from one condition may be exposed to another run.

A proposed bounded exploratory size is five matched pairs per primary fixture: 2 cases × 5 pairs × 2 conditions = 20 model outputs. This is a pilot-sized engineering experiment, not a powered statistical study. The Operator must approve or replace this count before the run manifest is frozen. Do not add runs selectively after seeing which condition is ahead.

Use one pinned model/provider configuration for the primary comparison. If the model or configuration changes, treat it as a separate experiment instance; do not pool results. Record whether a deterministic seed is supported and used. A fixed seed does not guarantee deterministic output.

### 4.2 Input and output controls

- Verify Invariant #7 for each fixture immediately before execution.
- Hash the canonical fixture and each rendered representation.
- Create an explicit, versioned allowlisted model-input projection. Do not pass arbitrary extensible fixture fields through.
- Exclude evaluator_metadata, expected answers, scoring notes, and any other evaluator-only information from every model-visible request.
- Use identical task instructions across F/S. The prompt must not tell the worker which condition is expected to be better.
- Validate every response against the closed evidence-assessment and model-output schemas.
- Preserve invalid outputs as invalid observations. Do not silently repair, regenerate, or discard them. Any retry rule must be predeclared and applied symmetrically.
- Keep the model's proposal separate from the evaluator's expected answer and from any application validation result.

### 4.3 Outcomes

Report results separately for each fixture and representation. At minimum record:

1. Decision correctness: whether the proposed decision matches the evaluator's predeclared expected behavior (increase for RW3-03; hold for RW3-13).
2. Evidence-assessment correctness: whether references resolve to the correct fixture records and the relevance, reliability, independence, and temporal-status assessments are defensible against the fixture.
3. Proposal correctness: whether EvidenceLink stance, subject, source references, and ConfidenceChange direction/absence match the case evidence and closed output contract.
4. Unsupported assertions: invented measurements, conclusions, alternative-explanation claims, or status changes not supported by the fixture.
5. Contract validity: schema-valid responses, invalid response count, and rejection reasons.
6. Operational measures: input/output tokens where available, latency, and estimated/actual cost.

The primary descriptive comparison should be the per-case rate of evaluator-correct, schema-valid outputs in each condition. Also report each individual run and matched-pair outcome. Do not collapse the two cases into a single score that hides a failure on the pending-evidence case.

Use the fixture's evaluator-only expectations as the predeclared answer key. Any ambiguous or disputed assessment must be recorded, not retrospectively redefined to favor a representation. If human adjudication is needed, reviewers must be blind to condition and the original assessment must be retained.

### 4.4 Analysis and interpretation

Report raw counts and denominators, per-case results, paired differences, invalid outputs, unsupported assertions, and operational measures. With the proposed small sample, treat differences as descriptive and hypothesis-generating. Do not claim statistical significance, broad superiority, or causal improvement beyond this controlled comparison.

Possible dispositions:

- Structured favored in these cases: a consistent, material improvement appears without a corresponding increase in unsupported assertions or contract failures.
- Flat favored in these cases: the same standard favors flat rendering.
- No clear difference: results are mixed, small, or unstable.
- Inconclusive/invalid: protocol deviations, provider/model drift, insufficient usable outputs, or input-equivalence failure prevent a defensible comparison.

No result automatically changes production architecture. The result is evidence for a design decision, not authority to change the model contract or application behavior.

## 5. Execution checkpoints

| Checkpoint | Work | Exit evidence | Authorization |
|---|---|---|---|
| EA-0 — protocol freeze | Confirm question, cases, primary metrics, run count, model/provider, prompt, allowlisted projection, retry rule, budget, randomization, and report format. | Versioned protocol and run manifest approved before outputs exist. | Documentation/review only. |
| EA-1 — offline readiness | Run the existing fixture/schema tests; verify Invariant #7; inspect model-input projection and evaluator-metadata exclusion; validate output schemas with positive/negative examples. | Exact commit, commands/results, fixture/render hashes, no provider or database calls. | Existing offline test authorization only; no production changes. |
| EA-2 — execution preflight | Pin provider/model/version and generation settings; confirm access, budget ceiling, data handling, session isolation, logging, and stop rules. | Signed-off execution checklist and exact run manifest. | Separate explicit Operator authorization for provider/model calls. |
| EA-3 — controlled execution | Execute all predeclared paired runs in randomized order; preserve every output and deviation. | Complete run ledger with input/output hashes, model metadata, timestamps, cost, and raw outputs. | Only the explicitly approved experiment instance. |
| EA-4 — blinded evaluation | Score outputs against the frozen evaluator expectations and rubric; adjudicate ambiguity without revealing condition where practical. | Complete score sheet, adjudication record, and protocol-deviation register. | Independent evaluation under the frozen protocol. |
| EA-5 — report and disposition | Compare conditions, classify result, record limitations, and decide the consequence for RW-4 Context design. | Reproducible report and explicit Operator disposition: adopt, reject, inconclusive, or accept residual risk. | Operator accepts the research checkpoint; this does not accept RW-3/RW-4/RW-5. |

## 6. Relationship to RW-4

Experiment A is relevant to only one part of RW-4: how evidence and Hypotheses are represented when assembled into a model-facing reasoning Context.

It does not test the other RW-4 responsibilities: Team-scoped Signal triage, SignalDisposition, deterministic matching/deduplication, Thread creation/reactivation, Task identity/admission, or retrieval authorization and bounds.

Accepted dependency rule:

- RW4-0 design reconciliation and RW4-1 through RW4-3 (disposition persistence, Task boundary, deterministic triage/Thread commit) can be designed and, after their own authorization, implemented independently of Experiment A's result.
- RW4-4 must define its model-facing representation and explicit allowlisted projection. Experiment A's result should inform that choice, but its two single-Thread fixtures do not validate multi-Thread retrieval or the complete RW-4 Context path.
- Experiment A is a decision input for freezing the RW4-4 evidence-representation choice, not a blanket prerequisite for all RW-4 work. If RW4-4 proceeds without a usable Experiment A result, the selected representation, rationale, and residual uncertainty must be explicitly recorded as an Operator disposition before the representation is frozen.
- Experiment A does not block RW-5 planning or implementation. RW-5 remains integrated with RW-4 through the dormant-Thread reactivation and post-decay retrieval proofs; those are independent of Experiment A.
- Before foundation exit/R8, the Experiment A result must have an accepted report with limitations carried forward, or an explicit Operator disposition that the result is inconclusive/not required for the selected RW4-4 representation, with residual uncertainty recorded.
- Do not claim that Experiment A has selected the correct RW-4 representation for multi-Thread retrieval. A separate RW-4 Context proof matrix must cover ownership, active status, evidence verification, deterministic ordering, bounds, and replay.

This dependency decision does not authorize Experiment A provider execution or RW-4/RW-5 implementation.

## 7. Relationship to RW-5

Experiment A has no direct technical dependency on RW-5. RW-5 is a deterministic maintenance operation, not a model-facing representation choice.

The current accepted RW-5 first-release contract (superseding the earlier architecture wording) says `apply_decay`:

- selects active Hypotheses whose last_touched_at exceeds the configured decay_window;
- lowers confidence according to decay_action, recording a Task-attributed ConfidenceChange with cause_kind=decay;
- never rejects a Hypothesis and never updates last_touched_at;
- does not change `Thread.status` or make active Threads dormant. D6.5 explicitly keeps Thread lifecycle ownership out of RW-5 first release; any future dormancy writer requires a separate accepted design and authorization.

Experiment A does not exercise elapsed-time decay, dormancy, reactivation, or decay/retrieval races. It must not be used as RW-5 proof.

RW-5 can be planned independently of Experiment A. The integrated RW-4/RW-5 proof must demonstrate that RW-4 retrieval respects post-decay Hypothesis confidence state; any future Thread-status writer must be separately designed and serialized with triage under the canonical lock protocol. The original milestone order RW-4 → RW-5 remains unless the Operator explicitly changes it.

## 8. Relationship to RW3.4 acceptance and the foundation exit

Experiment A is not a substitute for RW3.4 formal acceptance. RW3.4's seven PARTIAL proof rows and deferred disposition remain exactly as recorded in PLAN.md and the RW3.4 closeout plan.

Because Experiment A is a separate, isolated research run over frozen fixtures, its protocol preparation and offline readiness work can proceed without changing RW3.4's acceptance state. Actual provider execution still requires its own explicit authorization and must not be presented as evidence that the production RW3.4 runtime or external host integration is formally accepted.

Accepted foundation-exit disposition: before the foundation exit gate, Experiment A must have either (a) a completed, accepted report whose limitations are carried forward, or (b) an explicit Operator decision that the result is inconclusive/not required for the selected RW-4 representation, with the residual uncertainty recorded. It must not silently disappear from the gate, but it does not block unrelated RW-4 triage or RW-5 decay work.

RWN-01 remains a separate newsroom value-harness experiment. Its 10 matched control/treatment pairs, retained-experience snapshot, claim-level attribution, independent review, and three acceptance gates are not Experiment A's protocol and must not be merged with it.

## 9. Accepted dependency graph

| Work item | Experiment A dependency | Rationale |
|---|---|---|
| RW4-0 design decisions | Parallel; no hard block | Most decisions concern identity, ownership, matching, disposition, and Task boundaries, not representation. |
| RW4-1 disposition persistence | None | Physical schema and Team-isolation proofs do not depend on flat/structured model context. |
| RW4-2 triage Task boundary | None | Trusted creator, immutable request, admission, and TaskRuntime behavior are independent. |
| RW4-3 deterministic triage and Thread commit | None | Matching, deduplication, disposition, creation/reactivation, and atomic commit are deterministic application behavior. |
| RW4-4 Context representation | Experiment A result informs the choice; absent a usable result, an explicit Operator-approved rationale and residual-risk record is required before freeze | This is the only direct technical relationship; current fixtures are not multi-Thread retrieval tests. |
| RW-5 confidence decay | None | Deterministic decay does not depend on the model-facing representation experiment. |
| RW-4/RW-5 integrated exit | Result disposition required | Ensure the experiment is not omitted and cross-check retrieval after decay/reactivation. |
| RW foundation exit / R8 | Accepted Experiment A disposition required | Carry the result or explicit residual-risk decision into the foundation evidence package. |
| RWN-01 scored newsroom harness | Separate experiment | Different question, corpus, treatment, outcomes, and acceptance criteria. |

## 10. Operator decisions required before EA-0 closes

1. Approve the primary scope as RW3-03 and RW3-13, with SP-01 diagnostic-only.
2. Approve or replace the proposed five matched pairs per primary fixture (20 outputs total).
3. Select the one model/provider configuration and approve its use, cost ceiling, and data-handling boundary.
4. Approve the evaluation rubric and any human-adjudication role.
5. Confirm that protocol preparation may proceed while RW3.4 formal acceptance remains deferred, with no implication that the experiment accepts RW3.4.

Until these decisions are recorded, the plan remains a proposal. No model/provider calls, database operations, production changes, migrations, RW-4/RW-5 implementation, or RWN-01 scored runs are authorized by this document.
