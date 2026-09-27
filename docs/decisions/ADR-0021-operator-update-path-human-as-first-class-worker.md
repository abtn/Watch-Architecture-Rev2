# File: docs/decisions/0021-operator-update-path-human-as-first-class-worker.md

# ADR-0021: Operator update path — the human as first-class worker

**Status:** accepted  **Date:** 2025-01-15

## Context
Experts using Watch in their own field must put their own theories, evidence, and confidence judgments on the board. Previously only `update_thread` (a model worker) could write world memory — backwards for domains where the operator is the domain expert and their knowledge is the best input the system can get.

## Decision
`operator_update` is a manual task type with read/write scope and commit-time validation **identical** to `update_thread`. Expert hypotheses, EvidenceLinks, ConfidenceChanges, transitions, and disposition refinements go through the same proposal envelope and commit kernel. An unsubstantiated expert hypothesis (no EvidenceLink) enters at `low` band, like any worker's. Being human is never a validation exemption (INV-15).

## Alternatives considered
- **Direct operator writes outside the task system** — rejected: the exact bypass INV-02 exists to prevent; two validation regimes.
- **A separate "expert contribution" entity** — rejected: duplicates Hypothesis/EvidenceLink and fragments world memory; provenance already distinguishes authorship via task type and Event identity.

## Consequences
Expert knowledge is first-class, auditable, and quote-disciplined — the same friction that protects against model fabrication applies to humans, deliberately. Cost: none beyond the manual-task pattern already established (ADR-0011).

## Invariants
INV-02, INV-04, INV-05, INV-07, INV-14, INV-15.