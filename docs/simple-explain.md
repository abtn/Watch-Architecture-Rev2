# Watch in plain language

**Role of this document:** orientation only. It gives the whole picture in one read; it is not an authority. If it disagrees with [PLAN.md](../PLAN.md) about current status, or with [architecture.md](architecture.md), [invariants.md](invariants.md), [tasks.md](tasks.md), accepted ADRs, or implementation evidence, those sources win and this document must be corrected.

**Status rule:** this page does not own milestone or gate status. The implementation map below is a dated snapshot, not a second status tracker. For what is current, gated, or next, read [PLAN.md](../PLAN.md).

**Documentation boundary:** this page is an explanatory overview, not implementation evidence. Current milestone status, verification SHAs, and authorization are maintained in [PLAN.md](../PLAN.md).

## Current development path

Watch's implementation sequence, milestone status, evidence, and authorization gates are maintained exclusively in [PLAN.md](../PLAN.md). This page explains the architecture and its intended direction; it is not a parallel implementation tracker. At a high level, Watch is building a persistent cognitive architecture in which model and human reasoning operates through shared, governed context while deterministic application mechanisms coordinate work and retain authority over durable state.

## At a glance

**Goal.** Build a persistent cognitive architecture for AI-assisted teams: a system that helps models and people reason with shared context, preserves what the team learns, and makes work coherent across changing workers and models.

**The one rule.** A worker's reasoning is a contribution, not authority. A model or human proposes; application code checks the proposal against immutable sources, permissions, and rules; only the authorized application path can commit durable state with provenance.

**The intended loop.** Observe sources → assemble relevant context → let workers reason and propose → coordinate and validate through Watch → act through Tasks → record Outcomes → evaluate → approve useful lessons → reuse eligible knowledge in later work.

### What Watch means by a cognitive architecture

The model still performs its own reasoning. Watch does not replace that reasoning with a deterministic algorithm, nor does it require one privileged LLM to act as the system's brain. Watch provides the shared context, memory, task state, coordination, and governed interfaces through which a model can do useful work. Its architecture is intended to support multiple replaceable model contributors over time; that is a design direction, not a claim that multi-model collaboration is currently implemented or authorized.

The distinction is important:

- **Models and people contribute cognition:** they interpret information, reason, compare possibilities, and propose actions or updates.
- **Watch provides cognitive continuity:** it preserves canonical records, evidence, decisions, outcomes, and accepted experience so later work can build on earlier work.
- **Deterministic application mechanisms retain authority:** they assemble permitted context, route bounded work, validate proposals, enforce permissions, and commit durable changes.

The biology-inspired language is an analogy for the organization of cognition, memory, and coordination. It is not a claim that Watch is conscious or that its software components map literally to human brain structures.

For implementation status, current milestones, and authorization, use [PLAN.md](../PLAN.md).

---

## 1. Why Watch exists

AI agent software has become good at doing things: using tools, browsing, writing code, and carrying out multi-step work. Agent systems also retain files, notes, and skills between conversations. An assistant can watch a subject and remember yesterday.

That still leaves a harder question once a system is relied on over months:

> **Who is allowed to change what the system believes, under what rules, and how do we know those changes were earned?**

Agent memory often falls into one of two patterns:

- **Frozen:** a human edits the skill file or prompt; the system does not learn through its own work.
- **Ungoverned:** an agent updates memory without provenance, verification, review, or a safe way to unlearn it.

Watch aims at a third pattern: memory that can change, but only through earned, verified, reviewable change. This is a design aim, not a claim that no other system does it.

## 2. The five floors of memory

"Memory" means several different things. Watch separates them because each needs a different rule for who may write it and whether time should fade it.

