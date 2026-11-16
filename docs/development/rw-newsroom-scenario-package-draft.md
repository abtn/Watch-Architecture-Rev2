# RW Newsroom Scenario Package — Selected Story RWN-01 (LEAP), Draft

- **Status:** RWN-01 story identity selected by the Operator on 2026-11-16; source corpus and scored package not frozen; no scored runs authorized
- **Prepared:** 2026-11-16
- **Decision authority:** Operator, under RW-D101–D105 and RW-D135
- **Scope:** candidate story, proposed source manifest, draft assignment, answer-key outline, independent outcome-reference candidates, and remaining freeze gates

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
| SRC-002 | Official author data-release repository README and licence. | WD928/LEAP, pinned commit `f25fbe8238422439db10877ea79295ec233c4867`; root `README.md` and `LICENSE`. | Verified exact bytes: README 4,235 bytes, SHA-256 `333b6e82cc675c33cee858010bcab594d23d60a22e51c750383e16f0fc5bffce`; LICENSE 11,357 bytes, SHA-256 `2863ee8e0c463e799bbec0a3439bd8431a303cbb007f2eeb88d7a561191ee225`. Stable commit/path locators recorded; local packet archive remains to be staged. |
| SRC-003 | Candidate-selection data and definitions, including round-specific top-50 shortlists, ranks, GP predictions, uncertainty, expected improvement, descriptor scores, and advancement status. | `candidate_selection/top50_validation_shortlists_mechanism_scores.csv` (Git blob SHA-1 `7143342e0d864db71e71da442f47a227bce9f633`); `candidate_selection/README.md` (Git blob SHA-1 `9fff092854e0bfb1253bf8ac592dd4a32a4cb110`). | Verified exact bytes: README 2,238 bytes, SHA-256 `52745f1ae22e4c58a70988dda6495a751a72be039c57cb2b807f30c8b7fd34ba`. Shortlist CSV 60,452 bytes, SHA-256 `75d7b258df19137f83c035afbe1cb28b2e163e3f8471987811ba70b80a3485f9`. |
| SRC-004 | Hot-start data, descriptor definitions, and data dictionary. | `data/hot_start_additives.csv` (Git blob SHA-1 `69ff60da0210d8eabf475b3081f229e47cc90b18`); `data/hot_start_data_dictionary.json` (SHA-1 `d52ed76b5606c37d9e1c60a40c26fdd6f3fa7749`); `data/README.md` (SHA-1 `81d34a2f610d49b2f98b1384ef3f4ed2f9826c9b`). | Verified exact bytes: `data/README.md`, 397 bytes, SHA-256 `c6686708adb0a505ab463ced9ba187591fa125b044631f80f9d6366fe0d0cd23`; hot-start CSV, 13,243 bytes, SHA-256 `390c16f196e0d11319e015201010f49d61360f48df3ac27b79d260a03470ce8e`; dictionary JSON, 8,281 bytes, SHA-256 `199b5465a3e7301665b04241eb7d79c7878f3a8bbbfef6c30a10e24bb9fde5b4`. |
| SRC-005 | Mechanism-consistency benchmark, released benchmark questions/source list, six per-model response CSVs, summary statistics, and representation-ablation confidence intervals. | `benchmark/benchmark_sources.csv` (Git blob SHA-1 `72d5f2b346833feb2494c027297426a2d735f924`); `benchmark/questions.csv` (SHA-1 `ee1ac1c97cafa6fac530aec122d0a7eba37be1e4`); six `benchmark/model_results/*_results_ordered.csv` files; `benchmark/statistics/model_summary_with_ci.csv` (SHA-1 `132ca58cf4e8ec71683011425df62b47b82f0665`); `benchmark/statistics/mcnemar_vs_reference_holm.csv` (SHA-1 `f063293656cfd8f5cd2d7f495aa7dbc8eb87e84f`); `ablation/representation/figure3_bootstrap_ci_table.csv` (SHA-1 `283d40f85a3a10c290a227da78fa3a4609eb2318`). | Exact bytes retrieved and SHA-256 hashed at pinned commit for the sources CSV, questions CSV, six per-model response CSVs, two statistics CSVs, and representation CI table; see exact-byte log. The private/source PDF files behind the benchmark questions are not included in this public repo. |
| SRC-006 | Publisher Supplementary Information PDF, including the tables/figures referenced from the main text (notably Tables S3/S5 and Figure S5/S6/S9). | Listed as “Supplemental Material (download PDF)” on the official article page; the PDF also says device-comparison confidence intervals are reported in Supplementary Information. Exact direct file URL/version not captured. | Required before freezing any assignment that reports the paper’s Welch-test confidence intervals or supplementary device analyses. Binary/direct URL not acquired; review and inclusion decision remain open. |
| SRC-007 | Publisher Transparent Peer Review file. | Listed as “Transparent Peer Review file (download PDF)” on the official article page; exact direct file URL/version not captured. | Optional corroborating context. Acquire only if needed to assess a material methodological qualification; if excluded, record that decision and rationale. |

