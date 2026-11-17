"""Offline Experiment A canonical fixtures and representation renderers.

This module is isolated from Watch application code. It makes no network calls,
imports no core modules, and performs no database operations.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from copy import deepcopy
from typing import Any

CONFIDENCE_BANDS = frozenset({"low", "moderate", "high"})
DECISIONS = frozenset({"increase", "decrease", "hold", "no_update"})
REFERENCE_KINDS = frozenset(
    {"evidence_link", "proposed_link", "source", "observation", "task"}
)
EVIDENCE_ASSESSMENT_ENUMS = {
    "relevance": frozenset({"direct", "indirect", "out_of_scope", "tangential"}),
    "reliability": frozenset({"high", "moderate", "low", "unknown"}),
    "independence": frozenset({"independent", "related", "unknown"}),
    "temporal_status": frozenset({"completed", "pending", "missing"}),
}
FIXTURE_FIELDS = frozenset(
    {
        "case_id", "role", "hypothesis", "confidence_changes", "evidence_links",
        "unlinked_sources", "observations", "tasks", "outcomes", "lineage_pairs",
        "uncertainty_notes", "state_assessment", "evaluator_metadata",
    }
)
RW3_ARRAYS = (
    "confidence_changes", "evidence_links", "unlinked_sources", "observations",
    "tasks", "outcomes", "lineage_pairs", "uncertainty_notes",
)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def canonical_fixture_hash(fixture: dict[str, Any]) -> str:
    """Hash only model-visible facts; evaluator metadata is excluded."""
    if fixture["role"] == "strategy_proposer":
        payload = {
            "case_id": fixture["case_id"],
            "role": fixture["role"],
            "state_assessment": fixture["state_assessment"],
        }
    else:
        payload = {k: v for k, v in fixture.items() if k != "evaluator_metadata"}
    return canonical_hash(payload)


def presentation_hash(rendered: dict[str, Any]) -> str:
    return canonical_hash(rendered)


def _validate_state_assessment(value: dict[str, Any]) -> None:
    expected = {
        "objective", "team", "policies", "tasks", "events", "signals", "basis",
        "created_at",
    }
    if set(value) != expected:
        raise ValueError("StateAssessment fields do not match Watch projection")
    if set(value["objective"]) != {"id", "team_id", "statement", "status"}:
        raise ValueError("AssessmentObjective fields do not match Watch projection")
    if set(value["team"]) != {"id", "domain", "status"}:
        raise ValueError("AssessmentTeam fields do not match Watch projection")
    basis_fields = {
        "objective_id", "team_id", "policy_ids", "task_ids", "event_ids",
        "signal_ids", "sha256",
    }
    if set(value["basis"]) != basis_fields or len(value["basis"]["sha256"]) != 64:
        raise ValueError("AssessmentBasis fields do not match Watch projection")
    for policy in value["policies"]:
        if set(policy) != {"id", "team_id", "version", "rules_json"}:
            raise ValueError("AssessmentPolicy fields do not match Watch projection")
        if not isinstance(policy["version"], int) or isinstance(
            policy["version"], bool
        ):
            raise ValueError("AssessmentPolicy.version must be an integer")
        rules = json.loads(policy["rules_json"])
        for source in rules.get("sources", []):
            if set(source) != {"origin_url", "source_type"}:
                raise ValueError("TeamPolicy source requires origin_url/source_type")
    for task in value["tasks"]:
        if set(task) != {"id", "task_type", "status", "policy_version"}:
            raise ValueError("AssessmentTask fields do not match Watch projection")
        if not isinstance(task["policy_version"], int) or isinstance(
            task["policy_version"], bool
        ):
            raise ValueError("AssessmentTask.policy_version must be an integer")
    for event in value["events"]:
        if set(event) != {"id", "task_id", "event_type", "created_at", "signal_id"}:
            raise ValueError("AssessmentEvent fields do not match Watch projection")
    for signal in value["signals"]:
        if set(signal) != {
            "id", "source_type", "origin_url", "fetched_at", "content_hash",
            "snapshot_ref",
        }:
            raise ValueError("AssessmentSignal fields do not match Watch projection")


def validate_fixture(fixture: dict[str, Any]) -> None:
    unknown = set(fixture) - FIXTURE_FIELDS
    if unknown:
        raise ValueError(f"unknown fixture fields: {sorted(unknown)}")
    required = {"case_id", "role", "hypothesis", *RW3_ARRAYS}
    missing = required - set(fixture)
    if missing:
        raise ValueError(f"missing fixture fields: {sorted(missing)}")

    if fixture["role"] == "update_thread":
        if fixture["hypothesis"] is None:
            raise ValueError("update_thread fixture requires a Hypothesis")
        if fixture["hypothesis"]["current_confidence"] not in CONFIDENCE_BANDS:
            raise ValueError("invalid current confidence")
        if "state_assessment" in fixture:
            raise ValueError("update_thread fixture cannot contain StateAssessment")
    elif fixture["role"] == "strategy_proposer":
        if fixture["hypothesis"] is not None or "state_assessment" not in fixture:
            raise ValueError("StrategyProposer fixture requires StateAssessment only")
        if any(fixture[name] for name in RW3_ARRAYS):
            raise ValueError("StrategyProposer fixture contains RW-3-only records")
        _validate_state_assessment(fixture["state_assessment"])
        source_count = sum(
            len(json.loads(policy["rules_json"]).get("sources", []))
            for policy in fixture["state_assessment"]["policies"]
        )
        if source_count != 1:
            raise ValueError("StrategyProposer diagnostic requires exactly one source")
    else:
        raise ValueError("unsupported fixture role")

    identifiers: set[str] = set()
    if fixture["hypothesis"] is not None:
        identifiers.add(fixture["hypothesis"]["id"])
    for collection in RW3_ARRAYS:
        for record in fixture[collection]:
            identifier = (
                record.get("evidence_link_id") or record.get("id")
                or record.get("source_id") or record.get("observation_id")
            )
            if identifier is None:
                raise ValueError(f"{collection} record has no identifier")
            if identifier in identifiers:
                raise ValueError(f"duplicate fixture identifier: {identifier}")
            identifiers.add(identifier)

    for link in fixture["evidence_links"]:
        if link["stance"] not in {"supports", "challenges", "mentions"}:
            raise ValueError("invalid EvidenceLink stance")
        if link["source_kind"] not in {"signal", "outcome"}:
            raise ValueError("invalid EvidenceLink source_kind")
        if link.get("hypothesis_id", fixture["hypothesis"]["id"]) != fixture[
            "hypothesis"
        ]["id"]:
            raise ValueError("EvidenceLink belongs to a different Hypothesis")
    for source in fixture["unlinked_sources"]:
        if source["source_kind"] not in {"signal", "outcome"}:
            raise ValueError("invalid unlinked source_kind")
        if source["status"] not in {"completed", "pending", "missing"}:
            raise ValueError("invalid unlinked source status")
    for observation in fixture["observations"]:
        if observation["status"] not in {"completed", "pending", "missing"}:
            raise ValueError("invalid observation status")
    for task in fixture["tasks"]:
        if task["status"] not in {"completed", "running", "pending"}:
            raise ValueError("invalid fixture task status")
    for outcome in fixture["outcomes"]:
        if outcome["status"] not in {"completed", "pending", "missing"}:
            raise ValueError("invalid outcome status")


def _chronological(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = (
        "occurred_at", "created_at", "recorded_at", "observed_at",
        "requested_at", "fetched_at", "timestamp",
    )
    indexed = list(enumerate(records))
    indexed.sort(
        key=lambda pair: (
            next((pair[1][key] for key in fields if pair[1].get(key)), "\uffff"),
            pair[0],
        )
    )
    return [deepcopy(record) for _, record in indexed]


def render_flat(fixture: dict[str, Any]) -> dict[str, Any]:
    """Flat JSON arrays: no stance grouping or temporal partitioning."""
    validate_fixture(fixture)
    if fixture["role"] == "strategy_proposer":
        return {
            "case_id": fixture["case_id"],
            "role": fixture["role"],
            "state_assessment": deepcopy(fixture["state_assessment"]),
        }
    return {
        "case_id": fixture["case_id"],
        "role": fixture["role"],
        "hypothesis": deepcopy(fixture["hypothesis"]),
        **{name: _chronological(fixture[name]) for name in RW3_ARRAYS},
    }


def render_structured(fixture: dict[str, Any]) -> dict[str, Any]:
    """Decision-structured JSON with exactly the same underlying information."""
    validate_fixture(fixture)
    if fixture["role"] == "strategy_proposer":
        return {
            "case_id": fixture["case_id"],
            "role": fixture["role"],
            "state_assessment": deepcopy(fixture["state_assessment"]),
        }

    evidence: dict[str, list[dict[str, Any]]] = {
        "supporting": [], "challenging": [], "mentions": [], "unlinked_sources": [],
    }
    for link in _chronological(fixture["evidence_links"]):
        evidence[link["stance"]].append(link)
    evidence["unlinked_sources"] = _chronological(fixture["unlinked_sources"])

    temporal: dict[str, list[dict[str, Any]]] = {
        "pending_observations": [], "completed_observations": [],
        "missing_observations": [], "pending_tasks": [], "running_tasks": [],
        "completed_tasks": [], "pending_outcomes": [], "completed_outcomes": [],
        "missing_outcomes": [],
    }
    for item in _chronological(fixture["observations"]):
        temporal[f"{item['status']}_observations"].append(item)
    for item in _chronological(fixture["tasks"]):
        temporal[f"{item['status']}_tasks"].append(item)
    for item in _chronological(fixture["outcomes"]):
        temporal[f"{item['status']}_outcomes"].append(item)

    return {
        "case_id": fixture["case_id"],
        "role": fixture["role"],
        "hypothesis": deepcopy(fixture["hypothesis"]),
        "confidence_changes": _chronological(fixture["confidence_changes"]),
        "evidence": evidence,
        "provenance": {"lineage_pairs": _chronological(fixture["lineage_pairs"])},
        "temporal_state": temporal,
        "uncertainty": {"notes": _chronological(fixture["uncertainty_notes"])},
    }


def _record_multiset(value: dict[str, Any], structured: bool) -> Counter[str]:
    records: list[tuple[str, Any]] = []
    if "state_assessment" in value:
        records.append(("state_assessment", value["state_assessment"]))
    else:
        records.append(("hypothesis", value["hypothesis"]))
        records.extend(
            ("confidence_change", item)
            for item in value["confidence_changes"]
        )
        if structured:
            for stance in ("supporting", "challenging", "mentions"):
                records.extend(
                    ("evidence_link", item) for item in value["evidence"][stance]
                )
            records.extend(
                ("unlinked_source", item)
                for item in value["evidence"]["unlinked_sources"]
            )
            records.extend(
                ("lineage_pair", item)
                for item in value["provenance"]["lineage_pairs"]
            )
            for group in value["temporal_state"].values():
                for item in group:
                    if "observation_id" in item:
                        kind = "observation"
                    elif "task_type" in item:
                        kind = "task"
                    else:
                        kind = "outcome"
                    records.append((kind, item))
            records.extend(
                ("uncertainty_note", item) for item in value["uncertainty"]["notes"]
            )
        else:
            keys = {
                "evidence_links": "evidence_link",
                "unlinked_sources": "unlinked_source",
                "observations": "observation",
                "tasks": "task",
                "outcomes": "outcome",
                "lineage_pairs": "lineage_pair",
                "uncertainty_notes": "uncertainty_note",
            }
            for key, kind in keys.items():
                records.extend((kind, item) for item in value[key])
    return Counter(canonical_json([kind, item]) for kind, item in records)


def assert_representation_invariant_7(fixture: dict[str, Any]) -> None:
    flat = _record_multiset(render_flat(fixture), structured=False)
    structured = _record_multiset(render_structured(fixture), structured=True)
    if flat != structured:
        raise AssertionError(
            "Representation Invariant #7 failed: "
            f"missing={list((flat - structured).elements())}; "
            f"extra={list((structured - flat).elements())}"
        )


def validate_evidence_assessment(
    item: dict[str, Any],
    fixture: dict[str, Any],
    *,
    proposed_links: list[dict[str, Any]] | None = None,
) -> None:
    kind, reference = item.get("reference_kind"), item.get("reference")
    if kind not in REFERENCE_KINDS or not isinstance(reference, str):
        raise ValueError("invalid evidence assessment reference")
    valid = {
        "evidence_link": {
            link["evidence_link_id"] for link in fixture["evidence_links"]
        },
        "proposed_link": {link["link_ref"] for link in (proposed_links or [])},
        "source": {source["source_id"] for source in fixture["unlinked_sources"]},
        "observation": {
            item["observation_id"] for item in fixture["observations"]
        },
        "task": {task["id"] for task in fixture["tasks"]},
    }
    if reference not in valid[kind]:
        raise ValueError(
            "evidence assessment reference not present in fixture or batch"
        )
    for field, values in EVIDENCE_ASSESSMENT_ENUMS.items():
        if item.get(field) not in values:
            raise ValueError(f"invalid evidence assessment {field}")


def sample_fixtures() -> dict[str, dict[str, Any]]:
    """Three sample fixtures; expected answers are evaluator-only metadata."""
    rw3_03 = {
        "case_id": "RW3-03",
        "role": "update_thread",
        "hypothesis": {
            "id": "hyp-003",
            "statement": (
                "The intervention produces the specified effect under C1, C2, and C3."
            ),
            "scope": {"population": "population-P", "conditions": ["C1", "C2", "C3"]},
            "current_confidence": "low",
            "confidence_history": [],
        },
        "confidence_changes": [],
        "evidence_links": [],
        "unlinked_sources": [{
            "source_kind": "signal",
            "source_id": "sig-003",
            "status": "completed",
            "measurement": "Effect observed under C1, C2, and C3.",
            "precision": "within the predeclared measurement tolerance",
            "condition_coverage": ["C1", "C2", "C3"],
            "alternative_explanations": [
                {
                    "id": "alt-1", "description": "Alternative explanation A",
                    "status": "ruled_out", "test_reference": "test-003-A",
                },
                {
                    "id": "alt-2", "description": "Alternative explanation B",
                    "status": "ruled_out", "test_reference": "test-003-B",
                },
            ],
            "limitations": [],
        }],
        "observations": [],
        "tasks": [],
        "outcomes": [],
        "lineage_pairs": [],
        "uncertainty_notes": [],
        "evaluator_metadata": {
            "expected_decision": "increase",
            "expected_transition": ["low", "high"],
            "expected_new_link": {
                "source_kind": "signal", "source_id": "sig-003", "stance": "supports",
            },
        },
    }
    rw3_13 = {
        "case_id": "RW3-13",
        "role": "update_thread",
        "hypothesis": {
            "id": "hyp-013",
            "statement": "The intervention produces the specified effect under C1.",
            "scope": {"population": "population-P", "conditions": ["C1"]},
            "current_confidence": "moderate",
            "confidence_history": [],
        },
        "confidence_changes": [],
        "evidence_links": [],
        "unlinked_sources": [],
        "observations": [{
            "observation_id": "obs-013",
            "status": "pending",
            "expected_source_kind": "signal",
            "expected_source_id": None,
            "description": (
                "A measurement under C1 has been requested; no result is available."
            ),
            "result_available": False,
        }],
        "tasks": [{
            "id": "task-013", "task_type": "check_triggers",
            "status": "pending", "policy_version": 1,
        }],
        "outcomes": [],
        "lineage_pairs": [],
        "uncertainty_notes": [{
            "id": "uncertainty-013", "kind": "missing_information",
            "text": "The requested measurement result is not yet available.",
        }],
        "evaluator_metadata": {
            "expected_decision": "hold", "expected_confidence_change": False,
        },
    }
    assessment = {
        "objective": {
            "id": "00000000-0000-4000-8000-000000000101",
            "team_id": "00000000-0000-4000-8000-000000000100",
            "statement": "Monitor the configured source for new information.",
            "status": "active",
        },
        "team": {
            "id": "00000000-0000-4000-8000-000000000100",
            "domain": "research", "status": "active",
        },
        "policies": [{
            "id": "00000000-0000-4000-8000-000000000102",
            "team_id": "00000000-0000-4000-8000-000000000100",
            "version": 1,
            "rules_json": canonical_json({
                "sources": [{
                    "origin_url": "https://source.example.test/feed",
                    "source_type": "feed",
                }]
            }),
        }],
        "tasks": [{
            "id": "00000000-0000-4000-8000-000000000103",
            "task_type": "ingest_source", "status": "pending", "policy_version": 1,
        }],
        "events": [],
        "signals": [],
        "basis": {
            "objective_id": "00000000-0000-4000-8000-000000000101",
            "team_id": "00000000-0000-4000-8000-000000000100",
            "policy_ids": ["00000000-0000-4000-8000-000000000102"],
            "task_ids": ["00000000-0000-4000-8000-000000000103"],
            "event_ids": [], "signal_ids": [], "sha256": "a" * 64,
        },
        "created_at": "2026-11-17T00:00:00.000000Z",
    }
    sp01 = {
        "case_id": "SP-01", "role": "strategy_proposer", "hypothesis": None,
        "confidence_changes": [], "evidence_links": [], "unlinked_sources": [],
        "observations": [], "tasks": [], "outcomes": [], "lineage_pairs": [],
        "uncertainty_notes": [], "state_assessment": assessment,
        "evaluator_metadata": {
            "configured_source_count": 1,
            "state_assessment_source_identity_sufficient": True,
            "expected_duplicate_ingest_proposal": False,
        },
    }
    fixtures = {x["case_id"]: x for x in (rw3_03, rw3_13, sp01)}
    for fixture in fixtures.values():
        validate_fixture(fixture)
    return fixtures
