# ADR-0029 — LLM-assisted Experience Distillation

## Status

**Accepted — architectural principles only, 2026-10-25, by explicit operator agreement with the LLM-assisted Experience Distillation design.** This acceptance does not authorize implementation. The first schema/output contract, evidence threshold, approval workflow, versioning policy, and retrieval-publication details remain within R6-G0.

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
6. **Learning commit:** accepted changes go through the existing authorized LearningChange/learning commit path. The model does not write KnowledgeItem or TeamPolicy records directly. Where approval or policy authorization is required, the existing rule governs; G0 must resolve any ambiguity before implementation.
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

## Implementation decisions remaining for R6-G0

- Which durable records and Outcome/Evaluation types are the required input to the first distillation?
- What is the minimum acceptable evidence basis, and how can a single-case lesson be represented narrowly without being presented as a general rule?
- Which output fields and evidence-reference format are needed for the initial KnowledgeItem/LearningChange schema?
- Which learning changes require operator approval, and how does the first slice expose accept/reject/revise outcomes?
- How are versions, supersession, review/expiry, and retrieval eligibility represented?
- What constitutes a conflicting case, and how should it affect a proposed abstraction?
- How is successful later reuse recorded so R7 can evaluate whether the abstraction helped?
- What idempotency key or durable event boundary prevents replay from creating duplicate learning proposals or accepted versions?

## Acceptance criteria for a future implementation

- Given durable experience and an evidence basis, an LLM can propose a typed abstraction with applicable context, limitations, uncertainty, and source references.
- Invalid, missing, cross-Team, stale-version, or unsupported evidence references are rejected by application validation.
- A model cannot commit its own proposed abstraction or alter TeamPolicy directly.
- Counterexamples and uncertainty remain representable; the implementation does not infer causation or universal validity solely from recurrence or success.
- Acceptance/rejection is durable, auditable, versioned, and idempotent under retry/replay.
- Only accepted canonical knowledge is made eligible for retrieval, and its retrieval provenance resolves to the accepted version.
- A later Task can retrieve and use an accepted abstraction without relying on the prior model transcript.
- Tests cover failure, rejection, conflict, duplicate/replay, and index-update recovery paths.

These criteria describe the accepted architectural target, not completed tests or current capabilities.
