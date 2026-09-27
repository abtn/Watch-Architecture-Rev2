# File: docs/decisions/0001-persistent-team-as-first-class-entity.md

# ADR-0001: Persistent Team as first-class entity

**Status:** accepted  **Date:** 2025-01-15

## Context
The original design had domains and threads but no durable identity that owns a mission, a policy, a memory, and a work history. "Persistent team" was implicit, so nothing could accumulate experience.

## Decision
`Team` is a kernel entity. It owns Threads, Tasks, Outcomes, and team memory; it references an active TeamPolicy. A Team is not an agent, not a user, and not a model session. Signals are unowned; relevance is expressed per-team via SignalDispositions (ADR-0012).

## Alternatives considered
- **Teams as a UI grouping over threads** — rejected: policy and learned knowledge would have nowhere durable to live.
- **One deployment per subject** — rejected: multi-subject watching needs cheap boundaries, and shared signals (one wire story, two desks) would be impossible.

## Consequences
Every entity carries team-ownership validation. Kernel services must never assume a single team. Cost: an ownership check on every commit path.

## Invariants
INV-02, INV-09, INV-13, INV-14.

---

# File: docs/decisions/0002-world-and-team-memory-separated.md

# ADR-0002: World memory and team memory separated

**Status:** accepted  **Date:** 2025-01-15

## Context
Situational beliefs ("OPEC+ will extend cuts") and organizational lessons ("verify demand attribution before raising confidence") were at risk of living in one undifferentiated store, where a stale hypothesis could masquerade as a lesson and a lesson could decay like a rumor.

## Decision
Two memory layers with different change rules. **World memory** (Threads, Hypotheses, EvidenceLinks, ConfidenceChanges) is revisable by design and decays on schedule. **Team memory** (KnowledgeItems, TeamPolicy) changes only through the learning path (ADR-0003) and is never decayed — only reviewed.

## Alternatives considered
- **One memory store with tags** — rejected: decay rules and change-control rules would conflict on the same rows.
- **Knowledge kept only in prompts** — rejected: not durable, not auditable, not versioned.

## Consequences
Two write paths, two invariant families (decay vs. learning). Retrieval into task context draws from both, bounded by policy.

## Invariants
INV-08, INV-11, INV-12.

---

# File: docs/decisions/0003-learning-through-outcome-evaluation-learningchange.md

# ADR-0003: Learning through Outcome → Evaluation → LearningChange

**Status:** accepted  **Date:** 2025-01-15

## Context
Without a durable post-hoc loop, "the team learns" is aspiration. The specific danger: a successful-looking model response silently becoming doctrine.

## Decision
Team memory changes only through the path: Outcome (immutable observation) → Evaluation (assessment with provenance; a model evaluation is a proposal, never an oracle) → LearningChange (auditable proposed change) → committed new version. In v1, commits require Operator approval. Nothing is learned from an unrecorded outcome, and nothing is promoted by repetition alone.

## Alternatives considered
- **Automatic promotion of repeated hypotheses into practices** — rejected: popularity is not validity; this was an explicit non-goal.
- **Learning at render time** — rejected: render has no outcome grounding; it would encode pre-outcome opinion as practice.

## Consequences
Learning is slow and conservative by design. The oil-desk walkthrough shows the intended flavor: a lesson drawn from a *mixed* evaluation, not a success story. Cost: every learning path needs recorded evaluations to function.

## Invariants
INV-05, INV-12, INV-13, INV-14.

---

# File: docs/decisions/0004-versioned-team-policy-operator-approved.md

# ADR-0004: Versioned TeamPolicy, operator-approved

**Status:** accepted  **Date:** 2025-01-15

## Context
Team knowledge should eventually influence behavior; but "policy" as freeform model prose is unfalsifiable and silently mutable.

## Decision
TeamPolicy is versioned data with a `schema_version` and a fixed v1 rule vocabulary (routing, review, knowledge_selection, thresholds, budgets, preferences). Initial policy is seeded by an Operator; every change in v1 requires Operator approval via the learning path.

## Alternatives considered
- **Freeform config JSON** — rejected: any prose could count as "policy"; changes unauditable.
- **Autonomous policy evolution from M0** — deferred: revisit after M5 evidence exists.

## Consequences
Policy is not a security boundary — write scopes and tool allowlists remain code-enforced. Team-level budgets are expressible as policy rules. Cost: a JSON Schema for rules must exist from M0.

## Invariants
INV-12, INV-13, INV-14.

