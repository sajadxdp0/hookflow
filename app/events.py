"""Tenant-scoped endpoints, events, delivery history and replay."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import state
from .auth import Principal
from .config import get_settings
from .constants import (
    REQUEUEABLE_STATUSES,
    RETRYABLE_STATUSES,
    STATUS_DLQ,
    STATUS_QUEUED,
    STATUS_RETRYING,
    STATUS_SUCCESS,
)
from .crypto import get_secret_box
from .db import Delivery, Endpoint, Event, Tenant, as_utc_iso, utcnow
from .deps import require_principal
from .schemas import (
    DeliveryOut,
    EndpointCreate,
    EndpointCreated,
    EndpointOut,
    EndpointPatch,
    EndpointRotated,
    EventCreate,
    EventOut,
)
from .security import generate_secret
from .state import (
    DELIVERIES_REQUEUED,
    EVENTS_DEDUPLICATED,
    EVENTS_INGESTED,
    bump,
    get_db,
    to_delivery_out,
)


def _endpoint_fields(endpoint: Endpoint) -> dict[str, Any]:
    return {
        "id": endpoint.id,
        "url": endpoint.url,
        "rate_limit_per_minute": endpoint.rate_limit_per_minute,
        "enabled": endpoint.enabled,
        "created_at": as_utc_iso(endpoint.created_at),
    }


def _tenant_endpoint(db: Session, endpoint_id: str, principal: Principal) -> Endpoint:
    endpoint = db.get(Endpoint, endpoint_id)
    if endpoint is None or endpoint.tenant_id != principal.tenant_id:
        raise HTTPException(status_code=404, detail="endpoint not found")
    return endpoint


def _deduplicated_event_out(
    db: Session,
    event: Event,
    endpoint_id: str,
    expected_payload: dict[str, Any],
) -> EventOut:
    if json.loads(event.payload) != expected_payload:
        raise HTTPException(
            status_code=409, detail="idempotency key reused with a different payload"
        )
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


def _rate_limited() -> None:
    raise HTTPException(
        status_code=429,
        detail="tenant rate limit exceeded",
        headers={"Retry-After": "60"},
    )


def build_events_router() -> APIRouter:
    router = APIRouter(tags=["endpoints and events"])

    @router.get("/v1/stats")
    def stats(
        db: Session = Depends(get_db),
        principal: Principal = Depends(require_principal),
    ):
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
        settings = get_settings()
        tenant = (
            db.query(Tenant)
            .filter(Tenant.id == principal.tenant_id)
            .with_for_update()
            .one()
        )
        endpoint_count = (
            db.query(func.count(Endpoint.id))
            .filter(Endpoint.tenant_id == tenant.id)
            .scalar()
        )
        if endpoint_count >= settings.max_endpoints_per_tenant:
            raise HTTPException(status_code=409, detail="endpoint limit reached for tenant")
        plaintext_secret = payload.secret or generate_secret()
        endpoint = Endpoint(
            tenant_id=principal.tenant_id,
            url=payload.url,
            secret=get_secret_box(settings.secret_encryption_key).encrypt(plaintext_secret),
            rate_limit_per_minute=(
                payload.rate_limit_per_minute
                if payload.rate_limit_per_minute is not None
                else settings.default_rate_limit_per_minute
            ),
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
            .order_by(Endpoint.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return {"items": [_endpoint_fields(endpoint) for endpoint in rows]}

    @router.get("/v1/endpoints/{endpoint_id}", response_model=EndpointOut)
    def get_endpoint(
        endpoint_id: str,
        db: Session = Depends(get_db),
        principal: Principal = Depends(require_principal),
    ):
        return _endpoint_fields(_tenant_endpoint(db, endpoint_id, principal))

    @router.patch("/v1/endpoints/{endpoint_id}", response_model=EndpointOut)
    def update_endpoint(
        endpoint_id: str,
        payload: EndpointPatch,
        db: Session = Depends(get_db),
        principal: Principal = Depends(require_principal),
    ):
        endpoint = _tenant_endpoint(db, endpoint_id, principal)
        wake_deliveries: list[str] = []
        if payload.url is not None:
            endpoint.url = payload.url
        if payload.rate_limit_per_minute is not None:
            endpoint.rate_limit_per_minute = payload.rate_limit_per_minute
        if payload.enabled is not None:
            if payload.enabled and not endpoint.enabled:
                wake_deliveries = [
                    row_id
                    for (row_id,) in db.query(Delivery.id)
                    .filter(
                        Delivery.endpoint_id == endpoint.id,
                        Delivery.status.in_(RETRYABLE_STATUSES),
                    )
                    .all()
                ]
                db.query(Delivery).filter(
                    Delivery.endpoint_id == endpoint.id,
                    Delivery.status.in_(RETRYABLE_STATUSES),
                ).update({Delivery.next_attempt_at: None}, synchronize_session=False)
            endpoint.enabled = payload.enabled
        db.add(endpoint)
        db.commit()
        db.refresh(endpoint)
        for delivery_id in wake_deliveries:
            state.delivery_queue.enqueue(delivery_id)
        return _endpoint_fields(endpoint)

    @router.post("/v1/endpoints/{endpoint_id}/rotate-secret", response_model=EndpointRotated)
    def rotate_endpoint_secret(
        endpoint_id: str,
        db: Session = Depends(get_db),
        principal: Principal = Depends(require_principal),
    ):
        endpoint = _tenant_endpoint(db, endpoint_id, principal)
        plaintext_secret = generate_secret()
        endpoint.secret = get_secret_box(
            get_settings().secret_encryption_key
        ).encrypt(plaintext_secret)
        db.add(endpoint)
        db.commit()
        return EndpointRotated(id=endpoint.id, secret=plaintext_secret)

    @router.delete("/v1/endpoints/{endpoint_id}", status_code=204)
    def delete_endpoint(
        endpoint_id: str,
        db: Session = Depends(get_db),
        principal: Principal = Depends(require_principal),
    ):
        endpoint = _tenant_endpoint(db, endpoint_id, principal)
        active = (
            db.query(func.count(Delivery.id))
            .filter(
                Delivery.endpoint_id == endpoint.id,
                Delivery.status.in_(RETRYABLE_STATUSES),
            )
            .scalar()
        )
        if active:
            raise HTTPException(
                status_code=409,
                detail="re-enable and drain active deliveries before deleting",
            )
        db.delete(endpoint)
        db.commit()
        return Response(status_code=204)

    @router.post("/v1/events", status_code=201, response_model=EventOut)
    def ingest_event(
        payload: EventCreate,
        db: Session = Depends(get_db),
        principal: Principal = Depends(require_principal),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        settings = get_settings()
        header_key = idempotency_key.strip() if idempotency_key else None
        header_key = header_key or None
        if header_key and payload.idempotency_key and header_key != payload.idempotency_key:
            raise HTTPException(status_code=422, detail="conflicting idempotency keys")
        key = payload.idempotency_key or header_key
        if key is not None and len(key) > 128:
            raise HTTPException(
                status_code=422, detail="idempotency key must be at most 128 characters"
            )

        endpoint = _tenant_endpoint(db, payload.endpoint_id, principal)
        if not endpoint.enabled:
            raise HTTPException(status_code=409, detail="endpoint is disabled")
        if not state.rate_limiter.allow(
            f"ingest:{principal.tenant_id}", settings.ingest_rate_limit_per_minute
        ):
            _rate_limited()
        try:
            raw = json.dumps(
                payload.payload,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=422, detail="payload must be valid finite JSON"
            ) from exc
        if len(raw.encode("utf-8")) > settings.max_body_bytes:
            raise HTTPException(status_code=413, detail="payload too large")

        if key:
            existing = (
                db.query(Event)
                .filter(Event.endpoint_id == endpoint.id, Event.idempotency_key == key)
                .order_by(Event.created_at)
                .first()
            )
            if existing is not None:
                return _deduplicated_event_out(db, existing, endpoint.id, payload.payload)

        event = Event(endpoint_id=endpoint.id, idempotency_key=key, payload=raw)
        db.add(event)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            winner = (
                db.query(Event)
                .filter(Event.endpoint_id == endpoint.id, Event.idempotency_key == key)
                .order_by(Event.created_at)
                .first()
            )
            if winner is None:  # pragma: no cover - defensive
                raise HTTPException(status_code=409, detail="idempotency conflict") from None
            return _deduplicated_event_out(db, winner, endpoint.id, payload.payload)

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
        event = (
            db.query(Event)
            .join(Endpoint, Event.endpoint_id == Endpoint.id)
            .filter(Event.id == event_id, Endpoint.tenant_id == principal.tenant_id)
            .one_or_none()
        )
        if event is None:
            raise HTTPException(status_code=404, detail="event not found")
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
            "created_at": as_utc_iso(event.created_at),
            "deliveries": [to_delivery_out(delivery).model_dump() for delivery in deliveries],
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
        query = (
            db.query(Delivery)
            .join(Endpoint, Delivery.endpoint_id == Endpoint.id)
            .filter(Endpoint.tenant_id == principal.tenant_id)
        )
        if status:
            if status not in (STATUS_QUEUED, STATUS_SUCCESS, STATUS_RETRYING, STATUS_DLQ):
                raise HTTPException(status_code=422, detail="invalid status")
            query = query.filter(Delivery.status == status)
        if endpoint_id:
            query = query.filter(Delivery.endpoint_id == endpoint_id)
        rows = query.order_by(Delivery.created_at.desc()).offset(offset).limit(limit).all()
        return {"items": [to_delivery_out(delivery).model_dump() for delivery in rows]}

    @router.post("/v1/deliveries/{delivery_id}/requeue", response_model=DeliveryOut)
    def requeue_delivery(
        delivery_id: str,
        db: Session = Depends(get_db),
        principal: Principal = Depends(require_principal),
    ):
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
        changed = (
            db.query(Delivery)
            .filter(Delivery.id == delivery.id, Delivery.status == STATUS_DLQ)
            .update(
                {
                    Delivery.status: STATUS_QUEUED,
                    Delivery.attempts: 0,
                    Delivery.next_attempt_at: None,
                    Delivery.last_status_code: None,
                    Delivery.last_error: None,
                    Delivery.latency_ms: None,
                    Delivery.claim_token: None,
                    Delivery.claimed_at: None,
                    Delivery.updated_at: utcnow(),
                },
                synchronize_session=False,
            )
        )
        db.commit()
        if not changed:
            raise HTTPException(status_code=409, detail="delivery is no longer replayable")
        db.refresh(delivery)
        state.delivery_queue.enqueue(delivery.id)
        bump(DELIVERIES_REQUEUED)
        return to_delivery_out(delivery)

    return router
