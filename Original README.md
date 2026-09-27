# README.md

# Watch

Watch is a framework for **persistent teams** that keep building understanding over time.

It is not primarily a pipeline that receives a question and produces an answer. A Watch team has a durable identity, a scope, a working policy, a memory of the world, and a record of what it has learned about its own methods. Workers — model calls, deterministic services, or humans — are temporary. The team's state survives every worker, every model call, and every run.

The useful question is not only:

> What do we currently understand about this situation?

It is also:

> What has this team learned about how it should investigate, decide, and act?

Concrete examples of a Watch team:

- a newsroom-style team watching oil markets, holding competing price hypotheses and rendering a briefing when the story is ready to be told;
- the same shape applied to an election: candidates, polls, claims, and what the evidence actually supports;
- a dev-team scout watching the technology landscape and maintaining an evidence-backed position on what to adopt, avoid, or investigate;
- an expert's own field: they put their theories on the board themselves, and the loop consults them when a judgment call needs a human — the answer becomes citable evidence like any other source.

## The operating loop

```text
Observe
  Signals, sources, immutable snapshots
        ↓
Reason
  Threads, competing hypotheses, evidence
        ↓
Act
  Tasks, workers, tools, rendered Artifacts
        ↓
Outcome
  What happened after the work
        ↓
Evaluate
  Did the work or the method produce the intended result?
        ↓
Learn
  Update team knowledge and, cautiously, team policy
        ↺
  Future tasks use the accumulated memory
```

There are two distinct kinds of memory:

- **World memory** — what appears to be happening in the world. Threads, Hypotheses, EvidenceLinks. Revisable by design and allowed to decay.
- **Team memory** — what the team has learned about its own practices, patterns, methods, and playbooks. KnowledgeItems and versioned TeamPolicy. Changes only through an explicit, auditable learning path.

A Thread is not a permanent truth. A playbook is not an unreviewed instruction. Every important change has a recorded cause.

## The working model

Four principles summarize how Watch behaves. They are restated here for orientation only; the canonical, enforceable statements — with rationale, enforcement mechanism, and violation examples — live in `docs/invariants.md`.

1. **Durable records, not conversation.** Workers coordinate through persisted records and references to records. Model transcripts and graph state are temporary execution detail.
2. **Agents propose, code commits.** No model output enters durable state by being trusted. Application code validates schema, ownership, write scope, and evidence before committing anything.
3. **No unexplained changes.** Every confidence change, every rejection or supersession, and every team-knowledge change has a recorded cause.
4. **Human input passes the same gates.** Experts contribute theories, answer consultations, and approve changes through the same validation path as any worker — being human is never an exemption.

Day to day, the team ingests immutable Signals, proposes evidence-linked updates to its Threads, lets stale confidence decay on a schedule, and mostly maintains its current understanding. When asked — or when a Trigger fires — it renders an Artifact. When judgment is needed, it opens a Consultation and waits between Tasks. Outcomes are recorded afterward and evaluated, and occasionally produce controlled learning changes. `docs/walkthrough.md` traces one Thread through this entire cycle with concrete records.

## Domain packs

A **domain pack** adapts the shared kernel to a subject area. It supplies signal sources, entity vocabulary, match heuristics, render templates, and decay behavior. Kernel entities and the learning loop are identical across packs.

- **Newsroom** — watches an ongoing story: a company situation, a policy fight, a slow-moving event. Maintains what is confirmed, what is disputed, and which explanations remain plausible.
- **Dev-team scout** — watches tools, patterns, and postmortems. Maintains an evidence-backed position on what to adopt, avoid, or investigate.
- **Generalist** — shipped with the kernel: manual intake plus any RSS feed, default vocabulary, standard templates. A setup advisor drafts a team configuration for any subject; a human approves it. No new code needed to watch something new.

The pack contract and all three configurations are specified in `docs/domains.md`.

## What working looks like

Success is not measured by how many Artifacts are published.

After a month, a healthy Thread shows:

- Hypotheses supported, challenged, superseded, or rejected — each confidence change explained by an EvidenceLink or a decay record;
- stale assessments losing confidence on schedule;
- summaries traceable back to current hypotheses and evidence;
- fewer unsupported assumptions, not merely more stored text.

A healthy team also shows:

- Outcomes recorded instead of forgotten;
- Evaluations that distinguish success, failure, and uncertainty;
- practices revised when they repeatedly fail;
- active playbooks grounded in recorded experience rather than one-off model advice.

If the system is only accumulating Signals, Tasks, or prose without improving its assessments or methods, the update loop is not working.

## Version-one scope

Version one builds the smallest closed loop that supports the behavior above: one persistent Team; a Domain pack (plus the kernel-shipped generalist pack and a setup advisor, so a team can be configured for any subject); immutable Signals; Threads with competing Hypotheses — maintained by model workers *and* human experts through the same validation gates; evidence-linked confidence updates; scheduled decay; Consultations that let the loop request expert opinion and cite the answer as evidence; rendered Artifacts; manually recorded Outcomes, including registered predictions; and controlled learning changes.

The authoritative scope statement and the explicit **do not build in v1** list are in `docs/architecture.md` — Scope and non-goals. Do not add deferred features because they seem easy.

## Documentation

| File | Owns |
|---|---|
| `AGENTS.md` | Working contract for AI agents and human contributors: setup, commands, conventions, hard rules, doc map |
| `PLAN.md` | Phased production plan from empty repository to working beta |
| `docs/glossary.md` | Canonical vocabulary; every capitalized term used in these documents is defined here |
| `docs/invariants.md` | The non-negotiable rules: statement, rationale, enforcement, violation example |
| `docs/architecture.md` | The design spec: entities, state machines, flows, concurrency rules, tech stack, v1 scope |
| `docs/tasks.md` | One spec card per task type: inputs, allowed writes, graph, commit-time validation, budgets |
| `docs/walkthrough.md` | One Thread traced end to end through every record it produces |
| `docs/domains.md` | Domain pack contract plus the newsroom, devteam, and generalist configurations |
| `docs/decisions/` | Architecture decision records: each significant choice, its alternatives, and why they were rejected |

**If you are an AI agent working in this repository:** read `AGENTS.md` first, then the files it points to for your task.

## Status

Design phase. This document set is the current definition of the system; implementation has not started. The phased plan from empty repository to working beta is in `PLAN.md`.