---

# File: docs/decisions/0005-banded-confidence-with-caused-append-only-changes.md

# ADR-0005: Banded confidence with caused, append-only changes

**Status:** accepted  **Date:** 2025-01-15

## Context
The original design stored `confidence_history` as a JSON array and required every change to have an EvidenceLink — which contradicted scheduled decay, which by definition has no new evidence. That contradiction was the design's sharpest internal inconsistency.

## Decision
Confidence is a band (`low` | `moderate` | `high`) on the Hypothesis. Every transition is recorded as a first-class, append-only `ConfidenceChange` with exactly one cause: an EvidenceLink (`cause_kind="evidence"`) or a decay Task reference (`cause_kind="decay"`). No orphan changes.

## Alternatives considered
- **Continuous numeric confidence (0–1)** — rejected: false precision the underlying judgments cannot support; harder to attribute causally.
- **Keep the JSON array** — rejected: unqueryable, no enforcement point, no per-cause typing.

## Consequences
INV-05/06/08 exist because the cause is now a typed reference. Banded steps make decay arithmetic simple and auditable.

## Invariants
INV-05, INV-06, INV-08.

---

# File: docs/decisions/0006-decay-as-scheduled-maintenance.md

# ADR-0006: Decay as scheduled maintenance

**Status:** accepted  **Date:** 2025-01-15

## Context
Silence is not disproof, but stale assessments must lose standing automatically or the world model ossifies. The tension: automatic yet accountable.

## Decision
Only scheduled `apply_decay` Tasks lower bands for staleness, per the domain's `decay_window` and `decay_action`. Decay never rejects a Hypothesis and never updates `last_touched_at` — only newly accepted evidence does that. When all of a Thread's active hypotheses have been `low` for one window, the Thread becomes `dormant` (reversible by triage).

## Alternatives considered
- **Model-decided decay inside update tasks** — rejected: unaccountable judgment wearing maintenance clothing; would violate INV-05.
- **Time-based auto-rejection** — rejected: a hypothesis that is merely quiet may still be the best explanation.

## Consequences
Rejection remains a deliberate act with a recorded reason (INV-07). Domain packs may tune windows and band-step but may never make decay reject.

## Invariants
INV-05, INV-07, INV-08.

---

# File: docs/decisions/0007-generalized-evidence-links-with-deterministic-validation.md

# ADR-0007: Generalized evidence links with deterministic validation

**Status:** accepted  **Date:** 2025-01-15

## Context
The original EvidenceLink connected signals to hypotheses only. Evaluations also need provenance (citing outcomes and artifacts), and the quote rule — the system's strongest anti-fabrication control — needed a single, enforceable formulation.

## Decision
EvidenceLink is polymorphic: `subject_kind ∈ {hypothesis, evaluation}`, `source_kind ∈ {signal, outcome, artifact}` — every source carrying an immutable hashed snapshot. Validation is deterministic: the quote must be the exact substring at the supplied offsets, and the snapshot hash must match; any mismatch rejects. Stance vocabulary is `supports | challenges | mentions`, and only the first two may anchor a ConfidenceChange.

## Alternatives considered
- **Whole-document links without quotes** — rejected: nothing verifiable; drift between claim and source invisible.
- **Model-judged quote validity** — rejected: reintroduces trust in model output (violates ADR-0009).

## Consequences
This is the primary hallucination firewall. Rejection events feed the validation-rejection-rate metric — the earliest prompt-quality signal. Cost: render-time citation assembly must consume only validated links (ADR-0008).

## Invariants
INV-03, INV-04, INV-06.

---

# File: docs/decisions/0008-durable-artifacts-with-code-assembled-citations.md

# ADR-0008: Durable Artifacts with code-assembled citations

**Status:** accepted  **Date:** 2025-01-15

## Context
Rendered outputs are where fabrication does real damage — they are what humans read. Yet the quote standard applied to EvidenceLinks was not applied to outputs; a model asked to "include sources" will fabricate them.

## Decision
Artifacts are durable: identity, hashed content snapshot, lifecycle (`draft`/`delivered`/`superseded`/`discarded`). The render flow is fixed: code builds the evidence pack from validated links → model drafts prose against the pack only → **code** assembles the citation footer → deterministic post-check rejects any URL/link pattern in the model-authored body. In v1, acting is represented by the Task that creates or delivers an Artifact; a separate external-Action entity is deferred.

