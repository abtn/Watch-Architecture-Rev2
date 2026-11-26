"""Add the canonical Team/Signal identity prerequisites for triage Tasks.

Revision ID: 0020_rw4_task_identity
Revises: 0019_rw1_world_memory
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Sequence
from uuid import UUID, uuid5

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

revision: str = "0020_rw4_task_identity"
down_revision: str | None = "0019_rw1_world_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TRIAGE_NAMESPACE = UUID("383bbdde-37be-4895-8fb7-1afa196b5cf7")
_TRIAGE_IDENTITY_VERSION = "triage_identity_v1"
_TRIAGE_TASK_TYPE = "triage_signal"
_REQUEST_EVENT_TYPE = "triage_signal_requested"
_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_REQUEST_EVENT_FIELDS = (
    "schema_version",
    "task_id",
    "team_id",
    "signal_id",
    "signal_snapshot_ref",
    "signal_content_hash",
    "as_of",
    "team_revision_watermark",
    "policy_version",
    "matcher_id",
    "matcher_version",
    "embedding_space_key",
    "chunking_version",
    "requested_by_principal",
    "request_fingerprint",
    "matching_pins",
    "matching_pins_hash",
)


def _canonical_task_id(team_id: UUID, signal_id: UUID) -> UUID:
    name = (
        f"{_TRIAGE_IDENTITY_VERSION}|{_TRIAGE_TASK_TYPE}|"
        f"team:{str(team_id).lower()}|signal:{str(signal_id).lower()}"
    )
    return uuid5(_TRIAGE_NAMESPACE, name)


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_request_event(
    connection: Connection,
    row: Mapping[str, object],
    event_counts: Counter[UUID],
    logical_identities: Counter[tuple[UUID, UUID]],
    violations: Counter[str],
) -> None:
    event_task_id = row["task_id"]
    event_counts[event_task_id] += 1
    task_exists = row["joined_task_id"] is not None
    task_is_triage = task_exists and row["joined_task_type"] == _TRIAGE_TASK_TYPE
    if not task_exists:
        violations["orphan_request_event"] += 1
    elif not task_is_triage:
        violations["request_event_on_non_triage_task"] += 1

    payload = row["payload"]
    if not isinstance(payload, dict):
        violations["payload_not_object"] += 1
        return

    missing = [field for field in _REQUEST_EVENT_FIELDS if field not in payload]
    if missing:
        violations["payload_missing_required_fields"] += 1

    for field in (
        "schema_version",
        "signal_snapshot_ref",
        "matcher_id",
        "matcher_version",
        "embedding_space_key",
        "chunking_version",
    ):
        if not _nonempty_string(payload.get(field)):
            violations[f"invalid_{field}"] += 1

    for field in ("signal_content_hash", "request_fingerprint", "matching_pins_hash"):
        value = payload.get(field)
        if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value):
            violations[f"invalid_{field}"] += 1

    if not isinstance(payload.get("requested_by_principal"), dict) or not payload.get(
        "requested_by_principal"
    ):
        violations["invalid_requested_by_principal"] += 1
    if not isinstance(payload.get("matching_pins"), dict) or not payload.get(
        "matching_pins"
    ):
        violations["invalid_matching_pins"] += 1

    watermark = payload.get("team_revision_watermark")
    if isinstance(watermark, bool) or not isinstance(watermark, int) or watermark < 0:
        violations["invalid_team_revision_watermark"] += 1
    policy_version = payload.get("policy_version")
    if (
        isinstance(policy_version, bool)
        or not isinstance(policy_version, int)
        or policy_version < 1
    ):
        violations["invalid_policy_version"] += 1

    as_of = payload.get("as_of")
    if not isinstance(as_of, str):
        violations["invalid_as_of"] += 1
    else:
        try:
            parsed_as_of = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
            if parsed_as_of.tzinfo is None:
                violations["invalid_as_of"] += 1
        except ValueError:
            violations["invalid_as_of"] += 1

    try:
        payload_task_id = UUID(str(payload.get("task_id")))
        payload_team_id = UUID(str(payload.get("team_id")))
        signal_id = UUID(str(payload.get("signal_id")))
    except (ValueError, TypeError, AttributeError):
        violations["invalid_identity_uuid"] += 1
        return

    if payload_task_id != event_task_id:
        violations["event_payload_task_mismatch"] += 1

    task_id = row["joined_task_id"]
    if not task_is_triage:
        return
    if row["joined_team_id"] != payload_team_id:
        violations["event_payload_team_mismatch"] += 1
    if row["joined_policy_version"] != payload.get("policy_version"):
        violations["event_policy_version_mismatch"] += 1
    if (
        "identity_version" in payload
        and payload["identity_version"] != _TRIAGE_IDENTITY_VERSION
    ):
        violations["invalid_identity_version"] += 1
    if task_id != _canonical_task_id(payload_team_id, signal_id):
        violations["noncanonical_task_id"] += 1

    logical_identities[(payload_team_id, signal_id)] += 1
    signal = connection.execute(
        sa.text(
            "SELECT domain, content_hash, snapshot_ref "
            "FROM signals WHERE id = :signal_id"
        ),
        {"signal_id": signal_id},
    ).mappings().one_or_none()
    if signal is None:
        violations["missing_signal"] += 1
        return
    if payload.get("signal_content_hash") != signal["content_hash"]:
        violations["signal_content_hash_mismatch"] += 1
    if payload.get("signal_snapshot_ref") != signal["snapshot_ref"]:
        violations["signal_snapshot_ref_mismatch"] += 1
    team_domain = connection.scalar(
        sa.text("SELECT domain FROM teams WHERE id = :team_id"),
        {"team_id": payload_team_id},
    )
    if team_domain is None or team_domain != signal["domain"]:
        violations["signal_team_domain_mismatch"] += 1


def _assert_no_historical_triage(connection: Connection) -> None:
    task_rows = connection.execute(
        sa.text(
            "SELECT id, team_id FROM tasks "
            "WHERE task_type = :task_type ORDER BY id"
        ),
        {"task_type": _TRIAGE_TASK_TYPE},
    ).mappings().all()
    event_rows = connection.execute(
        sa.text(
            """
            SELECT
                event.id AS event_id,
                event.task_id,
                event.payload,
                task.id AS joined_task_id,
                task.task_type AS joined_task_type,
                task.team_id AS joined_team_id,
                task.policy_version AS joined_policy_version
            FROM events AS event
            LEFT JOIN tasks AS task ON task.id = event.task_id
            WHERE event.type = :event_type
            ORDER BY event.id
            """
        ),
        {"event_type": _REQUEST_EVENT_TYPE},
    ).mappings().all()

    violations: Counter[str] = Counter()
    if task_rows:
        # The pre-migration Task schema has no persisted Signal/version fields.
        violations["legacy_task_identity_columns_unavailable"] += len(task_rows)
    event_counts: Counter[UUID] = Counter()
    logical_identities: Counter[tuple[UUID, UUID]] = Counter()
    for row in event_rows:
        _validate_request_event(
            connection, row, event_counts, logical_identities, violations
        )

    for task in task_rows:
        if not event_counts[task["id"]]:
            violations["triage_task_missing_request_event"] += 1
    for count in event_counts.values():
        if count > 1:
            violations["duplicate_request_events_for_task"] += count - 1
    for count in logical_identities.values():
        if count > 1:
            violations["duplicate_logical_identity_tuples"] += count - 1

    if task_rows or event_rows or violations:
        task_ids = [str(row["id"]) for row in task_rows]
        event_ids = [str(row["event_id"]) for row in event_rows]
        raise RuntimeError(
            "RW4 D2 migration refuses historical triage data; "
            f"triage_task_count={len(task_rows)}, "
            f"triage_task_ids={task_ids}, "
            f"request_event_count={len(event_rows)}, "
            f"request_event_ids={event_ids}, "
            f"violations={dict(sorted(violations.items()))}. "
            "No rows will be repaired, deleted, or backfilled."
        )


def _create_team_lock_trigger(connection: Connection) -> None:
    schema = connection.scalar(sa.text("SELECT current_schema()"))
    if not schema:
        raise RuntimeError("RW4 D2 migration requires a current schema")
    preparer = connection.dialect.identifier_preparer
    quoted_schema = preparer.quote(schema)
    function_name = f"{quoted_schema}.lock_team_for_triage_task_insert"

    connection.exec_driver_sql(
        f"""
        CREATE FUNCTION {function_name}()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        BEGIN
            IF NEW.task_type = '{_TRIAGE_TASK_TYPE}' THEN
                PERFORM 1
                FROM {quoted_schema}.teams
                WHERE id = NEW.team_id
                FOR NO KEY UPDATE;

                IF NOT FOUND THEN
                    RAISE EXCEPTION 'triage Task references a missing Team'
                        USING ERRCODE = '23503';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $function$
        """
    )
    connection.exec_driver_sql(
        f"REVOKE ALL ON FUNCTION {function_name}() FROM PUBLIC"
    )
    connection.exec_driver_sql(
        f"""
        CREATE TRIGGER trg_tasks_triage_team_lock
        BEFORE INSERT ON {quoted_schema}.tasks
        FOR EACH ROW
        EXECUTE FUNCTION {function_name}()
        """
    )

    identity_guard_name = f"{quoted_schema}.guard_triage_task_identity_update"
    connection.exec_driver_sql(
        f"""
        CREATE FUNCTION {identity_guard_name}()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $function$
        BEGIN
            IF OLD.task_type = '{_TRIAGE_TASK_TYPE}'
               OR NEW.task_type = '{_TRIAGE_TASK_TYPE}' THEN
                IF OLD.id IS DISTINCT FROM NEW.id
                   OR OLD.team_id IS DISTINCT FROM NEW.team_id
                   OR OLD.task_type IS DISTINCT FROM NEW.task_type
                   OR OLD.signal_id IS DISTINCT FROM NEW.signal_id
                   OR OLD.identity_version IS DISTINCT FROM NEW.identity_version
                THEN
                    RAISE EXCEPTION 'triage Task identity is immutable'
                        USING ERRCODE = '23514';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $function$
        """
    )
    connection.exec_driver_sql(
        f"REVOKE ALL ON FUNCTION {identity_guard_name}() FROM PUBLIC"
    )
    connection.exec_driver_sql(
        f"""
        CREATE TRIGGER trg_tasks_triage_identity_immutable
        BEFORE UPDATE ON {quoted_schema}.tasks
        FOR EACH ROW
        EXECUTE FUNCTION {identity_guard_name}()
        """
    )


def upgrade() -> None:
    connection = op.get_bind()

    # Fixed order closes the preflight/DDL race for all ordinary database writers.
    connection.execute(sa.text("LOCK TABLE tasks IN ACCESS EXCLUSIVE MODE"))
    connection.execute(sa.text("LOCK TABLE events IN ACCESS EXCLUSIVE MODE"))
    _assert_no_historical_triage(connection)

    op.add_column("tasks", sa.Column("signal_id", sa.Uuid(), nullable=True))
    op.add_column("tasks", sa.Column("identity_version", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_tasks_signal", "tasks", "signals", ["signal_id"], ["id"]
    )
    op.create_check_constraint(
        "ck_tasks_triage_identity",
        "tasks",
        "((task_type = 'triage_signal' AND signal_id IS NOT NULL "
        "AND identity_version IS NOT NULL "
        "AND identity_version = 'triage_identity_v1') "
        "OR (task_type <> 'triage_signal' AND signal_id IS NULL "
        "AND identity_version IS NULL))",
    )
    op.create_unique_constraint(
        "uq_tasks_team_signal_identity",
        "tasks",
        ["team_id", "signal_id", "identity_version"],
    )
    # This redundant key is the exact referenced key required by RW4-1's
    # Task-attribution composite FK. The three-column key remains the D2
    # logical-identity uniqueness contract.
    op.create_unique_constraint(
        "uq_tasks_id_team_signal_identity",
        "tasks",
        ["id", "team_id", "signal_id", "identity_version"],
    )
    op.create_index(
        "uq_events_triage_signal_requested_task",
        "events",
        ["task_id"],
        unique=True,
        postgresql_where=sa.text("type = 'triage_signal_requested'"),
    )
    _create_team_lock_trigger(connection)


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE tasks IN ACCESS EXCLUSIVE MODE"))
    connection.execute(sa.text("LOCK TABLE events IN ACCESS EXCLUSIVE MODE"))
    triage_task_count = connection.scalar(
        sa.text("SELECT count(*) FROM tasks WHERE task_type = :task_type"),
        {"task_type": _TRIAGE_TASK_TYPE},
    )
    request_event_count = connection.scalar(
        sa.text("SELECT count(*) FROM events WHERE type = :event_type"),
        {"event_type": _REQUEST_EVENT_TYPE},
    )
    if triage_task_count or request_event_count:
        raise RuntimeError(
            "RW4 D2 downgrade refuses to discard triage identity or request history; "
            f"triage_task_count={triage_task_count}, "
            f"request_event_count={request_event_count}"
        )

    schema = connection.scalar(sa.text("SELECT current_schema()"))
    if not schema:
        raise RuntimeError("RW4 D2 downgrade requires a current schema")
    quoted_schema = connection.dialect.identifier_preparer.quote(schema)
    function_name = f"{quoted_schema}.lock_team_for_triage_task_insert"

    connection.exec_driver_sql(
        f"DROP TRIGGER trg_tasks_triage_identity_immutable ON {quoted_schema}.tasks"
    )
    connection.exec_driver_sql(
        f"DROP TRIGGER trg_tasks_triage_team_lock ON {quoted_schema}.tasks"
    )
    connection.exec_driver_sql(
        f"DROP FUNCTION {quoted_schema}.guard_triage_task_identity_update()"
    )
    connection.exec_driver_sql(f"DROP FUNCTION {function_name}()")
    op.drop_index("uq_events_triage_signal_requested_task", table_name="events")
    op.drop_constraint(
        "uq_tasks_id_team_signal_identity", "tasks", type_="unique"
    )
    op.drop_constraint("uq_tasks_team_signal_identity", "tasks", type_="unique")
    op.drop_constraint("ck_tasks_triage_identity", "tasks", type_="check")
    op.drop_constraint("fk_tasks_signal", "tasks", type_="foreignkey")
    op.drop_column("tasks", "identity_version")
    op.drop_column("tasks", "signal_id")
