# Watch in plain language

**Role of this document:** orientation only. It gives the whole picture in one read; it is not an authority. If it disagrees with [PLAN.md](../PLAN.md) about current status, or with [architecture.md](architecture.md), [invariants.md](invariants.md), [tasks.md](tasks.md), accepted ADRs, or implementation evidence, those sources win and this document must be corrected.

**Status rule:** this page does not own milestone or gate status. The implementation map below is a dated snapshot, not a second status tracker. For what is current, gated, or next, read [PLAN.md](../PLAN.md).

**Last checked against the repository:** 2026-11-15. The implementation-state descriptions are a static documentation/code review, not a fresh test run. For current milestone status and verified SHAs, use [PLAN.md](../PLAN.md).

## Current development path

B5.4 is complete and closed. The next lifecycle track is B6, beginning with a verified repository baseline and a read-only audit; implementation scope must come from demonstrated defects or proof gaps. After B6, the RW workstream completes the world-memory reasoning foundation. R8 then tests the completed architecture across three domains.

**R8 is planned to start on November 23, 2026.** That date is not a finish deadline. R8 must not start while a fundamental layer is still missing; unfinished foundation work is not added during the pressure test.

## At a glance

**Goal.** Build teams of AI-assisted workers that become expert in a domain by forcing their work through a governed record instead of trusting what a model says.

**The one rule.** Nobody writes to the durable record directly. A worker (a model or a human) proposes; ordinary application code checks the proposal against immutable sources and the rules; only then is it committed, with a recorded cause.

**The intended loop.** Observe sources → form and test beliefs → act through Tasks → record Outcomes → evaluate honestly → propose a lesson → a human approves → the lesson is retrieved in a later task.

### What exists today

| Floor of memory | Meaning | Repository reality at the check date |
|---|---|---|
| Perception | Raw observations (Signals and immutable Snapshots) | **Built in part.** Signal ingestion and content-addressed Snapshots exist. |
| Belief | Threads, competing Hypotheses, evidence, confidence | **Designed, not built.** The ORM has no Thread, Hypothesis, ConfidenceChange, or SignalDisposition models. EvidenceLink exists, but its current schema is limited to Evaluation subjects and Outcome/Signal sources; it does not yet support Hypothesis evidence. The reasoning workers are not implemented. |
| Skill | Lessons about the team's own methods (KnowledgeItems) | **Built and still being extended.** Distillation, Operator approval, create/revise/revalidate and lifecycle operations are implemented to the extent recorded in PLAN.md. |
| Doctrine | How the team operates (TeamPolicy) | **Exists.** Models cannot write it. |
| Instinct | What the model just knows | Not ours. It lives in model weights and is not durable Watch experience. |

Also built are Objectives, Plans and Tasks, task outcomes and recovery, Evaluations, Knowledge Cores/RAG retrieval into Task context, and a StrategyProposer. See PLAN.md and the implementation map in CHANGE_MAP.md for the current state of each.

The task names triage_signal, update_thread, operator_update, and apply_decay appear in specifications and in a Task-type whitelist, but that is not implementation. A whitelist entry is not a worker, data model, commit service, or end-to-end path.

Designed but not built includes the Thread/Hypothesis reasoning loop, signal triage and belief decay, rendered Artifacts with code-written citations, Consultations, and the team-setup advisor. See [architecture.md](architecture.md), [tasks.md](tasks.md), and the relevant ADRs for their intended contracts.

### How the vision maps to the work

| Part of the goal | Where it lives | Implementation reality |
|---|---|---|
| A governed record that workers cannot bypass | Kernel and Control layers | Built for the implemented paths; the belief-layer commit path is still future work. |
| Lessons that are earned, versioned and reviewable | Experience and KnowledgeItem lifecycle | Built and still being extended. |
| Beliefs grounded in checkable evidence | Hypothesis layer | Specified; implementation has not started. |
| Proof across different domains | R8 pressure test | A planned validation of the completed shared architecture, including the implemented world-memory reasoning loop; R8 does not add missing foundational layers. |

For current milestone status and authorization, read PLAN.md.

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
| **Belief** | What the team thinks is happening in the world | Threads, Hypotheses, evidence | Workers may propose; application rules validate | Yes, by the designed decay policy |
| **Perception** | Raw observations of the world | Signals and immutable Snapshots | Append-only ingestion | No; old observations remain, but stop being current |

Skills and beliefs need opposite time policies. A belief such as "leverage is building and a squeeze is coming" should lose confidence if the world goes quiet. A hard-won practice such as "register a price level, not just a direction" should not disappear after a quiet month. If beliefs never decayed, the board would fill with stale hunches; if lessons decayed like beliefs, the team would forget hard-won methods.

