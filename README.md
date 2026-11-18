# HookFlow

Webhook delivery that survives failures.

HookFlow accepts events durably before any delivery attempt, then dispatches them as signed requests with retries. A flaky receiver becomes a scheduled retry instead of a lost event, and every attempt stays visible in the dashboard.

## Features

- Persist-first ingest with atomic event and delivery rows
- HMAC-SHA256 signatures and Fernet-encrypted endpoint secrets
- Claim-and-lease worker with expired-lease recovery
- Exponential backoff, idempotency keys, and per-endpoint rate limits
- Dead-letter queue with delivery history and one-click replay
- Next.js dashboard for endpoints, deliveries, the DLQ, and metrics

## Stack

Python · FastAPI · PostgreSQL · Redis · Next.js

## Quick start

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
python -m app.worker
```

Run `docker compose -f docker/docker-compose.yml up --build` for the full stack.

## Tests

```bash
python -m pytest
```

## Documentation

[Architecture](docs/architecture.md) · [Database](docs/database.md) · [Security](docs/security.md) · [Deployment](docs/deployment.md)
