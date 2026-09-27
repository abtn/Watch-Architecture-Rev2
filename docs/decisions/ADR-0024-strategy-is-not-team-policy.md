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

Strategy is contextual and temporary. It may be represented in a StrategyProposal and, if accepted, recorded as part of a Plan's provenance. It is not a durable entity and is not Team memory.

## Consequence

The system can adapt its approach without treating every situational decision as organizational learning.

Only the Learning path can change TeamPolicy. The dual-entry model in ADR-0026 applies: Strategy operates inside the deliberative Control path, while routine reactive work follows existing rules without Strategy.
