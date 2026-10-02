# Watch — How an AI Becomes an Expert

## 1. The basic idea

A general-purpose AI can know something about almost everything.

It can write Python, explain a scientific paper, analyze a political event, investigate a technical problem, or summarize a large amount of information.

But knowing many things is not the same as being an expert.

An expert does more than store information.

An expert accumulates experience.

They learn which information matters, which sources deserve attention, which explanations are plausible, which methods work, which methods fail, what mistakes they have already made, and what they should do differently next time.

They also develop judgment.

When faced with a new problem, an experienced person does not start from zero. They begin with everything they have learned from previous problems.

**Watch is a system designed to give AI this persistent experience.**

The central idea is:

> **Use a general-purpose AI as the thinking worker, while Watch provides the persistent environment in which the AI can observe, reason, act, learn from outcomes, and accumulate validated domain experience.**

The underlying model does not have to become a completely different model for every domain.

Instead:

```text
                General-purpose AI
                       │
                       │ temporary worker
                       ▼
               ┌───────────────┐
               │     WATCH     │
               │               │
               │ Observe       │
               │ Remember      │
               │ Reason        │
               │ Act           │
               │ Evaluate      │
               │ Learn         │
               │ Improve       │
               └───────┬───────┘
                       │
                       ▼
              Persistent expertise
                 in a domain
```

A Watch Team can therefore specialize in almost any domain while the underlying learning architecture remains largely the same.

A Python-development team, a scientific-research team, a newsroom, a geopolitical-analysis team, and a financial-research team may look very different on the surface.

Underneath, they can use the same basic mechanism:

```text
Observe
   ↓
Understand
   ↓
Form explanations
   ↓
Investigate / act
   ↓
Observe the result
   ↓
Evaluate
   ↓
Learn
   ↓
Use the learning in future work
   ↺
```

That loop is the heart of Watch.

---

## 2. General intelligence is not the same thing as expertise

It helps to separate two ideas.

### General intelligence

A general-purpose LLM has broad capabilities.

It may already know:

* programming concepts,
* scientific concepts,
* history,
* mathematics,
* languages,
* common reasoning patterns,
* and many facts about the world.

It can perform many different tasks without being specially trained for each one.

This makes a general model extremely useful.

But broad capability has a limitation:

**the model does not automatically accumulate reliable, structured experience from everything it does.**

A conversation may contain an excellent solution today and be effectively irrelevant to the next session.

A mistake may happen repeatedly without becoming a permanent lesson.

A successful strategy may be remembered only as vague text.

A belief may remain in memory long after the world has changed.

And a piece of advice may become "knowledge" simply because a model generated it confidently.

Expertise requires more structure.

### Domain expertise

A domain expert has accumulated a history of interactions with a particular kind of world.

For example, an experienced Python developer may know much more than the Python language reference.

They may have learned:

> This kind of bug usually comes from this class of mistake.

> Check the data boundary before changing the algorithm.

> This apparently elegant abstraction becomes difficult to maintain under these constraints.

> This documentation is authoritative for this particular behavior.

> A previous solution failed because the original assumption was wrong.

Those lessons are not just facts.

They are **experience about how to work in the domain**.

That is the problem Watch is designed to address.

---

## 3. Watch treats expertise as something that develops over time

Watch starts with a general-purpose worker.

That worker may be capable, but it does not begin with the full accumulated experience of the team.

Instead, the team already has a persistent state.

The worker enters that state, performs work, and leaves behind durable consequences.

The next worker can then use what previous workers learned.

This creates something closer to organizational experience:

```text
Worker 1
   ↓
observation + reasoning + action
   ↓
outcome
   ↓
evaluation
   ↓
learning
   ↓
persistent team knowledge
   ↓
Worker 2
   ↓
better starting point
```

The workers may be temporary.

The experience is not.

This is one of the most important ideas in Watch:

> **The intelligence of a particular model call is temporary. The experience of the Team is persistent.**

The Team can therefore become more experienced even though its individual workers are replaced constantly.

This is similar to how an organization can become more competent even though its employees change.

---

## 4. What exactly does Watch remember?

"Memory" is too vague.

Watch separates different kinds of persistent information because different things should be changed in different ways.

There are two especially important categories.

### World knowledge

This is the Team's current understanding of the thing it is watching.

Examples:

* What happened?
* What evidence exists?
* Which explanations are plausible?
* Which explanation currently has more support?
* What remains uncertain?
* What has been contradicted?
* What has become stale?

