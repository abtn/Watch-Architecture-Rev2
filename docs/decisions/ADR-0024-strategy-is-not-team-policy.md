# ADR-0024 — Strategy Is Not TeamPolicy

## Status

Proposed

## Context

The system already has versioned TeamPolicy.

Adding a free-form Strategy field to policy would collapse general operating rules with situation-specific decisions.

## Decision

TeamPolicy remains general and versioned.

Strategy is contextual and temporary.

Policy:

> “For high-impact public artifacts, require review.”

Strategy:

> “Before publishing this briefing, obtain one independent primary source.”

A Strategy may be constrained by Policy but cannot silently modify Policy.

Strategy is contextual and temporary. Under the subsequent R4 semantic closure, one accepted StrategyProposal is one coordinated decision for one Objective and assessment basis; it may contain multiple concurrent Visions, Workstreams, Actions, and explicit Action dependencies. Acceptance validates legality and authorizes later Plan materialization; it does not establish wisdom or effectiveness. The canonical accepted proposal and hash remain Task-attributed audit provenance, not a Strategy entity or Team memory. R5 derives one Plan from the one active accepted Strategy and may not invent or reinterpret its strategic structure.

A Vision is a bounded strategic perspective; a Workstream groups related Actions for human comprehension; an Action is purposeful intent, not a Task. These concepts require stable provenance identity but do not by themselves imply standalone entities. Any Team/capability change is separate from strategy for ordinary work and requires a human-reviewed proposal path before durable structural change.

## Consequence

The system can adapt its approach without treating every situational decision as organizational learning.

Only the Learning path can change TeamPolicy. The dual-entry model in ADR-0026 applies: Strategy operates inside the deliberative Control path, while routine reactive work follows existing rules without Strategy.
