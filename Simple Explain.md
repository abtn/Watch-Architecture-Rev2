# Watch — Simple Explain

## 1. The basic idea

Watch is a system for helping a general-purpose AI become experienced in a domain.

A normal LLM can already know a lot and perform many kinds of work. It can write Python, read documentation, analyze a scientific paper, investigate a news event, or compare different technical approaches.

But a model call is temporary.

The important problem is:

> **How can the experience produced by many temporary AI workers become persistent, structured, reviewable, and useful to future workers?**

Watch is designed around that problem.

The central principle is:

> **Model-call intelligence is temporary. Team experience is persistent.**

A worker may disappear after completing a task. The Team keeps the durable records, evidence, outcomes, evaluations, lessons, and decisions that were accepted.

Conceptually:

~~~
temporary AI worker
       ↓
observe / reason / act
       ↓
proposal
       ↓
validation
       ↓
durable state
       ↓
future worker
~~~

Watch therefore is not simply a smarter prompt, a memory database, or an agent framework.

It is an architecture for turning repeated work and its consequences into persistent experience.

---

## 2. The goal is not just memory

Imagine telling Watch:

> **Become an expert Python developer.**

A simple memory system might collect Python documents and previous conversations.

Watch asks a larger question:

> **What would an experienced Python development organization need to understand, investigate, test, remember, evaluate, and improve over time?**

That produces two connected problems.

### Understanding the world

Watch needs to know things such as:

- what changed in Python;
- what the official documentation says;
- what practitioners are doing;
- which claims are supported;
- which ideas are disputed;
- what remains unknown;
- and what has become outdated.

### Learning how to work

Watch also needs to learn things such as:

- which sources are useful for which questions;
- which investigation methods work;
- which approaches repeatedly fail;
- which experiments are worth performing;
- how different perspectives complement each other;
- and what should receive attention next.

So:

> **World knowledge describes the domain. Team experience describes how the Team has learned to operate in that domain.**

---

## 3. The most important new idea: one Objective can have many perspectives

An Objective is the thing Watch is trying to accomplish.

For example:

~~~
Objective:
Become an expert Python developer
~~~

Watch should not assume there is only one correct way to approach that Objective.

Instead, it can form several **Visions**.

A Vision is a bounded way of understanding part of the Objective.

For example:

~~~
Objective
"Become an expert Python developer"

        ↓

Strategy

        ├── Vision A: Python ecosystem
        ├── Vision B: Python engineering
        ├── Vision C: Computer science
        └── Vision D: Practical experimentation
~~~

These are not four different Objectives.

They are four perspectives on the same Objective.

### Why Vision matters

A Vision is more than a category or label.

It defines a scope and boundary.

For example:

**Python ecosystem Vision**

> Understand Python releases, official developments, important packages, community practices, and ecosystem changes.

**Python engineering Vision**

> Understand how to build reliable, maintainable, secure, and performant software with Python.

**Computer science Vision**

> Understand the deeper concepts behind Python programming, such as abstraction, type systems, concurrency, language design, and programming paradigms.

**Experimentation Vision**

> Test important ideas through practical implementation instead of relying only on explanations.

This lets Watch look at one domain from several meaningful directions without collapsing everything into one giant undifferentiated task list.

---

## 4. A Strategy is therefore a structured set of Visions

The old R4 model was effectively:

~~~
StrategyProposal
└── one action
~~~

That is now understood to be too restrictive for the intended Watch architecture.

A more useful model is:

~~~
StrategyProposal
│
├── Vision A
│   └── work
│
├── Vision B
│   └── work
│
├── Vision C
│   └── work
│
└── Vision D
    └── work
~~~

The Strategy answers:

> **Given the Objective and what we currently understand, what different perspectives should Watch pursue?**

The accepted Strategy can therefore contain multiple meaningful lines of work.

This is why R4 needs to be redesigned before R5 continues.

R5 should not invent additional actions that were never authorized by the accepted Strategy.

---

## 5. Visions contain Workstreams

A Vision can still contain too much detail to think about as one unit.

We therefore need another abstraction.

The current proposed name is:

> **Workstream**

A Workstream is a coherent body of related work inside a Vision.

It hides the internal complexity of several related actions.

For example:

~~~
Vision:
Python ecosystem

    Workstream:
    "Monitor changes in Python"

        ├── collect official changes
        ├── collect ecosystem reports
        ├── compare findings
        └── evaluate significance
~~~

A human does not need to think about four unrelated little tasks.

They can think:

> "The Python ecosystem monitoring Workstream is running."

The Workstream provides a useful abstraction boundary.

It groups actions that belong together and may depend on one another.

---

## 6. What is an Action?

The simplest useful definition is:

> **An Action is a purposeful unit of work required by a Workstream to achieve its purpose.**

For example:

~~~
Workstream:
"Understand Python typing"

