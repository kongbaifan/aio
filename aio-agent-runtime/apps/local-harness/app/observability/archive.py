"""Audit archive relay: at-least-once delivery of PG audit facts to an external archive.

PG is authoritative. An archive outage only grows a backlog (``AUDIT_ARCHIVE_BACKLOG``); it never
blocks a business request, unlike a PG audit write failure (``AUDIT_SINK_UNAVAILABLE``).
Each delivery is claim (short tx, lease) -> send (no tx, no connection) -> finish (short tx, fenced).
No business row is locked: the claim locks only outbox rows, so it shares no prefix with Run/budget locks.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import logging
import re
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

from pydantic import Field, ValidationError
from sqlalchemy import and_, func, or_, select, text, update

from ..db import schema as s
from . import audit
from . import redaction as m
from . import scrub

logger = logging.getLogger(__name__)

# Stable codes only: a sink's response body or exception text is never stored or logged.
DeliveryCode = Literal["ARCHIVE_UNAVAILABLE", "ARCHIVE_REJECTED", "ARCHIVE_TIMEOUT", "ARCHIVE_DELIVERY_FAILED"]
ERROR_CODES = frozenset({
    "ARCHIVE_UNAVAILABLE", "ARCHIVE_REJECTED", "ARCHIVE_TIMEOUT", "ARCHIVE_DELIVERY_FAILED",
    "ARCHIVE_RECORD_INVALID",
})
BASE_BACKOFF_SECONDS, MAX_BACKOFF_SECONDS = 5, 900
_OWNER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")


class ArchiveDeliveryError(Exception):
    """Raised by a sink. Only ``code`` survives; the message is never persisted."""

    def __init__(self, code: DeliveryCode):
        super().__init__(code)
        self.code = code if code in ERROR_CODES else "ARCHIVE_DELIVERY_FAILED"


class ArchiveRecord(m.ClosedMetadata):
    """Exactly the audit row's typed columns plus its closed metadata; no free text exists to copy."""

    org_id: UUID
    audit_id: UUID
    actor_id: UUID
    service_actor_id: str | None
    run_id: UUID | None
    action: str
    resource_id: UUID | None
    resource_kind: m.ResourceKind | None
    outcome: str
    decision: Literal["allow", "deny", "approval_required"] | None
    reason_code: m.ReasonCode | None
    policy_revision: m.Revision | None
    subject_revision: m.Revision | None
    risk_class: Literal["R0", "R1", "R2"] | None
    trace_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")] | None
    metadata_schema: str
    metadata: dict[str, Any]
    created_at: datetime

    @property
    def idempotency_key(self) -> str:
        # Stable across retries, lease takeovers and relay restarts; a sink must dedupe on it.
        return f"{self.org_id}:{self.audit_id}"

    @classmethod
    def from_row(cls, row) -> "ArchiveRecord":
        contract = audit.CONTRACTS.get(row["action"])
        if contract is None or row["metadata_schema"] != row["action"] + ":v1" or row["outcome"] not in contract.outcomes:
            raise ValueError("Not a structured audit fact")
        metadata = contract.metadata.model_validate(row["metadata"]).model_dump(mode="json")
        values = {k: row[k] for k in cls.model_fields if k not in {"audit_id", "metadata"}}
        return cls(audit_id=row["id"], metadata=metadata, **values)


class ArchiveSink(Protocol):
    async def deliver(self, record: ArchiveRecord) -> None:
        """Store the record idempotently by ``record.idempotency_key`` or raise ArchiveDeliveryError."""


def backoff_seconds(attempts: int) -> int:
    """Delay after the ``attempts``-th failed delivery: 5, 10, 20 ... capped at 15 minutes."""
    return min(MAX_BACKOFF_SECONDS, BASE_BACKOFF_SECONDS * 2 ** max(0, min(attempts, 16) - 1))


@dataclass(frozen=True)
class Claim:
    outbox_id: UUID
    record: ArchiveRecord | None  # None: the pointed-to fact cannot be projected to a closed record