Watch represents this through things such as:

```text
Signals
Snapshots
Threads
Hypotheses
Evidence
Confidence changes
Outcomes
```

This knowledge is intentionally revisable.

The world changes.

New evidence appears.

Old evidence becomes less useful.

A hypothesis that once seemed plausible can become weak.

Therefore the world model must be allowed to change.

### Team knowledge

This is different.

It concerns what the Team has learned about **how to work effectively in the domain**.

Examples:

> When investigating this kind of problem, inspect these variables first.

> Do not treat this kind of evidence as sufficient by itself.

> This source type is useful for discovery but weak for confirmation.

> This method tends to fail under these conditions.

> Use this procedure when evaluating this class of result.

This is much closer to what we normally call skill, practice, method, pattern, or expertise.

Watch represents this through:

```text
Outcomes
   ↓
Evaluations
   ↓
LearningChanges
   ↓
KnowledgeItems / TeamPolicy
```

The distinction is fundamental.

> **World knowledge describes the domain. Team knowledge describes how the Team has learned to operate within that domain.**

---

## 5. Knowledge and experience are not the same thing

A Watch Team should not turn every statement it encounters into "knowledge."

Consider a Python team.

A worker says:

> "This architecture is better."

That is not yet a learned skill.

It is a claim.

For Watch to turn experience into durable team knowledge, there should be something behind it.

Perhaps the Team used the architecture.

An outcome was observed.

The result was evaluated.

The evaluation showed what worked and what did not.

Only then might the Team propose a learning change.

Conceptually:

```text
Statement
   ↓
Was it actually tested?
   ↓
What happened?
   ↓
What evidence do we have?
   ↓
Did the method succeed?
   ↓
Why?
   ↓
Should this change future behavior?
   ↓
Validated learning
```

This is important because **experience is not automatically wisdom**.

A single lucky result should not silently become a permanent rule.

A failure should not automatically invalidate an entire method.

A persuasive model response should not become organizational doctrine simply because it sounds correct.

Watch therefore treats learning as a separate process.

---

## 6. The scientific method is an important example — but not the boundary

The scientific method gives us an extremely useful pattern:

```text
Observe
→ form hypotheses
→ test
→ observe results
→ revise
```

Watch adopts many of the same principles:

* observation,
* explicit hypotheses,
* evidence,
* competing explanations,
* testing,
* outcomes,
* evaluation,
* revision.

But Watch is not intended to be a scientific-research-only system.

The same general pattern can apply to many activities.

A programmer can investigate a bug.

A newsroom can investigate an event.

A business can test a strategy.

A researcher can investigate a hypothesis.

An engineer can compare designs.

A research team can monitor a changing system.

A person can even use the same architecture for a broad personal knowledge domain.

The common structure is not "science."

The common structure is:

> **Observe reality, maintain explicit knowledge about it, act or investigate, observe consequences, evaluate what happened, and let experience improve future work.**

So Watch should be understood as a **general architecture for disciplined inquiry, feedback, and accumulation of expertise**.

It borrows ideas from the scientific method, forecasting, engineering, knowledge management, version control, and organizational learning, but is not identical to any one of them.

It is broader than a single scientific workflow because the goal is not only to discover scientific truth.

The goal is to help a persistent AI Team become more experienced at whatever domain it has been created to work in.

---

## 7. Why evidence is central

Learning from experience only works when the system can distinguish what actually happened from what someone merely said happened.

Suppose a worker says:

> "The previous investigation proved that method X works."

That sentence is not enough.

What investigation?

What was actually observed?

What source supports it?

Can the source still be inspected?

Did the result actually correspond to the method?

Could the result have happened for another reason?

Watch therefore treats evidence as a first-class part of the system.

When external information enters the system, Watch can preserve an immutable Snapshot of the observed material.

Later, a worker can propose:

> "This evidence supports Hypothesis A."

The application does not simply trust the worker.

It checks the proposal.

For example:

```text
Worker proposes:
"Quote X supports Hypothesis A."

             ↓

Watch checks:

Does the source exist?
Does the snapshot exist?
Does the quote actually occur?
Are the offsets correct?
Is this Task allowed to make this change?
Is the target still valid?
Are the preconditions still true?

             ↓

Accept
or
Reject
```

This gives the system an important property:

> **A worker can propose knowledge, but the worker cannot directly declare its proposal to be durable truth.**

---

## 8. Watch is deliberately skeptical

A major purpose of the architecture is to resist premature certainty.