Actions:

1. Read official typing documentation
2. Study current typing proposals
3. Compare major approaches
4. Test examples
5. Evaluate the findings
~~~

An Action describes intended work.

A Task is the executable runtime unit created from that intended work.

So:

~~~
Action
  ↓
Task
~~~

The distinction matters.

An Action answers:

> What purposeful work should happen?

A Task answers:

> What executable unit should the runtime perform?

The first R4/R5 implementation can keep the relationship simple, but the architecture should not permanently assume that every strategic Action is identical to one runtime Task.

---

## 7. Dependency belongs inside the Workstream abstraction

Not every Action needs another Action.

Many can happen independently.

For example:

~~~
Research Python typing
Research Python async
Monitor Python releases
Run Python experiments
~~~

These can all be active at the same time.

But some work naturally forms a sequence.

For example:

~~~
collect sources
      ↓
compare sources
      ↓
evaluate findings
~~~

Instead of making the entire Plan look like one complicated dependency graph, Watch should group this sequence into a Workstream.

The simple mental model is:

~~~
Vision
  ↓
Workstream
  ↓
internal Actions
  ↓
internal dependencies
~~~

This gives us a useful rule:

> **Visions provide parallel perspectives. Workstreams hide and organize the dependent work inside each perspective.**

This is deliberately an abstraction.

The system should expose the meaningful object to humans instead of forcing them to reason about every low-level dependency.

---

## 8. Multiple Visions should be able to work simultaneously

This is an important part of Watch.

Suppose the Python Team has four Visions:

~~~
Ecosystem
Engineering
Computer Science
Experimentation
~~~

Watch should be able to pursue all four at the same time.

Conceptually:

~~~
                    Objective
                       ↓
                    Strategy
                       ↓
       ┌───────────────┼────────────────┐
       ↓               ↓                ↓
    Vision A        Vision B         Vision C
       ↓               ↓                ↓
 Workstreams       Workstreams      Workstreams
       ↓               ↓                ↓
   Actions           Actions          Actions
~~~

One Vision does not need to finish before another starts.

Inside a Vision, a Workstream may have pending work that waits for earlier work to finish.

So Watch gets both:

**parallelism between perspectives**

and

**ordered work inside a perspective.**

The runtime is still responsible for actual Task execution. The Strategy/Plan layers describe what is intended and which work is eligible.

---

## 9. What does the Plan do?

A Plan is the durable execution intent derived from an accepted Strategy.

It does not decide what the Strategy should have been.

It does not invent missing strategic Actions.

It preserves the accepted decision and turns it into durable executable structure.

Conceptually:

~~~
Objective
    ↓
StateAssessment
    ↓
StrategyProposal
    ↓
validation
    ↓
accepted Strategy
    ↓
Plan
    ↓
Tasks
~~~

A Plan can contain the selected Vision structure and its Workstreams/Actions.

For example:

~~~
Plan:
"Improve Python expertise"

├── Vision: Ecosystem
│   └── Workstream: Python releases
│       ├── Action A
│       └── Action B
│
├── Vision: Engineering
│   └── Workstream: Testing practices
│       ├── Action C
│       └── Action D
│
└── Vision: Computer Science
    └── Workstream: Type systems
        └── Action E
~~~

The Plan is durable intent.

Actual execution is represented by Tasks, Events, and Outcomes.

---

## 10. Strategy decides direction; the runtime executes

Watch needs a strong separation between decision-making and execution.

### Strategy

> What approaches should we pursue?

### Vision

> From which bounded perspective should we pursue it?

### Workstream

> What coherent body of work belongs inside that perspective?

### Action

> What purposeful work is required?

### Plan

> What accepted intent should become durable execution structure?

### Task

> What executable unit should run?

### Worker

> Who or what performs the Task?

This gives Watch a clean chain:

~~~
Objective
   ↓
StateAssessment
   ↓
Strategy
   ↓
Vision
   ↓
Workstream
   ↓
Action
   ↓
Plan
   ↓
Task
   ↓
Worker
   ↓
Outcome
~~~

The exact persistence boundaries can evolve, but the conceptual separation is important.

---

## 11. The Team may eventually change itself — but not silently

The Python example also creates another problem.

Watch may discover:

> "Our current Team does not have enough security expertise."

It might therefore propose:

> "Create a Python Security Researcher capability."

That is not ordinary work.

It changes the structure of Watch itself.

Watch should therefore be able to propose structural changes, but a human should remain able to review, edit, approve, or reject what the system creates.

Conceptually:

~~~
Watch discovers a capability gap
        ↓
capability / Team-change proposal
        ↓
human review
        ↓
approve / edit / reject
        ↓
Team changes
~~~

The broader principle is:

> **Watch may become increasingly capable of designing its own organization, but durable structural changes remain controllable by humans.**