## Alternatives considered
- **Model writes the full document including references** — rejected: the one place trust in model output is most expensive.
- **No citations in v1** — rejected: provenance is the product's credibility, not a feature.

## Consequences
Render templates carry citation styles; the model's prompt explicitly excludes citation authoring. Cost: one post-check to maintain; bodies slightly constrained.

## Invariants
INV-04, INV-10, INV-11, INV-14.

---

# File: docs/decisions/0009-agents-propose-code-commits.md

# ADR-0009: Agents propose, code commits

**Status:** accepted  **Date:** 2025-01-15

## Context
Durable state must be deterministic-valid regardless of what the model returns — including on bad days, and including when a second model acts as judge.

## Decision
Graph nodes return proposal objects. Core repositories/services validate schema, ownership, write scope, state transitions, and evidence, then commit atomically. No model — and no model-as-judge — is the final arbiter of any write.

## Alternatives considered
- **LLM judge with write authority** — rejected: same trust problem one step removed.
- **Prompt-only discipline ("never write directly")** — rejected: convention is not enforcement; the commit path must make the correct action the only action.

## Consequences
The write-scope matrix (`docs/tasks.md` §4) and the commit services are the enforcement surface. Cost: every write funnels through `/core`; graph code is slightly more indirect.

## Invariants
INV-02, INV-13, INV-14.

---

# File: docs/decisions/0010-durable-records-over-shared-conversation.md

# ADR-0010: Durable records over shared conversation

**Status:** accepted  **Date:** 2025-01-15

## Context
The default shape for multi-step AI work is a shared transcript. Transcripts are ephemeral, unqueryable, and cannot survive worker replacement — the opposite of what a persistent team needs.

## Decision
Workers coordinate exclusively through durable records and references (IDs). LangGraph checkpoints and model transcripts are execution state, never team memory. There are no persistent Agent entities in v1: a worker is identified through Task and Event provenance and may be a model call, a deterministic service, or a human Operator. Agent personas are a deferred concept.

## Alternatives considered
- **Shared team transcript as memory** — rejected: unreadable by code, unbounded, unversioned; violates the premise by construction.
- **Persistent agent personas with private memory** — deferred: revisit only if task-type diversity proves insufficient for behavior shaping.

## Consequences
Every task's context must be assemblable from entities alone — context loaders are a first-class component. Cost: some redundancy in stored references versus a transcript.

## Invariants
INV-01, INV-11.

---

# File: docs/decisions/0011-operator-actions-as-manual-tasks.md

# ADR-0011: Operator actions as manual Tasks

**Status:** accepted  **Date:** 2025-01-15

## Context
Operator seeding, outcome recording, and approvals are durable writes. Making `Event.task_id` nullable for "human" actions would create two attribution schemes and a validation bypass.

## Decision
Operators act through manual task types — `manual_signal_ingest`, `record_outcome`, `approve_learning_change`, `seed_knowledge` — created by the API. Operator identity is recorded in the Event payload. Every durable write, human or machine, traces to a Task.

## Alternatives considered
- **Nullable task_id + separate actor columns everywhere** — rejected: two attribution models to maintain, and operator writes would skip task validation.
- **Direct operator writes outside the task system** — rejected: the exact bypass INV-02 exists to prevent.

## Consequences
Uniform provenance and uniform validation. Cost: trivial ceremony for operators (an API call is a Task).

## Invariants
INV-02, INV-12, INV-13, INV-14.

---

# File: docs/decisions/0012-signal-dispositions-record-triage.md

# ADR-0012: Signal dispositions record triage

**Status:** accepted  **Date:** 2025-01-15

## Context
Signals are unowned (ADR-0001), so nothing in the original design recorded which team matched a signal to which thread — or dismissed it. Untriaged signals became an invisible backlog; multi-team relevance was unrepresentable.

## Decision
`SignalDisposition`: one row per (signal, team), with disposition `matched | new_thread | noise | duplicate | deferred`, a reason, and the deciding Task. All dispositions except `deferred` are terminal; `deferred` can be refined by an update task. Missing dispositions are queryable as backlog.

## Alternatives considered
- **A `processed` boolean on Signal** — rejected: assumes a single team; no reasons; no duplicate semantics.
- **Implicit triage (absence of action = noise)** — rejected: invisible decisions compound; violates INV-09.

## Consequences
The oil walkthrough's rates-desk line (same signal, opposite dispositions) is representable. Cost: one row per signal-team pair; triage writes go through the scope matrix.

## Invariants
INV-09, INV-13, INV-14.

