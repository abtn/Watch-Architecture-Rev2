# Watch — A Persistent Cognitive Architecture

Watch is a persistent cognitive architecture for AI-assisted teams. It is designed to support reasoning, memory, experience, evaluation, and coordinated work in a system whose continuity does not depend on any individual model or worker.

Most AI workers are temporary. They can interpret information, reason, plan, use tools, and complete tasks, but their working context and knowledge of previous work are often fragmented across conversations, prompts, and files. Watch addresses a broader problem: how can a system preserve what it has observed, what it currently believes, what it has learned, how it reached those conclusions, and how that experience should inform later work—even as its workers and models change?

Watch treats models as contributors to intelligence, not as the system's source of identity or authority. Models and people contribute interpretation, reasoning, and proposals; specialized components and deterministic application mechanisms provide bounded capabilities, coordination, validation, and execution. The architecture is designed to support contributions from multiple LLMs, but this is a direction for the system, not a claim that multi-model collaboration is currently implemented or authorized.

> **Model intelligence is temporary. Watch experience is persistent.**

For a non-technical introduction to the overall idea, see [Watch in plain language](docs/simple-explain.md).

For current milestone status and authorization (maintained only in [PLAN.md](PLAN.md)), see the approved [RW-4/RW-5 sequencing decision](docs/development/rw-4-rw-5-sequencing-decision.md), the frozen [RW-5 shared clock, decay, and locking contract](docs/development/rw-5-shared-contract-proposal.md), and the [RW-4 Readiness and Delivery Plan](docs/development/rw-4-readiness-and-delivery-plan.md) for staged prerequisites. These planning documents do not themselves authorize implementation.

For the current PostgreSQL owner/migrator/runtime role setup and its development-only limitations, see [database role separation](docs/development/database-role-separation.md).

## What Watch is designed to do

Watch treats an AI-assisted team as a persistent organization and cognitive system rather than a collection of independent conversations or a model surrounded by tools.

A Team has a domain, mission, policies, working history, and memory. It can observe a subject, develop and revise beliefs about it, carry out tasks, evaluate results, and retain useful experience for future work. Its intended cognitive architecture distributes contributions across bounded workers, specialized components, persistent records, and deterministic application mechanisms.

The central principle is:

**Workers propose. Application code validates. The system commits.**

A model or human may suggest a new belief, evidence link, action, plan, or lesson. That suggestion does not become durable state simply because a worker produced it. Watch checks it against applicable rules, permissions, source records, and existing state. Accepted changes are committed with provenance so that the system can reconstruct what happened and why.

Watch is not a single model with memory attached, nor is it a replacement for language models or specialized AI. It provides the persistent cognitive, memory, governance, and coordination architecture through which different forms of intelligence can contribute to a continuing system. Multi-model collaboration is an architectural direction; the current implementation and authorization boundaries remain those recorded in PLAN.md.

## Watch as a cognitive architecture

The term *cognitive architecture* describes how Watch organizes the capabilities and processes needed for sustained, coherent work. It is an architectural description, not a claim that Watch is conscious, human-like, or generally intelligent. In this sense, Watch is intended to be a **thinking system**: not because one model thinks on its behalf, but because the architecture organizes reasoning, memory, evaluation, and coordinated contributions into a persistent process.

Watch does not assume that one LLM is the system's brain or permanent central coordinator. The architecture is designed to let different models and AI components take bounded responsibilities according to the task. This does not imply that multi-model orchestration is currently implemented. Coordination, state transitions, validation, permissions, and durable commits remain responsibilities of Watch's application architecture.

This distinction separates three concerns:

- **Cognitive contribution:** Models, people, and specialized components interpret information, reason within assigned scopes, generate hypotheses, evaluate alternatives, and propose work.
- **Cognitive continuity:** Watch preserves memory, evidence, decisions, outcomes, and accepted experience so that later work can build on earlier work.
- **System authority:** Deterministic application mechanisms enforce ownership, policy, validation, write boundaries, and execution. A model's output is a proposal, not permission to change authoritative state.

There is no architecturally privileged *primary LLM*. A model may be assigned a reasoning-heavy role for a particular workflow, but that is a replaceable operational assignment—not system authority. The architecture is intended to support collaboration among multiple models through Watch's shared context and coordination mechanisms. That future capability does not make any one model the identity or indispensable center of the system.

The biological brain is a useful source of questions about memory, reasoning, coordination, and specialized functions, but it is not a literal implementation blueprint. Watch does not need a one-to-one mapping between software components and brain regions. Its design should be guided by explicit responsibilities, evidence, and testable system properties.

### The memory architecture

Watch distinguishes between different kinds of memory because they represent different things and must not be changed in the same way.

#### 1. World memory — what the team knows about its subject

World memory represents the team's evolving understanding of the world it observes.

