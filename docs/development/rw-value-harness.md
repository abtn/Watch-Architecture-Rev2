# RW Value Harness — Newsroom First

**Status:** methodology approved during RW-0 on 2026-11-16; concrete experiment package not yet frozen; no scored runs authorized
**First domain:** science-and-technology newsroom research
**Decision authority:** the Operator freezes the actual story package and execution configuration before scored runs and explicitly accepts the final harness result.

## 1. What the harness measures

The harness evaluates whether a Watch Team produces better evidence-grounded newsroom analysis when it receives relevant, accepted, retained experience through the normal retrieval and Context path.

It separates three claims:

1. Relevant, accepted experience is available through retrieval and enters the later Task Context.
2. Specific output claims can be audibly attributed to an exact retained KnowledgeItem version through application-validated evidence and independent review.
3. Treatment outputs improve under independent evaluation compared with matched control outputs.

These are separate measurements. Context availability is not proof of actual claim-level use. Claim-level use is not proof of output improvement. A higher output score alone does not establish that retained knowledge caused the improvement.

The harness is a repeatable product-value check. It does not replace database/contract proofs, and a passing test suite does not establish newsroom value.

The first scenario is one completed, bounded science-and-technology story. The exact story, publication/source set, task brief, and independent outcome reference are not yet selected. They must be prepared and frozen before scored execution. Do not infer a topic or source list from this document.

## 2. Scenario and source package

The frozen scenario should exercise this path:

1. Select one completed story that meets the RW-D101 eligibility criteria.
2. Collect, review, preserve, and freeze a fixed source corpus and manifest.
3. Prepare the scored assignment brief using only the frozen packet.
4. Prepare the source-grounded answer key independently of model outputs.
5. Prepare and freeze the independent outcome reference set, resolution criteria, and evidence cutoff.
6. Establish the pre-experiment accepted experience state and freeze its canonical snapshot.
7. Run the matched control/treatment comparison using identical source and assignment inputs; treatment alone receives the frozen retained-experience snapshot through normal retrieval and Context.
8. Identify claims from immutable outputs and independently assess any explicit claim-to-knowledge relationships.
9. Report newsroom quality, evidence errors, retained-knowledge attribution, independent outcomes, and operational measures separately.

### Story eligibility

Choose one completed science-and-technology story with accessible primary evidence, important claims that can be directly verified against the proposed source packet, meaningful interpretive depth, bounded scope, and sources that can be preserved and independently checked.

Exclude breaking or rapidly changing stories; stories primarily dependent on anonymous or inaccessible sources; stories without sufficient evidence to distinguish established findings from speculation; and stories whose necessary specialist knowledge cannot be represented in the packet.

### Corpus composition and freeze

Determine corpus size by evidentiary sufficiency, not a fixed source count. Prefer original research, official datasets, and direct institutional material. Add independent expert/institutional sources and reputable secondary reporting only where they contribute necessary context, independent verification, qualifications, limitations, or alternative interpretations.

Every included source must contribute relevant evidence or necessary context. Exclude duplicative sources without additional evidence, irrelevant or unverifiable sources, and primarily promotional material. Do not exclude disagreement merely because it challenges a preferred interpretation. Record important candidate sources excluded and the reason.

Freeze the source corpus before writing the final scored brief. Assign a unique corpus ID/version and preserve stable source IDs, metadata, retrieval dates, cryptographic hashes, and exact source files or stable archived copies where possible. No post-freeze additions or silent replacements are allowed. Document corrections explicitly; a material source-set change creates a new corpus version and requires validity assessment and possibly a new experiment instance.

### Assignment brief

Use an identical brief for all 20 original runs. It must specify the task, intended audience, scope and exclusions, evidence rule, required analytical elements, output structure, and one common word limit. The audience is educated general readers without assuming specialist knowledge. The evidence rule limits claims to the supplied packet and requires distinctions between source-supported findings, interpretation, and uncertainty.

Require a headline, central finding, why it matters, evidence/source comparison, limitations and uncertainty, and what remains unknown. Identify sources consistently by packet IDs. Do not disclose the answer key, preferred conclusions, or detailed scoring rubric to generation. Do not reward verbosity or prescribe identical wording or conclusions. The exact word limit is a story-package item and must be frozen before scored runs.

