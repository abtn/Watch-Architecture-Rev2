# RW Newsroom Scenario Package — Selected Story RWN-01 (LEAP), Draft

**Status:** RWN-01 story identity selected by the Operator on 2026-11-16; source corpus and scored package not frozen; no scored runs authorized  
**Prepared:** 2026-11-16  
**Decision authority:** Operator, under RW-D101–D105 and RW-D135  
**Scope:** candidate story, proposed source manifest, draft assignment, answer-key outline, independent outcome-reference candidates, and remaining freeze gates

> This document is a preparation artifact, not a corpus manifest and not an authorization. Do not use it as a frozen scored packet. The publisher article is currently an Article in Press whose version will be replaced automatically by the final Version of Record. Any later publisher version must be treated as a new corpus version, not silently substituted.

## 1. Selected story

### Approved story identity

**Working headline:** *Can a literature-trained AI help select better perovskite additives? A three-round experiment shows promise—and important limits.*

**Primary research article:** Xin-De Wang, Zhi-Rui Chen, Ze-Feng Gao, Peng-Jie Guo, Cheng Mu, and Zhong-Yi Lu, “A closed-loop framework for perovskite precursor additive discovery,” Communications Materials (2026), published 4 November 2026, DOI [10.1038/s43246-026-01407-3](https://doi.org/10.1038/s43246-026-01407-3). Publisher page: https://www.nature.com/articles/s43246-026-01407-3. Publisher reference PDF: https://www.nature.com/articles/s43246-026-01407-3_reference.pdf.

**Publisher version observed:** Article in Press, 13-page reference PDF. The publisher states that this version is citable and has a permanent DOI, but will be replaced automatically by the final Version of Record. Received 29 May 2026; accepted 5 October 2026; published 4 November 2026. Article licence shown by the publisher: CC BY-NC-ND 4.0. Preserve and cite the exact version used. Do not adapt or publicly redistribute altered article material.

### D101 eligibility assessment — provisional pending final source review

| Criterion | Assessment |
|---|---|
| Completed, non-breaking story | Strong: a peer-reviewed, accepted research article published 4 November 2026; not a developing breaking-news item. |
| Accessible primary evidence | Strong: publisher full text/reference PDF plus an author-maintained public data-release repository. |
| Claim-level verifiability | Strong for the core reported workflow, model benchmark, three tested additives, device-level aggregate statistics, and the authors’ stated limitations. |
| Interpretive depth | Strong: combines a specialized LLM, mechanistic descriptors, Gaussian-process surrogate modelling, expected improvement, expert feasibility review, prospective device tests, and feedback from failed/successful rounds. |
| Bounded scope | Strong: one published proof-of-concept, one perovskite device platform, three validation rounds, and three prospective additives. |
| Preservation/reproducibility | Conditional: public data release can be pinned to a Git commit; publisher PDF and supplementary material still require local preservation, metadata capture, and SHA-256 hashing. |

**Operator selection — 2026-11-16:** the Operator approved RWN-01 as the selected newsroom story identity. This approval does not freeze the source corpus, final assignment, answer key, outcome reference, or execution configuration. Before corpus freeze, preserve and inspect the exact publisher Article in Press PDF and acquire the publisher-listed Supplementary Material: the article explicitly says that Welch-test confidence intervals are reported there. Assess whether any claims retained in the final assignment also require the author-requested raw device data.

### Why this story is useful for the harness

It tests whether an analysis can explain a compound workflow accurately without confusing model output with experimental validation or expert judgement. It has a meaningful negative round (Boc-DCPy), later positive rounds (6-CDQ and 2-CNA), a retrospective ablation, a small benchmark against human/model references, and explicit limitations. It is therefore less vulnerable to a one-sided “AI breakthrough” summary than a story with only a single positive headline result.

The key distinction is that LEAP is reported as an expert-in-the-loop framework, not a fully autonomous materials-discovery system. The paper describes preliminary proof-of-concept evidence, not general proof across materials, devices, or domains.

## 2. Proposed source corpus manifest (not frozen)

**Proposed corpus ID:** RWN-01-LEAP-AIP  
**Proposed corpus version:** 0.1-draft  
**Proposed retrieval date:** 2026-11-16  
**Freeze status:** story identity selected; publisher binary capture, Supplementary Material acquisition/review, complete source inventory, packet archive, and final corpus review remain outstanding.

The exact article and included public data files must be preserved as immutable bytes or stable archived copies. For the enumerated GitHub files below, exact byte streams were retrieved from the GitHub file API at the pinned commit and SHA-256 was computed over the Base64-decoded bytes. Git blob SHA-1 identifiers remain separate from packet SHA-256 values. The identified GitHub file hashes are now recorded; the publisher PDF and Supplementary Material remain unacquired or unverified.

| Source ID | Source and intended contents | Version/identity | Status |
|---|---|---|---|
| SRC-001 | Publisher research article; full text, methods, results, figures/captions, discussion, limitations, data availability, and licence. | DOI 10.1038/s43246-026-01407-3; Article in Press reference PDF URL above; 13-page version extracted 2026-11-16. | Publisher page and PDF text extraction inspected; binary download and page screenshots were unavailable (cache miss); exact PDF byte length/archive and SHA-256 remain pending. The final Version of Record must be treated as a new version. |
| SRC-002 | Official author data-release repository README and licence. | WD928/LEAP, pinned commit `f25fbe8238422439db10877ea79295ec233c4867`; root `README.md` and `LICENSE`. | Exact byte streams retrieved at the pinned commit and hashed: README 4,307 bytes, SHA-256 `9667b9c5f3f502b95bc2059e2b9f152eb30a1aa56f0ae197d49c88a08164c2c3`; LICENSE 11,547 bytes, SHA-256 `325e363ee2fd1a9efce65cdaa58c9cca365129d5b6ebe2aa206c239f1156a6cb`. Stable commit/path locators recorded; local packet archive remains to be staged. |
| SRC-003 | Candidate-selection data and definitions, including round-specific top-50 shortlists, ranks, GP predictions, uncertainty, expected improvement, descriptor scores, and advancement status. | `candidate_selection/top50_validation_shortlists_mechanism_scores.csv` (Git blob SHA-1 `7143342e0d864db71e71da442f47a227bce9f633`); `candidate_selection/README.md` (Git blob SHA-1 `9fff092854e0bfb1253bf8ac592dd4a32a4cb110`). | Exact bytes retrieved at pinned commit. README: 2,275 bytes, SHA-256 `a4ae89691aa727b88fb8f9794ead23224c49fdd35998abdbe745c7491c6217cb`. Shortlist CSV: 61,461 bytes, SHA-256 `625535a4e197ceb0fd26ac79fbe8f590ef0ab621de713e362b6bd3b53c603b04`. |
| SRC-004 | Hot-start data, descriptor definitions, and data dictionary. | `data/hot_start_additives.csv` (Git blob SHA-1 `69ff60da0210d8eabf475b3081f229e47cc90b18`); `data/hot_start_data_dictionary.json` (SHA-1 `d52ed76b5606c37d9e1c60a40c26fdd6f3fa7749`); `data/README.md` (SHA-1 `81d34a2f610d49b2f98b1384ef3f4ed2f9826c9b`). | Exact bytes retrieved at pinned commit. `data/README.md`: 405 bytes, SHA-256 `195ec1e39a3e6db59c0b934ada709fd123cf2732fdec1f4e943b678acab2b6df`; hot-start CSV: 13,466 bytes, SHA-256 `7dc9ea48f65b3c32724ae0460fef1306ac8c5eb2c70bfb009b5e789b20f2357c`; dictionary JSON: 8,421 bytes, SHA-256 `773156bc6304b3c77398da4c80a58611160278900536dcef4ddc395c76b9726f`. |
| SRC-005 | Mechanism-consistency benchmark, released benchmark questions/source list, six per-model response CSVs, summary statistics, and representation-ablation confidence intervals. | `benchmark/benchmark_sources.csv` (Git blob SHA-1 `72d5f2b346833feb2494c027297426a2d735f924`); `benchmark/questions.csv` (SHA-1 `ee1ac1c97cafa6fac530aec122d0a7eba37be1e4`); six `benchmark/model_results/*_results_ordered.csv` files; `benchmark/statistics/model_summary_with_ci.csv` (SHA-1 `132ca58cf4e8ec71683011425df62b47b82f0665`); `benchmark/statistics/mcnemar_vs_reference_holm.csv` (SHA-1 `f063293656cfd8f5cd2d7f495aa7dbc8eb87e84f`); `ablation/representation/figure3_bootstrap_ci_table.csv` (SHA-1 `283d40f85a3a10c290a227da78fa3a4609eb2318`). | Exact bytes retrieved and SHA-256 hashed at pinned commit for the sources CSV, questions CSV, six per-model response CSVs, two statistics CSVs, and representation CI table; see exact-byte log. The private/source PDF files behind the benchmark questions are not included in this public repo. |
| SRC-006 | Publisher Supplementary Information PDF, including the tables/figures referenced from the main text (notably Tables S3/S5 and Figure S5/S6/S9). | Listed as “Supplemental Material (download PDF)” on the official article page; the PDF also says device-comparison confidence intervals are reported in Supplementary Information. Exact direct file URL/version not captured. | Required before freezing any assignment that reports the paper’s Welch-test confidence intervals or supplementary device analyses. Binary/direct URL not acquired; review and inclusion decision remain open. |
| SRC-007 | Publisher Transparent Peer Review file. | Listed as “Transparent Peer Review file (download PDF)” on the official article page; exact direct file URL/version not captured. | Optional corroborating context. Acquire only if needed to assess a material methodological qualification; if excluded, record that decision and rationale. |

### Exact-byte hash capture log — author data-release repository

The following bytes were retrieved from the GitHub file API at commit `f25fbe8238422439db10877ea79295ec233c4867` on 2026-11-16 using Base64 content responses. SHA-256 was computed over the decoded bytes. Git blob SHA-1 is shown separately. These are exact-byte hashes, not claims that a local archive has already been staged in the Watch repository.

| Path | Bytes | Git blob SHA-1 | SHA-256 |
|---|---:|---|---|
| `README.md` | 4,307 | `0c2a9a10fc4c09e6f11bacd4bd523eb2b48e8e21` | `9667b9c5f3f502b95bc2059e2b9f152eb30a1aa56f0ae197d49c88a08164c2c3` |
| `LICENSE` | 11,547 | `261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64` | `325e363ee2fd1a9efce65cdaa58c9cca365129d5b6ebe2aa206c239f1156a6cb` |
| `candidate_selection/README.md` | 2,275 | `9fff092854e0bfb1253bf8ac592dd4a32a4cb110` | `a4ae89691aa727b88fb8f9794ead23224c49fdd35998abdbe745c7491c6217cb` |
| `candidate_selection/top50_validation_shortlists_mechanism_scores.csv` | 61,461 | `7143342e0d864db71e71da442f47a227bce9f633` | `625535a4e197ceb0fd26ac79fbe8f590ef0ab621de713e362b6bd3b53c603b04` |
| `data/README.md` | 405 | `81d34a2f610d49b2f98b1384ef3f4ed2f9826c9b` | `195ec1e39a3e6db59c0b934ada709fd123cf2732fdec1f4e943b678acab2b6df` |
| `data/hot_start_additives.csv` | 13,466 | `69ff60da0210d8eabf475b3081f229e47cc90b18` | `7dc9ea48f65b3c32724ae0460fef1306ac8c5eb2c70bfb009b5e789b20f2357c` |
| `data/hot_start_data_dictionary.json` | 8,421 | `d52ed76b5606c37d9e1c60a40c26fdd6f3fa7749` | `773156bc6304b3c77398da4c80a58611160278900536dcef4ddc395c76b9726f` |
| `benchmark/benchmark_sources.csv` | 2,607 | `72d5f2b346833feb2494c027297426a2d735f924` | `ada005499999ee3d673fa38317e5a32f5a9a31e938857555c23441d81a94037f` |
| `benchmark/questions.csv` | 53,478 | `ee1ac1c97cafa6fac530aec122d0a7eba37be1e4` | `479a64729d82e346b253c25fb7bcac856d59dbe77e7607a5c9ab24b35df72dea` |
| `benchmark/statistics/model_summary_with_ci.csv` | 771 | `132ca58cf4e8ec71683011425df62b47b82f0665` | `80e8344b8225806c4156f46498853394d6a516be09f8c2de9da56d59b8d1eb7c` |
| `benchmark/statistics/mcnemar_vs_reference_holm.csv` | 540 | `f063293656cfd8f5cd2d7f495aa7dbc8eb87e84f` | `11aaea3369649ff58f241ccc8e6b079494c992a848df672dbb7b871a0d34d248` |
| `benchmark/model_results/DeepSeek-V3.2_results_ordered.csv` | 9,416 | `131a237b9aff2a183c9c41a9fad07eccac941452` | `1b567043f3efc2c2b4c37f6cdc40290c53666092f5fa039ec3bf165c9315a8fb` |
| `benchmark/model_results/GPT-5_results_ordered.csv` | 9,416 | `92a176c4d4fe8296329166ed678742439456a9b6` | `763d5b968b2334a8fb56ce3e953177eec9ce4e5eb6f85eab0009f78dc2cc51ec` |
| `benchmark/model_results/Perovskite-RL_results_ordered.csv` | 9,416 | `a1c4893ca7c35254377789d40442e025e4431e28` | `1236f43de3d1151f2d0b123cddc663762a914d70091e33d11faf703519c01145` |
| `benchmark/model_results/Qwen3-32B_results_ordered.csv` | 9,416 | `9fde0b7540f78e10c1f5d8069acee1a6c06dff27` | `39b890934cb65fce460ab7cd48c8d67d2df6126fd3d0291b8187050cad3f922f` |
| `benchmark/model_results/gemini-3-flash_results_ordered.csv` | 9,416 | `f3a0ad327e7362d91368c233fad5139fb7530526` | `db5cdc40e3a718ba39f4f91d240317d902cf23e553a22ff4bcde5bbb6d42178f` |
| `benchmark/model_results/llama-3.3-70b-instruct_results_ordered.csv` | 9,416 | `eef6ad695cec4bc9c34432cdb3238ee54736bb64` | `ed32eb82f0179712d24a38f88577d7948c79ed18bb959111cde393f53df972a8` |
| `ablation/representation/figure3_bootstrap_ci_table.csv` | 997 | `283d40f85a3a10c290a227da78fa3a4609eb2318` | `741d7c3f7ecd8d335b1018d2398bdcc0621699cb2695047976ae1e6bf71fefdc` |

The repository README says it is a data release, not a complete reproduction package. The pinned `benchmark/model_results/` directory listing contained exactly the six per-model response CSVs above; each was retrieved at the pinned commit, measured at 9,416 bytes, and SHA-256 hashed over its decoded bytes. GitHub's returned Git blob SHA-1 matched the directory listing for every CSV. This does not mean the private source PDFs used to build the benchmark question set are included in the repo; the repository does not contain those raw PDFs.

### Source inclusion/exclusion notes

- Include the publisher Article in Press version only as one exact, versioned source. Do not mix text or tables from the May 2026 arXiv preprint with the November 2026 publisher version.
- Pin the public data repository at commit f25fbe8238422439db10877ea79295ec233c4867. The repository README says it is a data release, not a complete reproduction package: model weights, Hugging Face training datasets, raw PDFs, logs, procurement tables, and the full internally curated candidate pool are not stored there.
- The repository’s data/hot_start_additives.csv contains 36 characterized additives. The candidate_selection CSV contains 50 released shortlist entries for each of three rounds (150 rows total), not all candidates in each generated pool.
- The candidate-selection README explicitly warns that not advanced in this campaign does not establish that a specific molecule was individually reviewed and rejected. Do not infer molecule-specific expert rejection from that field.
- The main article says the SFT/GRPO training data are on Hugging Face and model weights are separately available there. They are not required for this newsroom reading task unless the Operator decides model reproducibility is part of the task.
- The article says additional raw experimental data are on institutional servers and available from corresponding authors on reasonable request. Do not describe the public LEAP data repository as containing all raw device-level data.
- The article states that its storage/thermal/ambient stability tests used unencapsulated devices and involved neither continuous illumination nor maximum-power-point tracking. Do not describe these as demonstrated operating lifetime.
- Do not add secondary reporting merely to increase source count. If the source packet is evidentially sufficient with the primary article and the author’s public data release, keep it that way. Any additional source must add necessary independent verification, context, qualification, or alternative interpretation under RW-D102.

### Required source-capture fields before corpus freeze

For every included source preserve: stable source ID; exact title; author/organization; publication/version date; DOI or stable URI; retrieval timestamp; licence/access terms; exact original file or stable archived copy; byte length; SHA-256 algorithm and lowercase digest; repository commit/blob locator where relevant; and inclusion rationale. Record important candidate sources excluded and why. Keep GitHub’s Git blob SHA-1 separate from the packet SHA-256.

**Current binary capture limitation:** the publisher page and 13-page Article in Press PDF text extraction were inspected, but attempts to retrieve the PDF binary and screenshots of pages 1, 12, and 13 returned cache-miss/download failures. The PDF binary, its byte length, local preservation, and SHA-256 are therefore still missing. The official page lists both the Supplementary Material PDF and Transparent Peer Review PDF, but their direct URLs and binaries were not obtained. These are explicit freeze blockers, not completed source-verification claims. The public data-file hashes above were computed from exact byte responses, but the files have not yet been staged into a local corpus archive.

## 3. Draft scored assignment brief (proposed; not frozen)

**Proposed word limit:** 700 words maximum. This is a draft value for Operator review, not yet frozen under RW-D47. Freeze the exact limit after the final story package and brief are reviewed.

### Task

Write an evidence-grounded science-and-technology news analysis explaining what the LEAP study demonstrates about using literature-grounded language-model reasoning and active learning to prioritize precursor additives for perovskite solar cells.

Explain how the workflow operates, what evidence supports its results, how the prospective device tests compare with the control, and what the experiment does not establish. Treat the study as a bounded research result rather than assuming its strongest interpretation.

### Intended audience

Educated general readers who are interested in science and technology but should not be assumed to know perovskite chemistry, Bayesian optimization, or photovoltaic-device characterization.

### Scope

Use only the frozen source packet. Do not introduce later versions, live web-search material, external performance records, or unsupported background claims. Define technical terms briefly where needed. Keep the discussion within this one study and the reported device platform.

### Evidence rule

Identify material factual claims with packet source IDs and the relevant page, section, figure/table, or data-file location. Distinguish clearly between:
- what the authors directly report;
- what the measurements are consistent with;
- what the authors interpret or hypothesize; and
- what remains unestablished or unresolved.

Do not present model-generated mechanism scores as experimentally proven mechanisms. Do not infer expert rejection reasons for candidates not individually documented. Do not equate device replicates with independent candidate molecules or independent experimental campaigns.

### Required output sections

1. Headline.
2. Central finding.
3. Why it matters.
4. Evidence and comparison across the workflow and prospective results.
5. Limitations and uncertainty.
6. What remains unknown.

Do not include material outside these sections. Source identifiers must be consistent across all outputs. No answer key, preferred conclusion, or detailed scoring rubric will be supplied to the generation worker.

## 4. Source-grounded answer-key outline (reviewer-only; never provide to generation)

This is an outline for the independent key, not a closed list of approved wording. Reviewers may credit an accurate, packet-supported claim that is not written here. The final key must be expanded with exact page/section/figure/table or dataset locations after SRC-001 and the supplementary files are captured.

### A. What LEAP is

- LEAP means LLM-driven Exploration via Active Learning for Perovskites.
- It combines a domain-specialized model (Perovskite-RL), literature-grounded mechanistic descriptors, hard molecular descriptors, a Gaussian-process surrogate, expected-improvement acquisition, expert feasibility review, and feedback from experimental validation.
- It is explicitly expert-in-the-loop. Model-ranked candidates are not automatically sent to the laboratory.
- Five mechanism-relevant descriptor dimensions are reported: binding mode, interfacial shielding, hydrophobic protection, ion-interaction potential, and electronic modulation; an overall predicted-effect score is also used in the full soft representation.
- Soft descriptors are generated through repeated probabilistic reasoning and aggregated; the methods report 10 sampled trajectories at temperature 0.7. The article describes a training corpus of 1,264 literature articles and adapting Qwen3-32B through SFT and RL. Preserve distinctions between literature training, descriptor generation, candidate-pool generation, and prospective device testing.

### B. Mechanism-consistency benchmark

- 32 multiple-choice questions were drawn from 11 literature studies excluded from the model’s training corpus.
- Perovskite-RL answered 25/32 correctly (78.1%); reported 95% Wilson interval: 61.2%–89.0%.
- Three human experts scored 27/32, 27/32, and 28/32 (mean 85.4%).
- Perovskite-RL outscored the tested model baselines in this 32-question set, but did not exceed the human-expert reference. The paired comparison against the human-expert majority-vote reference was −2 correct answers for Perovskite-RL, p = 0.727 (rounded in the paper to 0.73), not statistically significant.
- This was described as a focused sanity check, not an exhaustive model ranking or proof that the model exceeds expert reasoning.

### C. Retrospective representation ablation

- The retrospective set contained 36 hot-start additives.
- Hard-feature baseline: Spearman correlation 0.274; top-20% overlap 0.125.
- Hybrid LEAP representation: Spearman 0.394; top-20% overlap 0.375; a small RMSE improvement relative to the hard baseline.
- The mechanism-soft representation, not the hybrid representation, had the highest top-20% overlap (0.500). Hybrid tied Full-soft at 0.375 for that metric.
- The authors characterize the effect as modest and metric-dependent, not uniform superiority across all metrics.
- These were retrospective analyses, not prospective device validation of every shortlisted candidate.

### D. Candidate generation, ranking, and expert review

- The workflow scored pools of 25,639, 13,380, and 20,630 candidates in rounds 1–3; round 3 applied functional-group filtering to a final pool of 5,187 before shortlisting.
- Each round produced a top-50 EI shortlist for qualitative expert feasibility review.
- Tested additives occupied shortlist positions 25 (Boc-DCPy), 1 (6-CDQ), and 10 (2-CNA). They were advanced after qualitative expert review, not simply by automatically testing the highest EI-ranked candidate.
- Expert review considered chemical plausibility, commercial availability, precursor compatibility, solubility/processability, safety, cost, and device-fabrication feasibility.
- The released top-50 data do not document that each non-advanced molecule was individually reviewed/rejected; not advanced in this campaign must not be interpreted as a molecule-specific rejection label.

### E. Prospective device results

- One candidate was experimentally tested per round, in one device architecture.
- Round 1 Boc-DCPy did not improve performance: mean PCE 16.76 ± 0.58% compared with control 19.25 ± 0.28%; champion PCE 17.60% compared with control 19.85%.
- Round 2 6-CDQ: mean PCE 20.13 ± 0.25%; champion 20.57%.
- Round 3 2-CNA: mean PCE 20.87 ± 0.25%; champion 21.32%.
- The paper reports 24 devices per condition across four independent fabrication batches, with six devices per condition per batch. Device count is not candidate count: only three distinct LEAP-prioritized additives were prospectively tested.
- Mean PCE changes versus control were −2.49 percentage points for Boc-DCPy, +0.89 for 6-CDQ, and +1.62 for 2-CNA. Do not confuse percentage points with relative percentage change.
- The negative first-round result was added to the accumulated training set; the GP and Perovskite-RL prompting context were updated before the next candidate round. This is an important example of feedback, not a reason to omit the failed round.

### F. Non-LEAP comparison and causal limits

- The non-LEAP route tested three expert-selected additives under the same general device architecture/testing conditions.
- The authors describe this as a practical reference only: it was neither randomized nor exhaustive and is not a definitive comparison of LEAP versus experts.
- Prospective performance reflects the combined workflow (model ranking, expert feasibility review, changing candidate pools, and experimental feedback). It does not isolate the independent causal contribution of each component.

### G. Mechanistic and stability interpretations

- FTIR observations were consistent with interactions involving 6-CDQ and 2-CNA with PbI₂, and 2-CNA with FAI; accompanying XRD, optical, SEM, photophysical, and electrical measurements were consistent with improved film/device characteristics.
- The authors explicitly state that these results do not constitute atomistic proof of every model-assigned descriptor. Mechanistic rationales are hypotheses to be checked against experiments, not facts established by model output.
- Reported stability tests were storage in nitrogen at 25 °C (528 h), thermal storage in nitrogen at 65 °C (528 h), and ambient air at 20 °C/45 ± 5% RH (480 h), all on unencapsulated devices.
- The methods explicitly state that those tests involved neither continuous illumination nor maximum-power-point tracking. They cannot be described as demonstrated operational lifetime under working conditions.

### H. Explicit scope limitations

- Proof of concept, with three prospective candidates and one candidate tested per round, in one device architecture.
- The authors say more prospective campaigns are required to quantify discovery efficiency, robustness, and failure modes.
- Expert review was qualitative rather than a structured accept/reject dataset for all shortlisted molecules; no precise expert-rejection fraction or per-molecule rejection reasons are available for all untested candidates.
- The mechanism-aware representation has not been shown to generalize across other perovskite compositions, device structures, or materials-discovery domains.
- The retrospective ablations are based on limited experimental data and do not prove optimal representation/acquisition design.
- The article frames the result as application-level repurposing of known small molecules as precursor additives, not as synthesis of wholly new chemical compounds.
- The devices are approximately 1.55 eV; the authors say the study compares additives on a fixed platform and does not establish an efficiency record for that bandgap.

## 5. Independent outcome-reference candidates (draft; freeze separately)

Prepare the versioned independent reference set before scored execution, using the exact source packet and a fixed evidence cutoff. The following are proposed tracked claims and evidence resolutions. Final wording, scope, and exact source locations require independent reviewer review before freeze.

| Reference ID | Claim scope to resolve | Draft classification | Evidence/resolution basis |
|---|---|---|---|
| OUT-01 | LEAP is a fully autonomous model that sends its highest-ranked candidate directly to experiments without human review. | Contradicted | Article workflow/methods state qualitative expert feasibility review precedes validation; selected candidates were not simply auto-advanced by rank. |
| OUT-02 | The mechanism-consistency benchmark shows Perovskite-RL outperformed the human-expert reference. | Contradicted | Article reports 25/32 versus expert 27/32, 27/32, 28/32; model vs majority vote difference −2, p = 0.73. |
| OUT-03 | The 32-question unseen-literature check establishes broad superiority over general-purpose models. | Unresolved / scope not established | The benchmark compares specified models on a bounded set of 32 questions from 11 papers; broader model/domain superiority is not tested. Do not turn absence of a test into a contrary empirical result. |
| OUT-04 | Hybrid LEAP representation is uniformly better than every alternative on every reported retrospective metric. | Contradicted | Hybrid has best Spearman and ties Full-soft on top-20 overlap; Mechanism-soft has the highest top-20 overlap; RMSE difference is small. |
| OUT-05 | All three prospectively tested LEAP-prioritized additives improved mean PCE over control. | Contradicted | Boc-DCPy mean PCE is lower than control; 6-CDQ and 2-CNA are higher. |
| OUT-06 | The reported later-round PCE means exceed the control mean in the tested device platform. | Supported | Article reports 20.13% and 20.87% versus 19.25%, with 24 devices per condition across four batches; supplementary/raw-data capture is required before locking detailed statistical criteria. |
| OUT-07 | The prospective validation tested many distinct candidates in each round or established broad prospective hit rate. | Contradicted / scope not established | Only one candidate per round was device-tested; 24 devices are device replicates, not 24 candidate molecules. |
| OUT-08 | The three expert-selected non-LEAP candidates establish a definitive randomized comparison against LEAP selection. | Contradicted | Article explicitly says the three-candidate comparison was not randomized or exhaustive and is only a practical reference. |
| OUT-09 | The reported FTIR/film/device findings prove every proposed atomic mechanism assigned by the model. | Contradicted | Authors say the measurements are consistent with a mechanism-linked explanation but do not constitute atomistic proof of every descriptor. |
| OUT-10 | The stability measurements demonstrate continuous illuminated/maximum-power-point operating lifetime. | Contradicted | Methods explicitly say no continuous illumination and no maximum-power-point tracking. |
| OUT-11 | This study proves LEAP generalizes to arbitrary perovskite compositions, device structures, and other materials domains. | Contradicted / scope not established | Authors state generalization across compositions, structures, and discovery domains has not yet been shown. |
| OUT-12 | Every molecule not advanced to validation was individually reviewed and rejected for a specific reason. | Contradicted | Public shortlist README explicitly warns that not advanced in this campaign does not imply individual review/rejection or molecule-specific reason. |

For the final outcome reference, keep the difference between contradicted (evidence directly contradicts the claim) and unresolved/scope not established (the experiment does not answer it). Do not use absence of evidence as contradiction.

## 6. Freeze blockers and ownership

| Item | Current state | Owner / required acceptance |
|---|---|---|
| Operator selection of the LEAP story | **Complete:** Operator approved RWN-01 on 2026-11-16. | Selection is limited to story identity. It does not freeze the source corpus, assignment, answer key, outcome reference, or execution configuration. |
| Publisher PDF | Publisher text extraction inspected; binary download and requested page screenshots failed with cache-miss errors; no byte length or SHA-256. | Programmer/Operator obtains the exact Article in Press PDF through a working publisher/local route, preserves original bytes, visually checks all pages/metadata, and records direct URL, retrieval time, byte length, and SHA-256. |
| Supplementary Information | Publisher-listed; direct URL/binary not acquired. The paper places Welch-test confidence intervals in this file. | Programmer/Operator acquires and reviews the exact PDF. Include it when the final brief asks for confidence intervals or supplementary device analyses; otherwise record a reasoned exclusion and restrict the claims accordingly. |
| Transparent Peer Review | Publisher-listed; file not acquired | Optional. Include only if it adds material methodological qualification; record explicit include/exclude decision. |
| Public data repository | Commit `f25fbe8238422439db10877ea79295ec233c4867` pinned; exact bytes and SHA-256 verified for 18 identified files (full table above), including all six per-model response CSVs. | Preserve the pinned Git commit/path locators and stage the exact files into the corpus archive; decide whether all benchmark data are needed for the scored packet. Do not treat Git blob SHA-1 as SHA-256. |
| Raw device-level data | Not obtained; article says additional raw experimental data are stored on institutional servers and available from corresponding authors on reasonable request. | Operator decides whether author-reported aggregates plus the Supplementary Material suffice, or whether to request the additional raw data. Do not claim independent recomputation from raw device values unless acquired. |
| Source packet review and freeze | Not complete | Operator reviews all sources, inclusions/exclusions, corpus manifest, and exact versions; then records corpus ID/version and SHA-256 manifest. |
| Scored brief and exact word limit | Draft brief, proposed 700 words | Operator approves/edits final brief and exact word limit; freeze before scored runs. |
| Answer key and outcome reference | Draft outline only | Independent reviewers refine source locations, resolution criteria, accepted alternatives, and fixed evidence cutoff before freeze. |
| Story-specific rubric examples and calibration | Not prepared | Reviewers prepare examples using sources; freeze alongside answer key/rubric before freeze. |
| Execution package | Not prepared | Programmer/Operator freezes baseline/fixture identity, experience snapshot/hash, model/provider/parameters, prompts, tools, task/Context config, run slots, 10 pairs/5 blocks, randomization seed/order, retry/replacement schedule and operational windows. |

## 7. Explicit freeze checklist

Do not mark this selected story as a frozen corpus or authorize scored execution until every required item is resolved:

- [x] Operator selects RWN-01 as the first newsroom story (2026-11-16; story identity only).
- [ ] Exact publisher Article in Press PDF is preserved byte-for-byte, visually/textually checked, and SHA-256 hashed.
- [ ] Supplementary Information is acquired and assessed; include it or document why it is unnecessary for the frozen claims.
- [ ] Official data-release repository commit and required files are preserved; SHA-256 computed over each exact file.
- [ ] All source IDs, metadata, retrieval timestamps, licences, inclusion/exclusion rationales, and hashes are recorded in the final manifest.
- [ ] Final scored assignment brief and exact common word limit are approved and frozen.
- [ ] Source-grounded answer key is finalized independently of model outputs.
- [ ] Independent outcome reference, resolution criteria, and evidence cutoff are frozen independently of scored outputs.
- [ ] Story-specific scoring anchors/examples and reviewer calibration materials are frozen.
- [ ] Baseline and treatment fixture, accepted-experience snapshot identity/hash, execution configuration, 10 matched pairs in five randomized blocks, randomization seed/order, operational windows, and retry/replacement rules are frozen.
- [ ] Operator explicitly accepts the frozen experiment package before any scored runs.

**Authority boundary:** the Operator has selected the RWN-01 story identity on 2026-11-16. This draft does not freeze the source corpus or authorize scored runs, RW-1, R7-C implementation, or RW-0 closeout. See PLAN.md and the RW-0 decision record for authoritative status and authorization.
