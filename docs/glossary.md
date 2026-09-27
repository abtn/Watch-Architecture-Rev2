# Glossary

This is the canonical vocabulary of the Watch project. Every capitalized term in the documentation and in normative code comments refers to a definition below.

Rules for using this glossary:

- If a term is defined here, use the defined term in docs, code, prompts, and commit messages. Do not paraphrase in normative text.
- **Banned synonyms** are terms that have caused or will cause confusion. Never use them for the defined concept.
- A new kernel or domain concept must be added here *before* other documents reference it.
- Entities are written with a leading capital (Signal, Thread). The same word lowercase means the ordinary English word.

## Foundational concepts

### Watch
A framework for persistent teams that build understanding over time. The product, not any single deployment of it.

### Kernel
The domain-independent core: entities, invariants, state transitions, and services shared by every domain pack. Kernel schema lives in `/core` and `/migrations`.
*Not the same as:* "core logic" (vague). *Banned synonyms:* engine, framework-core.

### Domain / Domain pack
A **Domain** is a subject-area key (`"newsroom"`, `"devteam"`, `"generalist"`). A **Domain pack** is the code and configuration that adapts the kernel to that Domain: signal sources, vocabulary, match heuristics, render templates, decay behavior, dedup policy. Specified in `docs/domains.md`.
*Banned synonyms:* vertical, module, plugin.

### Generalist pack
The kernel-shipped Domain pack: manual intake plus a policy-parameterized generic RSS connector, default vocabulary extendable per team, keyword heuristics, standard templates, 14-day decay default. Makes any feed-followable subject watchable with zero new code; the setup advisor's fallback for any subject.
*Not the same as:* a specialized pack. *Banned synonyms:* default pack (ambiguous), catch-all.

### Team
A durable unit with a mission, a Domain, a policy, world memory, team memory, and a work history. A Team is not an agent, not a user, and not a model session.
*Banned synonyms:* workspace, project, org.

### Team mission
Long-lived purpose. Distinct from an Objective, which is bounded and operational.

### Shell team
A Team in `configuring` status: created with a key and a subject brief, without an active policy. It becomes active only through `activate_team`.
*Banned synonyms:* stub, empty team.

### TeamDraft
A proposed Team configuration — mission, vocabulary, source candidates, decay rationale, thresholds, starter Threads, policy — produced by `configure_team` from a subject brief and sample Signals, edited and approved by an Operator at activation. The approved, hashed config snapshot is the Team's birth certificate.
*Banned synonyms:* wizard, template, preset.

### Worker
The performer of a Task: a model-call graph, a deterministic service, or a human Operator. Workers are temporary; their effects persist only as durable records.
*Not the same as:* Agent (a specific kind of worker). *Banned synonyms:* bot, assistant, "agent" used generically for any worker.

### Agent
A worker implemented as an LLM-driven graph making model calls. One kind of worker among several. There are no persistent Agent entities in v1.
*Not the same as:* Team, worker in general.

### Operator
A human acting through the API or CLI: seeding knowledge, recording outcomes, approving learning changes, contributing to world memory, answering consultations, creating and activating teams. Operator actions are performed through manual Task types, so every durable write traces to a Task and receives identity attribution in Event payloads.

### Invariant
A non-negotiable rule listed in `docs/invariants.md`, enforced by application code and tests. Invariants are numbered `INV-NN` and cited by number.

## World memory

### World memory
What the Team believes is happening in the world: Threads, Hypotheses, EvidenceLinks, ConfidenceChanges. Revisable by design; allowed to decay.
*Banned synonyms:* short-term memory, context, "agent memory".

### Signal
An immutable observation of the outside world, created by a connector or an Operator. Stores a content hash and a reference to its Snapshot. A re-fetch that produces different content creates a new Signal; a re-fetch that produces identical content creates no new Signal.
*Not the same as:* Event (internal audit record). *Banned synonyms:* event, message, post, update.

### Snapshot
The immutable stored content behind a Signal, an Outcome observation, an Artifact, a Consultation answer, or a TeamDraft configuration. Identified by a storage reference plus a content hash; never modified after write.
*Banned synonyms:* cache, blob (implementation term only).