## 3. Controlled comparison and execution structure

Use **10 matched pairs**, each containing one control run and one treatment run, for 10 original control outputs and 10 original treatment outputs.

Within each pair, use the same frozen assignment, source corpus, model/provider configuration, generation settings, tool budget, and baseline identity. Each run starts from an equivalent copy of the same frozen baseline. Control receives no relevant prior accepted newsroom experience. Treatment alone receives the exact frozen retained-experience snapshot through the normal retrieval and Context path.

Prevent contamination:

- Do not let control receive the treatment snapshot through shared storage, prompt text, operator hints, or hidden state.
- Do not give treatment extra source material, different instructions, or a different tool budget.
- Do not let experience written by any scored run become available to another scored run.
- Preserve the complete Context manifest, source Snapshot hashes, Task IDs, provider/model identity, and execution evidence.
- Verify that every treatment run was configured with access to the exact same frozen snapshot identity and hash. Snapshot membership is distinct from what retrieval selects for a Task.
- Do not silently repair an incorrect/missing Context manifest or rerun a protocol-compromised output.

### Matched pairs and balanced blocks

Arrange the 10 pairs as **five blocks of four run slots**. Each block contains two complete matched pairs and therefore exactly two control and two treatment slots.

Before the first scored run, freeze the randomization algorithm and version, initial 20 run-slot IDs and assignments, seed, block order, pair order within each block, condition order within each pair, and complete planned execution order. Execute each randomized four-run block within one predefined operational window. Keep the provider, model version, generation settings, and infrastructure configuration fixed. Preserve the actual order and timestamps. Do not rerandomize or selectively pause/accelerate a condition in response to output quality.

Report condition-level comparisons as primary and all 10 within-pair differences as descriptive evidence. Pairing and blocking improve balance and transparency; they do not establish statistical proof or broad causal identification.

## 4. Measures and predeclared acceptance gates

### 4.1 Newsroom output score — 100 points

Use two distinct scoring components:

| Component | Points |
|---|---:|
| Structured claim verification | 50 |
| Independent editorial assessment | 50 |
| **Total** | **100** |

**Claim verification — 50 points**

| Category | Points |
|---|---:|
| Factual accuracy against the source packet | 20 |
| Evidence traceability | 15 |
| Quotation and attribution accuracy | 7 |
| Numerical and temporal accuracy, including figures, dates, and units | 8 |
| **Total** | **50** |

**Editorial assessment — 50 points**

| Category | Points |
|---|---:|
| Interpretation of findings | 12 |
| Significance without exaggeration | 10 |
| Uncertainty and limitations | 15 |
| Synthesis across sources | 13 |
| **Total** | **50** |

Score each category using five anchored levels:

| Level | Anchor |
|---:|---|
| 4 | Complete — accurate and adequately supported; material requirements satisfied |
| 3 | Strong — substantially correct, with limited non-material omissions or weaknesses |
| 2 | Partial — mixed performance; important elements incomplete or weakly supported |
| 1 | Weak — major deficiencies, unsupported elements, or substantial omissions |
| 0 | Absent/incorrect — requirement is not meaningfully satisfied or treatment is materially wrong |

For a category, calculate points as:

`category maximum × selected level ÷ 4`

This allows quarter-point increments. Freeze story-specific examples, detailed anchors, scoring instructions, and answer-key references before scored runs. Do not reward verbosity, preferred wording, or preferred conclusions. Concise answers receive full credit when they satisfy the requirements.

### 4.2 Critical factual errors

A critical factual error is a materially consequential false, unsupported, or misleading claim that changes the reader's understanding of the central finding, its strength, implications, or evidentiary basis.

Examples include reversing the central finding; presenting correlation as demonstrated causation; inventing or materially altering a result, quotation, or statistic; omitting a limitation in a way that materially changes the conclusion; or misattributing a finding. Minor wording issues and non-material inaccuracies do not qualify.

Count each distinct underlying critical error once per output, even if repeated; count genuinely different errors separately. Report separately for control and treatment:

- total distinct critical factual errors;
- number of outputs affected by at least one critical factual error;
- descriptions, evidence references, and material effect;
- reviewer disagreements and adjudication, if any.

### 4.3 The three primary acceptance gates

All three gates are predeclared and must be reported separately.

**Gate 1 — Downstream quality improvement**

Calculate each condition's mean total score from 10 valid completed outputs. Treatment must exceed control by at least 10 points out of 100:

`mean(treatment) − mean(control) ≥ 10`

Report individual scores and category-level results. The condition-level mean difference is the primary comparison; paired differences are also reported but do not create another threshold.

**Gate 2 — Critical factual errors**

Treatment must not exceed control in either total distinct critical factual errors or the number of outputs affected by at least one critical error. Disclose and examine every critical error in both conditions; aggregate scores cannot conceal them.

**Gate 3 — Claim-level retained-knowledge use**

Independently assess all 10 treatment outputs. At least one independently verified qualifying claim-to-knowledge relationship across the treatment condition is required. This minimum proves only that claim-level attribution occurred in the experiment; it does not imply consistent use across all outputs. Report the full distribution and unsupported attribution attempts. Do not invent a percentage threshold.

### 4.4 Deterministic validation and confidence calibration

Report validation proposal counts: all in-scope proposals submitted, accepted, rejected, rejection counts by stable reason, and acceptance/rejection rates. The denominator is every in-scope proposal presented to validation. Acceptance proves that defined structural/scope/quote/hash/stance/transition/cause checks passed; it does not prove the underlying claim is true. This is descriptive, not an additional pass/fail gate.

For Hypotheses that later resolve against the independent outcome reference, report observed resolution rates separately for Low, Moderate, and High confidence bands, with resolved and unresolved counts per band. Unresolved cases are neither correct nor incorrect. Do not convert ordinal bands into numerical probabilities or calculate a Brier score without a separately justified and explicitly approved probability mapping. This is descriptive, not an additional pass/fail gate.

### 4.5 Operational guardrails

Record provider/model identity and revision, cost, latency, tool-call count, failures, retries, incomplete slots, and relevant infrastructure incidents for every run and attempt. These are comparability/operational measures, not substitutes for quality.

## 5. Independent answer key, outcome reference, and reviewers

### Source-grounded answer key

Prepare the answer key before scored runs and independently of model-generated outputs. For each expected factual claim, record its source and exact location, supported statement, qualifications/limitations, central-or-secondary importance, and known ambiguity or source disagreement. Identify important facts the packet does not establish, potentially unsupported/misleading claims, and acceptable alternative interpretations. Do not make the key a closed list of approved wording: a novel claim may receive credit when its underlying factual content is accurate and supported by the frozen packet.

### Independent outcome reference set

Prepare a separate, versioned reference set before scored execution. For each material tracked finding/Hypothesis, record a stable reference ID, the statement and scope evaluated, supporting and challenging evidence with exact source references, resolution conditions, status, and rationale.

Use three classifications: **supported**, **contradicted**, and **unresolved**. Support or contradiction requires the predefined evidence and resolution conditions to be met. Insufficient or conflicting evidence remains unresolved; absence of evidence is not contradiction. Define resolution criteria before observing scored outputs and freeze them with a fixed evidence cutoff. Later discoveries do not silently change the original result; preserve them as subsequent evidence and assess whether a new reference-set version or experiment is required. Determine outcomes independently of scored outputs; human outcome reviewers should be blind to condition where feasible. Model-generated evaluation may contribute evidence but cannot be the sole authority.

### Independent output review

Use two independent reviewers for every output. Use the same two reviewers for all 20 outputs. They must have sufficient science/technology literacy and evidence-evaluation ability; professional journalism credentials are not required. Reviewers must not have generated scored outputs and should, where practicable, be independent of story/source selection and answer-key preparation. Disclose qualifications, conflicts, experiment relationships, and limitations.

Give reviewers anonymized outputs without condition labels. Randomize presentation order, use balanced batches and breaks, and preserve batch/order metadata. Before scored review, conduct calibration on sample analyses excluded from the 20 experimental runs. Reviewers independently score the same examples, discuss discrepancies, and clarify anchors. Accept calibration qualitatively when the critical-error definition and both 50-point components are applied consistently and no materially consequential anchor ambiguity remains; do not impose a numerical inter-rater reliability threshold.