---

# File: docs/decisions/0013-polymorphic-outcomes-and-minimal-prediction-checks.md

# ADR-0013: Polymorphic outcomes and minimal prediction checks

**Status:** accepted  **Date:** 2025-01-15

## Context
Prediction verification is a headline use case, but the original Outcome referenced only task/artifact/thread — with multiple active hypotheses per thread, a check could not name the hypothesis it verifies. The full Expectation entity was deferred as too heavy for v1.

## Decision
Outcome subject is polymorphic (`subject_kind`/`subject_id`), mirroring EvidenceLink. For predictions, v1 pulls in the *minimal* expectation semantics: `expected` JSON with a fixed schema (`resolution_condition`, `check_by`, `predicted_band`), recorded as two Outcomes — `prediction_registered` (before the outcome is known; observation fields nullable for this type only) and `prediction_check` (the observation, naming its registration). Overdue registrations are surfaced by the scheduler.

## Alternatives considered
- **Full Expectation/Prediction entity with scoring now** — deferred: more than the smallest loop needs; the deadline covers the v1 evaluation need.
- **Thread-level linkage only** — rejected: ambiguous with competing hypotheses, which is the system's normal state.

## Consequences
Registrations are honest — committed before results exist. Cost: two-outcome flow for one prediction; nullable observation fields confined to one outcome_type. Documented in `docs/walkthrough.md` §4.

## Invariants
INV-04, INV-12, INV-13.

---

# File: docs/decisions/0014-atomic-commits-revalidation-idempotency.md

# ADR-0014: Atomic commits with revalidation and idempotency

**Status:** accepted  **Date:** 2025-01-15

## Context
Two update tasks can touch one thread concurrently, and queue retries re-execute tasks. Last-writer-wins would silently corrupt the world model.

## Decision
Per-proposal validation; the valid set commits atomically all-or-nothing. Every transition re-checks preconditions at commit (`UPDATE … WHERE status = expected`); conflicts reject with an Event and the worker re-proposes against fresh state. Commits are recorded as Events keyed by Task id, making retries idempotent. Queue-level per-thread serialization is an optimization, never the correctness mechanism.

## Alternatives considered
- **Last-writer-wins with audit** — rejected: audit after corruption is not integrity.
- **Distributed locks as the guarantee** — rejected: the queue is infrastructure, not the correctness layer; locks leak on crash.

## Consequences
Conflicts are visible (Events) and cheap (re-propose). Cost: commit services carry optimistic checks; the walkthrough's TSK-203 demonstrates the semantics.

## Invariants
INV-05, INV-07, INV-13, INV-14.

---

# File: docs/decisions/0015-technology-stack.md

# ADR-0015: Technology stack

**Status:** accepted  **Date:** 2025-01-15

## Context
One runtime for kernel, agents, and API; a durable store with vector similarity; queues and schedules; resumable graphs — without the stack owning the commit path.

## Decision
Python 3.12+; PostgreSQL 16 + pgvector; Alembic (migrations are the authoritative schema); SQLAlchemy 2.x async; Redis + arq; LangGraph for resumable graphs (execution state only); Anthropic SDK called directly inside graph nodes; FastAPI; filesystem snapshots in dev, S3-compatible later; pytest + pytest-asyncio with real Postgres/Redis for integration tests.

## Alternatives considered
- **Temporal** — deferred: no runs genuinely span days with human waits yet; revisit when they do.
- **Claude Agent SDK / Managed Agents inside the kernel loop** — rejected for v1: the kernel must own the commit path; reconsider later for dev-team implementation workers where filesystem/command execution is central.
- **LangChain abstractions over model calls** — rejected: indirection between the kernel and the model boundary it controls.

## Consequences
Alembic migrations are authoritative; `architecture.md` §3 is narrative. Metrics come from Events + task accounting, no new infrastructure in v1.

## Invariants
INV-01, INV-02.

---

# File: docs/decisions/0016-domain-packs-cannot-extend-the-kernel.md

# ADR-0016: Domain packs cannot extend the kernel

**Status:** accepted  **Date:** 2025-01-15

## Context
Domain specifics (feeds, vocabularies, heuristics, templates) must not fragment the kernel into per-domain schemas, or shared invariants become per-domain suggestions.

