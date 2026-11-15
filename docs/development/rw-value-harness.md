# RW Value Harness — Newsroom First

**Status:** proposed measurement contract; not yet frozen for scored runs  
**First domain:** newsroom (Operator-confirmed 2026-11-15)  
**Decision authority:** the Operator freezes the exact scenario, rubric, and thresholds during RW-0 / before the R8 entry gate.

## 1. What the harness measures

The harness asks whether a Watch Team becomes more reliable at a bounded newsroom task because it retains and retrieves verified experience—not merely whether the code can store records or pass tests.

It is a repeatable product-value check across RW slices. It does not replace database/contract proofs, and a passing test suite does not establish newsroom value.

The first scenario is a **newsroom research desk tracking one bounded beat**. The exact beat, publication/source set, task brief, and outcome checks are deliberately left for RW-0 to select and freeze. Do not infer a topic or source list from this document.

## 2. Scenario shape

The frozen scenario should exercise this path:

1. A fixed set of source material is ingested or supplied through the approved Signal path.
2. The Team maintains a Thread for the developing story/beat.
3. The system records multiple plausible Hypotheses where the evidence warrants alternatives; it does not force a single narrative.
4. Each material claim is linked to exact quotes from immutable, hashed source Snapshots.
5. Confidence changes are justified by supporting/challenging evidence or by the separate deterministic decay rule.
6. A later Task receives bounded Context containing the current Thread, active Hypotheses, verified evidence, and any accepted Team Experience that is eligible for retrieval.
7. An independently checkable outcome is recorded. Evaluation and any resulting Team Experience follow the existing accepted R6/R7 gates; no model may directly write Team memory.
8. A subsequent run tests whether accepted and retrieved experience improves the work on a matched task.

The first harness measures reasoning, evidence discipline, and retained-experience effects. It does **not** claim to prove production publishing/delivery, public distribution, or consultation workflows unless RW-0 explicitly includes and implements those capabilities.

## 3. Controlled comparison

Use two equivalent Team states or isolated fixtures with the same frozen policy, source corpus, task brief, model/provider revision, tool budget, and evaluation set:

- **Baseline condition:** receives the current source material and ordinary allowed Context, but no prior accepted newsroom experience item relevant to the target task.
- **Experience-assisted condition:** receives the same inputs plus the exact accepted, current, eligible newsroom Experience item(s) produced by the first run and retrieved through the normal Context path.

The comparison must prevent contamination:
- Do not let the baseline Team receive the experience item through shared storage, prompt text, or operator hints.
- Do not let the experience-assisted Team receive extra source material or a different task brief.
- Keep model/provider revision and generation settings fixed within a comparison pair, or record the difference and treat the pair as non-comparable.
- Preserve the complete Context manifest, source Snapshot hashes, Task IDs, model/provider identity, and evaluation record for each run.
- Repeat the paired scenario enough times to distinguish a durable effect from one lucky generation; the required repeat count is an RW-0 decision.

If the same Team is used sequentially, reset/replay rules must be proven to avoid hidden state leakage. Prefer isolated, equivalent Team fixtures for controlled comparisons.

## 4. Measures

The proposal's three core measures are retained, with operational definitions below. Exact thresholds remain open until the Operator freezes them.

### 4.1 Deterministic validation acceptance and rejection

Report:
- number of material claim/evidence proposals submitted;
- number accepted by deterministic validation;
- number rejected;
- rejection counts by stable reason;
- acceptance rate and rejection rate.

The denominator is all in-scope proposals presented to the validator, not only the successful ones. A rejected proposal is not silently dropped from the report. Acceptance means the proposal satisfied the specified structural, scope, quote/hash, stance, transition, and cause checks; it does not prove the claim is true.

### 4.2 Retained-experience effect on the second run

Score the baseline and experience-assisted runs against the same independent newsroom rubric. Report the paired difference per rubric dimension and overall.

The rubric should assess at least:
- factual correctness against the frozen outcome/reference set;
- evidence traceability (every material claim has a verifiable source quote);
- coverage of material facts and relevant counter-evidence;
- treatment of uncertainty and competing explanations;
- consistency with the accepted prior lesson without treating it as unquestionable truth.

The primary value question is whether the experience-assisted condition improves independently scored work without increasing unsupported claims or hiding contrary evidence. A model's own self-rating is not an independent score and must never be the sole judge.

### 4.3 Confidence calibration against recorded outcomes

For Hypotheses that later resolve against the frozen outcome set, report the observed resolution rate separately for low, moderate, and high confidence bands. Preserve unresolved cases as unresolved; do not count them as correct or incorrect.

Do not convert the ordinal bands into numeric probabilities or calculate a Brier score unless RW-0 explicitly defines and justifies that mapping. The report must include the sample count per band so a small sample is not presented as strong calibration evidence.

### 4.4 Operational guardrails

Record cost, latency, provider/model revision, number of tool calls, and task failures for each run. These are guardrails and comparability metadata, not substitutes for quality.

## 5. Independent outcome and scoring controls

Before any scored run, RW-0 must freeze:
- the exact newsroom beat and task brief;
- the source corpus, source timestamps, immutable content hashes, and allowed-source rules;
- material facts, known counter-evidence, and outcome/resolution conditions;
- the scoring rubric, scoring instructions, and independent reviewer role;
- the run count, paired comparison method, and exclusion rules;
- acceptance thresholds for each measure and any minimum sample size.

Where feasible, the reviewer should be blind to whether a run is baseline or experience-assisted. A human reviewer or independently verified reference set must anchor factual scoring. Automated deterministic checks may score quote validity, scope, and record consistency. Model-generated evaluations may contribute evidence but cannot be the only judge of model quality.

## 6. What counts as retained experience

Only accepted, versioned Team Experience eligible under current lifecycle/review rules counts. A proposed LearningChange, unapproved KnowledgeItem, stale/retired item, embedding match alone, or transcript text does not count.

The harness must record:
- the source Outcome/Evaluation and accepted LearningChange that produced the item;
- the KnowledgeItem ID/version and current status;
- its review eligibility at retrieval time;
- the retrieval result and Context manifest proving it entered the later Task Context.

This makes the causal claim testable: the second run received a specific accepted lesson through the real retrieval path.

## 7. Capability gate

The first scenario should remain within the minimum accepted RW foundation. During RW-0, decide explicitly whether the newsroom value claim requires:
- R7-C capabilities;
- persistent Artifact/output and delivery;
- Consultation requests/answers;
- the setup advisor and TeamDraft;
- expanded domain-pack machinery.

Do not build any of these merely because they appear in the architecture specification. If the selected newsroom scenario cannot be meaningfully scored without one, record the dependency and obtain approval before adding it to a slice. If the first scenario intentionally excludes publication and consultation, state that limitation in the R8 product claim.

## 8. Acceptance and reporting

The harness is ready for scored use only when the Operator has frozen the scenario, corpus, rubric, run count, exclusions, and thresholds. The report for each run must include exact code/PR SHA, CI evidence, source hashes, Context manifest, Task/Outcome/Evaluation references, provider revision, costs, scores, and limitations.

A harness pass requires:
- all deterministic contract proofs to pass independently of the value score;
- no critical evidence-integrity, cross-Team, replay, or scope violation;
- the pre-agreed newsroom quality and retained-experience thresholds to be met;
- confidence-band results to be reported with adequate sample counts and unresolved cases kept separate;
- explicit Operator acceptance.

No numeric threshold is invented in this draft. Until thresholds are frozen, results are descriptive and cannot be labelled a formal pass.
