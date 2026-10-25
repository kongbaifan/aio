"""Durable embedding intents, budget reservations and append-only receipts for ingestion and retrieval."""

import asyncio
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..platform_errors import PlatformError
from ..billing import budgets as shared_budgets
from ..policy.repository import current_facts, db_now
from ..runtime.actions import canonical_digest
from ..db import schema as s
from ..observability import audit
from .catalog import current_embedding, current_knowledge, current_version


def run_totals(c, org, run_id):
    rows = (
        c.execute(
            select(s.embedding_calls).where(s.embedding_calls.c.org_id == org, s.embedding_calls.c.run_id == run_id)
        )
        .mappings()
        .all()
    )
    charged = sum((r["actual_charge"] or Decimal(0) for r in rows), Decimal(0))
    unknown = [r for r in rows if r["actual_charge"] is None and r["state"] in {"started", "unknown", "succeeded"}]
    held = sum((r["max_charge"] for r in unknown), Decimal(0))
    committed = sum(
        (
            r["actual_charge"] if r["actual_charge"] is not None else r["max_charge"]
            for r in rows
            if r["state"] != "not_sent"
        ),
        Decimal(0),
    )
    return committed, charged, held, len(unknown)


class EmbeddingStore:
    def __init__(self, database, settings, jobs, execution):
        self.db, self.settings, self.jobs, self.execution = database, settings, jobs, execution

    @staticmethod
    def _reserve(c, p, model, digest, *, job=None, query=None, batch=0, run=None):
        context = s.embedding_calls.c.job_id == job["id"] if job else s.embedding_calls.c.query_id == query["id"]
        existing = (
            c.execute(
                select(s.embedding_calls).where(
                    s.embedding_calls.c.org_id == p.org_id, context, s.embedding_calls.c.batch == batch
                )
            )
            .mappings()
            .first()
        )
        generation = job["generation"] if job else query.get("generation") or 1
        if existing:
            pools = shared_budgets.lock_subject(c, p.org_id, **shared_budgets.embedding_subject(existing))
            if existing["request_digest"] != digest or existing["model_id"] != model["id"]:
                raise PlatformError("EMBEDDING_CALL_CONFLICT", "Embedding intention changed", 409)
            if existing["state"] == "not_sent":
                budget = (
                    c.execute(
                        select(s.budgets)
                        .where(s.budgets.c.org_id == p.org_id, s.budgets.c.id == existing["budget_id"])
                        .with_for_update()
                    )
                    .mappings()
                    .one()
                )
                if existing["standalone_reserved"]:
                    shared_budgets.check(pools, existing["max_charge"])
                    if budget["consumed"] + budget["reserved"] + existing["max_charge"] > budget["hard_limit"]:
                        raise PlatformError("QUOTA_EXCEEDED", "Insufficient embedding budget", 429)
                    shared_budgets.change(c, p.org_id, embedding_call_id=existing["id"], add=existing["max_charge"])
                    c.execute(
                        update(s.budgets)
                        .where(s.budgets.c.id == budget["id"])
                        .values(reserved=s.budgets.c.reserved + existing["max_charge"])
                    )
                c.execute(
                    update(s.embedding_calls)
                    .where(s.embedding_calls.c.id == existing["id"])
                    .values(state="prepared", actual_charge=None, generation=generation)
                )
                return {**dict(existing), "state": "prepared", "generation": generation, "definition": model}
            if existing["state"] not in {"prepared", "succeeded"}:
                raise PlatformError(
                    "EMBEDDING_OUTCOME_UNKNOWN", "Embedding result/charge must be reconciled before a retry", 409
                )
            if existing["state"] == "prepared":
                c.execute(
                    update(s.embedding_calls)
                    .where(s.embedding_calls.c.id == existing["id"])
                    .values(generation=generation)
                )
            return {**dict(existing), "generation": generation, "definition": model}
        maximum = Decimal(model["config"]["max_call_charge"])
        pools = shared_budgets.lock_subject(c, p.org_id, run_id=run["id"]) if run else shared_budgets.for_actor(c, p)
        shared_budgets.check(pools, Decimal(0) if run else maximum)
        budget = (
            c.execute(
                select(s.budgets)
                .where(s.budgets.c.org_id == p.org_id, s.budgets.c.owner_id == p.user_id, s.budgets.c.currency == "USD")
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if budget is None:
            raise PlatformError("QUOTA_EXCEEDED", "An embedding budget is required", 429)
        if run:
            reservation = (
                c.execute(
                    select(s.reservations).where(
                        s.reservations.c.org_id == p.org_id, s.reservations.c.run_id == run["id"]
                    )
                )
                .mappings()
                .one()
            )
            chat = c.execute(
                select(s.model_calls.c.actual_charge, s.model_calls.c.max_charge).where(
                    s.model_calls.c.org_id == p.org_id, s.model_calls.c.run_id == run["id"]
                )
            ).mappings()
            committed = (
                sum(
                    (r["actual_charge"] if r["actual_charge"] is not None else r["max_charge"] for r in chat),
                    Decimal(0),
                )
                + run_totals(c, p.org_id, run["id"])[0]
            )
            if reservation["state"] != "reserved" or committed + maximum > reservation["amount"]:
                raise PlatformError("RUN_BUDGET_EXCEEDED", "Embedding would exceed this Run's reserved budget", 429)
        else:
            if budget["consumed"] + budget["reserved"] + maximum > budget["hard_limit"]:
                raise PlatformError("QUOTA_EXCEEDED", "Insufficient budget for this embedding request", 429)
            c.execute(
                update(s.budgets).where(s.budgets.c.id == budget["id"]).values(reserved=s.budgets.c.reserved + maximum)
            )
        id = uuid4()
        values = {
            "org_id": p.org_id,
            "id": id,
            "model_id": model["id"],
            "job_id": job["id"] if job else None,
            "query_id": query["id"] if query else None,
            "run_id": run["id"] if run else None,
            "budget_id": budget["id"],
            "requested_by": p.user_id,
            "batch": batch,
            "generation": generation,
            "request_digest": digest,
            "max_charge": maximum,
            "standalone_reserved": run is None,
        }
        c.execute(insert(s.embedding_calls).values(**values))
        if run is None:
            shared_budgets.reserve(c, p.org_id, pools, maximum, embedding_call_id=id)
        return {**values, "state": "prepared", "definition": model}

    def prepare_job(self, handle, batch, texts):
        with self.jobs.owned(handle) as (c, job, now):
            version, _, _ = self.jobs.source(c, job)
            p = self.jobs.principal(job)
            model = current_embedding(c, p, version["embedding_model_id"])
            digest = canonical_digest("aio-embedding-input-v1", {"model": str(model["id"]), "texts": texts})
            return self._reserve(c, p, model, digest, job=job, batch=batch)

    def prepare_query(self, p, query_id, texts, handle=None):
        if handle:
            with self.execution.locked(handle, budget=True) as (c, run, job, now, facts):
                return self._query_call(c, p, query_id, texts, run)
        with self.db.transaction(p) as c:
            c.execute(select(s.organizations.c.id).where(s.organizations.c.id == p.org_id).with_for_update()).one()
            current_facts(c, p, lock=True)
            return self._query_call(c, p, query_id, texts, None)

    def _query_call(self, c, p, id, texts, run):
        query = (
            c.execute(
                select(s.knowledge_queries).where(
                    s.knowledge_queries.c.org_id == p.org_id, s.knowledge_queries.c.id == id
                )
            )
            .mappings()
            .one()
        )
        if query["requested_by"] != p.user_id or query["run_id"] != (run["id"] if run else None):
            raise PlatformError("RESOURCE_NOT_FOUND", "Embedding query is private", 404)
        kb = current_knowledge(c, p, query["knowledge_id"])
        model = current_embedding(c, p, kb["embedding_model_id"])
        digest = canonical_digest("aio-embedding-input-v1", {"model": str(model["id"]), "texts": texts})
        return self._reserve(c, p, model, digest, query=dict(query), run=run)

    def start(self, p, call, handle=None):
        if call["job_id"]:
            with self.jobs.owned(handle) as (c, job, now):
                self._start(c, p, call, now)
        elif handle:
            with self.execution.locked(handle, budget=True) as (c, run, job, now, facts):
                self._start(c, p, call, now)
        else:
            with self.db.transaction(p) as c:
                current_facts(c, p, lock=True)
                self._start(c, p, call, db_now(c))

    @staticmethod
    def _start(c, p, call, now):
        shared_budgets.check(shared_budgets.lock_subject(c, p.org_id, **shared_budgets.embedding_subject(call)))
        current_embedding(c, p, call["model_id"])
        updated = c.execute(
            update(s.embedding_calls)
            .where(
                s.embedding_calls.c.org_id == p.org_id,
                s.embedding_calls.c.id == call["id"],
                s.embedding_calls.c.state == "prepared",
                s.embedding_calls.c.generation == call["generation"],
            )
            .values(state="started", started_at=now)
        ).rowcount
        if updated != 1:
            raise PlatformError("EMBEDDING_OUTCOME_UNKNOWN", "Embedding dispatch is not safely replayable", 409)

    @staticmethod
    def _receipt(c, row, amount, tokens, status):
        c.execute(
            pg_insert(s.embedding_ledger)
            .values(
                org_id=row["org_id"],
                id=uuid4(),
                call_id=row["id"],
                actor_id=row["requested_by"],
                budget_id=row["budget_id"],
                status=status,
                amount=amount,
            )
            .on_conflict_do_nothing(index_elements=["org_id", "call_id", "status"])
        )
        if row["standalone_reserved"] and amount is not None:
            shared_budgets.change(
                c, row["org_id"], embedding_call_id=row["id"], release=row["max_charge"], charge=amount
            )
            c.execute(
                update(s.budgets)
                .where(s.budgets.c.org_id == row["org_id"], s.budgets.c.id == row["budget_id"])
                .values(reserved=s.budgets.c.reserved - row["max_charge"], consumed=s.budgets.c.consumed + amount)
            )
        elif row["run_id"] and amount is not None:
            reservation = (
                c.execute(
                    select(s.reservations)
                    .where(s.reservations.c.org_id == row["org_id"], s.reservations.c.run_id == row["run_id"])
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            if reservation["state"] == "held_unknown":
                if reservation["amount"] < row["max_charge"]:
                    raise PlatformError("BUDGET_INTEGRITY_ERROR", "Embedding receipt exceeds its retained hold", 409)
                remaining = reservation["amount"] - row["max_charge"]
                shared_budgets.change(c, row["org_id"], run_id=row["run_id"], release=row["max_charge"], charge=amount)
                c.execute(
                    update(s.budgets)
                    .where(s.budgets.c.id == row["budget_id"])
                    .values(reserved=s.budgets.c.reserved - row["max_charge"], consumed=s.budgets.c.consumed + amount)
                )
                c.execute(
                    update(s.reservations)
                    .where(s.reservations.c.id == reservation["id"])
                    .values(amount=remaining, state="held_unknown" if remaining else "settled")
                )
        c.execute(
            update(s.embedding_calls)
            .where(s.embedding_calls.c.id == row["id"])
            .values(state="succeeded", actual_charge=amount, input_tokens=tokens, finished_at=db_now(c))
        )

    def complete(self, p, call, reply, *, chunk_ids=None, handle=None):
        vectors, amount, tokens = reply["vectors"], reply["charge"], reply["input_tokens"]
        with self.db.scoped(p.org_id, p.user_id) as c:
            c.execute(select(s.organizations.c.id).where(s.organizations.c.id == p.org_id).with_for_update()).one()
            shared_budgets.lock_subject(c, p.org_id, **shared_budgets.embedding_subject(call))
            c.execute(
                select(s.budgets.c.id)
                .where(s.budgets.c.org_id == p.org_id, s.budgets.c.id == call["budget_id"])
                .with_for_update()
            ).one()
            row = (
                c.execute(
                    select(s.embedding_calls)
                    .where(s.embedding_calls.c.org_id == p.org_id, s.embedding_calls.c.id == call["id"])
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            if row["state"] in {"succeeded", "resolved", "not_sent"}:
                return
            if row["state"] not in {"started", "unknown"} or row["request_digest"] != call["request_digest"]:
                raise PlatformError("EMBEDDING_CALL_CONFLICT", "Embedding receipt is not bound to this intention", 409)
            self._receipt(c, row, amount, tokens, "actual" if amount is not None else "unknown")
            c.execute(
                update(s.embedding_calls)
                .where(s.embedding_calls.c.id == row["id"])
                .values(result_digest=canonical_digest("aio-embedding-result-v1", vectors))
            )
            # Billing facts survive revocation, but revoked/deleted content must never be published again.
            allowed = True
            try:
                current_facts(c, p)
                current_embedding(c, p, row["model_id"])
                if row["job_id"]:
                    job = (
                        c.execute(
                            select(s.knowledge_jobs).where(
                                s.knowledge_jobs.c.org_id == p.org_id, s.knowledge_jobs.c.id == row["job_id"]
                            )
                        )
                        .mappings()
                        .one()
                    )
                    self.jobs.source(c, job)
                    allowed = job["generation"] == handle["generation"] and job["state"] == "leased"
                else:
                    query = (
                        c.execute(
                            select(s.knowledge_queries).where(
                                s.knowledge_queries.c.org_id == p.org_id, s.knowledge_queries.c.id == row["query_id"]
                            )
                        )
                        .mappings()
                        .one()
                    )
                    current_knowledge(c, p, query["knowledge_id"])
                    for version in query["version_ids"]:
                        current_version(c, p, UUID(version))
            except PlatformError:
                allowed = False
            if allowed and chunk_ids:
                if len(vectors) != len(chunk_ids):
                    raise PlatformError("EMBEDDING_DIMENSION_MISMATCH", "Embedding batch receipt count differs", 409)
                for id, vector in zip(chunk_ids, vectors, strict=True):
                    c.execute(
                        update(s.knowledge_chunks)
                        .where(s.knowledge_chunks.c.org_id == p.org_id, s.knowledge_chunks.c.id == id)
                        .values(embedding=vector)
                    )
            elif allowed and row["query_id"]:
                c.execute(
                    update(s.knowledge_queries)
                    .where(s.knowledge_queries.c.org_id == p.org_id, s.knowledge_queries.c.id == row["query_id"])
                    .values(query_vector=vectors[0], state="preparing")
                )

    def uncertain(self, p, call):
        with self.db.scoped(p.org_id, p.user_id) as c:
            # Same structural prefix as receipt/admission; no call-row -> budget inversion.
            c.execute(
                select(s.organizations.c.id).where(s.organizations.c.id == p.org_id).with_for_update(read=True)
            ).one()
            shared_budgets.lock_subject(c, p.org_id, **shared_budgets.embedding_subject(call))
            c.execute(
                select(s.budgets.c.id)
                .where(s.budgets.c.org_id == p.org_id, s.budgets.c.id == call["budget_id"])
                .with_for_update()
            ).one()
            row = (
                c.execute(
                    select(s.embedding_calls)
                    .where(s.embedding_calls.c.org_id == p.org_id, s.embedding_calls.c.id == call["id"])
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            if row["state"] in {"succeeded", "resolved", "not_sent"}:
                return
            if row["state"] == "prepared":
                if row["standalone_reserved"]:
                    shared_budgets.change(c, p.org_id, embedding_call_id=row["id"], release=row["max_charge"])
                    c.execute(
                        update(s.budgets)
                        .where(s.budgets.c.id == row["budget_id"])
                        .values(reserved=s.budgets.c.reserved - row["max_charge"])
                    )
                c.execute(
                    update(s.embedding_calls)
                    .where(s.embedding_calls.c.id == row["id"])
                    .values(state="not_sent", actual_charge=Decimal(0))
                )
            else:
                c.execute(update(s.embedding_calls).where(s.embedding_calls.c.id == row["id"]).values(state="unknown"))
                c.execute(
                    pg_insert(s.embedding_ledger)
                    .values(
                        org_id=p.org_id,
                        id=uuid4(),
                        call_id=row["id"],
                        actor_id=p.user_id,
                        budget_id=row["budget_id"],
                        status="unknown",
                        amount=None,
                    )
                    .on_conflict_do_nothing(index_elements=["org_id", "call_id", "status"])
                )

    def pending(self, p):
        from ..admin.service import AdminService

        with self.db.transaction(p) as c:
            if AdminService.role(c, p) not in {"org_admin", "auditor"}:
                raise PlatformError("ADMIN_FORBIDDEN", "Embedding receipt inspection requires an audit role", 403)
            rows = c.execute(
                select(
                    s.embedding_calls.c.id,
                    s.embedding_calls.c.requested_by,
                    s.embedding_calls.c.job_id,
                    s.embedding_calls.c.run_id,
                    s.embedding_calls.c.state,
                    s.embedding_calls.c.max_charge,
                    s.embedding_calls.c.created_at,
                )
                .where(
                    s.embedding_calls.c.org_id == p.org_id,
                    s.embedding_calls.c.actual_charge.is_(None),
                    s.embedding_calls.c.state.in_(["unknown", "succeeded"]),
                )
                .order_by(s.embedding_calls.c.created_at.desc())
                .limit(100)
            ).mappings()
            return [dict(row) for row in rows]

    def reconcile(self, p, id, amount, evidence):
        from ..admin.service import AdminService

        with self.db.transaction(p) as c:
            c.execute(select(s.organizations.c.id).where(s.organizations.c.id == p.org_id).with_for_update()).one()
            if AdminService.role(c, p) != "org_admin":
                raise PlatformError("ADMIN_FORBIDDEN", "Embedding accounting requires organization administration", 403)
            row = (
                c.execute(
                    select(s.embedding_calls)
                    .where(s.embedding_calls.c.org_id == p.org_id, s.embedding_calls.c.id == id)
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if row is None:
                raise PlatformError("RESOURCE_NOT_FOUND", "Embedding call is not available", 404)
            if row["requested_by"] == p.user_id:
                raise PlatformError(
                    "SEPARATION_OF_DUTIES", "Another authorized administrator must reconcile this usage", 403
                )
            old = (
                c.execute(
                    select(s.embedding_ledger).where(
                        s.embedding_ledger.c.org_id == p.org_id,
                        s.embedding_ledger.c.call_id == id,
                        s.embedding_ledger.c.status == "adjustment",
                    )
                )
                .mappings()
                .first()
            )
            if old:
                if old["amount"] != amount or old["evidence_ref"] != evidence:
                    raise PlatformError("USAGE_RECEIPT_CONFLICT", "Receipt was already bound to another fact", 409)
                return {"id": id, "recorded": True}
            if row["state"] not in {"succeeded", "unknown"} or row["actual_charge"] is not None:
                raise PlatformError("USAGE_NOT_PENDING", "Embedding call has no unresolved usage receipt", 409)
            shared_budgets.lock_subject(c, p.org_id, **shared_budgets.embedding_subject(row))
            budget = (
                c.execute(
                    select(s.budgets)
                    .where(s.budgets.c.org_id == p.org_id, s.budgets.c.id == row["budget_id"])
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            if row["run_id"]:
                reservation = (
                    c.execute(
                        select(s.reservations)
                        .where(s.reservations.c.org_id == p.org_id, s.reservations.c.run_id == row["run_id"])
                        .with_for_update()
                    )
                    .mappings()
                    .one()
                )
                if reservation["state"] != "held_unknown" or reservation["amount"] < row["max_charge"]:
                    raise PlatformError(
                        "USAGE_NOT_PENDING", "Run must finish and retain its usage hold before reconciliation", 409
                    )
                remaining = reservation["amount"] - row["max_charge"]
                c.execute(
                    update(s.reservations)
                    .where(s.reservations.c.id == reservation["id"])
                    .values(amount=remaining, state="held_unknown" if remaining else "settled")
                )
            if budget["reserved"] < row["max_charge"]:
                raise PlatformError("BUDGET_INTEGRITY_ERROR", "Embedding usage hold is inconsistent", 409)
            shared_budgets.change(
                c, p.org_id, **shared_budgets.embedding_subject(row), release=row["max_charge"], charge=amount
            )
            c.execute(
                update(s.budgets)
                .where(s.budgets.c.id == row["budget_id"])
                .values(reserved=s.budgets.c.reserved - row["max_charge"], consumed=s.budgets.c.consumed + amount)
            )
            c.execute(
                insert(s.embedding_ledger).values(
                    org_id=p.org_id,
                    id=uuid4(),
                    call_id=id,
                    actor_id=p.user_id,
                    budget_id=row["budget_id"],
                    status="adjustment",
                    amount=amount,
                    evidence_ref=evidence,
                )
            )
            c.execute(
                update(s.embedding_calls)
                .where(s.embedding_calls.c.id == id)
                .values(actual_charge=amount, state="succeeded" if row["result_digest"] else "resolved")
            )
            audit.record(
                c,
                p,
                'embedding.usage.reconcile',
                id,
                'recorded',
            )
            return {"id": id, "recorded": True}


class Embedder:
    def __init__(self, store, factory):
        self.store, self.factory = store, factory

    async def _invoke(self, p, call, texts, *, handle=None, chunk_ids=None):
        if call["state"] == "succeeded":
            return
        client = None
        try:
            client = self.factory.create(call["definition"])
            await asyncio.to_thread(self.store.start, p, call, handle)
            reply = await client.embed(texts)
            await asyncio.to_thread(self.store.complete, p, call, reply, handle=handle, chunk_ids=chunk_ids)
        except BaseException:
            await asyncio.shield(asyncio.to_thread(self.store.uncertain, p, call))
            raise
        finally:
            if client:
                await client.close()

    def _chunks(self, handle):
        with self.store.jobs.owned(handle) as (c, job, now):
            version, _, _ = self.store.jobs.source(c, job)
            if not version["embedding_model_id"]:
                return None, []
            model = current_embedding(c, self.store.jobs.principal(job), version["embedding_model_id"])
            chunks = (
                c.execute(
                    select(s.knowledge_chunks.c.id, s.knowledge_chunks.c.content)
                    .where(
                        s.knowledge_chunks.c.org_id == job["org_id"], s.knowledge_chunks.c.version_id == version["id"]
                    )
                    .order_by(s.knowledge_chunks.c.ordinal)
                )
                .mappings()
                .all()
            )
            return model, [dict(row) for row in chunks]

    async def index(self, handle):
        model, chunks = await asyncio.to_thread(self._chunks, handle)
        if not model:
            return
        p = self.store.jobs.principal(handle)
        size = model["config"]["batch_size"]
        for number, offset in enumerate(range(0, len(chunks), size)):
            batch = chunks[offset : offset + size]
            texts = [r["content"] for r in batch]
            call = await asyncio.to_thread(self.store.prepare_job, handle, number, texts)
            await self._invoke(p, call, texts, handle=handle, chunk_ids=[r["id"] for r in batch])

    async def query(self, p, id, query, handle=None):
        call = await asyncio.to_thread(self.store.prepare_query, p, id, [query], handle)
        await self._invoke(p, call, [query], handle=handle)