Real domains contain:

* incomplete information,
* contradictory evidence,
* misleading signals,
* outdated information,
* ambiguous events,
* mistaken interpretations,
* and successful-looking outcomes that were actually caused by something else.

Watch therefore does not need one permanent answer to every question.

It can maintain competing hypotheses.

For example:

```text
Thread:
"Why did the system fail?"

Hypothesis A:
Database connection exhaustion

Hypothesis B:
Application-level retry storm

Hypothesis C:
External service degradation
```

New evidence can support one hypothesis and challenge another.

The alternatives do not need to disappear simply because one currently looks stronger.

This is important because expertise is not the ability to be certain all the time.

An expert is often better described as someone who knows:

> "Here is what we currently believe, here is why, here is what contradicts it, and here is what would change our mind."

Watch tries to preserve exactly that structure.

---

## 9. Beliefs can become stale

The system also distinguishes between **knowledge that should remain stable until reviewed** and **beliefs about a changing world**.

Suppose a financial Team has the belief:

> "Current market conditions support a particular hypothesis."

That belief should not remain equally strong forever just because nobody bothered to change it.

The world may have changed.

Watch therefore allows certain world beliefs to decay conservatively over time.

Conceptually:

```text
evidence supports belief
        ↓
confidence increases
        ↓
no new relevant evidence
        ↓
time passes
        ↓
confidence may decay
```

But a learned Team practice is different.

Suppose the Team learned:

> "When investigating this class of failure, inspect the queue before changing the worker."

That lesson should not disappear merely because the Team went a month without encountering the failure.

It should be reviewed, revised, or retired because of evidence and experience, not because the clock happened to advance.

This produces an important distinction:

```text
World belief
    → can decay with time

Team skill / method
    → changes through learning and review
```

The difference prevents the Team from either forgetting everything or keeping every old belief forever.

---

## 10. The Team is the persistent entity

The LLM is not the Team.

A model call is a Worker.

The Team is the durable entity that remembers.

The Team has:

* a domain,
* a mission,
* policy,
* world knowledge,
* accumulated experience,
* tasks,
* outcomes,
* and a history of learning.

A simple analogy is a professional organization.

```text
Human analogy                 Watch
────────────────────────────────────────────
Organization                  Team
Employees                     Workers
Company records               Durable state
Research archive              Signals / Snapshots
Current understanding         Threads / Hypotheses
Experience                    Outcomes
Postmortems                   Evaluations
Lessons learned               KnowledgeItems
Operating rules               TeamPolicy
Work assignment               Task
Managerial deliberation       Control layer
Quality / governance          Kernel
```

The analogy is not meant to claim that Watch literally reproduces a human organization.

It is useful because it explains where persistence belongs.

Workers come and go.

The organization remembers.

---

## 11. What is the role of the LLM?

The LLM is the system's general cognitive worker.

It can:

* read,
* reason,
* summarize,
* compare,
* propose hypotheses,
* investigate,
* generate strategies,
* write,
* interpret evidence,
* and perform other forms of domain work.

But the LLM does not own the durable state.

A worker receives a bounded context.

It performs a task.

It proposes changes.

The application validates those changes.

The Kernel commits accepted changes.

This gives the system a deliberately asymmetric relationship:

```text
LLM:
"Here is what I think we should change."

Watch:
"Let me check whether that change is allowed,
supported, attributable, and still valid."

Watch:
"Accepted."

or

Watch:
"Rejected, and here is why."
```

That boundary is one of the foundations of the architecture.

The model supplies intelligence.

The system supplies persistence, rules, provenance, and controlled change.

---

## 12. This is different from ordinary AI memory

A conventional AI memory system often tries to answer:

> "What should I remember from previous conversations?"

Watch asks a more demanding question:

> **"What should this Team learn from its experience, and what should that learning change?"**

Those are not the same problem.

Saving a conversation transcript is not the same as learning.

Saving summaries is not the same as learning.

Adding more documents to a vector database is not the same as learning.

Even storing successful answers is not necessarily learning.

Learning requires a causal loop:

```text
Experience
   ↓
Outcome
   ↓
Evaluation
   ↓
Learning decision
   ↓
Changed future behavior
```

That final step matters.

The purpose of memory is not merely to preserve the past.

It is to improve the future.

---

## 13. Watch therefore has a learning loop

The complete conceptual loop looks like this:

