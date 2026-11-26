# Contributing to HookFlow

Thanks for helping improve HookFlow. The project values correctness, clear operational behavior, and small, reviewable changes.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md). Report suspected security vulnerabilities privately as described in [SECURITY.md](SECURITY.md), not in a public issue.

## Prerequisites

- Python 3.11 or newer.
- [uv](https://docs.astral.sh/uv/) for Python dependencies.
- Docker Compose for PostgreSQL and Redis integration work.
- Node.js 22 and npm for dashboard changes.

## Set up

```bash
git clone https://github.com/sajadxdp0/hookflow.git
cd hookflow
uv sync --extra dev
cp .env.example .env
uv run alembic upgrade head
```

Run the API and worker in separate terminals:

```bash
uv run uvicorn app.main:app --reload
```

```bash
uv run python -m app.worker
```

Local development uses SQLite and database polling by default. Set `HOOKFLOW_ADMIN_TOKEN` in `.env` before exercising tenant and API-key provisioning. Never use the development encryption key with real data.

## Repository map

| Path | Purpose |
|---|---|
| `app/` | FastAPI routes, authentication, persistence, worker, signing, quotas, and configuration. |
| `migrations/` | Alembic schema history; schema changes belong here. |
| `tests/` | API, correctness, concurrency, crypto, and integration tests. |
| `dashboard/` | Next.js operator UI; API credentials are server-only. |
| `docker/` | Development Docker image and Compose stack. |
| `docs/` | Product, architecture, security, deployment, database, and performance guides. |
| `assets/` | Original HookFlow branding assets. |

## Tests and checks

The fast default suite uses SQLite:

```bash
uv run pytest
```

Run a focused module while iterating:

```bash
uv run pytest tests/test_api.py
```

Before opening a pull request, run the relevant tests plus migration drift detection:

```bash
uv run alembic upgrade head
uv run alembic check
uv run pytest
```

For production-engine behavior, start the dependencies and use a dedicated test database:

```bash
docker compose -f docker/docker-compose.yml up -d postgres redis
```

```bash
HOOKFLOW_TEST_DATABASE_URL=postgresql+psycopg://hookflow:hookflow@localhost:5432/hookflow \
REDIS_URL=redis://localhost:6379/0 \
uv run pytest
```

`HOOKFLOW_TEST_DATABASE_URL` must point to a disposable database: the test fixtures reset schema and data. Do not use a development or production database.

For dashboard changes:

```bash
cd dashboard
npm ci
npm run typecheck
npm run build
```

Do not weaken or delete assertions to make a change pass. If a test is flaky, explain the race and fix it rather than adding sleeps or retries around the assertion.

## Change conventions

- Keep changes focused; do not mix unrelated refactors with a feature or bug fix.
- Preserve the shared API contract and existing response shapes unless the change explicitly updates the contract and all callers.
- Add regression tests for new behavior, error paths, and concurrency-sensitive logic.
- Any model change requires an Alembic migration and a successful `alembic check`.
- Test PostgreSQL for changes involving constraints, locking, claims, timestamps, or cascading deletes.
- Use Redis tests for changes involving wake-ups or shared quotas.
- Never put credentials, real customer payloads, or absolute developer paths in source, tests, screenshots, or documentation.
- Keep endpoint secrets out of endpoint responses after one-time creation or rotation.
- Keep `HOOKFLOW_API_KEY` and `HOOKFLOW_ADMIN_TOKEN` in dashboard server code. Never prefix them with `NEXT_PUBLIC_` or import the server API client into a client component.

## Documentation and release notes

Update the relevant guide under `docs/` and add a concise [CHANGELOG.md](CHANGELOG.md) entry for user-visible changes. Configuration changes must update `.env.example`, the README configuration table, and the deployment guide.

When documenting reliability or security, state the actual guarantee and its boundary. In particular:

- Delivery is at-least-once; receivers must deduplicate.
- PostgreSQL is the source of truth; Redis wake-ups are best effort.
- Redis is required for replica-safe quotas.
- Public HTTP(S) destinations only; redirects are disabled.
- TLS termination, backups, retention, and high availability are operator responsibilities.

## Pull requests

Use the [pull-request template](.github/PULL_REQUEST_TEMPLATE.md). Include the problem, the approach, test evidence, and any migration or configuration impact. Link the issue when one exists. Screenshots are helpful for dashboard changes; redact tokens and customer data.

Maintainers may ask for smaller commits, additional tests, or documentation changes before merging. Review feedback in good faith and keep the discussion technical.

## Reporting issues

- Use the [bug report form](.github/ISSUE_TEMPLATE/bug_report.yml) for reproducible defects.
- Use the [feature request form](.github/ISSUE_TEMPLATE/feature_request.yml) for proposed behavior.
- Use [private vulnerability reporting](https://github.com/sajadxdp0/hookflow/security/advisories/new) for security concerns.