Reviewers submit independent scores before discussing disagreements. Preserve both original assessments. Require formal disagreement resolution when total scores differ by more than 10 points, reviewers disagree about a critical error, or they disagree whether a central claim is unsupported or materially misleading. Reconcile against the frozen answer key/rubric; a third qualified reviewer adjudicates unresolved material scoring disagreements. Do not automatically average scores to conceal disagreements. Preserve original judgments, rationale, adjudication, and final score.

### Claim-level retained-knowledge review

Only accepted, versioned Team Experience eligible under current lifecycle/review rules counts. A proposed LearningChange, unapproved/stale/retired KnowledgeItem, embedding match alone, or transcript text does not count.

A qualifying claim-level relationship requires:

- an identified claim in the immutable output;
- exact KnowledgeItem ID/version and originating LearningChange;
- immutable application-written TaskKnowledgeReference;
- relevant Team eligibility and immutable Task Context evidence proving the same version entered that Task's Context;
- application validation of identity, version, eligibility, and Context linkage; and
- independent reviewer judgment that the knowledge materially supported, qualified, or corrected/prevented a misleading interpretation in that claim.

Mere topical similarity, passing mention, irrelevant citation, or an unsupported model assertion does not count. A Context manifest proves availability, not use.

Reviewers identify claims from the actual immutable output, including substantive headlines/headings and meaningful uncertainty assertions. Split independently evaluable compound claims; do not count repeated statements of the same underlying claim separately. Both reviewers independently create claim inventories and reconcile differences; unresolved inventory disputes go to a third qualified reviewer. Keep claim inventory and claim-to-knowledge relationship records separate.

Report unique relationships as qualifying, non-qualifying, or indeterminate; relationship counts and technical validation failures; output-level qualifying-use distribution across all 10 treatment outputs; and treatment-level aggregate results. Preserve both reviewers' original classifications and any adjudication. Do not impose a percentage threshold beyond the minimum in Gate 3.

## 6. Frozen retained-experience snapshot

Only accepted, current, eligible Team Experience is included. The canonical snapshot manifest must enumerate every KnowledgeItem ID and exact version, originating LearningChange ID, Team, freeze time, and eligibility state used during construction. Serialize as deterministic versioned canonical JSON, preserve exact bytes, and compute SHA-256 over those bytes. Record the algorithm and lowercase hexadecimal digest.

Before the first treatment run, independently recompute and verify the digest. Verify every treatment run references the same frozen snapshot identity and digest through the intended retrieval path. Hash verification establishes identity and consistency, not relevance or actual claim-level use.

After freeze, the manifest, canonical bytes, hash, and membership are immutable. Any addition, removal, replacement, or change to a KnowledgeItem requires a new snapshot identity. Before the first scored run, a corrected snapshot may be frozen if all pre-run verification is repeated. After the first scored run, do not silently change remaining runs to another snapshot: stop the affected experiment and obtain an explicit Operator decision whether to restart under a new experiment ID and repeat all 10 control and 10 treatment runs. Do not pool runs across experiment instances.

## 7. Execution failures, retries, and deviations

Assign stable IDs to the 20 original run slots and distinct attempt IDs. Preserve every attempt, partial output, configuration, logs, timestamp, cost, and failure reason.

A returned response is evidence and is retained/evaluated even if poor, incomplete, malformed, or refused. It is never retried because of content or score. Permit one retry after the initial attempt only for an objectively evidenced technical failure before a complete output artifact exists, such as transient provider/server unavailability, network failure/timeout, rate limiting, or worker interruption. Apply the same rule to both conditions.

If the original slot remains technically incomplete after its permitted retry, at most one separately identified replacement slot may be used under the predeclared replacement schedule and explicit Operator disposition. It remains in the same condition and uses the same frozen inputs/configuration/snapshot; it receives the same one-retry limit. No valid output may be replaced; no replacement may depend on output quality or score; no replacement of a replacement is permitted. Preserve the original slot and all attempts. If fewer than 10 valid outputs per condition are obtained under these rules, the experiment is incomplete and cannot pass the mean-score gate.

