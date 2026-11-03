# ADR-0029 — LLM-assisted Experience Distillation

## Status

**Accepted — architectural principles and initial R6 implementation contract, 2026-10-25, under the operator's explicit request to resolve the remaining R6-G0 decisions.** This records design authority only; no implementation is authorized.

## Context

Watch is intended to preserve what its team learns beyond a single Task or model run. Saving transcripts, generating a summary, or automatically promoting every successful result does not establish reusable experience. The system needs a controlled method for using LLMs to abstract lessons from specific work while preserving the evidence, limitations, and circumstances that justify those lessons.

The existing architecture describes Outcomes, Evaluations, KnowledgeItems, and LearningChanges and states that Team memory changes only through the authorized learning path (INV-12). Those concepts are not all implemented in the current ORM/migration baseline. This ADR records their intended role in the future R6 loop; it does not claim the path already exists.

## Decision

### 1. Meaning of distillation

**Experience distillation is the process of proposing a reusable abstraction from concrete, durable work and its evidence.** It is not merely transcript summarization, free-form reflection, a confidence score, or model-weight training.

An abstraction should express what may transfer from one or more experiences to another situation, under what conditions it applies, what evidence supports it, and what limitations or counterexamples are known.

The initial abstraction vocabulary should align with the existing architecture's KnowledgeItem kinds:

- **Practice:** a repeatable way to carry out a class of work.
- **Pattern:** a recurring relationship or structure observed across cases.
- **Method:** a procedure for investigating, reasoning, or solving a problem.
- **Playbook:** a more complete collection of conditional steps for a recurring situation.

The exact persisted schema remains a G0 decision and must follow the authoritative model and migration state, not be improvised from this prose.

### 2. Distillation pipeline

The intended first pipeline is:

1. **Experience:** collect durable Task, Event, source, decision, and execution records. Do not use an unbounded conversation transcript as the durable basis.
2. **Outcome:** record what happened or what was observed, with source provenance where applicable. An Outcome is an observation, not an interpretation.
3. **Evaluation:** assess the Outcome and relevant work using the recorded evidence. An Evaluation is itself a proposal until validated and recorded; it is not an oracle.
4. **Distillation proposal:** an LLM receives the bounded, traceable basis and proposes an abstraction, including its applicable situation, assumptions/preconditions, supporting cases, counterexamples or contradictions, known limitations, uncertainty, and references to the basis.
5. **Validation:** application code validates the proposal schema, Team ownership, basis references, evidence and version preconditions, allowed write scope, and policy requirements. A model cannot validate its own authority to commit.
6. **Learning commit:** accepted changes go through the authorized LearningChange/learning commit path. For the first R6 slice, every LearningChange is explicitly reviewed by an operator through `approve_learning_change`; a model cannot approve its own proposal. The first slice does not authorize TeamPolicy changes. The model does not write KnowledgeItem or TeamPolicy records directly.
7. **Publication for reuse:** only accepted canonical knowledge becomes eligible for RAG indexing. Indexing is a regenerable projection and is not the learning commit itself. Subsequent Tasks retrieve the accepted version through ADR-0028's Context path.

### 3. Guard against overgeneralization

- One apparent success is not sufficient proof of a universal method. The first slice must allow an explicitly narrow, tentative candidate to be proposed without representing it as a generally validated rule.
- Keep observations and Outcomes distinct from interpretation and abstraction.
- Retain direct references to the source cases and evidence; do not replace their provenance with the LLM's prose.
- Preserve contradictory and disconfirming cases rather than deleting them to make an abstraction look consistent.
- Describe applicability and non-applicability conditions, missing evidence, assumptions, limitations, and uncertainty.
- Repeated cases may support a candidate pattern, but recurrence alone does not prove causation or guarantee transfer to a new domain.
- Knowledge must be versioned and auditable. Revision, supersession, retirement, review, and RAG eligibility must follow explicit state transitions; accepted past versions must not be silently rewritten.

### 4. Authority boundary

The LLM proposes a candidate abstraction. It cannot commit an accepted KnowledgeItem, revise TeamPolicy, alter a Task's allowed writes/tools/budget, mutate the Kernel, or bypass the learning path. Application code checks provenance, schema, ownership, scope, policy, current target version, and concurrency before commit.

For the first R6 vertical slice, the recommended path is bounded and reviewable, with explicit operator-reviewed acceptance through the authorized learning path. It must not auto-accept a lesson merely because its originating Task succeeded. TeamPolicy changes retain their existing additional approval requirements.

### 5. Relationship to RAG

RAG helps retrieve knowledge for the current Task; distillation proposes new reusable knowledge from accumulated experience. They are complementary but not interchangeable:

- RAG does not turn retrieved content into verified truth.
- Distillation does not bypass evidence or learning commit rules.
- A proposed abstraction is not made available as accepted Team Experience merely because it has been generated.
- After an accepted canonical change, the retrieval projection must be updated or rebuilt. Until it is eligible and current, the new version must not be represented as already available for retrieval.
- Later evaluations should examine whether retrieved abstractions were useful, misleading, stale, or inapplicable and should preserve that evidence for future review.

## Consequences

- Watch can accumulate reusable team experience rather than depend on chat history.
- LLMs perform the high-level abstraction work, while application code governs evidence, authority, persistence, and version transitions.
- A useful lesson remains explainable by pointing to the specific experiences that support it.
- The first R6 integrated slice demonstrates the cycle from durable experience to proposed abstraction, authorized acceptance, RAG publication, and later reuse.

## Alternatives considered