This should be a separate architectural concern from ordinary Plan execution.

---

## 12. Provenance must survive all these abstractions

The more layers we introduce, the more important provenance becomes.

Suppose six months later Watch has executed:

~~~
Task:
"Research Python async programming"
~~~

We should be able to trace why it existed.

Conceptually:

~~~
Objective
   ↓
StateAssessment
   ↓
StrategyProposal
   ↓
Vision
   ↓
Workstream
   ↓
Action
   ↓
Plan
   ↓
Task
   ↓
Outcome
   ↓
Evaluation
   ↓
Learning
~~~

This lets Watch answer:

> Why did we do this?

> Which perspective produced it?

> Which strategic decision authorized it?

> What happened?

> What did we learn?

This is one of the reasons durable IDs and explicit provenance are important.

---

## 13. Every Vision should have its own experience

Multiple Visions create another important opportunity.

Suppose Watch has:

~~~
Vision A: Ecosystem
Vision B: Engineering
Vision C: Computer Science
Vision D: Experimentation
~~~

Over time, each Vision will produce its own experience.

For example:

~~~
Vision: Experimentation
│
├── Actions
├── Outcomes
├── Evaluations
├── useful discoveries
├── failed approaches
└── lessons
~~~

This gives Watch a history of how each perspective has performed.

But performance should not automatically become a simplistic score.

One successful experiment does not prove that a Vision is better.

One failed investigation does not prove that a Vision is useless.

Instead, each Vision accumulates evidence about its usefulness.

Then R4 can use that evidence when forming future Strategies.

Conceptually:

~~~
Vision
   ↓
Work
   ↓
Outcomes
   ↓
Evaluation
   ↓
evidence about usefulness
   ↓
future Strategy
~~~

This is an important future design problem in its own right.

---

## 14. Watch should learn from outcomes, not from model confidence

Suppose a Worker says:

> "This is the best architecture."

That statement should not automatically become Team knowledge.

Instead:

~~~
Worker proposal
      ↓
actual work
      ↓
Outcome
      ↓
Evaluation
      ↓
possible LearningChange
~~~

The same principle applies to Vision evaluation.

The system should not say:

> "The model sounded confident, therefore Vision B is excellent."

It should accumulate actual experience.

This is how Watch can gradually learn:

> "This perspective is consistently useful for this kind of Objective."

rather than merely storing opinions.

---

## 15. The human and the AI have different roles

The AI worker provides temporary intelligence.

The durable Watch system provides:

- persistence;
- validation;
- provenance;
- evidence;
- execution structure;
- evaluation;
- controlled learning;
- and governance.

The basic authority chain remains:

~~~
Worker
  ↓
proposal
  ↓
application validation
  ↓
Kernel/application commit
  ↓
durable state
~~~

Workers do not directly write durable truth.

Plans are execution intent, not execution history. Tasks, Events, and Outcomes remain authoritative for what actually happened.

StateAssessment remains derived and non-authoritative.

---

## 16. Reactive work still exists

Not everything needs a new Strategy.

Suppose Watch already knows:

> "Every morning, check the Python release feed."

That can remain a normal reactive Task.

Conceptually:

~~~
Trigger / Scheduler / Operator
            ↓
           Task
            ↓
          Worker
            ↓
         proposal
            ↓
        validation
            ↓
          commit
~~~

When Watch genuinely needs to decide what to pursue, the deliberative path can be used:

~~~
Objective
   ↓
StateAssessment
   ↓
Strategy
   ↓
Visions
   ↓
Workstreams
   ↓
Actions
   ↓
Plan
   ↓
Tasks
~~~

Both paths eventually use the same ordinary Task execution system.

There should not be a second scheduler hidden inside the planning layer.

---

## 17. Evidence and durable experience remain central

Watch is not trying to make every model statement permanent.

When external information enters the system, it can be preserved as evidence.

When a Worker proposes an interpretation, the system can check it.

When a Task produces a result, the result can be evaluated.

When a lesson is worth keeping, the system can record a LearningChange.

So the larger loop is:

~~~
World
 ↓
Observation
 ↓
Evidence
 ↓
Understanding
 ↓
Strategy
 ↓
Visions
 ↓
Work
 ↓
Outcomes
 ↓
Evaluation
 ↓
Learning
 ↓
better future Strategy
 ↺
~~~

That is what makes Watch different from a static knowledge base.

---

## 18. The full Python example

Now we can describe the original example using the new abstractions.

A human gives Watch:

> **Become an expert Python developer.**

Watch creates the Objective.

It assesses its current state and realizes that Python expertise has many dimensions.

It forms a Strategy containing several Visions.

~~~
Objective:
Become an expert Python developer

