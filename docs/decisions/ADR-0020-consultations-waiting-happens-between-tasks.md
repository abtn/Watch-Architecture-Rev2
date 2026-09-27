# File: docs/decisions/0020-consultations-waiting-happens-between-tasks.md

# ADR-0020: Consultations — waiting happens between tasks

**Status:** accepted  **Date:** 2025-01-15

## Context
High-stakes domains need the loop to request human judgment — e.g., a proposed treatment for a patient, or a question the evidence cannot settle. Nothing in the design allowed a durable, structured request for expert opinion, and putting a human wait *inside* a running task would have required a durable workflow engine, contradicting the Temporal deferral (ADR-0015).

## Decision
`Consultation` is a kernel entity: subject, question, and a hashed context snapshot of exactly what the expert will be shown. `request_consultation` opens it and **ends its task immediately** — waiting for humans happens between Tasks, never inside one. `answer_consultation` (Operator) records the answer as an immutable, hashed snapshot (plus optional structured verdict) and may enqueue follow-up work so the answer enters the loop. `EvidenceLink.source_kind` gains `"consultation"`: answers are citable with verified quotes and may anchor confidence like any other source. Policy `review` rules can require a consultation before delivery (delivery outcomes are rejected while open); an `update_gating` flag is reserved in the policy schema to block update commits the same way (default off). The scheduler expires consultations past `check_by`, mirroring prediction registrations.

## Alternatives considered
- **Agent-to-operator chat** — rejected: ephemeral, unauditable, violates INV-01.
- **Blocking wait inside the task** — rejected: requires suspended workflows; the exact dependency ADR-0015 defers.
- **Freeform comment entity** — rejected: answers must be evidence-grade (immutable, hashed, quotable), not prose in a side channel.

## Consequences
Consultations add latency by design — that is the point. Cost: snapshot storage for contexts and answers; one overdue scan; two task types. The context snapshot also answers "what exactly was the expert shown?" forever.

## Invariants
INV-01, INV-03, INV-04, INV-14, INV-15.