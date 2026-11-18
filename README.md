# HookFlow

Webhooks that survive a flaky receiver.

Events are persisted before delivery, then sent signed with backoff, idempotency keys, per-endpoint rate limits, and a dead-letter queue with one-click replay. A failing consumer becomes a retry instead of a lost event.

Python · FastAPI · PostgreSQL · Redis · Next.js

## Run

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
python -m app.worker
```

`docker compose -f docker/docker-compose.yml up --build` starts the full stack, including the dashboard.

## Test

```bash
python -m pytest
```

Design notes live in [docs](docs/architecture.md).