- **Persist whole transcripts as organizational memory:** rejected. Transcripts are execution-scoped and do not provide validated, reusable, permission-scoped knowledge.
- **Save an LLM summary as accepted knowledge automatically:** rejected. A summary can omit counterexamples, conflate correlation and cause, or overgeneralize from a single case; it also bypasses INV-12.
- **Have a second model act as final authority for durable learning:** rejected. Another model's judgment is still a proposal and cannot replace application validation or operator approval where required.
- **Automatically modify policy or the Kernel from a distilled lesson:** rejected. TeamPolicy and Kernel authority remain separate from learned domain practices, and no recursive self-modifying runtime is introduced.

## Initial proposal, evidence, review, and publication contract

The first distillation operation reads durable Task Events, terminal `task_execution` Outcomes, recorded Evaluations, and their canonical Signal/Snapshot evidence. It never uses an unbounded transcript as its evidence basis.

A proposed `LearningChange.proposed_state` must validate against this logical payload before commit:

- `kind`: `practice`, `pattern`, `method`, or `playbook`;
- `title`, `statement`, and `body`;
- `applicability` and preconditions/task class;
- assumptions, limitations, missing information, uncertainty, and known counterexamples;
- references to supporting Outcome IDs, Evaluation IDs, canonical Signal IDs and Snapshot hashes;
- references to contrary/disconfirming records where present;
- a deterministic hash/version of the complete evidence basis.

These fields belong to the proposed state and evidence references; they do not imply that every field needs a new column. The minimum `KnowledgeItem` and `LearningChange` schema must follow the architecture fields and existing learning-commit path, not a parallel memory subsystem.

**Evidence rule:** two independently recorded Outcomes from distinct Task IDs, with corresponding recorded Evaluations, are required before an abstraction is represented as a cross-case Pattern, Method, or Playbook. That threshold permits a proposal; it does not prove causation or universal transfer. A single case may only motivate a narrowly scoped `practice` candidate, explicitly marked low confidence and tied to its exact situation; it must not be described as a general rule. Counterexamples and conflicting evidence must be preserved, not averaged away. If no counterexample is known, say it was not observed in the available basis rather than claiming none exists.

**Review and commit:** every first-slice LearningChange is reviewed explicitly by an operator using the authorized `approve_learning_change` path. The model cannot accept its own proposal. Application validation checks Team ownership, every referenced record/hash, evidence rule, current target version, status, allowed Task scope, and concurrency. Acceptance/rejection and any committed KnowledgeItem version are durable and attributable; replay cannot create a second accepted version. No R6-F distillation write may change TeamPolicy.

**Versioning:** accepted changes create an auditable version. The prior state is retained in LearningChange history; only the current accepted `active` version that has not reached `review_after` is eligible for Team Experience retrieval. `needs_review`, retired, rejected, proposed, or superseded material is excluded.

**D7 — Review scheduling and retrieval eligibility (resolved 2026-11-02):**

- The sole interval source is the optional TeamPolicy rule `review.knowledge_item_interval_days`. It must be a positive integer (booleans are invalid); there is no global, pack, or implicit default. Add this key only through a forward TeamPolicy rules-JSON-Schema revision, not by silently changing the fixed v1 rule vocabulary. Existing policy versions without the key are unscheduled.
- When an `approve_learning_change` Task accepts a create proposal, application code reads the TeamPolicy row pinned by that Task's `(team_id, policy_version)`. If the key is valid, set `review_after` to the canonical `committed_at` plus that many 24-hour days. Use timezone-aware UTC values. If the key is absent, persist `review_after = NULL`. A present but invalid value fails policy validation and cannot be silently treated as absent.
- A later TeamPolicy version affects only approval Tasks pinned to that version. It does not rewrite existing KnowledgeItem dates. Existing/null-dated items are not retroactively backfilled by this decision; any authorized scheduling/backfill operation must be separately designed and must not use direct database mutation.
- `NULL` means no schedule has been established and is **ineligible for Team Experience indexing and retrieval**. It does not mean indefinitely valid. A non-null item is due at the exact boundary `now_utc >= review_after`; a due item is excluded from retrieval immediately, even before its status transition is processed.
- Only a deterministic ordinary `review_knowledge` Task may transition a current same-Team item from `active` to `needs_review`. The Task producer/scheduler only enqueues an ordinary Task and never mutates the item. The deterministic application service rechecks the current row under lock and commits the status transition with its Task-attributed Event atomically. `TaskRuntime` remains the sole Task lifecycle authority; no second runtime, general scheduler, or `TaskDispatcher` expansion is authorized.
- The scheduled review Task never reactivates an item, resets its date, revises it, or retires it. A `needs_review → active` revalidation requires a separate explicit and authorized operation. D7 does not authorize TeamPolicy writes, a TeamPolicy backfill, or Checkpoint 4 implementation.

**Publication:** canonical learning commit is independent from its retrieval projection. If indexing fails, keep the canonical decision and record projection staleness; do not advertise the new version as retrievable. Retrieval must verify the current canonical version/status/hash before sending content to a model. Projection retry/rebuild is idempotent and does not create or accept knowledge.

## Acceptance criteria for implementation

- Missing, mismatched, cross-Team, stale, or unauthorized evidence references are rejected by application validation.
- A single success cannot become a generalized Pattern, Method, or Playbook. A one-case practice is clearly narrow and low confidence.
- Conflicts, contrary evidence, uncertainty, and applicability limits remain inspectable.
- Operator rejection and acceptance are durable; replay cannot duplicate a proposal commit or version.
- Only the accepted current canonical version is eligible for retrieval; failed/stale publication never claims that the new version is already available.
- No distillation result can alter TeamPolicy, bypass INV-12, or write directly from the LLM to Team memory.