class AuditRelay:
    def __init__(
        self, db, org_id: UUID, owner: str, sink: ArchiveSink, *, batch_size: int = 50, lease_seconds: int = 60,
        timeout_seconds: float = 10, backlog_alert_seconds: int = 300,
    ):
        if not isinstance(org_id, UUID) or not _OWNER.fullmatch(owner or ""):
            raise ValueError("A verified organization and bounded relay identity are required")
        if not (1 <= batch_size <= 500 and 0 < timeout_seconds < lease_seconds <= 3600 and backlog_alert_seconds >= 0):
            # A lease shorter than the send timeout would let a second relay take over mid-delivery.
            raise ValueError("Relay bounds are invalid")
        self.db, self.org_id, self.owner, self.sink = db, org_id, owner, sink
        self.batch_size, self.lease_seconds, self.timeout_seconds = batch_size, lease_seconds, timeout_seconds
        self.backlog_alert_seconds = backlog_alert_seconds

    def _scope(self):
        return self.db.scoped(self.org_id, UUID(int=0))

    def due(self):
        """The claim query; its ORDER BY matches ix_aio_outbox_audit_pending so no sort is needed."""
        o = s.outbox
        now = text("clock_timestamp()")
        return (
            select(o.c.id, o.c.aggregate_id)
            .where(
                o.c.org_id == self.org_id, o.c.kind == audit.ARCHIVE_KIND, o.c.delivered_at.is_(None),
                o.c.next_attempt_at <= now, or_(o.c.leased_until.is_(None), o.c.leased_until < now),
            )
            .order_by(o.c.next_attempt_at, o.c.id)
            .limit(self.batch_size)
            .with_for_update(of=o, skip_locked=True)
        )

    def claim(self, c) -> list[Claim]:
        """Lease due rows on ``c``. Locks outbox rows only (SKIP LOCKED), never a business row."""
        o = s.outbox
        ids = c.execute(self.due()).all()
        if not ids:
            return []
        c.execute(
            update(o).where(o.c.org_id == self.org_id, o.c.id.in_([row.id for row in ids])).values(
                lease_owner=self.owner,
                leased_until=text(f"clock_timestamp() + interval '{int(self.lease_seconds)} seconds'"),
            )
        )
        facts = {
            row["id"]: row for row in c.execute(
                select(s.audit).where(s.audit.c.org_id == self.org_id, s.audit.c.id.in_([r.aggregate_id for r in ids]))
            ).mappings()
        }
        claims = []
        for row in ids:
            try:
                record = ArchiveRecord.from_row(facts[row.aggregate_id])
                scrub.assert_clean(record.model_dump_json())  # never ship known material off-host
            except (KeyError, ValueError, ValidationError, scrub.SensitiveLeak):
                record = None
            claims.append(Claim(row.id, record))
        return claims

    def _claim(self) -> list[Claim]:
        with self._scope() as c:
            return self.claim(c)

    def finish(self, outbox_id: UUID, error: str | None) -> bool:
        """Record one outcome. Fenced by the lease: a relay that lost its lease changes nothing."""
        o = s.outbox
        mine = and_(o.c.org_id == self.org_id, o.c.id == outbox_id, o.c.lease_owner == self.owner,
                    o.c.delivered_at.is_(None))
        with self._scope() as c:
            attempts = c.execute(select(o.c.attempts).where(mine).with_for_update()).scalar()
            if attempts is None:
                return False
            if error is None:
                values = dict(delivered_at=text("clock_timestamp()"), last_error_code=None)
            else:
                values = dict(
                    last_error_code=error if error in ERROR_CODES else "ARCHIVE_DELIVERY_FAILED",
                    next_attempt_at=text(f"clock_timestamp() + interval '{backoff_seconds(attempts + 1)} seconds'"),
                )
            c.execute(update(o).where(mine).values(attempts=attempts + 1, lease_owner=None, leased_until=None, **values))
            return True

    async def run_once(self) -> dict:
        claims = await asyncio.to_thread(self._claim)
        result = {"claimed": len(claims), "delivered": 0, "failed": 0, "lost_lease": 0}
        for claim in claims:
            # No transaction or pooled connection is held while the sink is called.
            error = "ARCHIVE_RECORD_INVALID" if claim.record is None else None
            if error is None:
                try:
                    await asyncio.wait_for(self.sink.deliver(claim.record), self.timeout_seconds)
                except TimeoutError:
                    error = "ARCHIVE_TIMEOUT"
                except ArchiveDeliveryError as exc:
                    error = exc.code
                except Exception:
                    error = "ARCHIVE_DELIVERY_FAILED"
            if not await asyncio.to_thread(self.finish, claim.outbox_id, error):
                result["lost_lease"] += 1
            else:
                result["delivered" if error is None else "failed"] += 1
        return result

    def backlog(self) -> dict:
        """Operational counts only (no fact content); for metrics/alerts, never a business response."""
        o = s.outbox
        pending = and_(o.c.org_id == self.org_id, o.c.kind == audit.ARCHIVE_KIND, o.c.delivered_at.is_(None))
        with self._scope() as c:
            row = c.execute(
                select(
                    func.count(),
                    func.count().filter(o.c.attempts > 0),
                    func.date_part("epoch", func.clock_timestamp() - func.min(o.c.created_at)),
                ).where(pending)
            ).one()
            errors = dict(c.execute(
                select(o.c.last_error_code, func.count()).where(pending, o.c.last_error_code.is_not(None))
                .group_by(o.c.last_error_code)
            ).all())
        oldest = int(row[2]) if row[2] is not None else 0
        alert = row[0] > 0 and oldest >= self.backlog_alert_seconds
        return {
            "state": "backlog" if alert else "ok", "code": "AUDIT_ARCHIVE_BACKLOG" if alert else None,
            "pending": row[0], "retrying": row[1], "oldest_pending_seconds": oldest, "errors": errors,
        }

    async def serve(self, stopping: asyncio.Event, *, poll_seconds: float = 2) -> None:
        while not stopping.is_set():
            drained = False
            try:
                result = await self.run_once()
                drained = result["claimed"] < self.batch_size
                status = await asyncio.to_thread(self.backlog)
                if status["code"]:
                    logger.warning(
                        "%s org=%s pending=%d retrying=%d oldest_pending_seconds=%d",
                        status["code"], self.org_id, status["pending"], status["retrying"],
                        status["oldest_pending_seconds"],
                    )
            except Exception:
                # PG stays authoritative and leases expire; never log a DB or sink message body.
                logger.warning("Audit archive relay iteration failed; pending facts are retained")
                drained = True
            if drained:
                try:
                    await asyncio.wait_for(stopping.wait(), timeout=poll_seconds)
                except TimeoutError:
                    pass