It is built around:

- **Signals:** observations received from external sources.
- **Snapshots:** immutable copies of source content, identified by content hashes.
- **Threads:** continuing subjects or situations the team follows.
- **Hypotheses:** possible explanations or beliefs about those subjects.
- **EvidenceLinks:** traceable evidence that supports, challenges, or mentions a Hypothesis.
- **ConfidenceChanges:** recorded changes in confidence with explicit causes.

A Thread can contain several competing Hypotheses. Watch does not assume that the newest explanation is automatically correct or that disagreement should be erased. Evidence and confidence changes must remain traceable to their sources and causes.

World memory is revisable. New evidence can strengthen, weaken, challenge, or supersede an existing belief. The design also includes confidence decay so that beliefs can lose strength when they are no longer supported by new observations.

#### 2. Team experience — what the team has learned from its work

Team experience is different from knowledge about the outside world.

It represents lessons about how the team performs its work: methods, practices, patterns, and playbooks derived from completed tasks and evaluated outcomes.

A lesson does not become accepted team experience merely because a model suggests it or because a task succeeds once. The learning path preserves its origin, evaluation, review, approval, and version history.

Unlike world beliefs, accepted team practices do not simply lose confidence because time has passed. They are reviewed and revised through an explicit learning process.

#### 3. Task Context — what matters right now

A worker should not receive the team's entire history every time it performs a task.

Watch assembles a bounded Task Context from relevant world knowledge, accepted team experience, current state, objectives, and applicable policies.

Retrieval-Augmented Generation (RAG) helps locate potentially relevant material. However, retrieval is not verification: a similarity match does not establish that a statement is true, current, authorized, or relevant.

Canonical records remain authoritative. Embeddings, indexes, summaries, and rankings are derived projections that can be rebuilt. Before information enters a Task Context, the application must resolve it to the appropriate records and preserve its provenance, ownership, status, and version.

The three roles are therefore distinct:

| Layer | Main question | How it changes |
|---|---|---|
| World memory | What do we currently know or believe about the subject? | Through evidence-backed updates and explicit confidence changes |
| Team experience | What have we learned about doing the work? | Through evaluation, review, and an approved learning process |
| Task Context | What information is relevant to this particular task? | Reassembled from current, eligible records |

## How the system works

The intended operating cycle connects observation, distributed reasoning, action, evaluation, and learning:

1. **Observe:** Watch receives information from configured sources and preserves immutable source Snapshots.
2. **Contextualize:** Watch assembles bounded Task Context from eligible world knowledge, accepted team experience, current state, objectives, and policies.
3. **Reason:** A worker examines that context and uses its own reasoning capabilities to propose observations, Hypotheses, plans, evidence links, or changes. The architecture is intended to support multiple model contributions; deterministic mechanisms provide bounded analysis and system coordination, not a substitute for model reasoning.
4. **Coordinate and validate:** Watch's application architecture routes bounded work, checks source integrity, ownership, permissions, proposal structure, and applicable invariants, and determines which proposals are eligible for acceptance.
5. **Act:** The existing Task and Kernel architecture governs authorized execution and durable commits.
6. **Evaluate:** Outcomes are recorded and assessed against the task's intent and available evidence.
7. **Learn and reuse:** Useful lessons can enter the Team Experience Core through the approved learning path. Relevant world knowledge and accepted experience can then inform later Task Contexts.

The architecture separates cognitive contribution from system authority. Workers may reason, recommend, and coordinate within assigned responsibilities, but they do not acquire authority over durable state by producing an answer. Objectives describe what a Team is trying to achieve. Assessments provide a deterministic view of its current state. Strategy proposals express possible directions, Plans organize accepted work, and ordinary Tasks carry out that work.

No single model is required to own this cycle. Watch coordinates the work and enforces its rules; individual models and other components contribute bounded capabilities.

## Technical foundations

The architecture is built around a few important engineering principles:

- **Durable records instead of conversational memory:** important state is stored in structured, attributable records rather than relying on a model transcript.
- **One controlled commit path:** proposals pass through application validation and the existing Kernel boundary.
- **Immutable evidence:** source Snapshots and content hashes make it possible to verify the exact material behind a claim.
- **Explicit provenance:** durable changes identify their originating Tasks and causes.
- **Team and domain isolation:** one Team's records and experience must not silently become another Team's authoritative knowledge.
- **Competing explanations:** multiple Hypotheses can coexist, with supporting and challenging evidence preserved.
- **Distributed, replaceable intelligence:** the architecture is designed to support bounded contributions from multiple models and specialized components without making any of them authoritative owners of system state.
- **Deterministic rules around probabilistic workers:** model output is treated as an untrusted proposal, not as an authority.
- **Rebuildable retrieval:** indexes and embeddings improve access to information but never replace canonical records.
- **Tested failure behavior:** replay, concurrency, invalid references, partial failures, and recovery are part of the architecture—not afterthoughts.