### SignalDisposition
A per-Team record of how a Signal was handled: `matched` to a Thread, started a `new_thread`, `noise`, `duplicate`, or `deferred`. One row per (Signal, Team). Triage decisions are never implicit.
*Banned synonyms:* classification (loose), routing.

### Thread
An ongoing situation or shift a Team tracks. Holds competing Hypotheses and is the unit that decays, renders, and resolves.
*Not the same as:* a conversation or chat thread. *Banned synonyms:* topic, story (informal use only), case.

### Hypothesis
A competing explanation, assessment, or working belief within a Thread. Multiple Hypotheses may be active simultaneously. Removal happens only by explicit rejection or supersession, never silently. Hypotheses may originate from model workers or from an Operator's expert contribution (`operator_update`); unsubstantiated entries begin at `low`.
*Banned synonyms:* belief, opinion, verdict, claim.

### EvidenceLink
A validated provenance link from a subject (a Hypothesis or an Evaluation) to an immutable source (a Signal, Outcome, Artifact, or Consultation answer), carrying a Stance and a verbatim quote verified against the source Snapshot.
*Not the same as:* Artifact citations (assembled by code at render time). *Banned synonyms:* citation, reference, source link.

### Stance
The relationship asserted by an EvidenceLink: `supports`, `challenges`, or `mentions`. Only `supports` and `challenges` may drive confidence.

### Confidence band
One of `low`, `moderate`, `high`. Bands are ordered labels, not numbers.
*Banned synonyms:* score, probability, percentage, "confidence level" (say "band").

### ConfidenceChange
An append-only record of a band transition on one Hypothesis, with a recorded cause: an EvidenceLink or a decay Task. No ConfidenceChange may exist without a cause.

### Decay
The scheduled lowering of a Hypothesis's band after its Domain's decay window passes without newly accepted evidence. Decay never rejects a Hypothesis and never updates `last_touched_at`.
*Banned synonyms:* forgetting, expiry, timeout.

## Team memory

### Team memory
What the Team has learned about its own practices, patterns, methods, and playbooks: KnowledgeItems and versioned TeamPolicy. Changes only through the learning path.
*Banned synonyms:* agent memory, long-term memory (say "team memory").

### Outcome
A durable, immutable observation of what happened after a Task, Artifact, or Hypothesis — recorded against a subject. An Outcome records what was observed, never what it means. Predictions are recorded as two Outcomes: a `prediction_registered` before the result is known, and a `prediction_check` against it.
*Banned synonyms:* result (loose), feedback (that is an `outcome_type` value).

### Evaluation
A recorded assessment of an Outcome and/or method, with a conclusion (`worked` / `mixed` / `failed` / `inconclusive`) and provenance. A model-generated Evaluation is a Proposal until validated and recorded. Evaluations may classify failures as `world_failure`, `strategy_failure`, `execution_failure`, `evidence_failure`, or `policy_failure`.
*Banned synonyms:* review, grade, score.

### KnowledgeItem
A versioned, reusable piece of Team memory. Kinds: `practice`, `pattern`, `method`, `playbook`. Created or revised only through a committed LearningChange.
*Banned synonyms:* note, document, lesson (informal only).

### LearningChange
An auditable proposal — or explicit Operator seed — to create, revise, or retire a KnowledgeItem or a TeamPolicy version. The only path by which Team memory changes.

### TeamPolicy
A versioned configuration of how a Team currently operates (routing, review, knowledge selection, thresholds, budgets, vocabulary, sources, decay, preferences), validated against a versioned schema. Not a security boundary.
*Banned synonyms:* config, settings, "the rules" (loose).

## Control layer

### Objective
One durable entity representing a bounded operational goal that the Team is currently trying to accomplish. It is not a Thread and not TeamPolicy. It has one explicit lifecycle: `draft → active/cancelled`; `active → paused/blocked/completed/cancelled`; `paused → active/cancelled`; `blocked → active/cancelled`; `completed` and `cancelled` are terminal. Tasks may reference an Objective, but there is no second task-scoped ephemeral Objective abstraction.
*Banned synonyms:* goal (loose), project (loose).