```text
                 ┌─────────────────────┐
                 │      DOMAIN         │
                 │       WORLD         │
                 └──────────┬──────────┘
                            │
                         Observe
                            │
                            ▼
                   Signals / Snapshots
                            │
                            ▼
                Threads / Hypotheses
                            │
                       Evidence
                            │
                            ▼
                    Current belief
                            │
                            ▼
                    Decide what next
                            │
                            ▼
                     Task + Worker
                            │
                            ▼
                       Action
                  / investigation
                            │
                            ▼
                        Outcome
                            │
                            ▼
                       Evaluation
                            │
                            ▼
                        Learning
                            │
                            ▼
                  Team knowledge
                            │
                            │
                            ▼
                  Future task behavior
                            │
                            └───────────────↺
```

There are really two feedback loops here.

### World loop

The Team continuously updates its model of the domain.

```text
Observe
→ interpret
→ test
→ update belief
→ observe again
```

### Experience loop

The Team learns how to work better.

```text
Work
→ outcome
→ evaluation
→ lesson
→ changed future behavior
```

The combination of these two loops is what produces something resembling accumulated expertise.

---

## 14. The Control layer: expertise also requires deciding what to do next

Knowing more is not enough.

An expert must also decide what deserves attention.

This is why Watch has a higher-level Control layer.

The basic question is:

> **Given the Team's current understanding, mission, policy, constraints, and unanswered questions, what should the Team do next?**

The Control model is:

```text
Objective
    ↓
StateAssessment
    ↓
StrategyProposal
    ↓
Plan
    ↓
Tasks
    ↓
existing execution system
```

Each part has a distinct role.

### Objective

What are we trying to accomplish?

### StateAssessment

What do we currently know?

What is uncertain?

What is contradictory?

What is stale?

What remains unresolved?

### StrategyProposal

Given that state, what approaches could make sense?

### Plan

Which bounded approach should become actual work?

### Task

What concrete unit of work should be performed?

### Worker

Who or what performs it?

This is important because Watch should not merely become a better storage system.

A genuine expert also knows how to allocate attention.

The system therefore needs both:

```text
memory of what happened
```

and

```text
reasoning about what should happen next
```

---

## 15. Not every action needs deliberation

Watch has two valid ways to begin work.

Sometimes the correct response is already known.

For example:

```text
A scheduled source fetch is due
        ↓
create Task
        ↓
execute
```

There is no reason to invoke a large deliberative planning process for every routine operation.

This is the **reactive path**:

```text
Signal / Trigger / Scheduler / Operator
                ↓
               Task
                ↓
             Worker
                ↓
             Proposal
                ↓
      Kernel validation
                ↓
              Commit
```

Other times, the Team genuinely needs to decide what to investigate next.

Then the **deliberative path** can be used:

```text
Objective
   ↓
StateAssessment
   ↓
StrategyProposal
   ↓
Plan
   ↓
Tasks
   ↓
existing Task execution
```

The two paths eventually converge.

The Control layer does not create a second execution system.

It decides.

The existing Task system executes.

The Kernel commits.

That separation keeps the architecture coherent.

---

## 16. The Kernel: protecting the learning process

The Kernel is the part of Watch that enforces the rules around durable change.

Its purpose is not to make all decisions itself.

Its purpose is to make sure that durable changes obey the Team's rules.

For example:

```text
Worker proposes a change
          ↓
Validate schema
          ↓
Validate ownership
          ↓
Validate write scope
          ↓
Validate evidence
          ↓
Validate current state
          ↓
Validate concurrency
          ↓
Commit atomically
          ↓
Record Event
```

This matters because learning changes the future.

A bad memory entry can cause one bad answer.

A bad learned rule can cause thousands of future bad answers.

Therefore the threshold for turning experience into durable Team knowledge must be higher than the threshold for merely generating a piece of text.

This is one reason Watch separates:

```text
proposal
```

from

```text
committed state
```

The model can think freely.

The durable system changes carefully.

---

## 17. Versioning is part of learning

A Team should not merely know its current rules.

It should be possible to understand how those rules changed.

Suppose a development Team learns:

> Version 1:
> "Use approach A for this class of problem."

Later, experience reveals problems.

The Team may revise it:

> Version 2:
> "Use approach B unless constraint C is present."

The old version should not simply disappear.

The history matters.

This is similar to version control.

```text
Old knowledge
     ↓
new experience
     ↓
proposed revision
     ↓
validation
     ↓
new version
     ↓
old version remains auditable
```

This allows the Team to answer:

