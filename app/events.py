"""Tenant-scoped API routes: endpoints, events, deliveries and stats."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import state
from .auth import Principal
from .config import get_settings
from .constants import (
    REQUEUEABLE_STATUSES,
    STATUS_QUEUED,
    STATUS_RETRYING,
)
from .crypto import get_secret_box
from .db import Delivery, Endpoint, Event, utcnow
from .deps import require_principal
from .schemas import DeliveryOut, EndpointCreate, EndpointCreated, EventCreate, EventOut
from .security import generate_secret
from .state import (
    EVENTS_DEDUPLICATED,
    EVENTS_INGESTED,
    DELIVERIES_REQUEUED,
    bump,
    get_db,
    to_delivery_out,
)


def _endpoint_fields(endpoint: Endpoint) -> dict:
    """Fields shared by endpoint listings and the one-time creation response."""
    return {
        "id": endpoint.id,
        "url": endpoint.url,
        "rate_limit_per_minute": endpoint.rate_limit_per_minute,
        "created_at": endpoint.created_at.isoformat(),
    }


def _deduplicated_event_out(db: Session, event: Event, endpoint_id: str) -> EventOut:
    """Build the replay response for an already-ingested event."""
    bump(EVENTS_DEDUPLICATED)
    delivery = (
        db.query(Delivery)
        .filter(Delivery.event_id == event.id)
        .order_by(Delivery.created_at)
        .first()
    )
    return EventOut(
        id=event.id,
        endpoint_id=endpoint_id,
        delivery_id=delivery.id if delivery else "",
        deduplicated=True,
    )


def build_events_router() -> APIRouter:
    """Build the authenticated tenant-facing API router."""
    router = APIRouter()

    @router.get("/v1/stats")
    def stats(
        db: Session = Depends(get_db),
        principal: Principal = Depends(require_principal),
    ):
        """Queue-depth + delivery-state overview for dashboards/alerts."""
        rows = (
            db.query(Delivery.status, func.count(Delivery.id))
            .join(Endpoint, Delivery.endpoint_id == Endpoint.id)
            .filter(Endpoint.tenant_id == principal.tenant_id)
            .group_by(Delivery.status)
            .all()
        )
        by_status = {status: count for status, count in rows}
        queued = by_status.get(STATUS_QUEUED, 0) + by_status.get(STATUS_RETRYING, 0)
        return {
            "by_status": by_status,
            "queue_depth": queued,
            "redis": "configured" if state.delivery_queue.has_redis else "not-configured",
        }

    @router.post("/v1/endpoints", status_code=201, response_model=EndpointCreated)
    def register_endpoint(
        payload: EndpointCreate,
        db: Session = Depends(get_db),
        principal: Principal = Depends(require_principal),
    ):
        if len(payload.url.encode()) > 2000:
            raise HTTPException(status_code=413, detail="url too long")
        # The secret is encrypted before it reaches the database and returned to
        # the caller exactly once, in this response.
        plaintext_secret = payload.secret or generate_secret()
        endpoint = Endpoint(
            tenant_id=principal.tenant_id,
            url=payload.url,
            secret=get_secret_box(get_settings().secret_encryption_key).encrypt(
                plaintext_secret
            ),
            rate_limit_per_minute=payload.rate_limit_per_minute,
        )
        db.add(endpoint)
        db.commit()
        db.refresh(endpoint)
        return EndpointCreated(**_endpoint_fields(endpoint), secret=plaintext_secret)

    @router.get("/v1/endpoints")
    def list_endpoints(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        db: Session = Depends(get_db),
        principal: Principal = Depends(require_principal),
    ):
        rows = (
            db.query(Endpoint)
            .filter(Endpoint.tenant_id == principal.tenant_id)
            .order_by(Endpoint.created_at)
            .offset(offset)
            .limit(limit)
            .all()
        )
        return {"items": [_endpoint_fields(e) for e in rows]}

    @router.post("/v1/events", status_code=201, response_model=EventOut)
    def ingest_event(
        payload: EventCreate,
        db: Session = Depends(get_db),
        principal: Principal = Depends(require_principal),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        settings = get_settings()
        key = payload.idempotency_key or idempotency_key
        endpoint = db.get(Endpoint, payload.endpoint_id)
        # 404 rather than 403: another tenant's endpoint must be indistinguishable
        # from one that does not exist.
        if endpoint is None or endpoint.tenant_id != principal.tenant_id:
            raise HTTPException(status_code=404, detail="endpoint not found")
        try:
            raw = json.dumps(payload.payload, separators=(",", ":"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="payload must be JSON-serializable")
        if len(raw.encode()) > settings.max_body_bytes:
            raise HTTPException(status_code=413, detail="payload too large")

        if key:
            existing = (
                db.query(Event)
                .filter(Event.endpoint_id == endpoint.id, Event.idempotency_key == key)
                .order_by(Event.created_at)
                .first()
            )
            if existing is not None:
                return _deduplicated_event_out(db, existing, endpoint.id)

        event = Event(endpoint_id=endpoint.id, idempotency_key=key, payload=raw)
        db.add(event)
        try:
            db.flush()
        except IntegrityError:
            # Lost the race: a concurrent ingest with the same key won. The
            # UNIQUE constraint is what makes returning the winner safe.
            db.rollback()
            winner = (
                db.query(Event)
                .filter(Event.endpoint_id == endpoint.id, Event.idempotency_key == key)
                .order_by(Event.created_at)
                .first()
            )
            if winner is None:  # pragma: no cover - defensive
                raise HTTPException(status_code=409, detail="idempotency conflict")
            return _deduplicated_event_out(db, winner, endpoint.id)

        delivery = Delivery(
            event_id=event.id,
            endpoint_id=endpoint.id,
            status=STATUS_QUEUED,
            attempts=0,
            next_attempt_at=None,
        )
        db.add(delivery)
        db.commit()
        db.refresh(event)
        db.refresh(delivery)
        state.delivery_queue.enqueue(delivery.id)
        bump(EVENTS_INGESTED)
        return EventOut(
            id=event.id,
            endpoint_id=endpoint.id,
            delivery_id=delivery.id,
            deduplicated=False,
        )

    @router.get("/v1/events/{event_id}")
    def get_event(
        event_id: str,
        db: Session = Depends(get_db),
        principal: Principal = Depends(require_principal),
    ):
        event = db.get(Event, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="event not found")
        principal.require_tenant(db.get(Endpoint, event.endpoint_id).tenant_id)
        deliveries = (
            db.query(Delivery)
            .filter(Delivery.event_id == event.id)
            .order_by(Delivery.created_at)
            .all()
        )
        return {
            "id": event.id,
            "endpoint_id": event.endpoint_id,
            "payload": json.loads(event.payload),
            "created_at": event.created_at.isoformat(),
            "deliveries": [to_delivery_out(d).model_dump() for d in deliveries],
        }

    @router.get("/v1/deliveries")
    def list_deliveries(
        status: str | None = Query(default=None),
        endpoint_id: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        db: Session = Depends(get_db),
        principal: Principal = Depends(require_principal),
    ):
        # Join scopes results to the caller's endpoints: another tenant's
        # delivery is unreachable, not merely hidden from the listing.
        q = (
            db.query(Delivery)
            .join(Endpoint, Delivery.endpoint_id == Endpoint.id)
            .filter(Endpoint.tenant_id == principal.tenant_id)
        )
        if status:
            if status not in ("queued", "success", "retrying", "dlq"):
                raise HTTPException(status_code=422, detail="invalid status")
            q = q.filter(Delivery.status == status)
        if endpoint_id:
            q = q.filter(Delivery.endpoint_id == endpoint_id)
        rows = q.order_by(Delivery.created_at.desc()).offset(offset).limit(limit).all()
        return {"items": [to_delivery_out(d).model_dump() for d in rows]}

    @router.post("/v1/deliveries/{delivery_id}/requeue", response_model=DeliveryOut)
    def requeue_delivery(
        delivery_id: str,
        db: Session = Depends(get_db),
        principal: Principal = Depends(require_principal),
    ):
        """Replay a dead-letter (or retrying/queued) delivery as a fresh attempt."""
        delivery = db.get(Delivery, delivery_id)
        if delivery is None:
            raise HTTPException(status_code=404, detail="delivery not found")
        endpoint = db.get(Endpoint, delivery.endpoint_id)
        if endpoint is None or endpoint.tenant_id != principal.tenant_id:
            raise HTTPException(status_code=404, detail="delivery not found")
        if delivery.status not in REQUEUEABLE_STATUSES:
            raise HTTPException(
                status_code=409,
                detail=f"cannot requeue delivery in status {delivery.status!r}",
            )
        delivery.status = STATUS_QUEUED
        delivery.attempts = 0
        delivery.next_attempt_at = None
        delivery.last_error = None
        delivery.updated_at = utcnow()
        db.add(delivery)
        db.commit()
        db.refresh(delivery)
        state.delivery_queue.enqueue(delivery.id)
        bump(DELIVERIES_REQUEUED)
        return to_delivery_out(delivery)

    return router