Do not stop early because results look unusually good or poor. Material execution changes (provider/model/weights, generation settings, prompts, Context construction, retrieval/embedding configuration, or consequential infrastructure changes) require a pause and validity assessment before resumption. Preserve before/after configuration, affected runs, independent reviewer assessment, Operator decision, uncertainties, and deviation register. The Operator alone authorizes resumption, stopping, or restart. Disclose every deviation. Critical deviations require stopping or restarting. Follow the frozen incident and restart rules; never rerandomize or combine different experiment instances.

## 8. Reporting and gate disposition

Use the final reconciled/adjudicated score as the official score while preserving both original reviewer assessments, critical-error judgments, disagreements, and adjudication rationale.

For each condition, report mean, median, minimum, maximum, category-level scores, and every individual output score. Report all 10 matched-pair differences, observed distributions/spread, incomplete slots, and relevant uncertainty/limitations. Do not add a p-value, statistical-significance test, confidence-interval threshold, or inferential-statistics requirement as an acceptance gate. Ten runs per condition are a bounded engineering evaluation, not proof of general statistical superiority or broad causal effectiveness.

The final report must include:

1. Experiment ID and frozen protocol/configuration.
2. Story, corpus/version/manifest, source hashes, and assignment/word-limit identities.
3. Baseline and treatment-snapshot identities/hashes and verification results.
4. Planned run slots, pairs/blocks, randomization record, attempts, retries, replacements, and incomplete slots.
5. Reviewer qualifications/conflicts, calibration, blinding, batch/order, original assessments, disagreements, and adjudications.
6. Total/category/individual scores and matched-pair differences.
7. Critical factual errors and affected outputs.
8. Claim-level retained-knowledge relationships and output-level distribution.
9. Independent outcome classifications and confidence-band results.
10. Validation proposal counts/rates and operational cost, latency, tool calls, failures, and deviations.
11. Limitations, sensitivity analyses where required, and interpretation boundaries.
12. Pass/fail/not-assessable disposition for each of the three primary gates and the Operator's final decision.

A gate is **pass** when its required evidence is available and the predeclared condition is met; **fail** when evidence shows it was not met; and **not assessable** when evidence is missing, incomplete, or insufficient. An unassessable primary gate cannot be reported as a successful harness pass. Final acceptance remains with the Operator.

## 9. Capability and authorization boundaries

The first newsroom scenario is limited to reasoning quality, retained-experience retrieval/reuse, claim-level attribution, and independently evaluated downstream benefit.

Include only D99's minimum R7-C capabilities: application-written immutable TaskKnowledgeReference and minimal typed, application-validated KnowledgeUseAssessment. The implementation plan must map them to named RW slice(s) and proof obligations before authorizing any slice that implements them. This does not authorize a separate R7-C milestone or broader retrieval benchmark/label-provenance/autonomous evaluation subsystem; those remain harness responsibilities.

Exclude persistent production Artifacts, general-purpose rendering, publishing, distribution, and delivery from the first newsroom scenario and RW foundation. Preserve experiment records as harness evidence without implying a production Artifact subsystem. Preserve the accepted Artifact source vocabulary in the EvidenceLink target contract; operational Artifact support may remain staged until an entity/use case is authorized.

Operational Consultation entities and Tasks are not a prerequisite for the first newsroom scenario. Preserve ADR-0020's accepted Consultation EvidenceLink source vocabulary. Defer broad human input-curation/domain-guidance design until after R8 tests. Use a human-configured Team and existing generalist defaults; do not add setup-advisor, TeamDraft, or expanded domain-pack machinery without a demonstrated requirement and explicit approval.

This document freezes the measurement methodology, not the actual story package. The selected story, frozen source corpus, scored brief, answer key, independent outcome reference, story-specific scoring examples, reviewer calibration samples, and exact execution configuration remain to be prepared and frozen (or explicitly tracked as pre-execution deliverables with named owners and acceptance gates) before scored runs. This document does not authorize RW implementation or scored execution.
