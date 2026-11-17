import json
from copy import deepcopy
from pathlib import Path

import pytest

from research.experiment_a.canonical_fixtures import (
    EVIDENCE_ASSESSMENT_ENUMS,
    assert_representation_invariant_7,
    canonical_fixture_hash,
    presentation_hash,
    render_flat,
    render_structured,
    sample_fixtures,
    validate_evidence_assessment,
    validate_fixture,
)


@pytest.fixture(scope="module")
def fixtures():
    return sample_fixtures()


@pytest.mark.parametrize("case_id", ["RW3-03", "RW3-13", "SP-01"])
def test_sample_fixtures_satisfy_representation_invariant_7(fixtures, case_id):
    assert_representation_invariant_7(fixtures[case_id])


def test_flat_rw3_is_flat_json_without_decision_grouping(fixtures):
    rendered = render_flat(fixtures["RW3-03"])
    assert set(rendered) == {
        "case_id", "role", "hypothesis", "confidence_changes", "evidence_links",
        "unlinked_sources", "observations", "tasks", "outcomes", "lineage_pairs",
        "uncertainty_notes",
    }
    assert "supporting" not in rendered
    assert "temporal_state" not in rendered


def test_structured_rw3_groups_evidence_and_temporal_state(fixtures):
    rendered = render_structured(fixtures["RW3-13"])
    assert set(rendered["evidence"]) == {
        "supporting", "challenging", "mentions", "unlinked_sources"
    }
    assert (
        rendered["temporal_state"]["pending_observations"][0]["observation_id"]
        == "obs-013"
    )
    assert (
        rendered["temporal_state"]["pending_tasks"][0]["task_type"]
        == "check_triggers"
    )


def test_sp01_matches_real_state_assessment_projection(fixtures):
    fixture = fixtures["SP-01"]
    flat = render_flat(fixture)
    structured = render_structured(fixture)
    assessment = flat["state_assessment"]
    assert set(assessment) == {
        "objective", "team", "policies", "tasks", "events", "signals", "basis",
        "created_at",
    }
    assert "outcomes" not in assessment
    assert "source_identity_visibility" not in assessment
    assert assessment["policies"][0]["version"] == 1
    assert assessment["tasks"][0]["policy_version"] == 1
    assert assessment["tasks"][0]["task_type"] == "ingest_source"
    assert json.loads(assessment["policies"][0]["rules_json"])["sources"] == [{
        "origin_url": "https://source.example.test/feed",
        "source_type": "feed",
    }]
    assert fixture["evaluator_metadata"]["state_assessment_source_identity_sufficient"]
    assert "evaluator_metadata" not in flat
    assert "evaluator_metadata" not in structured
    assert presentation_hash(flat) == presentation_hash(structured)


def test_state_assessment_rejects_non_watch_fields(fixtures):
    fixture = deepcopy(fixtures["SP-01"])
    fixture["state_assessment"]["outcomes"] = []
    with pytest.raises(ValueError, match="StateAssessment fields"):
        validate_fixture(fixture)


def test_closed_evidence_assessment_enums_are_frozen():
    assert EVIDENCE_ASSESSMENT_ENUMS == {
        "relevance": frozenset({"direct", "indirect", "out_of_scope", "tangential"}),
        "reliability": frozenset({"high", "moderate", "low", "unknown"}),
        "independence": frozenset({"independent", "related", "unknown"}),
        "temporal_status": frozenset({"completed", "pending", "missing"}),
    }


@pytest.mark.parametrize(
    ("kind", "reference"),
    [("source", "sig-003"), ("observation", "obs-013"), ("task", "task-013")],
)
def test_evidence_assessment_can_reference_non_link_fixture_identifiers(
    fixtures, kind, reference
):
    fixture = fixtures["RW3-03"] if kind == "source" else fixtures["RW3-13"]
    validate_evidence_assessment(
        {
            "reference_kind": kind,
            "reference": reference,
            "relevance": "direct",
            "reliability": "high",
            "independence": "independent",
            "temporal_status": "completed" if kind == "source" else "pending",
        },
        fixture,
    )


def test_evidence_assessment_rejects_invalid_enum(fixtures):
    with pytest.raises(ValueError, match="invalid evidence assessment relevance"):
        validate_evidence_assessment(
            {
                "reference_kind": "source", "reference": "sig-003",
                "relevance": "strong", "reliability": "high",
                "independence": "independent", "temporal_status": "completed",
            },
            fixtures["RW3-03"],
        )