### StateAssessment
A derived, deterministic reconstruction of authoritative state relevant to an Objective. It is never authoritative and never directly commits state. When a Strategy/Plan is selected, its exact historical basis must be reconstructable from basis references, hash, and creation timestamp; preserve an immutable Snapshot of the assessment payload using the existing Snapshot mechanism if those references cannot recreate it. This is decision provenance, not a second authoritative state store. Current world state and historical decision context remain distinct.
*Banned synonyms:* assessment (loose), summary, report, world model.

### Strategy
A temporary approach for making progress toward an Objective under the current StateAssessment and TeamPolicy. Not a durable entity; represented by a StrategyProposal and, if accepted, by Plan provenance.
*Banned synonyms:* plan (ambiguous), policy (forbidden), playbook (reserved for KnowledgeItem).

### StrategyProposal
A structured, validated proposal describing how an Objective should be pursued. It is not Team memory and is not TeamPolicy. It can be accepted into a Plan or rejected with an Event.
*Banned synonyms:* plan, instruction, directive.

### Plan
A durable record of intended orchestration for an Objective/Strategy. It contains Tasks, dependencies, conditions, budget envelopes, and stop conditions. It is execution intent, not execution truth. Tasks, Events, and Outcomes remain authoritative for what actually happened. Budget hierarchy is TeamPolicy ceiling > Plan envelope > Task budget: a Plan cannot exceed TeamPolicy, materialized Task allocations cannot exceed the Plan envelope, and each Task budget remains authoritative for its own execution. Plan membership is optional for a Task.
*Banned synonyms:* workflow (loose), project (loose), strategy (forbidden).

## Work and audit

### Task
A bounded unit of work with a type, a Team, a write scope, a tool allowlist, and a budget, performed by a Worker. All durable writes trace to a Task. A Task may be reactive/unplanned, associated with an Objective, or associated with both an Objective and a Plan. The existing Task state machine and write scopes are unchanged by the Control layer.
*Not the same as:* a queue job (arq jobs are infrastructure that run Tasks). *Banned synonyms:* job, run, request.

### Write scope
The set of entity kinds a given Task type may write, enforced by application code at commit time.
*Banned synonyms:* permissions (reserved for future auth), access control.

### Proposal
A record with status `proposed` awaiting validation and commit (an Evaluation, a LearningChange, a StrategyProposal, or model-proposed state inside an update Task).

### Commit
The application-validated, atomic act of writing proposed state to durable entities. Not a git commit; when both are meant, write "commit" for the former and "merge" for the latter.
*Banned synonyms:* save, write (in normative text).

### Consultation
A durable request for expert opinion opened by the loop (or an Operator) against a subject, answered by an immutable, hashed answer snapshot that may be cited as evidence (`source_kind="consultation"`). Waiting for an answer happens between Tasks, never inside one.
*Not the same as:* a chat message or model conversation. *Banned synonyms:* question (loose), ticket, chat.

### Trigger
A stored condition that creates Tasks when it fires: `threshold`, `scheduled`, or `manual`. Triggers never mutate world memory or publish output directly. A Trigger may also create or activate an Objective when deliberation is required.
*Banned synonyms:* webhook, event, cron (cron is an implementation detail of scheduled triggers).

### Event
An append-only audit record of a state transition or important decision, attributed to the Task that caused it. Events are structured records, not log lines.
*Banned synonyms:* signal (never — Signal is an inbound observation), log, audit row (loose).

### Artifact
A durable rendered output (article, briefing, recommendation) with identity, content Snapshot and hash, and a lifecycle. An Artifact is a product of the Team's current model, not a replacement for it.
*Banned synonyms:* output (generic), report (that is an `artifact_type` value).

### Projection
Derived, regenerable data: Thread summaries, embeddings, indexes, dashboards, StateAssessments. Projections are never the authority for a decision; the underlying records are.
*Banned synonyms:* copy, cache, view (DB-view ambiguity).

### Reactive execution path
The existing Watch execution entry point: Signal / Trigger / Scheduler / Operator → Task → Worker → Proposal → Kernel validation → Commit. This path remains valid and unchanged in its authority model.

### Deliberative control path
The new execution entry point: Objective → StateAssessment → StrategyProposal → Plan → Task materialization → existing Task execution path. The Control layer converges into the reactive path by creating ordinary Tasks.
