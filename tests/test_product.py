"""Product-level regressions for security, lifecycle, reliability, and readiness."""

from __future__ import annotations

import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from redis import RedisError

from app import state
from app.config import Settings, clear_settings_override, set_settings
from app.db import Delivery, Endpoint, Event, Tenant, make_engine, make_session_factory, new_id
from app.migrations import upgrade_to_head
from app.queue import DeliveryQueue
from app.ratelimit import MemoryRateLimiter, RateLimiter
from app.worker import deliver_once, process_due_deliveries


def _register(client, url="https://example.com/hook"):
    response = client.post("/v1/endpoints", json={"url": url})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.1/internal",
        "http://[::1]/admin",
        "http://localhost/admin",
        "http://user:password@example.com/hook",
        "http://example.com/hook#fragment",
    ],
)
def test_registration_rejects_non_public_destinations(client, url):
    assert client.post("/v1/endpoints", json={"url": url}).status_code == 422


def test_endpoint_lifecycle_and_secret_rotation(client, session):
    created = _register(client)
    endpoint_id = created["id"]
    assert created["enabled"] is True

    updated = client.patch(
        f"/v1/endpoints/{endpoint_id}",
        json={"url": "https://example.com/new", "rate_limit_per_minute": 12, "enabled": False},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["enabled"] is False
    assert updated.json()["rate_limit_per_minute"] == 12
    assert client.post(
        "/v1/events", json={"endpoint_id": endpoint_id, "payload": {"n": 1}}
    ).status_code == 409

    assert client.patch(f"/v1/endpoints/{endpoint_id}", json={"enabled": True}).status_code == 200
    ingested = client.post(
        "/v1/events", json={"endpoint_id": endpoint_id, "payload": {"n": 1}}
    )
    assert ingested.status_code == 201, ingested.text

    rotated = client.post(f"/v1/endpoints/{endpoint_id}/rotate-secret")
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["secret"] != created["secret"]
    stored = session.get(Endpoint, endpoint_id).secret
    assert stored.startswith("enc:v1:")
    assert rotated.json()["secret"] not in stored

    assert client.delete(f"/v1/endpoints/{endpoint_id}").status_code == 409
    session.get(Delivery, ingested.json()["delivery_id"]).status = "success"
    session.commit()
    assert client.delete(f"/v1/endpoints/{endpoint_id}").status_code == 204
    assert client.get(f"/v1/endpoints/{endpoint_id}").status_code == 404


def test_idempotency_key_is_bound_to_payload(client):
    endpoint_id = _register(client)["id"]
    first = client.post(
        "/v1/events",
        json={"endpoint_id": endpoint_id, "payload": {"amount": 100}, "idempotency_key": "order-1"},
    )
    assert first.status_code == 201, first.text
    conflict = client.post(
        "/v1/events",
        json={"endpoint_id": endpoint_id, "payload": {"amount": 1}, "idempotency_key": "order-1"},
    )
    assert conflict.status_code == 409
    same = client.post(
        "/v1/events",
        json={"endpoint_id": endpoint_id, "payload": {"amount": 100}, "idempotency_key": "order-1"},
    )
    assert same.status_code == 201
    assert same.json()["deduplicated"] is True


def test_idempotency_header_validation(client):
    endpoint_id = _register(client)["id"]
    payload = {"endpoint_id": endpoint_id, "payload": {"n": 1}}
    response = client.post(
        "/v1/events", json=payload, headers={"Idempotency-Key": "x" * 129}
    )
    assert response.status_code == 422
    conflict = client.post(
        "/v1/events",
        json={**payload, "idempotency_key": "body-key"},
        headers={"Idempotency-Key": "header-key"},
    )
    assert conflict.status_code == 422

    first = client.post("/v1/events", json=payload, headers={"Idempotency-Key": ""})
    second = client.post("/v1/events", json=payload, headers={"Idempotency-Key": ""})
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_non_finite_json_is_rejected(client):
    endpoint_id = _register(client)["id"]
    response = client.post(
        "/v1/events",
        content=f'{{"endpoint_id":"{endpoint_id}","payload":{{"n":NaN}}}}'.encode(),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422

def test_invalid_request_id_is_not_reflected(client):
    response = client.get("/health", headers={"X-Request-ID": "bad value"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "bad value"


def test_body_limit_rejects_before_authentication(anon_client):
    anon_client.headers.pop("Authorization", None)
    response = anon_client.post(
        "/v1/events",
        content=b"x" * (256 * 1024 + 1),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413


def test_tenant_ingest_rate_limit(client):
    current = state.get_settings_dep()
    set_settings(
        Settings(
            database_url=current.database_url,
            redis_url="",
            admin_token=current.admin_token,
            ingest_rate_limit_per_minute=1,
        )
    )
    endpoint_id = _register(client)["id"]
    payload = {"endpoint_id": endpoint_id, "payload": {"n": 1}}
    assert client.post("/v1/events", json=payload).status_code == 201
    limited = client.post("/v1/events", json=payload)
    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "60"


def test_committed_event_survives_queue_failure(client, monkeypatch):
    class BrokenRedis:
        def lpush(self, *_args):
            raise RedisError("unavailable")

    monkeypatch.setattr(state.delivery_queue, "_redis", BrokenRedis())
    endpoint_id = _register(client)["id"]
    response = client.post(
        "/v1/events", json={"endpoint_id": endpoint_id, "payload": {"n": 1}}
    )
    assert response.status_code == 201, response.text
    assert response.json()["delivery_id"]


def test_production_readiness_fails_closed():
    from app import main as main_module

    database_url, _factory, _session, _delivery_id = _worker_fixture()
    _session.close()
    settings = Settings.model_construct(
        database_url=database_url,
        redis_url="",
        admin_token="short",
        environment="production",
    )
    app = main_module.create_app(settings)
    try:
        with TestClient(app) as test_client:
            response = test_client.get("/ready")
        assert response.status_code == 503
        checks = response.json()["detail"]["checks"]
        assert checks["database"] == "postgresql-required"
        assert checks["secret_encryption"] == "production-key-required"
        assert checks["redis"] == "required-in-production"
    finally:
        clear_settings_override()


def test_unsafe_worker_lease_configuration_is_rejected():
    with pytest.raises(ValidationError):
        Settings(delivery_timeout_seconds=10, claim_lease_seconds=10)


@pytest.mark.parametrize(
    "override",
    [
        {"database_url": "sqlite:///./unsafe.db"},
        {"redis_url": ""},
        {"secret_encryption_key": ""},
        {"admin_token": "short"},
    ],
)
def test_production_settings_reject_unsafe_configuration(override):
    safe = {
        "database_url": "postgresql+psycopg://hookflow:secret@localhost/hookflow",
        "redis_url": "redis://localhost:6379/0",
        "secret_encryption_key": "a-production-key",
        "admin_token": "x" * 32,
        "environment": "production",
    }
    with pytest.raises(ValidationError):
        Settings(**{**safe, **override})


def test_configured_redis_readiness_failure(client, monkeypatch):
    class UnreachableRedis:
        def ping(self):
            raise RedisError("unavailable")

    monkeypatch.setattr(state.delivery_queue, "_redis", UnreachableRedis())
    assert client.get("/ready").status_code == 503


def test_outbound_response_body_is_not_buffered():
    class ExplodingStream(httpx.SyncByteStream):
        def __iter__(self):
            raise AssertionError("response body must not be consumed")

        def close(self):
            return None

    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, stream=ExplodingStream())
        )
    )
    status, error, _latency = deliver_once(
        b"{}", "https://example.com/hook", "secret", 1.0, client
    )
    client.close()
    assert (status, error) == (200, None)


def test_memory_limiter_is_safe_under_concurrency():
    limiter = MemoryRateLimiter()
    barrier = Barrier(20)

    def consume():
        barrier.wait(timeout=5)
        return limiter.allow("tenant", 5, now=1000.0)

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(lambda _index: consume(), range(20)))
    assert sum(results) == 5


def test_queue_zero_timeout_is_nonblocking():
    class FakeRedis:
        def brpop(self, *_args):
            raise AssertionError("zero timeout must never call BRPOP")

        def rpop(self, _key):
            return None

    queue = DeliveryQueue("redis://unused")
    queue._redis = FakeRedis()
    assert queue.dequeue(timeout=0) is None


def test_egress_pins_validated_address(monkeypatch):
    from app import egress

    monkeypatch.setattr(
        egress.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (2, 1, 6, "", ("93.184.216.34", 443)),
        ],
    )
    outbound = egress.prepare_outbound_request("https://example.com/hook")
    assert outbound.url.host == "93.184.216.34"
    assert outbound.headers["Host"] == "example.com"
    assert outbound.extensions["sni_hostname"] == "example.com"


