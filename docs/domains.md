# docs/domains.md

# Domain packs

## 1. Role

A Domain pack adapts the shared kernel to a subject area. Kernel entities, invariants, state machines, and the learning loop are identical across packs; nothing domain-specific enters the kernel schema. The Team's mission, policy, and learned practices are kernel concepts regardless of Domain.

## 2. The pack contract

A Domain pack supplies exactly these seven things:

| Item | Type | Purpose |
|---|---|---|
| `signal_sources` | list of `{name, connector, poll_interval, parser}` | where observations come from and how they are parsed |
| `entity_vocabulary` | allowed keys and value constraints for `Thread.entities` | what the Domain's situations are made of |
| `match_heuristics` | deterministic functions: `(signal, threads, recent_signals) → candidates` | cheap candidate Thread matching and dedup checks |
| `render_templates` | `artifact_type → template + citation style` | Domain-appropriate outputs |
| `decay_window` | timedelta | how long a Hypothesis survives without fresh evidence |
| `decay_action` | band-step and dormancy rules | what decay does when the window elapses |
| `dedup_policy` | similarity threshold + lookback window | near-duplicate suppression at triage |

Packs may also provide prompt templates and normalizers for update/render tasks. Packs **may not** add kernel tables or columns, bypass validation, write outside Task scopes, or define decay that rejects Hypotheses.

Kernel-provided defaults: the default `decay_action` is "lower one band per elapsed window; flag Thread dormant when all active Hypotheses have been `low` for one window; never reject." Packs may tighten but not loosen the never-reject rule.

## 3. Newsroom pack

**Watched situations:** a company situation, a policy fight, a market shift, an election, a slow-moving investigation.

### `signal_sources` — TBD (first concrete watch target decides)
Candidate shapes: RSS feeds of major wires and topic-specific outlets; official data pages (for an oil-economy team: EIA, OPEC, central-bank and exchange announcements); poll aggregators (for an election team); manual ingest for paywalled or offline material. Exact feeds and access are an open question (§6).

### `entity_vocabulary`
`organization`, `person`, `policy_instrument`, `commodity`, `region`, `metric`, `event`, `claim`. Values are normalized names; `match_heuristics` maintains an alias table (e.g., "OPEC" / "OPEC+" / "Organization of the Petroleum Exporting Countries").

### `match_heuristics`
1. Entity overlap: ≥ 2 shared normalized entities → candidate match; 1 shared entity + recency (Thread updated within window) → candidate.
2. Embedding similarity above the Domain threshold against the Thread's embedding.
3. Dedup: cosine similarity ≥ threshold against Signals ingested within the lookback window → `duplicate` disposition.
4. No candidate → `deferred` (an update Task judges whether a new Thread starts) unless the signal matches the new-thread heuristic (strong multi-entity match with no Thread).

### `render_templates`
- `briefing` — current state: confirmed / disputed / open questions, per Hypothesis with bands.
- `article` — narrative rendering when a story is ready; evidence-backed claims only.
- `daily_digest` — what changed today: new evidence, confidence changes, new/retired Threads.

### Decay
`decay_window`: 72 hours default. Breaking-news Threads live and die fast; structural Threads (policy fights) are expected to re-earn confidence with fresh evidence or fade — which is the intended behavior, and the signal.

**Election variant:** same pack, election vocabulary (`candidate`, `party`, `poll`, `district`) set as a team `vocabulary` policy over the pack defaults, poll-release-driven sources via the `sources` rule, and a decay window keyed to the poll cycle via the `decay` rule. Treated as a newsroom configuration, not a new pack, unless it forces kernel changes (per M6's rule).

## 4. Devteam pack

**Watched situations:** emerging tools and stacks, engineering patterns, postmortems and failure modes, adoption evidence.

### `signal_sources` — TBD
Candidate shapes: arXiv categories, GitHub releases and trending, Hacker News, engineering blogs, curated postmortem collections.

### `entity_vocabulary`
`tool`, `language`, `framework`, `platform`, `practice`, `benchmark`, `failure_mode`. Alias table for tool names and spellings ("k8s" / "Kubernetes").

### `match_heuristics`
Repository/tool-name match; alias-table match; embedding similarity; dedup as above (release notes and announcement reposts syndicate heavily — dedup against canonical origins per the learned K-003 v2 semantics).

### `render_templates`
- `recommendation_memo` — adopt / avoid / investigate positions with evidence.
- `radar_entry` — a single tool or practice assessment.
- `digest` — weekly landscape changes.

### Decay
`decay_window`: 14 days. The landscape moves slower than news; adoption evidence ages gradually.

## 5. Generalist pack (kernel-shipped)

Makes any subject watchable with zero new code; the setup advisor's fallback (architecture F7).

- **`signal_sources`:** `manual` (always) + a generic RSS connector parameterized by the team's `sources` policy rule. Advisor-suggested feeds are marked *unverified until first successful fetch*; repeated fetch failures surface in metrics.
- **`entity_vocabulary` defaults:** `topic`, `actor`, `event`, `metric` — extendable per team via the `vocabulary` policy rule (keys and values must follow the pack's structure).
- **`match_heuristics`:** normalized keyword/alias match + recency; embedding similarity activates with M3.
- **`render_templates`:** `briefing`, `memo`, `digest`.
- **`decay_window`:** 14 days default; per-team override via the `decay` rule within pack bounds. The never-reject rule is not overridable by pack or policy.
- **`dedup_policy`:** exact-origin only at v1 start; similarity dedup activates with M3.

Expert-heavy teams (a clinician's field watcher, a game-strategy desk) run on this pack: the expert contributes via `operator_update` and is consulted via F8; the pack supplies only the plumbing.

### Precedence: pack defaults vs. team policy

| Concern | Pack supplies | Team policy may |
|---|---|---|
| `entity_vocabulary` | default keys + structure | add team-specific keys/values within the structure |
| `sources` (parameterized connectors) | the connector | set the per-team source list |
| `decay` | default window/action | override window/action within pack bounds; never reject |
| heuristics, templates | fixed | select among templates via `preferences` |

Invariants always win: no pack configuration or policy rule can bypass validation, write scopes, or the never-reject decay rule.

## 6. Open questions

1. **Concrete source list and access** for the first newsroom Team — which feeds/APIs are actually pullable (free vs. auth-gated), tied to the first M2 watch target.
2. **Final entity vocabularies** — seeded above, tightened after M1 runs against real material.
3. **Numeric thresholds** — match and dedup similarity thresholds; starting guesses, tuned against observed precision/recall of triage.
4. **Per-thread decay override** — v1 has one window per Domain (plus the team-level `decay` policy rule); if breaking vs. structural Threads need different windows within one team, add a thread-class override (small kernel extension, decided deliberately).
5. **Devteam pack timing** — pressure-tests the abstraction in M6; not built before the newsroom loop is proven.
6. **Generalist vocabulary growth** — how team-added vocabulary keys are reviewed, so ten teams don't fork the default structure silently.