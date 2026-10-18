# docs/invariants.md

# Invariants

These are the normative, non-negotiable rules of Watch. They define what the system must preserve; they do not imply that every later-phase capability is already implemented in the current checkout. Use `PLAN.md`, the current code/migrations, and executed tests to determine implementation status. None of the invariants may be bypassed by a domain pack, a graph, or an operator shortcut.

Each invariant states the rule, why it exists, intended enforcement, and what a violation looks like. When writing or reviewing code, treat this list as a checklist and verify the enforcement evidence rather than inferring it from this document alone.

**Change process:** invariants are edited here first, mirrored to `AGENTS.md` second, reflected in tests third. A PR that changes behavior without updating invariants first is rejected.

---

### INV-01 — Workers coordinate through durable records, not conversation
Model transcripts and graph state are execution-scoped. Cross-task and cross-run coordination happens only through persisted entities and references to them.
**Why:** the team must survive the death of any worker, model call, or run; transcripts are ephemeral and unqueryable.
**Enforcement:** no persistent transcript tables; LangGraph checkpoints treated as execution state only; context for every Task is loaded from entities.
**Violation:** an update task "remembers" the previous task by passing the prior model chat log forward instead of reading committed records.

### INV-02 — Agents propose, code commits
No model output enters durable state by being trusted — including output from a second model used as judge. Application code validates schema, ownership, write scope, state transitions, and evidence before any commit.
**Why:** model output is probabilistic; durable state must be deterministic-valid and auditable.
**Enforcement:** all writes go through core repositories/services that enforce scope and validation; graph nodes return proposal objects, never perform writes.
**Violation:** a graph node parses model JSON and writes a Hypothesis directly to the database.

### INV-03 — Sources are immutable
Snapshots are never overwritten or edited. A re-fetch with identical content creates no new Signal; a re-fetch with new content creates a new Signal. Corrections arrive as new evidence, not edits.
**Why:** provenance and quote validation are meaningless against mutable sources.
**Enforcement:** snapshot storage is write-once and content-addressed; hash checked at every commit that references a snapshot.
**Violation:** a connector replaces the stored text of an article with the publisher's post-publication edit.

### INV-04 — Quotes are checked, not trusted
Every quoted span in an EvidenceLink must be the exact substring at the supplied offsets of the hashed Snapshot, and the hash must match the stored hash. Any mismatch rejects the proposal.
**Why:** fabricated or drifted quotes are the primary hallucination risk in evidence-based work.
**Enforcement:** deterministic offset + hash validation in the commit path; rejection recorded as an Event with a reason.
**Violation:** an EvidenceLink is accepted because the model asserted the quote came from the source.

### INV-05 — No unexplained confidence change
Every ConfidenceChange has a recorded cause: an EvidenceLink, or a scheduled decay Task reference. Nothing else.
**Why:** confidence is the system's core output; unexplained drift destroys its value.
**Enforcement:** `cause_kind` + non-null cause reference required by schema and validation; orphan changes rejected.
**Violation:** an update task lowers a hypothesis band "for tidiness" before proposing new evidence.

### INV-06 — Only supporting or challenging evidence drives confidence
EvidenceLinks with Stance `mentions` may be recorded but may never anchor a ConfidenceChange.
**Why:** mere mention is context, not argument; counting mentions as evidence inflates confidence without information.
**Enforcement:** commit validation rejects a ConfidenceChange whose EvidenceLink has `stance="mentions"`.
**Violation:** three articles that merely name OPEC are used to raise a price-cut hypothesis to `high`.

### INV-07 — Threads retain competing hypotheses
A new favored explanation never deletes alternatives. Rejection and supersession are explicit, name the affected Hypothesis, give a reason, and emit an Event.
**Why:** premature convergence is the failure mode this whole design exists to prevent.
**Enforcement:** no delete path for Hypotheses; transitions validated; Events required; merge is expressed as supersession naming the surviving Hypothesis.
**Violation:** an update task deletes the losing hypothesis because the model found it "unlikely".

### INV-08 — Decay is scheduled and conservative
Only `apply_decay` Tasks lower confidence for staleness, on the Domain's decay window and decay action. Decay never rejects a Hypothesis and never updates `last_touched_at`. Only newly accepted evidence does that.
**Why:** eager or model-initiated decay is unaccountable; decay is maintenance, not judgment.
**Enforcement:** decay writes permitted only to the `apply_decay` task type; validation rejects `cause_kind="decay"` from any other task.
**Violation:** a model decays a hypothesis inside an update task because the evidence "seemed old".

### INV-09 — Triage is recorded
Every Signal is dispositioned for every Team whose scope it plausibly enters: matched, new_thread, noise, duplicate, or deferred. No Signal silently disappears.
**Why:** untriaged signals create an invisible backlog and make noise levels unmeasurable.
**Enforcement:** SignalDisposition rows per (Signal, Team); backlog metrics read from missing/deferred dispositions.
**Violation:** a signal matching no heuristic simply produces no records.

### INV-10 — Artifacts cite what they used, and code writes the citations
The citation apparatus of an Artifact (sources, quotes, links) is assembled deterministically by code from the EvidenceLinks the render Task actually consumed. The model never authors citation metadata, and rendered bodies contain no bare URLs.
**Why:** user-facing artifacts are where fabrication does real damage; code-assembled citations make the provenance guarantee hold at the output boundary, not just the input boundary.
**Enforcement:** render graph builds the evidence pack first, model drafts prose against it, code appends the citation footer; a deterministic post-check rejects bodies containing URL/link patterns.
**Violation:** the render model appends its own source list from memory.

