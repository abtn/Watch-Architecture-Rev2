"""Draft 2020-12 validation for Experiment A's machine-readable contracts."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError
import pytest

from research.experiment_a.canonical_fixtures import sample_fixtures


SCHEMA_DIR = Path(__file__).parents[1] / "research" / "experiment_a"
SCHEMA_FILES = {
    "fixture": "canonical-fixture.schema.json",
    "assessment": "evidence-assessment.schema.json",
    "output": "model-output.schema.json",
}


@pytest.fixture(scope="module")
def schemas():
    return {
        name: json.loads((SCHEMA_DIR / filename).read_text(encoding="utf-8"))
        for name, filename in SCHEMA_FILES.items()
    }


@pytest.fixture(scope="module")
def fixtures():
    return sample_fixtures()


def validator(schema):
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@pytest.mark.parametrize("name", ["fixture", "assessment", "output"])
def test_schema_definitions_are_valid_draft_2020_12(schemas, name):
    Draft202012Validator.check_schema(schemas[name])


@pytest.mark.parametrize("case_id", ["RW3-03", "RW3-13", "SP-01"])
def test_canonical_fixture_instances_conform_to_schema(schemas, fixtures, case_id):
    validator(schemas["fixture"]).validate(fixtures[case_id])


@pytest.mark.parametrize(
    ("kind", "temporal_status"),
    [
        ("evidence_link", "completed"),
        ("proposed_link", "completed"),
        ("source", "completed"),
        ("observation", "pending"),
        ("task", "pending"),
    ],
)
def test_evidence_assessment_instances_conform_to_schema(
    schemas, kind, temporal_status
):
    validator(schemas["assessment"]).validate(
        {
            "reference_kind": kind,
            "reference": "reference-001",
            "relevance": "direct",
            "reliability": "moderate",
            "independence": "independent",
            "temporal_status": temporal_status,
        }
    )


@pytest.mark.parametrize(
    "change",
    [
        {"relevance": "strong"},
        {"reliability": "excellent"},
        {"independence": "unrelated"},
        {"temporal_status": "future"},
        {"reference_kind": "task_run"},
        {"unexpected": "not allowed"},
    ],
)
def test_evidence_assessment_schema_rejects_invalid_values_and_fields(
    schemas, change
):
    instance = {
        "reference_kind": "task",
        "reference": "task-014",
        "relevance": "direct",
        "reliability": "moderate",
        "independence": "independent",
        "temporal_status": "pending",
    }
    instance.update(change)
    with pytest.raises(ValidationError):
        validator(schemas["assessment"]).validate(instance)


def model_output(decision, *, proposed, from_confidence=None, to_confidence=None,
                 evidence_links=None):
    return {
        "case_id": "RW3-03",
        "decision": decision,
        "confidence_change": {
            "proposed": proposed,
            "from_confidence": from_confidence,
            "to_confidence": to_confidence,
            "cause_kind": "evidence" if proposed else None,
            "evidence_link_id": None,
            "evidence_link_ref": "link-001" if proposed else None,
        },
        "evidence_links": evidence_links or [],
        "evidence_assessment": [],
        "justification": "The decision follows the available evidence and task state.",
    }


def proposed_link(stance="supports"):
    return {
        "operation": "create",
        "link_ref": "link-001",
        "source_kind": "signal",
        "source_id": "sig-003",
        "stance": stance,
        "subject_hypothesis_id": "hyp-003",
    }


@pytest.mark.parametrize(
    ("decision", "source", "target"),
    [("increase", "low", "high"), ("decrease", "high", "low")],
)
def test_model_output_schema_accepts_directional_confidence_changes(
    schemas, decision, source, target
):
    instance = model_output(
        decision,
        proposed=True,
        from_confidence=source,
        to_confidence=target,
        evidence_links=[proposed_link()],
    )
    validator(schemas["output"]).validate(instance)


def test_model_output_schema_accepts_hold_with_mentions_link(schemas):
    instance = model_output(
        "hold", proposed=False, evidence_links=[proposed_link("mentions")]
    )
    validator(schemas["output"]).validate(instance)


def test_model_output_schema_accepts_no_update_without_new_links(schemas):
    validator(schemas["output"]).validate(model_output("no_update", proposed=False))


@pytest.mark.parametrize(
    "instance",
    [
        model_output(
            "increase",
            proposed=True,
            from_confidence="low",
            to_confidence="low",
            evidence_links=[proposed_link()],
        ),
        model_output(
            "decrease",
            proposed=True,
            from_confidence="moderate",
            to_confidence="high",
            evidence_links=[proposed_link()],
        ),
        model_output(
            "hold",
            proposed=True,
            from_confidence="low",
            to_confidence="moderate",
            evidence_links=[proposed_link()],
        ),
        model_output(
            "no_update", proposed=False, evidence_links=[proposed_link()]
        ),
    ],
)
def test_model_output_schema_rejects_invalid_decision_semantics(schemas, instance):
    with pytest.raises(ValidationError):
        validator(schemas["output"]).validate(instance)


def test_model_output_schema_rejects_hash_echo_and_unknown_properties(schemas):
    instance = model_output(
        "hold", proposed=False, evidence_links=[proposed_link("mentions")]
    )
    instance["evidence_links"][0]["snapshot_hash"] = "must-not-be-echoed"
    with pytest.raises(ValidationError):
        validator(schemas["output"]).validate(instance)

    instance = model_output("no_update", proposed=False)
    instance["unrecognized"] = True
    with pytest.raises(ValidationError):
        validator(schemas["output"]).validate(instance)


def test_model_output_schema_requires_all_contract_fields(schemas):
    instance = model_output("no_update", proposed=False)
    del instance["justification"]
    with pytest.raises(ValidationError):
        validator(schemas["output"]).validate(instance)
