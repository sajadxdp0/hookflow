# HookFlow

**Persist-first webhook and event delivery with lease-based workers, HMAC signing, and a dead-letter queue.**

Webhook receivers time out, return `5xx`, or drop connections mid-deploy. Producers that POST inline lose events on transient failures and have no audit trail when a customer asks what was sent. HookFlow commits each event and its initial delivery row in one database transaction before acknowledging the request, then dispatches signed payloads asynchronously with exponential backoff, per-endpoint rate limits, and one-click dead-letter replay.

## Design notes

- **Persist before enqueue.** An ingest call returns `201` only after the `Event` and `Delivery` rows are committed in PostgreSQL. Redis is used afterward as a low-latency wake-up hint (`LPUSH`), while the worker also polls due rows—so losing Redis costs latency, never an event.
- **Database-enforced idempotency.** Callers may pass an `Idempotency-Key` header. A `UNIQUE (endpoint_id, idempotency_key)` constraint prevents duplicate acceptance under concurrent retries; the losing transaction catches the `IntegrityError` and returns the existing event.
- **Claim-and-lease workers.** Workers claim due deliveries with `FOR UPDATE SKIP LOCKED`, stamp a `claim_token` and lease expiry, and rescue rows whose worker died mid-flight once the lease expires.
- **Signed payloads, encrypted secrets.** Outbound requests carry `X-Hookflow-Signature: sha256=<hmac>`. Endpoint signing secrets are stored Fernet-encrypted at rest (not hashed, since the worker needs the raw bytes to compute the HMAC), and `/ready` flags when the process is running with the development key.

## Stack

Python 3.11 · FastAPI · SQLAlchemy & Alembic · PostgreSQL · Redis · Next.js (operator dashboard)

## Where to look

- `app/worker.py` — claim-and-lease loop, expired-lease rescue, backoff scheduling, and dead-letter transitions
- `app/events.py` — tenant-scoped endpoints, idempotent event ingest, delivery inspection, and DLQ replay
- `app/crypto.py` — HMAC-SHA256 payload signing and Fernet secret encryption at rest
- `tests/test_correctness.py` & `tests/test_claims.py` — concurrency and lease-recovery tests
- `scripts/load_test.py` — authenticated ingest benchmark

## Running locally

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env

alembic upgrade head
uvicorn app.main:app --reload
python -m app.worker
```

In development mode HookFlow runs with zero external services (SQLite and an in-process queue). For the full PostgreSQL + Redis + dashboard stack:

```bash
docker compose -f docker/docker-compose.yml up --build
```

## Testing

```bash
python -m pytest
```

75 tests pass locally (93% coverage across `app/`); 4 additional Redis integration tests run when `REDIS_URL` is set.

## Documentation

[Architecture](docs/architecture.md) · [Database](docs/database.md) · [Security](docs/security.md) · [Performance](docs/performance.md) · [Deployment](docs/deployment.md)

MIT License.