| Floor | What it is | In Watch | Who changes it | Does time fade it? |
|---|---|---|---|---|
| **Instinct** | What the AI already knows | Model weights | Nobody in Watch | No; it is not ours |
| **Doctrine** | How the team operates | TeamPolicy | Human approval only | No; reviewed, not decayed |
| **Skill** | What the team learned about its own methods | KnowledgeItems: practices and playbooks | Through evidence, evaluation, and approval | No; versioned and revised, not expired on a clock |
| **Belief** | What the team thinks is happening in the world | Threads, Hypotheses, evidence | Operator commits are implemented in RW-2; model workers and triage remain future work | Yes, by the designed decay policy, not yet implemented |
| **Perception** | Raw observations of the world | Signals and immutable Snapshots | Append-only ingestion | No; old observations remain, but stop being current |

Skills and beliefs need opposite time policies. A belief such as "leverage is building and a squeeze is coming" should lose confidence if the world goes quiet. A hard-won practice such as "register a price level, not just a direction" should not disappear after a quiet month. If beliefs never decayed, the board would fill with stale hunches; if lessons decayed like beliefs, the team would forget hard-won methods.

The Belief layer is partially implemented: Thread/Hypothesis/ConfidenceChange persistence and a deterministic Operator commit path exist. RW-3 implementation is merged, but formal RW3.4 acceptance remains deferred with seven PARTIAL qualifications; live provider calls remain unauthorized. Signal triage, decay, and retrieval projections remain unimplemented or deferred.

## 3. The research-desk metaphor

Think of a research desk at a newsroom:

- **The desk** is the durable thing: files, a wall of current beliefs, a binder of methods, and a logbook. In Watch, this is the database and governed application layer.
- **The reporters** are brilliant but temporary: a new one every shift, with no dependable memory overnight. In Watch, these are model calls and other workers.
- **The mailroom** copies everything that arrives and stamps it with a fingerprint. The original may later change or disappear; the stored copy does not. In Watch, these are Signals and Snapshots.
- **The wall** holds the current story: what is supported, disputed, or still open. Competing explanations remain visible with their reasons. In Watch, these are Threads and Hypotheses; the physical records and deterministic Operator update path are implemented. RW-3 model-worker implementation is merged, but formal acceptance remains deferred and live provider calls are not authorized; triage and decay remain future work.
- **The clerk** is simple and reliable. Every suggestion is checked against the immutable source and the rules. A failed check is rejected with a recorded reason. In Watch, this is deterministic validation and the commit boundary.
- **The binder** holds what the desk learned about its own work. A lesson is proposed from an Outcome and Evaluation, reviewed by a human, versioned, and retained with its history. In Watch, this is the KnowledgeItem lifecycle.
- **The expert** is one of the workers, not an exempt authority. RW-2 implements a deterministic Operator update path through the same validation boundary intended for model workers; human authorship is provenance, not an exemption.

The motto: **reporters leave; the desk remembers.**

## 4. One day at a desk — an illustration

The following story follows the crypto-desk scenario in [walkthrough.md](walkthrough.md), Scenario C. It illustrates the intended design; it is not a statement that the whole flow runs today.

**Morning.** The mailroom fetches a market snapshot and renders it into a fixed-format text copy. The copy is hashed, so a later quote can be checked against exact source text. Signal ingestion and immutable Snapshots are built.

**Triage.** A repost is classified as a duplicate of the original publisher's version. This triage flow is specified, not built.

**A reporter works the wall.** The deterministic Operator path can create a Hypothesis, attach Signal/Outcome evidence, and make a later evidence-caused ConfidenceChange. Exact quote offsets, source hashes, stance, Team scope, and legal transitions are checked before commit. The `update_thread` implementation is merged, but formal RW3.4 acceptance remains deferred and live provider calls are not authorized; signal triage remains future work.

**The prediction.** The desk registers a falsifiable claim before the result is known, with a measurable condition and deadline. The Outcome/Evaluation foundations exist, but the full prediction-to-Hypothesis loop depends on the unbuilt Belief layer.

**Two weeks later.** The observation is checked. A missed prediction returns as challenging evidence, and the system lowers confidence with an auditable cause. This belief update is not built.