### Exact-byte hash capture log — author data-release repository

The following bytes were retrieved from the GitHub file API at commit `f25fbe8238422439db10877ea79295ec233c4867` on 2026-11-16 using Base64 content responses. Transport whitespace was removed before Base64 decoding. For every file, the decoded byte length matches GitHub file-size metadata and a recomputed Git blob SHA-1 (`blob ` + byte length + NUL + bytes) matches the repository blob SHA-1. SHA-256 was computed over those exact decoded bytes. These are exact-byte hashes, not claims that a local archive has already been staged in the Watch repository.

| Path | Bytes | Git blob SHA-1 | SHA-256 |
|---|---:|---|---|
| `README.md` | 4,235 | `0c2a9a10fc4c09e6f11bacd4bd523eb2b48e8e21` | `333b6e82cc675c33cee858010bcab594d23d60a22e51c750383e16f0fc5bffce` |
| `LICENSE` | 11,357 | `261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64` | `2863ee8e0c463e799bbec0a3439bd8431a303cbb007f2eeb88d7a561191ee225` |
| `candidate_selection/README.md` | 2,238 | `9fff092854e0bfb1253bf8ac592dd4a32a4cb110` | `52745f1ae22e4c58a70988dda6495a751a72be039c57cb2b807f30c8b7fd34ba` |
| `candidate_selection/top50_validation_shortlists_mechanism_scores.csv` | 60,452 | `7143342e0d864db71e71da442f47a227bce9f633` | `75d7b258df19137f83c035afbe1cb28b2e163e3f8471987811ba70b80a3485f9` |
| `data/README.md` | 397 | `81d34a2f610d49b2f98b1384ef3f4ed2f9826c9b` | `c6686708adb0a505ab463ced9ba187591fa125b044631f80f9d6366fe0d0cd23` |
| `data/hot_start_additives.csv` | 13,243 | `69ff60da0210d8eabf475b3081f229e47cc90b18` | `390c16f196e0d11319e015201010f49d61360f48df3ac27b79d260a03470ce8e` |
| `data/hot_start_data_dictionary.json` | 8,281 | `d52ed76b5606c37d9e1c60a40c26fdd6f3fa7749` | `199b5465a3e7301665b04241eb7d79c7878f3a8bbbfef6c30a10e24bb9fde5b4` |
| `benchmark/benchmark_sources.csv` | 2,563 | `72d5f2b346833feb2494c027297426a2d735f924` | `2d818109e1d278531a5c5dd487b52cf2246ed75f9e19d0f4ca6cb296818fae37` |
| `benchmark/questions.csv` | 52,600 | `ee1ac1c97cafa6fac530aec122d0a7eba37be1e4` | `755215c87e717deebd3599f35775109d3ba17061398173b977f5e4272b5e9f7d` |
| `benchmark/statistics/model_summary_with_ci.csv` | 759 | `132ca58cf4e8ec71683011425df62b47b82f0665` | `4a8a53b6e0649988e419eb110bb86da081ed22d72eceff4d65f74220b10df84b` |
| `benchmark/statistics/mcnemar_vs_reference_holm.csv` | 531 | `f063293656cfd8f5cd2d7f495aa7dbc8eb87e84f` | `99cf62ca81818ead53637982bc37d0ad63c3d2eab8fbc7a283c10dd8979ad415` |
| `benchmark/model_results/DeepSeek-V3.2_results_ordered.csv` | 9,416 | `131a237b9aff2a183c9c41a9fad07eccac941452` | `3a8ac955711da739cf93d5b19cbe2c8a601b09442e9e562c40c4f7ecd6c78360` |
| `benchmark/model_results/GPT-5_results_ordered.csv` | 9,416 | `92a176c4d4fe8296329166ed678742439456a9b6` | `fdc44a866e3802030e26d7d1db8c0ed782753af3a0a4b929e88e9ac212cddbcb` |
| `benchmark/model_results/Perovskite-RL_results_ordered.csv` | 9,416 | `a1c4893ca7c35254377789d40442e025e4431e28` | `81de4343770665c07752cfb1ce23d1ed6cd93a55932c4056fa183ae6edb7754d` |
| `benchmark/model_results/Qwen3-32B_results_ordered.csv` | 9,416 | `9fde0b7540f78e10c1f5d8069acee1a6c06dff27` | `4a5b6e273bfe54a0064c0349f586e7c2a3bd6bdc3c49131accfce507e2584484` |
| `benchmark/model_results/gemini-3-flash_results_ordered.csv` | 9,416 | `f3a0ad327e7362d91368c233fad5139fb7530526` | `fadffef03e8cdce846e7ee21be43278a7c673063f39849659ef603f5795d9ee3` |
| `benchmark/model_results/llama-3.3-70b-instruct_results_ordered.csv` | 9,416 | `eef6ad695cec4bc9c34432cdb3238ee54736bb64` | `44496c8149cb2b371739632b43a872fbdfb4cc4ed9d1b504c32723dc8065948a` |
| `ablation/representation/figure3_bootstrap_ci_table.csv` | 979 | `283d40f85a3a10c290a227da78fa3a4609eb2318` | `e8c0b0a389fe85c0abc27b0b14112fc241fc26c0a74050f6dd2d8c33344c4b26` |

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