The implementation uses Python, PostgreSQL, and pgvector, with Alembic for schema migrations and automated tests for application and database behavior. Model providers sit behind defined interfaces so that cognitive contributions can be replaced or expanded without tying durable experience, coordination, or system authority to one model or vendor.

For the detailed system design, see [Architecture](docs/architecture.md), [Invariants](docs/invariants.md), [Control Model](docs/control-model.md), and the [Architecture Decision Records](docs/decisions/).

## What we are building now: the World-Memory Reasoning Loop (RW)

The existing foundations provide governed task execution, planning, outcomes, evaluation, and persistent team experience. The next major architectural layer is the complete reasoning loop for world memory.

The RW work connects incoming observations to explicit beliefs, evidence, confidence, and later learning. It is divided into five implementation stages:

| Stage | Purpose |
|---|---|
| **RW-0 — Design and value definition** | Define the reasoning architecture, its boundaries, and how its practical value will be evaluated. |
| **RW-1 — World-memory foundations** | Establish durable Threads, competing Hypotheses, EvidenceLinks, and ConfidenceChanges, with source and Team integrity. |
| **RW-2 — Deterministic human reasoning path** | Establish the Operator's ability to create and update Hypotheses through the same validation and commit rules, without depending on model output. |
| **RW-3 — Model reasoning worker** | Introduce the model-driven `update_thread` worker. Its output remains a proposal subject to application validation. |
| **RW-4 — Signal triage and reasoning retrieval** | Connect incoming Signals to relevant Threads and make current, relevant Hypotheses available in bounded Task Context. |
| **RW-5 — Confidence decay** | Implement deterministic confidence decay so that unsupported or inactive beliefs do not remain indefinitely strong. |

The purpose is not to create another independent agent runtime or a separate memory-writing mechanism. It is to complete the reasoning layer within Watch's existing Task, validation, and commit architecture.

See the [RW implementation plan and proof matrix](docs/development/rw-implementation-plan.md) for the detailed design and implementation boundaries.

## R8 — Testing the architecture across domains

Once the foundational architecture and world-memory reasoning loop are complete, R8 will test whether the system works as a coherent whole.

This is a pressure test, not another opportunity to add missing fundamental architecture. The goal is to discover whether the same underlying system can support different kinds of teams without losing its guarantees.

R8 covers three domains:

1. **Newsroom:** following a real scientific or technological subject, evaluating sources, maintaining competing explanations, and examining whether retained experience improves later analysis.
2. **Development team:** applying the same reasoning and memory architecture to technical work, including competing diagnoses, implementation decisions, test results, and project knowledge.
3. **Generalist:** testing a materially different domain to see whether the architecture depends on assumptions specific to journalism or software development.

Across these scenarios, R8 examines whether:

- Evidence and source references remain verifiable.
- Competing explanations can coexist and change for explicit reasons.
- Team and domain boundaries are respected.
- Relevant experience can be retrieved and used in later work.
- Irrelevant, stale, conflicting, or insufficient information is handled safely.
- A later task can demonstrate measurable improvement from retained experience.

The newsroom scenario also includes a controlled comparison between work performed with and without retained team experience. Independent evaluation is used to assess the quality of the results. Passing technical tests alone is not enough to demonstrate that persistent experience provides practical value.

R8 is therefore the point where the architecture is evaluated as a working system rather than only as a collection of individually verified components.

See the [R8 delivery plan](docs/development/r8-delivery-plan.md) and [newsroom value harness](docs/development/rw-value-harness.md).

## R9 — Agent-assisted production workflow

R9 is the next planned stage after the architectural pressure test.

Its purpose is to codify a reliable way of producing and maintaining software with AI-assisted workers. This includes:

- Clearly bounded task packets.
- Test-first implementation.
- Architecture and design reviews.
- Traceable verification evidence.
- Explicit human approval boundaries.

The goal is to make agent-assisted development a repeatable engineering process rather than a sequence of loosely coordinated model interactions.

R9 is a future stage. Its detailed implementation will follow the results and lessons of the preceding work.

## Research

Watch uses research to inform experiment design, not to turn published findings into assumed system capabilities. The purpose is to test whether explicit reasoning guidance and better-organized evidence context can improve the quality and consistency of model proposals—and to preserve the limits of what each experiment demonstrates.

### Cognitive grounding and LLM reasoning

A relevant starting point is:

Hongan Zhu and Babak Heydari, [“Cognitive grounding improves LLM simulation of collective human behavior”](https://www.nature.com/articles/s43588-026-01080-z), *Nature Computational Science* (2026). [https://doi.org/10.1038/s43588-026-01080-z](https://doi.org/10.1038/s43588-026-01080-z)

The study examines whether giving LLM agents qualitative descriptions of human decision-making heuristics improves their ability to reproduce collective behavior. Across 231 sessions of the Beer Distribution Game and seven LLMs, the authors report that heuristic-aware cognitive grounding improved alignment with human-calibrated behavior, although the size of the effect varied across models and roles. The study also examines alternative prompting and memory designs.

The lesson we take from this work is methodological: a model's plausible answer is not enough. We should test whether the representation and decision guidance supplied to a worker change its behavior in a measurable way. The paper studies a supply-chain game and human-behavior simulation; it does not directly validate Watch's world-memory architecture or establish that one particular evidence representation is superior for scientific reasoning.

### Experiment A — testing representations for world-memory reasoning

The repository includes an offline research package at [`research/experiment_a/`](research/experiment_a/). It translates the cognitive-grounding question into a bounded RW-3 experiment: when a reasoning worker receives the same underlying case information in different representations, does the structure of that context affect its evidence assessment and proposed update?

Experiment A currently defines three canonical sample fixtures:

- **RW3-03 — evidence supports an update:** a low-confidence Hypothesis is accompanied by a completed Signal reporting the specified effect under all stated conditions, with alternative explanations recorded as ruled out. The evaluator-only expected behavior is a supporting EvidenceLink and an increase in confidence.
- **RW3-13 — evidence is not yet available:** a measurement has been requested but remains pending. The expected behavior is to hold the current confidence and avoid inventing a result or proposing a ConfidenceChange.
- **SP-01 — StrategyProposer diagnostic:** a separate StateAssessment case checks whether a configured single source is handled without proposing a duplicate ingestion task. It is a diagnostic case, not an RW-3 world-memory update case.

For the two RW-3 cases, the package provides two renderings of the same underlying fixture information:

1. **Flat representation:** records are presented in flat arrays, chronologically ordered, without grouping evidence by stance or records by temporal state.
2. **Structured representation:** the same records are organized into supporting, challenging, and mentioning evidence; provenance; pending, completed, and missing temporal states; and uncertainty notes.

The key control is that the representations must preserve the same underlying information. Representation Invariant #7 checks that the flat and structured renderings contain the same record multiset. This prevents a comparison from quietly giving one condition extra evidence or omitting inconvenient information.

The package also defines closed JSON Schemas for model-facing evidence assessments and RW-3 proposal outputs. These contracts constrain the worker's permitted decisions and references. For example, they distinguish `increase`, `decrease`, `hold`, and `no_update`; define evidence relevance, reliability, independence, and temporal-status vocabularies; and constrain when a ConfidenceChange or new EvidenceLink may be proposed. Evaluator-only expected answers are excluded from the model-visible fixture hash and must not be supplied as model context.

### What this experiment does—and does not—establish

Experiment A is an offline fixture, schema, and renderer package. Its current tests validate the three canonical fixtures, the JSON Schema contracts, the renderers, and the representation-preservation invariant. It makes no network calls, model-provider calls, or database operations, and it is isolated from Watch application code.

These artifacts prepare a controlled comparison of context representations. They do not mean that the model experiment has already been executed or that structured context has been shown to improve reasoning. RW3.1–RW3.3 are accepted; RW3.4 implementation is merged, but formal Operator acceptance remains deferred with seven PARTIAL qualifications. The fixtures do not establish RW3.4 acceptance or close those qualifications. The experiment's results must be measured against the same underlying cases and evaluated independently; schema validity alone is not evidence that a proposed belief is true.

To run the offline checks:

```bash
uv run pytest tests/test_experiment_a_fixtures.py tests/test_experiment_a_json_schemas.py -q
```

For implementation details and the exact limits of the current fixture contract, see the [Experiment A README](research/experiment_a/README.md) and the [Experiment A execution plan](docs/development/experiment-a-execution-plan.md). The [RW implementation plan and proof matrix](docs/development/rw-implementation-plan.md) and [newsroom value harness](docs/development/rw-value-harness.md) describe separate work and evaluation tracks; neither should be confused with completed Experiment A model runs.

## Further reading

- [Watch in plain language](docs/simple-explain.md) — the overall idea and its research-desk metaphor.
- [Architecture](docs/architecture.md) — system structure, entities, and major flows.
- [Control Model](docs/control-model.md) — Objectives, assessments, strategies, Plans, and Task Context.
- [Task specifications](docs/tasks.md) — the responsibilities and write boundaries of individual Task types.
- [Invariants](docs/invariants.md) — rules that durable state and application behavior must preserve.
- [Architecture Decision Records](docs/decisions/) — the reasoning behind important design choices.
- [Project roadmap](PLAN.md) — milestone sequence and current project state.
- [Testing record](docs/testing.md) — verification history and evidence.