> Why do we work this way now?

> What caused the change?

> What did we believe before?

> What happened that caused the revision?

In other words:

> **Watch treats organizational learning as a versioned process, not an invisible edit to a memory file.**

---

## 18. Humans can participate too

Watch is not intended to make human experts unnecessary.

Humans can be workers.

Humans can provide evidence.

Humans can answer consultations.

Humans can evaluate outcomes.

Humans can approve certain learning changes.

The important architectural principle is that human input should not become an untraceable escape hatch.

A human contribution enters through the same durable validation model.

That means an expert can say:

> "I believe Hypothesis A is wrong."

But the system still records:

* who made the contribution,
* what Task produced it,
* what evidence was supplied,
* what changed,
* and why the change was accepted or rejected.

Human expertise and machine expertise can therefore participate in the same persistent learning environment.

---

## 19. Domain packs: change the subject, not the learning machinery

Watch should work across domains without rewriting the Kernel every time.

The general system provides the common machinery.

A **Domain Pack** describes how that machinery is applied to a particular subject.

For example:

```text
                 WATCH KERNEL
        ─────────────────────────────
        persistence
        validation
        provenance
        tasks
        evidence
        outcomes
        learning
        control
        concurrency
        budgets
        audit
        ─────────────────────────────

          Domain Pack
               │
       ┌───────┼────────┐
       │       │        │
    sources vocabulary templates
    heuristics   decay   workflows
```

A Python development Team might care about:

* Python releases,
* documentation,
* issues,
* repositories,
* benchmarks,
* design patterns,
* postmortems.

A scientific Team might care about:

* papers,
* experiments,
* datasets,
* replications,
* measurements.

A newsroom might care about:

* reporting,
* primary sources,
* statements,
* events,
* competing narratives.

The Kernel should not need to understand every domain-specific concept.

That is the purpose of the separation.

The underlying mechanism can remain general while the knowledge and behavior are specialized.

---

## 20. The long-term effect

Imagine creating a new Watch Team for Python development.

On day one:

```text
General-purpose LLM
+
Python domain knowledge
+
empty Team experience
```

It starts working.

It investigates bugs.

It reads documentation.

It builds software.

It encounters failures.

It observes what happened.

It records outcomes.

It evaluates its methods.

Some experiences produce useful learning.

Months later:

```text
General-purpose LLM
+
Python knowledge
+
accumulated Team experience
+
validated methods
+
historical outcomes
+
domain-specific patterns
```

The model underneath might not have changed at all.

But the system surrounding it has.

It now approaches new problems with:

* better context,
* better questions,
* better investigation strategies,
* better source selection,
* better awareness of previous failures,
* better domain-specific methods,
* and a history of what happened before.

That is the sense in which Watch creates an "expert AI."

More precisely:

> **Watch creates a persistent expert system around a general-purpose AI by accumulating validated domain experience and using that experience to influence future work.**

---

## 21. What happens when the underlying AI gets better?

This is an important part of the design.

General-purpose AI models will continue to improve.

New models may become:

* better at reasoning,
* better at coding,
* better at multimodal work,
* cheaper,
* faster,
* more reliable,
* or specialized for particular tasks.

Watch does not need to become obsolete whenever the underlying model changes.

The model is replaceable.

The experience is persistent.

Conceptually:

```text
Watch Team experience
        │
        ├── Model A
        ├── Model B
        ├── Model C
        └── future models
```

A better model can enter an existing Team and use the accumulated experience.

A weaker or different model can still benefit from the same history.

This creates a useful separation:

> **Models provide changing general capability. Watch provides persistent domain experience.**

That means the system does not have to rebuild its expertise from zero whenever the underlying model changes.

---

## 22. What Watch is not

Watch is not simply:

### An LLM

The LLM performs cognitive work, but Watch is the persistent system around it.

### An agent framework

Agent frameworks are primarily concerned with how an agent executes work using tools.

Watch can use an agent framework.

Its central concern is different:

> What should become durable knowledge, what evidence supports it, what was learned from experience, and how should that learning affect future work?

### A vector database

Embeddings and retrieval may be useful implementation mechanisms.

But retrieving documents is not the same as learning.

### A workflow engine

Tasks and execution are necessary, but workflow alone does not create expertise.

### A knowledge base

A static knowledge base stores information.

Watch also stores:

* hypotheses,
* uncertainty,
* outcomes,
* evaluations,
* failures,
* methods,
* revisions,
* and the reasons behind changes.