def test_egress_rejects_private_dns_answer(monkeypatch):
    from app import egress

    monkeypatch.setattr(
        egress.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (2, 1, 6, "", ("127.0.0.1", 80)),
        ],
    )
    with pytest.raises(egress.EgressError):
        egress.prepare_outbound_request("http://public-looking.example/hook")


def _worker_fixture(url="https://example.com/hook"):
    database_url = f"sqlite:///{Path(tempfile.mkdtemp()) / 'worker.db'}"
    engine = make_engine(database_url)
    upgrade_to_head(database_url)
    factory = make_session_factory(engine)
    session = factory()
    tenant = Tenant(id=new_id(), name="product-worker")
    session.add(tenant)
    session.flush()
    endpoint = Endpoint(
        tenant_id=tenant.id,
        url=url,
        secret="s",
        rate_limit_per_minute=100,
    )
    session.add(endpoint)
    session.flush()
    event = Event(endpoint_id=endpoint.id, payload='{"n":1}')
    session.add(event)
    session.flush()
    delivery = Delivery(event_id=event.id, endpoint_id=endpoint.id, status="queued", attempts=0)
    session.add(delivery)
    session.commit()
    return database_url, factory, session, delivery.id


def test_worker_holds_claim_during_network_request():
    database_url, factory, session, delivery_id = _worker_fixture()
    observed = []

    def handler(_request):
        probe = factory()
        try:
            observed.append(probe.get(Delivery, delivery_id).claim_token)
        finally:
            probe.close()
        return httpx.Response(200)

    stats = process_due_deliveries(
        session,
        Settings(database_url=database_url, redis_url=""),
        RateLimiter(),
        httpx.Client(transport=httpx.MockTransport(handler)),
        claim_token="worker-token",
    )
    assert observed == ["worker-token"]
    assert stats["success"] == 1
    assert session.get(Delivery, delivery_id).claim_token is None
    session.close()


