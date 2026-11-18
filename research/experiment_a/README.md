# Experiment A canonical fixtures (offline only)

This package defines the first three canonical sample fixtures and their JSON
renderers. It is isolated from Watch application code: no core imports, network
calls, provider calls, database access, or production edits.

## Files

- canonical-fixture.schema.json: strict top-level fixture envelope with explicitly extensible case-specific record payloads.
- evidence-assessment.schema.json: closed assessment enums and reference kinds.
- model-output.schema.json: closed RW-3 output contract, including confidence-transition direction and hold/no_update.
- canonical_fixtures.py: fixture validation, renderers, hashing, and Invariant #7.
- tests/test_experiment_a_fixtures.py: fixture, renderer, and Invariant #7 tests.
- tests/test_experiment_a_json_schemas.py: Draft 2020-12 schema checks and positive/negative instance validation.

## Schema boundaries

The canonical fixture schema closes the top-level envelope and fixes shared record identifiers/status fields where defined. Some scientific evidence details (for example measurement descriptions, confidence-history entries, lineage details, and uncertainty annotations) remain intentionally extensible because the current three fixtures do not establish a complete shared vocabulary for them. Do not treat those payloads as fully closed. The model-facing evidence-assessment and proposal-output schemas are closed. Draft 2020-12 validation checks each schema definition and validates all three canonical fixture instances plus representative evidence-assessment and model-output instances. These checks prove structural conformance; fixture-specific reference existence remains the responsibility of the Python semantic validator.

### Normative boundary: contract versus scientific payload

The model-facing contract and the scientific fixture payload are separate boundaries:

- **Model-facing contract:** role-specific inputs and outputs are explicit, closed, and validated against their applicable schemas. Undeclared fields are rejected. Contract changes require a deliberate schema/version change.
- **Scientific fixture payload:** case-specific observations, measurements, assumptions, provenance, confidence history, lineage, and uncertainty details may remain extensible where the canonical schema explicitly allows them. Preserve these details as research data; do not claim that every nested scientific object is fully closed.

Extensibility is not authority. An unknown or newly added scientific payload field may be preserved as data, but must not automatically become a model instruction, application permission, evidence reference, or executable semantic. Any projection of scientific fixture content into a model-facing request must be explicit and controlled by the application. Model outputs remain constrained by the closed role-specific output contract regardless of what fields appear in the scientific payload.

When adding a field, determine first which boundary owns it. If it changes what a model is permitted or required to receive or return, update and version the relevant model-facing contract and its tests. If it adds case-specific scientific detail, keep it within an explicitly extensible payload and add preservation/validation tests without widening model-output schemas.

For model output, `increase` requires a strictly higher confidence band and `decrease` a strictly lower band (`low < moderate < high`). A proposed ConfidenceChange requires non-null source and target bands. `hold` and `no_update` prohibit a ConfidenceChange; `no_update` also prohibits new EvidenceLinks. A `hold` may include a `mentions` EvidenceLink, and stance alone does not determine whether confidence changes.

## Representations

- Flat: flat JSON arrays; no stance grouping or temporal partitioning.
  Timestamped records are ordered by the first available field in this fixed
  precedence: occurred_at, created_at, recorded_at, observed_at, requested_at,
  fetched_at, timestamp. Values must be ISO-8601 timestamps with an explicit
  UTC offset; sorting compares actual instants after UTC normalization. Equal
  instants retain canonical input order. Untimed records follow timestamped
  records and retain their relative input order.
- Structured: evidence stance groups, provenance, temporal-state groups, and
  uncertainty notes.
- SP-01: a separate StrategyProposer diagnostic. Both renderers preserve the
  exact same StateAssessment projection. Evaluator metadata is never model input.
  Renderer labels are not included in the model-facing JSON.

SP-01 mirrors StateAssessment fields: objective, team, policies, tasks, events,
signals, basis, and created_at. It deliberately has no outcomes or
source_identity_visibility field. TeamPolicy sources are objects containing
origin_url and source_type. AssessmentPolicy.version and AssessmentTask.policy_version
are integers. The policy's rules_json string is preserved as exposed by the
actual projection.

The SP-01 single-source fact is evaluator metadata, not a model-facing field.
It is true because the policy contains exactly one configured source.

## Evidence assessment and proposal output

The closed vocabularies are:

- relevance: direct, indirect, out_of_scope, tangential
- reliability: high, moderate, low, unknown
- independence: independent, related, unknown
- temporal_status: completed, pending, missing

Reference kinds are evidence_link, proposed_link, source, observation, and task.
The task kind is included so an in-flight Task such as task-014 can be assessed
without pretending it is an EvidenceLink or an observation.

hold means relevant evidence or an in-flight state was assessed but no
ConfidenceChange is proposed. A relevant new source may still receive a mentions
EvidenceLink. no_update means no material new evidence or state change: neither
an EvidenceLink nor a ConfidenceChange is proposed.

A ConfidenceChange references either a pre-existing evidence_link_id or a
same-batch evidence_link_ref. Newly proposed EvidenceLinks contain source_kind,
source_id, stance, and subject_hypothesis_id. They do not ask the model to echo
snapshot_ref, snapshot_hash, or reference_key; those belong to canonical source
and database validation.

The SHA-256 value in SP-01's StateAssessment basis is input context, not a value
the model must reproduce in its output.

## Run

From the repository root, run:

uv run pytest tests/test_experiment_a_fixtures.py tests/test_experiment_a_json_schemas.py -q

No model calls or database setup are needed. Passing these tests proves only the
fixture and renderer contract for these three samples. It does not authorize or
constitute Experiment A execution, RW-2/RW-3 implementation, scored RWN-01 runs,
or RW-1 formal Operator closeout.


Fixture identity validation checks record-owning identifiers only. For example,
a ConfidenceChange's `evidence_link_id` is a reference to an EvidenceLink, not
the identity of the ConfidenceChange, so that reference may legitimately match
the referenced EvidenceLink's identifier. Explicit record identifiers remain
unique within the fixture.