## 6. Pre-execution deliverables, owners, and acceptance gates

RW-D135 permits RW-0 documentation closeout while the experiment package remains unfrozen, provided every deferred pre-execution component has an accountable owner and an explicit acceptance gate. The following register is that control. These are **open pre-execution deliverables**, not RW-0 documentation-closeout blockers. No scored run may begin while a required gate is open.

| Item | Current state | Accountable owner | Acceptance gate |
|---|---|---|---|
| RWN-01 story identity | **Complete:** Operator selected the LEAP publisher Article in Press version on 2026-11-16. | Operator | Identity remains pinned to the 4 November 2026 Article in Press version; a later Version of Record requires a new corpus version. |
| Publisher Article in Press PDF (SRC-001) | Text extraction and publisher reference PDF URL inspected; binary, byte length, local archive, visual page inspection, and SHA-256 not captured. | Programmer — local source-capture executor | Preserve the exact publisher bytes; record retrieval URL/time, byte length, page count, SHA-256; visually inspect every page and reconcile it with the extracted text. Operator accepts the captured version. |
| Supplementary Information (SRC-006) | Publisher-listed; direct URL/binary not acquired. The article points to it for Welch-test confidence intervals. | Programmer — capture; Operator — inclusion decision | Acquire and hash the PDF, review the relevant tables/figures, then either include it in the corpus or record an explicit exclusion rationale and omit claims that depend on it. Operator accepts the disposition. |
| Transparent Peer Review (SRC-007) | Publisher-listed; binary not acquired; optional. | Operator | Record include/exclude decision and rationale. If included, Programmer archives the exact PDF and records URL/time/bytes/SHA-256; Operator accepts it. |
| Pinned author data-release files | Commit `f25fbe8238422439db10877ea79295ec233c4867` pinned; exact bytes and SHA-256 verified for 18 identified files, including all six model-response CSVs; local packet archive not staged. | Programmer — archive executor; Operator — source selection | Select the files needed for the assignment, archive those exact bytes, recompute each SHA-256 against the capture log, and record included/excluded paths and reasons in the manifest. Operator accepts the selected set. |
| Raw device-level data | Not obtained; article says additional data are held on institutional servers and may be requested from corresponding authors. | Operator | Record whether the final claims can be supported by article aggregates plus Supplementary Information or whether raw data must be requested. If requested and used, archive and hash the received files; do not claim independent recomputation before that gate passes. |
| Final source packet and corpus manifest | Not frozen. | Operator — final corpus authority; Programmer — manifest preparation | Review every included/excluded source, version, licence, retrieval time, exact file/archive locator, byte length, and SHA-256; freeze a unique corpus ID/version and manifest digest. Operator records acceptance. |
| Scored brief and common word limit | Draft only; 700 words is provisional. | Operator | Approve a brief grounded only in the frozen packet, with one exact word limit and identical instructions for all 20 runs. Freeze its version/hash. |
| Answer key and independent outcome reference | Source-grounded outline and outcome candidates exist; independent final review remains outstanding. | Operator — appoints reviewers; two appointed independent reviewers — prepare/review | Record the two reviewers' identities, qualifications, conflicts, and independence. Finalize exact source locations, acceptable alternatives, resolution criteria, classifications, and evidence cutoff independently of scored outputs; preserve reviewer disagreements and adjudication. Operator accepts the versioned set. |
| Story-specific scoring examples and calibration | Not prepared. | Operator — appoints the same two reviewers; appointed reviewers — prepare | Freeze examples and review instructions; both reviewers independently calibrate on non-scored samples; record that D35 acceptance criteria are met before scored review. |
| Execution package | Not prepared. | Programmer — execution/configuration record; Operator — authorization | Freeze baseline/fixture identities, accepted-experience snapshot manifest/hash, provider/model and parameters, prompts/tools/budgets, Task/Context configuration, 20 slot IDs, 10 matched pairs/five blocks, randomization seed/order, retry/replacement schedule, and operational windows. Verify exact hashes and obtain explicit Operator acceptance before any scored run. |

The named accountable owners above are project roles, not a claim that reviewer individuals have already been appointed. The Operator owns appointment and recording of the two independent reviewers before answer-key finalization and calibration. Completion of this register closes only the **RW-0 documentation ownership requirement**; it does not close any listed pre-execution gate.


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

**Authority boundary:** the Operator selected the RWN-01 story identity on 2026-11-16. This document remains a draft and does not freeze the corpus, authorize scored runs, authorize RW-1 implementation, or authorize R7-C implementation. Under RW-D135, RW-0 documentation closeout may proceed because every remaining pre-execution deliverable is assigned an accountable owner and an explicit acceptance gate in §6. The actual experiment package must still be fully frozen and explicitly accepted before scored runs. See PLAN.md and the RW-0 decision record for status and authorization.
