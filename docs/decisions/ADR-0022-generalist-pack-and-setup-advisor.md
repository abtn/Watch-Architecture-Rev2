# File: docs/decisions/0022-generalist-pack-and-setup-advisor.md

# ADR-0022: Generalist pack and the setup advisor

**Status:** accepted  **Date:** 2025-01-15

## Context
Subjects with no domain pack — a brand-new game, a personal field of expertise — had no on-ramp: packs require code, and building one per subject defeats "watch anything."

## Decision
The kernel ships a **generalist pack**: manual intake plus a generic RSS connector parameterized by the team's `sources` policy rule; a default vocabulary extendable per team via `vocabulary`; keyword/alias heuristics; standard templates; 14-day decay default overridable via `decay` (never-reject stays fixed). Team creation follows F7: `create_team` (shell team, `configuring`, freeform subject brief snapshotted) → `configure_team` (model drafts a TeamDraft — mission, vocabulary, candidate sources marked unverified, thresholds, starter Threads, policy v1, advisor notes citing the samples) → `activate_team` (operator edits/approves; policy schema, vocabulary structure, and pack conformance validated; policy v1 + starter threads committed; team `active`). The approved config snapshot is the team's birth certificate. TeamPolicy gains the `vocabulary`, `sources`, and `decay` rule groups; Team.status gains `configuring`.

## Alternatives considered
- **Advisor generates a new pack (code)** — rejected: arbitrary code generation is beyond v1 and unauditable; configuration-within-contract is safer and evaluable.
- **Fully automatic team creation** — rejected: operator approval is the v1 rule for anything that shapes behavior.
- **Wait for per-subject packs** — rejected: defeats the "team of experts for any subject" premise.

## Consequences
Any feed-followable subject is watchable on day one; specialized packs become optimizations, not prerequisites. The advisor is the strongest abstraction pressure test — an arbitrary team must run with zero per-subject code. Draft configs are immutable and evaluable, so advisor quality itself becomes learnable team memory. Cost: three policy rule groups, one new team status, three task types.

## Invariants
INV-02, INV-12, INV-14, INV-15.