### INV-11 — Projections are not authority
Summaries, embeddings, dashboards, and retrieval indexes are regenerable and never the basis for a decision. Decisions read the underlying records.
**Why:** projections compress and lag; treating them as truth turns drift into error.
**Enforcement:** decision-making code paths read entities; `summary_basis` records which Hypotheses produced a summary; embeddings carry their model name for coherent regeneration.
**Violation:** a render task decides the story is "confirmed" by reading `thread.summary` instead of active Hypotheses and EvidenceLinks.

### INV-12 — Team memory changes only through the learning path
Creating, revising, or retiring a KnowledgeItem or TeamPolicy version requires a committed LearningChange, backed by a recorded Evaluation or an explicit Operator seed. In v1, policy changes additionally require Operator approval. No other path exists.
**Why:** one successful-looking outcome must never silently become a playbook; organizational rules must not be rewritten by model prose.
**Enforcement:** write scopes exclude KnowledgeItem/TeamPolicy from all task types except `approve_learning_change` and `seed_knowledge`; commit service checks evaluation basis, evidence, and target version.
**Violation:** an evaluation task bumps a KnowledgeItem's confidence directly because the evaluation went well.

### INV-13 — Commits revalidate
At commit time, all preconditions are re-checked atomically: entity status, ownership, target version, and scope. Writes are idempotent per Task (re-execution after a retry never double-commits). Conflicting concurrent commits are rejected and re-proposed, never silently overwritten.
**Why:** two workers can touch the same Thread, and queues retry; last-writer-wins corruption is otherwise inevitable.
**Enforcement:** optimistic transitions (`UPDATE ... WHERE status = expected`); commit Events as idempotency markers; per-Thread serialization of update Tasks preferred at the queue level, with revalidation as the hard guarantee.
**Violation:** two concurrent update tasks both supersede the same Hypothesis and both succeed.

### INV-14 — Tasks stay in scope
A Task may write only its type's allowed entity kinds, use only its allowed tools, and only within its budget. Out-of-scope write attempts are rejected and recorded.
**Why:** scoped tasks are what make "agents propose, code commits" enforceable per-action, and budgets are what make costs bounded.
**Enforcement:** scope matrix in `docs/tasks.md` enforced in the commit path/runtime. `W`/`C` entries bound business/domain proposals; explicitly marked `K` entries bound only the corresponding application-managed Task lifecycle, Event, Snapshot, or enqueue side effect. Those writes are not exceptions to scope and are never worker-authored. Tool calls and token usage are attributed to the Task and counted against its budget.
**Violation:** a render task "helpfully" also updates the Thread summary.

### INV-15 — Human input enters through the same gates
No durable write bypasses validation because a human performed it. Operator contributions to world memory go through the same proposal and commit path as model workers; consultation answers, subject briefs, and team drafts are immutable, hashed snapshots; operator identity is recorded in Event payloads and is never a substitute for validation.
**Why:** the expert's value is their judgment, not an exemption. One validation path is auditable; two is a bypass waiting to be used.
**Enforcement:** manual task types route through the same core commit services; INV-04 quote checks apply to operator EvidenceLinks; snapshots required for consultation answers, subject briefs, and draft configurations.
**Violation:** an operator's EvidenceLink commits with a quote that does not match the snapshot "because the operator insisted".

### INV-16 — Plan dependencies gate Task admission
A Plan-linked Task must not start execution while any prerequisite Plan-action Task is not `done`. A failed prerequisite leaves dependent Tasks ineligible until the Plan is stopped or replanned; it does not imply success or rewrite Plan intent.
**Why:** Plan dependencies express intended prerequisites and must hold when ordinary Tasks execute.
**Enforcement:** the existing Task admission/claim path checks linked action prerequisites atomically before transitioning a Task to `running`; no separate scheduler or Task state is introduced.
**Violation:** a dependent Task starts while its prerequisite Task is pending, running, or failed.

---

## Invariant → test mapping

Planned for M0; each row is a named test module under `tests/invariants/`. Tests are written with the schema, before any agent code.

| Invariant | Test focus |
|---|---|
| INV-01 | no persistent transcript storage; task context built from entities |
| INV-02 | direct entity write from a graph node raises; proposal path required |
| INV-03 | snapshot immutability; identical refetch creates no Signal; changed refetch does |
| INV-04 | offset/hash mismatch rejected; exact quote accepted |
| INV-05 | ConfidenceChange without cause rejected |
| INV-06 | `mentions` cannot anchor a ConfidenceChange |
| INV-07 | no delete path; rejection/supersession require reason + Event |
| INV-08 | decay only from `apply_decay`; no auto-reject; `last_touched_at` untouched |
| INV-09 | every in-scope signal produces a disposition |
| INV-10 | citation footer matches consumed evidence; URL in body fails render |
| INV-11 | decision paths read entities, not projections |
| INV-12 | learning writes blocked outside learning task types; policy requires approval |
| INV-13 | concurrent conflicting commits: one succeeds, one rejects and re-proposes; retry does not double-commit |
| INV-14 | out-of-scope write rejected and recorded |
| INV-15 | operator quote mismatch rejected; consultation answer requires snapshot; operator identity present in Event payload |
| INV-16 | Plan-linked Task cannot start before prerequisite action Tasks are done; failed prerequisites keep dependents ineligible |