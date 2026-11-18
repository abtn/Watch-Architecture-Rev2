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

### Normative boundary: strict model contract versus extensible scientific payload

The model-facing contract and the scientific fixture payload are separate boundaries with different validation and authority rules. The distinction is normative: extensibility in scientific data must never widen the model's permitted inputs, outputs, or authority.

#### 1. Strict model-facing contract

Model-facing inputs and outputs are explicit, role-specific, and closed. Their applicable schemas define the permitted fields, types, required values, enums, and structural constraints. Undeclared fields are rejected at the model-contract boundary; required fields and nested structures are validated, not merely the top-level object. Changes that affect what a model may receive or return require a deliberate, reviewed, and versioned contract change.

The evidence-assessment and RW-3 proposal-output schemas are examples of this strict boundary. Their closed vocabularies and output constraints must not be loosened merely to accommodate a new scientific fixture field.

#### 2. Extensible scientific fixture payload

Scientific fixture payloads preserve case-specific research content, including observations, measurements, assumptions, provenance, confidence history, lineage, uncertainty annotations, and other domain details. These details may remain extensible only where the canonical fixture schema explicitly permits extension. This is intentional: the current fixture corpus does not establish a complete universal vocabulary for every scientific record.

Extensibility means that a fixture can preserve additional scientific data without requiring every such field to become part of a shared model contract. It does not mean every nested scientific object is unconstrained: the canonical envelope, record-owning identity fields, and any explicitly defined shared fields retain their declared validation rules.

#### 3. Illustrative conceptual separation

The following is a conceptual example of the boundary, not a prescribed replacement for the current canonical fixture format and not a request to change the existing fixture schemas:

```json
{
  "fixture_version": 1,
  "case_id": "RW3-03",
  "model_contract": {
    "role": "strategy_proposer",
    "required_outputs": ["proposal", "evidence_references"]
  },
  "scientific_context": {
    "domain": "case-specific",
    "payload": {
      "observations": [],
      "assumptions": [],
      "additional_scientific_details": {}
    }
  }
}
```

The example makes the conceptual separation visible: the contract declares the model's bounded role and required output, while the scientific context carries case-specific data. The actual repository fixture shape remains the one defined by the current canonical schema and samples.

#### 4. Enforcement boundaries

The distinction must be maintained across four layers:

| Layer | Strict model-facing contract | Extensible scientific payload |
|---|---|---|
| Schema | Declare permitted fields and types; reject undeclared fields, including at nested contract objects. Version deliberate contract changes. | Preserve extensible case-specific content only at schema locations that explicitly allow it; retain validation for shared envelope and identity fields. |
| Validation | Check required fields, types, enums, nested constraints, and cross-field rules. Reject malformed or undeclared model output. | Check fixture structure and semantic relationships, including record identity and reference validity, without discarding permitted scientific detail. |
| Rendering | Project only explicitly selected, contract-approved fields into the model request. Do not pass arbitrary fixture keys through as instructions or permissions. | Preserve scientific meaning and relevant provenance when rendering research context; do not reinterpret unknown fields as executable semantics. |
| Application boundary | Treat model output as an untrusted proposal and validate it against the closed role-specific contract before application code acts on it. | Keep fixture content as data. Only explicit application-controlled projection can expose selected scientific content to a model or downstream operation. |

A schema's allowance for additional scientific fields is not a grant of authority. An unknown scientific field must not automatically become a model instruction, application permission, evidence reference, or executable semantic.

#### 5. Regression tests required when the boundary is implemented or extended

Tests should prove both sides of the distinction. At minimum, the relevant validation and rendering layers should cover:

- An unknown field in a strict model-facing object is rejected.
- A missing required model-contract field is rejected.
- An invalid confidence transition or other prohibited cross-field combination is rejected.
- A new field at an explicitly extensible scientific-payload location is accepted and preserved.
- An unknown scientific field is not treated as an authorized instruction, permission, evidence reference, or executable command.
- Rendering preserves the meaning and relevant provenance of scientific data while projecting only approved fields into model-facing requests.
- A reference to a nonexistent record is rejected by the appropriate semantic-validation layer.

These are boundary requirements for the relevant implementation and future changes. They do not claim that every listed case is already covered by the current three-fixture test suite. Keep schema validation and Python semantic validation aligned as the fixture corpus grows; document which layer owns each invariant rather than assuming that one validator performs the other's work.

#### 6. Documentation and change discipline

Keep this distinction visible in the documentation that governs the artifact:

- This README explains the two boundaries, the enforcement layers, and the current limitations of the fixture contract.
- Schema documentation identifies which objects are closed and which payload locations are intentionally extensible.
- Implementation guidance explains how renderers and application code explicitly project scientific data into model-facing requests and validate model proposals.

When adding a field, first decide which boundary owns it:

1. If it changes what a model is permitted or required to receive or return, update the relevant closed model-facing schema, version the contract as appropriate, and add positive and negative contract tests.
2. If it adds case-specific scientific detail, place it only in an explicitly extensible scientific payload, preserve it through the relevant renderer, and add validation/preservation tests.
3. In either case, verify that the field cannot silently acquire authority through rendering or application handling.

Do not close every scientific payload merely for uniformity, and do not make model-facing contracts permissive merely to accommodate scientific variation. The boundary should be explicit at the point where data is validated and at the point where it is projected into model context.

**Governing principle:** A scientific record may contain more information than a model contract understands. That must never mean the model gets more authority than the contract grants it.

For model output, `increase` requires a strictly higher confidence band and `decrease` a strictly lower confidence band (`low < moderate < high`). A proposed ConfidenceChange requires non-null source and target bands. `hold` and `no_update` prohibit a ConfidenceChange; `no_update` also prohibits new EvidenceLinks. A `hold` may include a `mentions` EvidenceLink, and stance alone does not determine whether confidence changes.

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