def test_stale_worker_cannot_overwrite_new_owner():
    database_url, factory, session, delivery_id = _worker_fixture()

    def handler(_request):
        probe = factory()
        try:
            probe.query(Delivery).filter(Delivery.id == delivery_id).update(
                {Delivery.claim_token: "new-owner"}, synchronize_session=False
            )
            probe.commit()
        finally:
            probe.close()
        return httpx.Response(200)

    stats = process_due_deliveries(
        session,
        Settings(database_url=database_url, redis_url=""),
        RateLimiter(),
        httpx.Client(transport=httpx.MockTransport(handler)),
        claim_token="old-owner",
    )
    row = session.get(Delivery, delivery_id)
    assert stats["stale"] == 1
    assert row.status == "queued"
    assert row.attempts == 0
    assert row.claim_token == "new-owner"
    session.close()


def test_worker_blocks_private_destination_even_with_test_transport():
    database_url, _factory, session, delivery_id = _worker_fixture("http://127.0.0.1/admin")
    sent = []

    def handler(_request):
        sent.append(True)
        return httpx.Response(200)

    stats = process_due_deliveries(
        session,
        Settings(database_url=database_url, redis_url=""),
        RateLimiter(),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert sent == []
    assert stats["retrying"] == 1
    assert "private webhook destinations" in session.get(Delivery, delivery_id).last_error
    session.close()


def test_permanent_client_failure_skips_retry_schedule():
    database_url, _factory, session, delivery_id = _worker_fixture()
    stats = process_due_deliveries(
        session,
        Settings(database_url=database_url, redis_url="", max_attempts=5),
        RateLimiter(),
        httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(422))),
    )
    row = session.get(Delivery, delivery_id)
    assert stats["dlq"] == 1
    assert row.status == "dlq"
    assert row.attempts == 1
    session.close()