def test_canonical_hash_ignores_evaluator_metadata_and_presentations_differ(fixtures):
    fixture = fixtures["RW3-03"]
    before = canonical_fixture_hash(fixture)
    fixture["evaluator_metadata"]["private_note"] = "not model input"
    assert canonical_fixture_hash(fixture) == before
    assert presentation_hash(render_flat(fixture)) != presentation_hash(
        render_structured(fixture)
    )
    assert "private_note" not in render_flat(fixture)


def test_evidence_assessment_can_reference_a_batch_local_proposed_link(fixtures):
    validate_evidence_assessment(
        {
            "reference_kind": "proposed_link", "reference": "link-003",
            "relevance": "direct", "reliability": "high",
            "independence": "independent", "temporal_status": "completed",
        },
        fixtures["RW3-03"],
        proposed_links=[{"link_ref": "link-003"}],
    )


def test_existing_evidence_link_reference_uses_record_identifier(fixtures):
    fixture = deepcopy(fixtures["RW3-03"])
    fixture["evidence_links"] = [{
        "evidence_link_id": "ev-003",
        "hypothesis_id": "hyp-003",
        "source_kind": "signal",
        "source_id": "sig-old",
        "stance": "supports",
    }]
    validate_evidence_assessment(
        {
            "reference_kind": "evidence_link", "reference": "ev-003",
            "relevance": "direct", "reliability": "high",
            "independence": "independent", "temporal_status": "completed",
        },
        fixture,
    )


def test_machine_readable_schemas_freeze_enums_and_omit_hash_echo_fields():
    schema_dir = Path(__file__).parents[1] / "research" / "experiment_a"
    fixture_schema = json.loads(
        (schema_dir / "canonical-fixture.schema.json").read_text(encoding="utf-8")
    )
    assessment_schema = json.loads(
        (schema_dir / "evidence-assessment.schema.json").read_text(encoding="utf-8")
    )
    output_schema = json.loads(
        (schema_dir / "model-output.schema.json").read_text(encoding="utf-8")
    )
    assert fixture_schema["$schema"].endswith("2020-12/schema")
    assert assessment_schema["properties"]["relevance"]["enum"] == [
        "direct", "indirect", "out_of_scope", "tangential",
    ]
    assert assessment_schema["properties"]["reliability"]["enum"] == [
        "high", "moderate", "low", "unknown",
    ]
    assert assessment_schema["properties"]["independence"]["enum"] == [
        "independent", "related", "unknown",
    ]
    assert assessment_schema["properties"]["temporal_status"]["enum"] == [
        "completed", "pending", "missing",
    ]
    assert "task" in assessment_schema["properties"]["reference_kind"]["enum"]
    link_fields = output_schema["$defs"]["proposedEvidenceLink"]["properties"]
    assert not {"snapshot_ref", "snapshot_hash", "reference_key"} & set(link_fields)

    confidence_change = output_schema["$defs"]["confidenceChange"]
    proposed_rule = confidence_change["allOf"][0]["then"]["properties"]
    assert proposed_rule["from_confidence"]["type"] == "string"
    assert proposed_rule["to_confidence"]["type"] == "string"

    direction_rules = {
        rule["if"]["properties"]["decision"]["const"]: rule["then"]
        for rule in output_schema["allOf"]
        if "const" in rule.get("if", {}).get("properties", {}).get("decision", {})
    }
    expected_increase = {
        ("low", "moderate"), ("low", "high"), ("moderate", "high"),
    }
    expected_decrease = {
        ("high", "moderate"), ("high", "low"), ("moderate", "low"),
    }
    for decision, expected in (
        ("increase", expected_increase), ("decrease", expected_decrease),
    ):
        variants = direction_rules[decision]["properties"]["confidence_change"]["oneOf"]
        actual = {
            (
                variant["properties"]["from_confidence"]["const"],
                variant["properties"]["to_confidence"]["const"],
            )
            for variant in variants
        }
        assert actual == expected

    assert output_schema["$defs"]["proposedEvidenceLink"]["properties"]["stance"]["enum"] == [
        "supports", "challenges", "mentions",
    ]
    assert "intentionally extensible" in fixture_schema["properties"]["outcomes"]["description"]


def test_flat_arrays_order_timestamped_records_chronologically(fixtures):
    fixture = deepcopy(fixtures["RW3-13"])
    fixture["observations"] = [
        {
            "observation_id": "obs-later",
            "status": "completed",
            "observed_at": "2026-11-17T12:00:00Z",
        },
        {
            "observation_id": "obs-earlier",
            "status": "completed",
            "observed_at": "2026-11-17T10:00:00Z",
        },
    ]
    rendered = render_flat(fixture)
    assert [item["observation_id"] for item in rendered["observations"]] == [
        "obs-earlier", "obs-later",
    ]
