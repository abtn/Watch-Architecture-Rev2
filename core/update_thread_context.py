"""Deterministic, Thread-scoped Context for RW-3 update_thread Tasks."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.models import (
    Event,
    EvidenceLink,
    Hypothesis,
    Outcome,
    Signal,
    Task,
    Team,
    Thread,
)
from core.snapshot_store import SnapshotIntegrityError, SnapshotStore
from core.update_thread import (
    REQUEST_EVENT_TYPE,
    UpdateThreadTaskEnvelope,
    UpdateThreadTaskError,
    load_pinned_policy,
    validate_update_thread_task_request,
)

CONTEXT_EVENT_TYPE = "update_thread_context_assembled"
CONTEXT_SCHEMA_VERSION = "rw3-update-thread-context-v1"
MAX_HYPOTHESES = 8
MAX_EVIDENCE_LINKS = 8
MAX_SOURCE_SNAPSHOTS = 8
MAX_EVIDENCE_CHARACTERS = 8_000


class UpdateThreadContextError(ValueError):
    """The canonical update_thread Context is invalid or exceeds its bounds."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class AssembledUpdateThreadContext:
    task_id: UUID
    team_id: UUID
    thread_id: UUID
    attempt: int
    snapshot_ref: str
    content_hash: str
    event_id: UUID
    manifest: dict[str, Any]
    document: dict[str, Any]
    replayed: bool = False


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _is_exact_int(value: Any) -> bool:
    """JSON booleans must never satisfy an integer protocol field."""
    return isinstance(value, int) and not isinstance(value, bool)