### Automatic self-learning

Watch does not mean:

> "Let the AI rewrite its own memory whenever it wants."

The whole architecture is designed to avoid that.

Workers propose.

The system validates.

Experience is evaluated.

Learning changes are controlled.

---

## 23. The central problem Watch is solving

The problem can now be stated very simply.

Today's general AI can often perform an impressive task.

The harder problem is:

> **How do we make the system around that AI become systematically better because of everything it has experienced?**

Without such a mechanism:

```text
good work
   ↓
disappears

mistake
   ↓
may happen again

successful method
   ↓
may not become reusable

new evidence
   ↓
may not revise old assumptions

new model
   ↓
may start from almost the same place
```

With Watch:

```text
good work
   ↓
Outcome
   ↓
Evaluation
   ↓
Learning
   ↓
future behavior improves
```

And:

```text
mistake
   ↓
Outcome
   ↓
Evaluation
   ↓
lesson
   ↓
future behavior changes
```

And:

```text
new evidence
   ↓
Hypothesis challenged
   ↓
belief changes
   ↓
current understanding changes
```

And:

```text
better AI model
   ↓
joins existing Team
   ↓
uses accumulated experience
```

The system is therefore designed around a simple principle:

> **Work should leave behind useful experience, and useful experience should influence future work.**

---

## 24. Expertise is a process, not a file

One temptation is to imagine that an AI becomes an expert when we finally produce a giant "expert knowledge base."

That is probably the wrong mental model.

Expertise is not a document.

It is a process.

A real expert continuously:

* encounters new information,
* tests assumptions,
* updates beliefs,
* learns from mistakes,
* discovers patterns,
* revises methods,
* and decides what deserves attention next.

The knowledge is important, but the **learning loop** is more important.

Therefore the ultimate product of Watch is not a huge database.

It is a continuously operating learning system.

---

## 25. A compact model of Watch

The entire architecture can be reduced to a small conceptual model.

### The world

```text
Signals
→ Evidence
→ Hypotheses
→ Beliefs
```

### The work

```text
Objectives
→ Strategies
→ Plans
→ Tasks
→ Workers
```

### The experience

```text
Tasks
→ Outcomes
→ Evaluations
→ Learning
→ Knowledge
```

### The governance

```text
Proposals
→ Validation
→ Commit
→ Events
```

### The future

```text
Knowledge
+
current world state
+
new observations
        ↓
better decisions
        ↓
new experience
        ↺
```

Put together:

```text
                         WATCH
                           │
           ┌───────────────┼────────────────┐
           │               │                │
         WORLD            WORK          EXPERIENCE
           │               │                │
       Observe          Decide             Learn
           │               │                │
      Hypotheses        Tasks            Outcomes
           │               │                │
        Evidence        Workers          Evaluation
           │               │                │
        Beliefs          Actions        Knowledge
           │               │                │
           └───────────────┼────────────────┘
                           │
                      Future behavior
                           │
                           └──────────↺
```

The Kernel sits underneath these processes and protects the boundary between **what a worker proposes** and **what the Team accepts as durable state**.

---

## 26. The simplest explanation

Watch is a system for helping a general-purpose AI become experienced in a domain.

A general LLM can think and perform many kinds of work, but a single model call does not provide the persistent experience of an expert.

Watch provides that persistence.

It gives the AI a Team with a memory of the world, a memory of its own experience, explicit hypotheses, evidence, outcomes, evaluations, learned methods, and a history of how those things changed.

The AI workers observe and investigate the world, propose changes, perform tasks, and produce outcomes.

Watch records what happened.

It evaluates the results.

It turns appropriate experience into reusable knowledge.

And future workers begin with what the Team has already learned.

The process is:

```text
Observe
   ↓
Understand
   ↓
Hypothesize
   ↓
Investigate / Act
   ↓
Observe the result
   ↓
Evaluate
   ↓
Learn
   ↓
Use the learning
   ↺
```

The model can change.

The workers can change.

The tasks can change.

The domain can change.

The Team's accumulated experience persists.

That is the central idea of Watch:

> **General AI provides the intelligence to do the work. Watch provides the persistent process through which that intelligence can accumulate experience and develop domain expertise over time.**

Or even more simply:

> **The models do the thinking. Watch remembers the experience, tests the lessons, and uses what was learned to make future thinking better.**

That is why Watch is not just an agent system, a memory system, or a workflow engine.

It is an architecture for **persistent AI learning through disciplined experience**.