The Belief layer and its decay are designed but not implemented in the current repository snapshot.

## 3. The research-desk metaphor

Think of a research desk at a newsroom:

- **The desk** is the durable thing: files, a wall of current beliefs, a binder of methods, and a logbook. In Watch, this is the database and governed application layer.
- **The reporters** are brilliant but temporary: a new one every shift, with no dependable memory overnight. In Watch, these are model calls and other workers.
- **The mailroom** copies everything that arrives and stamps it with a fingerprint. The original may later change or disappear; the stored copy does not. In Watch, these are Signals and Snapshots.
- **The wall** holds the current story: what is supported, disputed, or still open. Competing explanations remain visible with their reasons. In Watch, these are Threads and Hypotheses; this part is specified but not yet built.
- **The clerk** is simple and reliable. Every suggestion is checked against the immutable source and the rules. A failed check is rejected with a recorded reason. In Watch, this is deterministic validation and the commit boundary.
- **The binder** holds what the desk learned about its own work. A lesson is proposed from an Outcome and Evaluation, reviewed by a human, versioned, and retained with its history. In Watch, this is the KnowledgeItem lifecycle.
- **The expert** is one of the workers, not an exempt authority. The intended Operator update path uses the same validation as a model worker; that path is specified but not yet implemented.

The motto: **reporters leave; the desk remembers.**

## 4. One day at a desk — an illustration

The following story follows the crypto-desk scenario in [walkthrough.md](walkthrough.md), Scenario C. It illustrates the intended design; it is not a statement that the whole flow runs today.

**Morning.** The mailroom fetches a market snapshot and renders it into a fixed-format text copy. The copy is hashed, so a later quote can be checked against exact source text. Signal ingestion and immutable Snapshots are built.

**Triage.** A repost is classified as a duplicate of the original publisher's version. This triage flow is specified, not built.

**A reporter works the wall.** A worker proposes that funding and open-interest data support one hypothesis. The validator checks the quoted spans, stance, cause, and transition. A second proposal that tries to raise confidence from an article that merely mentions the theory is rejected. The validation contract is specified; the Thread/Hypothesis commit path is not built.

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

1. **Beliefs that lose confidence with time.** Designed, not built.
2. **Competing explanations remain visible.** Designed, not built.
3. **Grounded assertions.** Quotes are checked against immutable, hashed source copies; the general source-integrity foundations exist, while the Hypothesis evidence path is not built.
4. **A closed learning loop.** Outcomes are evaluated and accepted lessons can affect later work; the team-experience portion is built, while prediction-driven belief correction is not.

One honest boundary: Watch does not manufacture a trading edge or guarantee predictive accuracy. It aims to structure evidence, accountability, and improvement. Specialized quantitative tooling remains a separate job that Watch may govern or wrap.

## 7. Where AI agents fit

**Role 1: builders.** Coding agents help build Watch. AGENTS.md is the repository operating contract, the glossary fixes vocabulary, invariants define hard constraints, and ADRs record decisions. Coding agents should inspect, propose, implement, and verify within those boundaries.

**Role 2: proven before trusted.** The smallest Kernel path established proposal, deterministic validation, atomic commit, and an Event using deterministic ingestion before model workers were introduced.

**Role 3: workers.** A model worker reads context assembled from durable records and proposes changes. It must not write durable state directly. Existing model-backed services use narrow provider interfaces where implemented; the planned update_thread reasoning worker is not yet implemented. Human approval is designed to happen between Tasks, not by blocking a running worker.

**Role 4: future consumers.** A future Watch desk could provide validated, versioned, outcome-tested skills to other agent systems. Exporting knowledge beyond the Kernel would need its own decision because it changes important boundaries. This is a direction, not current authorization.

In one line: **agents give Watch its labor; Watch gives agents their experience.**

## 8. The whole thing in one paragraph

Watch is intended to be a small software organization that behaves like a research desk. AI models, humans, and deterministic services do the reading and thinking as temporary workers, while durable records preserve observations, evidence, beliefs, plans, outcomes, evaluations, and lessons. The governing rule is that no worker writes durable state directly: proposals are checked against immutable sources and application rules, then committed with a recorded cause. Beliefs should change with evidence and lose confidence with silence; predictions should be registered before they can be graded; lessons should enter team memory only through evaluation and human approval. The implemented foundation already supports governed Tasks, outcomes, evaluation, and durable team experience. The missing Thread/Hypothesis reasoning loop is a substantial part of the intended product and remains future implementation work. Watch is not competing with agent frameworks for the work itself; it is trying to turn forgettable work into an accountable team history that can be reused.