## Decision
A pack supplies exactly seven things: `signal_sources`, `entity_vocabulary`, `match_heuristics`, `render_templates`, `decay_window`, `decay_action`, `dedup_policy` — plus optional prompt templates and normalizers. Packs may not add kernel tables or columns, bypass validation, write outside task scopes, or define decay that rejects. The second pack (devteam) is the boundary's pressure test: if it needs kernel changes, revisit the abstraction instead of patching.

## Alternatives considered
- **Per-domain schema extensions** — rejected: N-way kernel fork; invariants tested N times.
- **Config-only packs (no code)** — rejected: heuristics and templates are code, and pretending otherwise hides logic in YAML.

## Consequences
Kernel stays small and uniformly tested; devteam vs. newsroom differences (14-day vs. 72-hour decay, release-notes dedup) live entirely in pack configuration. Cost: some domain nuance must be expressed within the fixed vocabulary.

## Invariants
INV-08, INV-09, INV-14.

---

# File: docs/decisions/0017-dedup-at-triage-not-ingestion.md

# ADR-0017: Dedup at triage, not ingestion

**Status:** accepted  **Date:** 2025-01-15

## Context
Syndication would let one wire story inflate confidence fifty-fold. But ingestion dedup by content similarity would silently discard signals, and "identical" is only definable per-origin.

## Decision
Uniqueness at ingestion is `(origin_url, content_hash)` only: identical refetch from the same origin creates no new Signal; different content or origin does. Cross-origin near-duplicates are dispositioned `duplicate` at triage under the domain's `dedup_policy` (similarity threshold + lookback). Dispositions are immutable history; a mis-disposition is corrected by learning, not by rewriting.

## Alternatives considered
- **Global content-hash dedup across origins** — rejected: loses the (weak but real) signal that multiple outlets carried the item; conflates identity with relevance.
- **Similarity dedup at ingestion** — rejected: ingestion must stay cheap and lossless; a wrong discard at ingestion is unrecoverable, while a wrong `duplicate` disposition at triage is at least visible and evaluable.

## Consequences
The devteam walkthrough's failure (a canonical release-notes signal absorbed by a repost's disposition) is the known cost — deliberately retained so evaluation can catch it and the practice can be revised (K-003 v1 → v2). Triage refinement scope in v1 covers `deferred` only.

## Invariants
INV-03, INV-09, INV-12.

---

# File: docs/decisions/0018-projections-are-never-authoritative.md

# ADR-0018: Projections are never authoritative

**Status:** accepted  **Date:** 2025-01-15

## Context
Summaries and embeddings are convenient — and lossy, lagging, and model-dependent. If any decision path reads a projection, drift becomes silent error.

## Decision
Entities are the only authority. Thread summaries persist with `summary_basis` (the hypothesis IDs that produced them); embeddings persist with `embedding_model` and are regenerated per entity class under one model version (reindex job) so similarity stays coherent. Prompts and raw model responses may be persisted as execution records but are never read as team state.

## Alternatives considered
- **Treat `thread.summary` as the thread's truth** — rejected: the summary would decay independently of its evidence.
- **No persistence of projections** — rejected: recompute-on-read is wasteful for hot paths like triage similarity.

## Consequences
Decision paths (update, render, evaluation) load entities; projections serve retrieval and display only. Cost: `embedding_model` bookkeeping and a reindex path.

## Invariants
INV-01, INV-11.

---

# File: docs/decisions/0019-documentation-designed-for-agent-workforce.md

# ADR-0019: Documentation designed for an agent workforce

**Status:** accepted  **Date:** 2025-01-15

## Context
A primary workforce for building and operating Watch is LLM agents. For them, the documentation is the interface: ambiguity becomes wrong code, and history mixed into specs becomes resurrected rejected ideas.

## Decision
One responsibility per file (`README`, `AGENTS.md`, `PLAN.md`, `docs/glossary|invariants|architecture|tasks|walkthrough|domains`, `docs/decisions/`). Sources of truth are declared (migrations > schema sketches; ADRs for why; PLAN for roadmap). Invariants are mirrored into `AGENTS.md` with an explicit "edit there first" rule. Glossary terms carry banned synonyms. Specs are written as current truth only; history lives exclusively in ADRs.

## Alternatives considered
- **Single comprehensive README** — rejected: every session pays the full context cost, and drift is undetectable.
- **External wiki** — rejected: not versioned with code, invisible to agents in-repo.

## Consequences
Maintenance triggers in `AGENTS.md` §10; the PR rule that code contradicting a doc is never merged. Cost: mirrored content must be kept in sync deliberately (the mirror is marked as such).

## Invariants
None directly; this ADR governs the repository itself.