**The learning.** An Evaluation identifies what the method got wrong. A new playbook is proposed, reviewed, approved, versioned, and retrieved in a later task. The team-learning path is built.

That last step is the product direction: **the desk gets experienced**, rather than merely accumulating notes.

## 5. A skill that updates versus a skill that learns

When an agent updates a skill file, important questions can remain unanswered: who changed it, why, from which experience, whether that experience was assessed, what prevented a bad result from becoming doctrine, whether the diff is visible, and whether the change can be reviewed or reversed.

Watch treats a durable lesson as a governed change. A proposed lesson resembles a pull request against the team's own methods: the application validates it, a human reviews it, the previous version remains available, and the decision is attributable. This is why Watch's learning path is more than an agent writing to a memory file.

## 6. Watch next to an agent framework

- **Agent frameworks orchestrate behavior:** how work gets done, step by step, with tools.
- **Watch governs durable team state:** what may become a recorded belief or lesson, on what evidence, under which rules, and with what history.

Watch does not aim to replace the hands. It is the ledger and governance layer the hands must use.

Four ideas are central to the intended product:

1. **Beliefs that lose confidence with time.** Designed; RW-5 decay execution is not built.
2. **Competing explanations remain visible.** The Hypothesis records and deterministic Operator transitions are implemented.
3. **Grounded assertions.** RW-2 implements Hypothesis EvidenceLinks with exact Snapshot hash, quote, and offset validation.
4. **A closed learning loop.** Outcomes are evaluated and accepted lessons can affect later work; prediction-driven belief correction and model-driven updates remain incomplete.

One honest boundary: Watch does not manufacture a trading edge or guarantee predictive accuracy. It aims to structure evidence, accountability, and improvement. Specialized quantitative tooling remains a separate job that Watch may govern or wrap.

## 7. Where AI agents fit

**Role 1: builders.** Coding agents help build Watch. AGENTS.md is the repository operating contract, the glossary fixes vocabulary, invariants define hard constraints, and ADRs record decisions. Coding agents should inspect, propose, implement, and verify within those boundaries.

**Role 2: proven before trusted.** The smallest Kernel path established proposal, deterministic validation, atomic commit, and an Event using deterministic ingestion before model workers were introduced.

**Role 3: workers.** A model worker reads bounded context assembled from durable records and proposes changes; it must not write durable state directly. The deterministic human `operator_update` path is implemented in RW-2. The RW-3 `update_thread` implementation is merged, but formal RW3.4 acceptance remains deferred and live provider calls remain unauthorized. The architecture is intended to support multiple replaceable model contributors through shared Watch context and coordination; it does not depend on a privileged primary LLM. Human approval happens between Tasks, not by blocking a running worker.

**Role 4: future consumers.** A future Watch desk could provide validated, versioned, outcome-tested skills to other agent systems. Exporting knowledge beyond the Kernel would need its own decision because it changes important boundaries. This is a direction, not current authorization.

In one line: **agents give Watch its labor; Watch gives agents their experience.**

## 8. The whole thing in one paragraph

Watch is intended to be a persistent cognitive architecture that behaves like a research desk. Models and people contribute interpretation and reasoning as replaceable workers; deterministic application services assemble context, coordinate bounded work, validate proposals, and control commits. Durable records preserve observations, evidence, beliefs, plans, outcomes, evaluations, and lessons. The governing rule is that no worker writes durable state directly: proposals are checked against immutable sources and application rules, then committed with a recorded cause. Beliefs should change with evidence and lose confidence with silence; predictions should be registered before they can be graded; lessons should enter team memory only through evaluation and human approval. The implemented foundation supports governed Tasks, outcomes, evaluation, and durable team experience. The Thread/Hypothesis layer and deterministic human commit path exist; RW-3 model-worker implementation is merged but formal acceptance remains deferred, while triage, decay, and retrieval work remain incomplete. Watch is not a replacement for agent frameworks or model reasoning. It is the persistent cognitive and governance architecture intended to turn temporary work into an accountable team history that can be reused.