def _utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise UpdateThreadContextError("world_memory_timestamp_not_timezone_aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


class UpdateThreadContextAssembler:
    """Assemble and persist one immutable Context for an admitted Task attempt.

    This component does not admit/finalize Tasks, invoke a provider, retrieve
    Team Experience, or write world-memory business rows.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        snapshot_store: SnapshotStore,
    ) -> None:
        self._session_factory = session_factory
        self._snapshot_store = snapshot_store

    def assemble(
        self, task_id: UUID, attempt: int
    ) -> AssembledUpdateThreadContext:
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
            raise UpdateThreadContextError("update_thread_attempt_invalid")

        with self._session_factory.begin() as session:
            task = session.scalar(
                select(Task).where(Task.id == task_id).with_for_update()
            )
            if (
                task is None
                or task.status != "running"
                or task.attempt_count != attempt
            ):
                raise UpdateThreadContextError("update_thread_task_attempt_not_current")

            try:
                request = validate_update_thread_task_request(session, task)
            except UpdateThreadTaskError as error:
                raise UpdateThreadContextError(error.reason) from error

            team = session.scalar(
                select(Team).where(Team.id == task.team_id).with_for_update()
            )
            thread = session.scalar(
                select(Thread)
                .where(
                    Thread.id == request.thread_id,
                    Thread.team_id == task.team_id,
                )
                .with_for_update()
            )
            if team is None or team.status != "active":
                raise UpdateThreadContextError("update_thread_team_not_active")
            if (
                thread is None
                or thread.status == "resolved"
            ):
                raise UpdateThreadContextError("update_thread_target_not_available")

            try:
                policy = load_pinned_policy(
                    session, task.team_id, task.policy_version
                )
            except UpdateThreadTaskError as error:
                raise UpdateThreadContextError(error.reason) from error

            prior = self._prior_context(session, task, request, attempt)
            if prior is not None:
                return prior

            hypotheses = list(
                session.scalars(
                    select(Hypothesis)
                    .where(
                        Hypothesis.team_id == task.team_id,
                        Hypothesis.thread_id == thread.id,
                        Hypothesis.status == "active",
                    )
                    .order_by(Hypothesis.created_at, Hypothesis.id)
                    .limit(MAX_HYPOTHESES + 1)
                    .with_for_update()
                )
            )
            if len(hypotheses) > MAX_HYPOTHESES:
                raise UpdateThreadContextError(
                    "update_thread_hypothesis_bound_exceeded"
                )

            hypothesis_ids = [item.id for item in hypotheses]
            links: list[EvidenceLink] = []
            if hypothesis_ids:
                links = list(
                    session.scalars(
                        select(EvidenceLink)
                        .where(
                            EvidenceLink.team_id == task.team_id,
                            EvidenceLink.subject_kind == "hypothesis",
                            EvidenceLink.hypothesis_id.in_(hypothesis_ids),
                        )
                        .order_by(
                            EvidenceLink.hypothesis_id,
                            EvidenceLink.created_at,
                            EvidenceLink.id,
                        )
                        .limit(MAX_EVIDENCE_LINKS + 1)
                        .with_for_update()
                    )
                )
            if len(links) > MAX_EVIDENCE_LINKS:
                raise UpdateThreadContextError(
                    "update_thread_evidence_link_bound_exceeded"
                )

            source_snapshots: dict[str, dict[str, str]] = {}
            source_snapshot_texts: dict[str, str] = {}
            evidence_documents: list[dict[str, Any]] = []
            evidence_characters = 0

            active_hypothesis_ids = set(hypothesis_ids)
            for link in links:
                if link.hypothesis_id not in active_hypothesis_ids:
                    raise UpdateThreadContextError(
                        "update_thread_evidence_hypothesis_mismatch"
                    )
                reference, expected_hash = self._source_snapshot(
                    session, team, link
                )
                if (
                    link.snapshot_ref != reference
                    or link.snapshot_hash != expected_hash
                ):
                    raise UpdateThreadContextError(
                        "update_thread_evidence_snapshot_stale"
                    )

                snapshot = source_snapshots.get(reference)
                if snapshot is None:
                    try:
                        raw = self._snapshot_store.read(reference)
                    except SnapshotIntegrityError as error:
                        raise UpdateThreadContextError(
                            "update_thread_source_snapshot_integrity_failure"
                        ) from error
                    actual_hash = "sha256:" + hashlib.sha256(raw).hexdigest()
                    if actual_hash != expected_hash:
                        raise UpdateThreadContextError(
                            "update_thread_source_snapshot_hash_mismatch"
                        )
                    try:
                        source_text = raw.decode("utf-8")
                    except UnicodeDecodeError as error:
                        raise UpdateThreadContextError(
                            "update_thread_source_snapshot_not_utf8"
                        ) from error
                    source_snapshot_texts[reference] = source_text
                    snapshot = {
                        "snapshot_ref": reference,
                        "snapshot_hash": expected_hash,
                    }
                    source_snapshots[reference] = snapshot

                source_text = source_snapshot_texts[reference]
                quote = link.quote_text
                if (
                    (quote is None and (
                        link.quote_start is not None or link.quote_end is not None
                    ))
                    or (
                        quote is not None
                        and (
                            link.quote_start is None or link.quote_end is None
                        )
                    )
                ):
                    raise UpdateThreadContextError(
                        "update_thread_evidence_quote_shape_invalid"
                    )
                if quote is not None and (
                    not quote
                    or link.quote_start is None
                    or link.quote_end is None
                    or link.quote_start < 0
                    or link.quote_end <= link.quote_start
                    or link.quote_end > len(source_text)
                    or source_text[link.quote_start:link.quote_end] != quote
                ):
                    raise UpdateThreadContextError(
                        "update_thread_evidence_quote_mismatch"
                    )
                if quote is not None:
                    evidence_characters += len(quote)
                    if evidence_characters > MAX_EVIDENCE_CHARACTERS:
                        raise UpdateThreadContextError(
                            "update_thread_evidence_character_bound_exceeded"
                        )

                evidence_documents.append(
                    {
                        "id": str(link.id),
                        "hypothesis_id": str(link.hypothesis_id),
                        "source_kind": link.source_kind,
                        "signal_id": str(link.signal_id) if link.signal_id else None,
                        "outcome_id": str(link.outcome_id) if link.outcome_id else None,
                        "stance": link.stance,
                        "snapshot_ref": reference,
                        "snapshot_hash": expected_hash,
                        "quote_text": quote,
                        "quote_start": link.quote_start,
                        "quote_end": link.quote_end,
                        "created_at": _utc(link.created_at),
                    }
                )

            if len(source_snapshots) > MAX_SOURCE_SNAPSHOTS:
                raise UpdateThreadContextError("update_thread_snapshot_bound_exceeded")

            ordered_snapshots = [
                source_snapshots[reference]
                for reference in sorted(source_snapshots)
            ]
            request_event = session.scalar(
                select(Event).where(
                    Event.task_id == task.id,
                    Event.type == REQUEST_EVENT_TYPE,
                )
            )
            if request_event is None:
                raise UpdateThreadContextError("update_thread_request_event_missing")
            assembled_at = datetime.now(timezone.utc)
            manifest: dict[str, Any] = {
                "schema_version": CONTEXT_SCHEMA_VERSION,
                "task_id": str(task.id),
                "team_id": str(task.team_id),
                "thread_id": str(thread.id),
                "attempt": attempt,
                "policy_version": task.policy_version,
                "request_event_id": str(request_event.id),
                "assembled_at": _utc(assembled_at),
                "hypothesis_ids": [str(item.id) for item in hypotheses],
                "evidence_link_ids": [item["id"] for item in evidence_documents],
                "source_snapshot_refs": sorted(source_snapshots),
                "source_snapshot_hashes": {
                    reference: source_snapshots[reference]["snapshot_hash"]
                    for reference in sorted(source_snapshots)
                },
                "evidence_characters": evidence_characters,
            }
            document: dict[str, Any] = {
                "schema_version": CONTEXT_SCHEMA_VERSION,
                "task": {
                    "id": str(task.id),
                    "type": task.task_type,
                    "team_id": str(task.team_id),
                    "thread_id": str(thread.id),
                    "attempt": attempt,
                    "policy_version": task.policy_version,
                },
                "team": {"id": str(team.id), "domain": team.domain},
                "thread": {
                    "id": str(thread.id),
                    "domain": thread.domain,
                    "title": thread.title,
                    "status": thread.status,
                    "created_at": _utc(thread.created_at),
                    "last_updated_at": _utc(thread.last_updated_at),
                },
                "policy": {
                    "version": policy.version,
                    "schema_version": policy.schema_version,
                    "rules": policy.rules,
                },
                "hypotheses": [
                    {
                        "id": str(item.id),
                        "statement": item.statement,
                        "status": item.status,
                        "confidence": item.confidence,
                        "created_at": _utc(item.created_at),
                        "last_touched_at": _utc(item.last_touched_at),
                    }
                    for item in hypotheses
                ],
                "evidence_links": evidence_documents,
                "source_snapshots": ordered_snapshots,
                "manifest": manifest,
            }
            snapshot_bytes = _canonical_json(document)
            content_hash = "sha256:" + hashlib.sha256(snapshot_bytes).hexdigest()
            snapshot_ref, stored_hash = self._snapshot_store.put(snapshot_bytes)
            if stored_hash != content_hash:
                raise UpdateThreadContextError(
                    "update_thread_context_snapshot_hash_mismatch"
                )

            event = Event(
                id=uuid4(),
                task_id=task.id,
                type=CONTEXT_EVENT_TYPE,
                payload={
                    "schema_version": 1,
                    "task_id": str(task.id),
                    "team_id": str(task.team_id),
                    "thread_id": str(thread.id),
                    "attempt": attempt,
                    "policy_version": task.policy_version,
                    "snapshot_ref": snapshot_ref,
                    "content_hash": content_hash,
                    "manifest": manifest,
                },
                created_at=assembled_at,
            )
            session.add(event)
            session.flush()
            return AssembledUpdateThreadContext(
                task_id=task.id,
                team_id=task.team_id,
                thread_id=thread.id,
                attempt=attempt,
                snapshot_ref=snapshot_ref,
                content_hash=content_hash,
                event_id=event.id,
                manifest=manifest,
                document=document,
            )

    def verify_context(
        self, context: AssembledUpdateThreadContext
    ) -> AssembledUpdateThreadContext:
        """Reload and verify the exact durable Context before provider use."""
        with self._session_factory.begin() as session:
            task = session.scalar(
                select(Task)
                .where(Task.id == getattr(context, "task_id", None))
                .with_for_update()
            )
            return self.verify_context_in_session(session, task, context)

    def verify_context_in_session(
        self,
        session: Session,
        task: Task | None,
        context: AssembledUpdateThreadContext,
    ) -> AssembledUpdateThreadContext:
        """Verify Context identity and bytes inside an existing transaction.

        The returned object is reconstructed from the content-addressed
        Snapshot, not from the caller's mutable in-memory dictionaries.
        """
        if (
            not isinstance(context, AssembledUpdateThreadContext)
            or isinstance(context.attempt, bool)
            or not isinstance(context.attempt, int)
            or context.attempt < 1
        ):
            raise UpdateThreadContextError("update_thread_context_identity_invalid")
        if (
            task is None
            or task.id != context.task_id
            or task.status not in {"running", "done"}
            or task.attempt_count != context.attempt
        ):
            raise UpdateThreadContextError(
                "update_thread_task_attempt_not_current"
            )
        try:
            request = validate_update_thread_task_request(session, task)
        except UpdateThreadTaskError as error:
            raise UpdateThreadContextError(error.reason) from error

        verified = self._prior_context(
            session, task, request, context.attempt
        )
        if verified is None:
            raise UpdateThreadContextError(
                "update_thread_context_event_missing"
            )
        if (
            verified.event_id != context.event_id
            or verified.snapshot_ref != context.snapshot_ref
            or verified.content_hash != context.content_hash
            or verified.task_id != context.task_id
            or verified.team_id != context.team_id
            or verified.thread_id != context.thread_id
            or verified.attempt != context.attempt
        ):
            raise UpdateThreadContextError(
                "update_thread_context_identity_mismatch"
            )
        return verified

    @staticmethod
    def _source_snapshot(
        session: Session, team: Team, link: EvidenceLink
    ) -> tuple[str, str]:
        if link.source_kind == "signal":
            if link.signal_id is None or link.outcome_id is not None:
                raise UpdateThreadContextError("update_thread_signal_reference_invalid")
            source = session.get(Signal, link.signal_id)
            if source is None or source.domain != team.domain:
                raise UpdateThreadContextError("update_thread_signal_team_mismatch")
            return source.snapshot_ref, source.content_hash

        if link.source_kind == "outcome":
            if link.outcome_id is None or link.signal_id is not None:
                raise UpdateThreadContextError(
                    "update_thread_outcome_reference_invalid"
                )
            outcome_source = session.get(Outcome, link.outcome_id)
            if (
                outcome_source is None
                or outcome_source.team_id != team.id
                or outcome_source.observation_snapshot_ref is None
                or outcome_source.observation_hash is None
            ):
                raise UpdateThreadContextError("update_thread_outcome_team_mismatch")
            return (
                outcome_source.observation_snapshot_ref,
                outcome_source.observation_hash,
            )

        raise UpdateThreadContextError("update_thread_source_kind_invalid")

    def _prior_context(
        self,
        session: Session,
        task: Task,
        request: UpdateThreadTaskEnvelope,
        attempt: int
    ) -> AssembledUpdateThreadContext | None:
        events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task.id,
                    Event.type == CONTEXT_EVENT_TYPE,
                )
            )
        )
        for event in events:
            if (
                not isinstance(event.payload, dict)
                or not _is_exact_int(event.payload.get("attempt"))
                or not 1 <= event.payload["attempt"] <= 3
            ):
                raise UpdateThreadContextError("update_thread_context_event_corrupt")
        if any(event.payload["attempt"] > attempt for event in events):
            raise UpdateThreadContextError(
                "update_thread_context_event_future_attempt"
            )
        matching = [event for event in events if event.payload["attempt"] == attempt]
        if len(matching) > 1:
            raise UpdateThreadContextError("update_thread_context_event_duplicate")
        if not matching:
            return None

        event = matching[0]
        payload = event.payload
        expected_keys = {
            "schema_version",
            "task_id",
            "team_id",
            "thread_id",
            "attempt",
            "policy_version",
            "snapshot_ref",
            "content_hash",
            "manifest",
        }
        if (
            set(payload) != expected_keys
            or not _is_exact_int(payload.get("schema_version"))
            or payload.get("schema_version") != 1
            or payload.get("task_id") != str(task.id)
            or payload.get("team_id") != str(task.team_id)
            or payload.get("thread_id") != str(request.thread_id)
            or not _is_exact_int(payload.get("attempt"))
            or payload.get("attempt") != attempt
            or not _is_exact_int(payload.get("policy_version"))
            or payload.get("policy_version") != task.policy_version
            or not isinstance(payload.get("snapshot_ref"), str)
            or not isinstance(payload.get("content_hash"), str)
            or not isinstance(payload.get("manifest"), dict)
        ):
            raise UpdateThreadContextError("update_thread_context_event_corrupt")

        try:
            snapshot_bytes = self._snapshot_store.read(payload["snapshot_ref"])
        except SnapshotIntegrityError as error:
            raise UpdateThreadContextError(
                "update_thread_context_snapshot_integrity_failure"
            ) from error
        actual_hash = "sha256:" + hashlib.sha256(snapshot_bytes).hexdigest()
        if actual_hash != payload["content_hash"]:
            raise UpdateThreadContextError(
                "update_thread_context_snapshot_hash_mismatch"
            )
        try:
            document = json.loads(snapshot_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise UpdateThreadContextError(
                "update_thread_context_document_corrupt"
            ) from error
        request_event_id = session.scalar(
            select(Event.id).where(
                Event.task_id == task.id,
                Event.type == REQUEST_EVENT_TYPE,
            )
        )
        task_document = (
            document.get("task") if isinstance(document, dict) else None
        )
        team_document = (
            document.get("team") if isinstance(document, dict) else None
        )
        thread_document = (
            document.get("thread") if isinstance(document, dict) else None
        )
        policy_document = (
            document.get("policy") if isinstance(document, dict) else None
        )
        snapshot_manifest = (
            document.get("manifest") if isinstance(document, dict) else None
        )
        try:
            manifest_matches = (
                isinstance(snapshot_manifest, dict)
                and _canonical_json(snapshot_manifest)
                == _canonical_json(payload["manifest"])
            )
        except (TypeError, ValueError) as error:
            raise UpdateThreadContextError(
                "update_thread_context_manifest_corrupt"
            ) from error
        if (
            not isinstance(task_document, dict)
            or not isinstance(team_document, dict)
            or not isinstance(thread_document, dict)
            or not isinstance(policy_document, dict)
            or not isinstance(document, dict)
            or set(document)
            != {
                "schema_version",
                "task",
                "team",
                "thread",
                "policy",
                "hypotheses",
                "evidence_links",
                "source_snapshots",
                "manifest",
            }
            or document.get("schema_version") != CONTEXT_SCHEMA_VERSION
            or not manifest_matches
            or set(payload["manifest"])
            != {
                "schema_version",
                "task_id",
                "team_id",
                "thread_id",
                "attempt",
                "policy_version",
                "request_event_id",
                "assembled_at",
                "hypothesis_ids",
                "evidence_link_ids",
                "source_snapshot_refs",
                "source_snapshot_hashes",
                "evidence_characters",
            }
            or payload["manifest"].get("schema_version") != CONTEXT_SCHEMA_VERSION
            or payload["manifest"].get("task_id") != str(task.id)
            or payload["manifest"].get("team_id") != str(task.team_id)
            or payload["manifest"].get("thread_id") != str(request.thread_id)
            or not _is_exact_int(payload["manifest"].get("attempt"))
            or payload["manifest"].get("attempt") != attempt
            or not _is_exact_int(payload["manifest"].get("policy_version"))
            or payload["manifest"].get("policy_version") != task.policy_version
            or payload["manifest"].get("request_event_id") != str(request_event_id)
            or not isinstance(payload["manifest"].get("assembled_at"), str)
            or not isinstance(payload["manifest"].get("hypothesis_ids"), list)
            or not all(
                isinstance(value, str)
                for value in payload["manifest"]["hypothesis_ids"]
            )
            or not isinstance(payload["manifest"].get("evidence_link_ids"), list)
            or not all(
                isinstance(value, str)
                for value in payload["manifest"]["evidence_link_ids"]
            )
            or not isinstance(payload["manifest"].get("source_snapshot_refs"), list)
            or not all(
                isinstance(value, str)
                for value in payload["manifest"]["source_snapshot_refs"]
            )
            or not isinstance(payload["manifest"].get("source_snapshot_hashes"), dict)
            or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in payload["manifest"]["source_snapshot_hashes"].items()
            )
            or not _is_exact_int(payload["manifest"].get("evidence_characters"))
            or payload["manifest"]["evidence_characters"] < 0
            or task_document.get("id") != str(task.id)
            or task_document.get("team_id") != str(task.team_id)
            or task_document.get("thread_id") != str(request.thread_id)
            or not _is_exact_int(task_document.get("attempt"))
            or task_document.get("attempt") != attempt
            or not _is_exact_int(task_document.get("policy_version"))
            or task_document.get("policy_version") != task.policy_version
            or team_document.get("id") != str(task.team_id)
            or thread_document.get("id") != str(request.thread_id)
            or not _is_exact_int(policy_document.get("version"))
            or policy_document.get("version") != task.policy_version
            or not _is_exact_int(policy_document.get("schema_version"))
        ):
            raise UpdateThreadContextError("update_thread_context_manifest_corrupt")
        return AssembledUpdateThreadContext(
            task_id=task.id,
            team_id=task.team_id,
            thread_id=request.thread_id,
            attempt=attempt,
            snapshot_ref=payload["snapshot_ref"],
            content_hash=payload["content_hash"],
            event_id=event.id,
            manifest=payload["manifest"],
            document=document,
            replayed=True,
        )