Strategy
│
├── Vision: Python ecosystem
│   │
│   ├── Workstream: Monitor Python releases
│   │   ├── collect official changes
│   │   ├── compare changes
│   │   └── evaluate significance
│   │
│   └── Workstream: Monitor ecosystem
│       ├── research important packages
│       └── track important community developments
│
├── Vision: Python engineering
│   │
│   ├── Workstream: Modern engineering practices
│   │   ├── research architecture patterns
│   │   └── evaluate maintainability
│   │
│   └── Workstream: Testing
│       ├── research testing practices
│       └── run practical experiments
│
├── Vision: Computer science
│   │
│   ├── Workstream: Type systems
│   │   ├── study concepts
│   │   └── compare approaches
│   │
│   └── Workstream: Concurrency
│       ├── research concepts
│       └── test implementations
│
└── Vision: Critical analysis
    │
    └── Workstream: Compare competing claims
        ├── collect arguments
        ├── identify disagreements
        └── evaluate evidence
~~~

The Visions can operate simultaneously.

Within each Workstream, Actions can wait for prerequisites.

The accepted Strategy becomes durable execution intent through Plan materialization.

The Plan produces ordinary Tasks.

Workers execute those Tasks.

Outcomes are recorded.

Each Vision accumulates its own experience.

Evaluations produce learning.

Future Strategy can then change.

Perhaps later Watch realizes:

> "Security is becoming an important gap."

It can propose a new Vision:

~~~
Vision: Python security
~~~

Perhaps it also realizes:

> "We lack sufficient security expertise."

It can propose a Team capability change, which a human can approve, edit, or reject.

This means the system does not stay permanently fixed.

It can learn both:

> **what is true about the domain**

and

> **how the Team should organize its attention and capabilities.**

---

## 19. The deeper architecture

The emerging model is therefore:

~~~
                    OBJECTIVE
                 "What do we want?"
                        │
                        ▼
                STATE ASSESSMENT
               "Where are we now?"
                        │
                        ▼
                    STRATEGY
            "How should we approach it?"
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
       VISION A       VISION B       VISION C
       "scope"        "scope"        "scope"
          │             │             │
          ▼             ▼             ▼
     WORKSTREAMS   WORKSTREAMS   WORKSTREAMS
          │             │             │
          ▼             ▼             ▼
       ACTIONS        ACTIONS       ACTIONS
          │             │             │
          └─────────────┼─────────────┘
                        ▼
                      PLAN
             durable execution intent
                        │
                        ▼
                      TASKS
                        │
                        ▼
                     WORKERS
                        │
                        ▼
                    OUTCOMES
                        │
                        ▼
                   EVALUATIONS
                        │
                        ▼
                     LEARNING
                        │
                        └──────────────→ future Strategy
~~~

And alongside it:

~~~
Capability / Team proposal
           ↓
      Human review
           ↓
    Team modification
~~~

The architecture therefore has two different kinds of adaptation:

**Knowledge adaptation**

> "Our understanding of the world changed."

**Organizational adaptation**

> "The way Watch approaches the domain should change."

Both can eventually happen without giving a model direct control of durable state.

---

## 20. What has changed in our understanding of R4

The current R4 implementation proved an important first concept:

~~~
Objective
   ↓
StateAssessment
   ↓
StrategyProposal
   ↓
validation
   ↓
audit
~~~

But it constrained the StrategyProposal to one candidate action.

That constraint is now recognized as too narrow for the intended architecture.

The problem is not that R4 was badly implemented.

The problem is that the first R4 slice was a small experiment that exposed the wrong abstraction boundary.

The redesigned R4 should therefore support:

~~~
one Objective
      ↓
one Strategy
      ↓
many Visions
      ↓
many Workstreams
      ↓
many Actions
~~~

The actions can be pursued concurrently.

Dependent work is organized within Workstreams.

R5 then materializes the accepted strategic structure instead of inventing missing work.

This is the reason R5 should pause while the R4 Strategy model is redesigned.

---

## 21. What Watch ultimately becomes

The long-term vision is not:

> "Build an AI that knows Python."

It is:

> **Build a persistent system that can continuously improve how it understands, investigates, and works within Python.**

The same architecture can then be applied to another domain.

For example:

~~~
Objective:
Become an expert scientific research team
~~~

or:

~~~
Objective:
Monitor and understand global energy markets
~~~

or:

~~~
Objective:
Become an expert geopolitical analysis team
~~~

The domain changes.

The fundamental process remains:

~~~
Objective
   ↓
understand current state
   ↓
form multiple bounded perspectives
   ↓
organize coherent work
   ↓
act
   ↓
observe results
   ↓
evaluate
   ↓
learn
   ↓
change future behavior
   ↺
~~~

That is the central idea of Watch.

> **The model provides temporary intelligence. Watch provides the persistent structure through which many temporary intelligences can accumulate experience, pursue multiple perspectives, learn from results, and gradually become a more capable expert Team.**
