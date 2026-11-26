# HookFlow deployment guide

HookFlow 0.2.0 supports Python 3.11+ and uses uv for dependency management. This guide covers local development and the minimum controls expected for a production deployment.

## Production requirements

| Concern | Requirement |
|---|---|
| Database | PostgreSQL. SQLite is only for local development and tests. |
| Redis | Required for replica-safe ingest quotas and per-endpoint delivery limits; also provides best-effort wake-ups. |
| Egress | Workers may call public HTTP(S) destinations only. Private, loopback, link-local, and reserved addresses are blocked; redirects are disabled. |
| Ingress | Terminate TLS at a trusted reverse proxy or load balancer for both API and dashboard. |
| Schema | Run `alembic upgrade head` once per release before rolling application or worker replicas. |
| Secrets | Supply a production `SECRET_ENCRYPTION_KEY` and a strong `HOOKFLOW_ADMIN_TOKEN`; keep them out of images and source control. |
| Backups | Back up PostgreSQL and the encryption key together; test restoration. |
| Receivers | Must tolerate at-least-once delivery and deduplicate side effects. |

The worker needs outbound access to customer receivers, not to private networks. Give PostgreSQL and Redis private network reachability from the API and workers instead.

## Local development with uv

```bash
uv sync --extra dev
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Run the worker in another terminal:

```bash
uv run python -m app.worker
```

The default SQLite database needs no external service. Redis can be omitted locally; workers poll the database and quota counters remain process-local. Set `HOOKFLOW_ADMIN_TOKEN` before calling the provisioning routes.

## Docker development stack

```bash
docker compose -f docker/docker-compose.yml up --build -d app worker
```

This starts PostgreSQL 15, Redis 7, the API on port 8000, and a worker. The database and Redis ports are published for local debugging. Compose uses development credentials and does not terminate TLS. It is not a production deployment template.

Application and worker services intentionally do not run migrations at startup. Compose's one-shot `migrate` service must complete successfully before dependent services start.

## Configuration reference

| Variable | Default | Production guidance |
|---|---|---|
| `HOOKFLOW_ENVIRONMENT` | `development` | Set to `production`. |
| `DATABASE_URL` | `sqlite:///./hookflow.db` | Use `postgresql+psycopg://user:password@host:5432/hookflow` with managed credentials. |
| `REDIS_URL` | empty | Configure a private Redis endpoint for shared quotas. |
| `SECRET_ENCRYPTION_KEY` | empty | Required in production; empty selects the published development key. |
| `HOOKFLOW_ADMIN_TOKEN` | empty | Required to enable admin provisioning; use a strong random secret. |
| `INGEST_RATE_LIMIT_PER_MINUTE` | `600` | Per-tenant fixed-window quota. |
| `MAX_ENDPOINTS_PER_TENANT` | `100` | Per-tenant endpoint cap. |
| `DEFAULT_RATE_LIMIT_PER_MINUTE` | `60` | Default per-endpoint delivery quota. |
| `MAX_BODY_BYTES` | `262144` | Maximum serialized payload size. |
| `DELIVERY_TIMEOUT_SECONDS` | `10.0` | Per-attempt outbound timeout. |
| `CLAIM_LEASE_SECONDS` | `60.0` | Keep above the delivery timeout with margin for scheduler delays. |
| `MAX_ATTEMPTS` | `5` | Total attempts before DLQ. |
| `BACKOFF_SCHEDULE_SECONDS` | `[60,300,1800,7200,43200]` | Retry delays; last value repeats when exhausted. |

Generate production secrets and immediately store the output in a secret manager:

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
openssl rand -hex 32
```

Use a secret manager to inject values. Do not commit `.env`, bake secrets into images, or pass them as command-line arguments in process listings.

## Release procedure

1. **Back up.** Take a PostgreSQL snapshot and confirm the encryption key is recoverable.
2. **Migrate once.** Run `alembic upgrade head` as a dedicated deployment job or init container against the release's schema.
3. **Verify readiness.** Start a canary API with production configuration and start a worker. Require the API's `/ready` to return `200` with `secret_encryption: ok`, and confirm the worker can claim due deliveries.
4. **Roll out.** Roll API and worker replicas independently. Keep enough old workers running to drain accepted deliveries during a rolling update.
5. **Observe.** Watch readiness failures, ingest `429` rates, queue depth, DLQ growth, Redis health, and worker restarts.
6. **Roll back carefully.** Application rollback does not revert schema automatically. Use a migration tested for the prior application version; do not run `alembic downgrade` as a reflexive production rollback.

Migrations must be forward-compatible with rolling deploys: add nullable or defaulted columns before code starts writing them, and remove old assumptions only in a later release.

## First-run provisioning

Start the API with `HOOKFLOW_ADMIN_TOKEN` set, then create a tenant and key:

```bash
export HOOKFLOW_URL="https://hookflow.example.com"
read -rsp "Admin token: " HOOKFLOW_ADMIN_TOKEN; echo
export HOOKFLOW_ADMIN_TOKEN

TENANT_ID=$(curl -fsS -X POST "$HOOKFLOW_URL/v1/admin/tenants" \
  -H "X-Admin-Token: $HOOKFLOW_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"acme"}' | jq -er '.id')

curl -fsS -X POST "$HOOKFLOW_URL/v1/admin/tenants/$TENANT_ID/keys" \
  -H "X-Admin-Token: $HOOKFLOW_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"label":"production"}'
```

The plaintext API key is shown once. Store it immediately. The tenant endpoint then returns the endpoint signing secret once; give that secret to the receiver and keep it out of logs.

## Dashboard

The dashboard is protected by a fail-closed HTTP Basic access gate. Configure `dashboard/.env.local` for a source deployment, or the dashboard service environment for Compose:

| Variable | Default | Purpose |
|---|---|---|
| `DASHBOARD_USERNAME` | `admin` | Basic access username. |
| `DASHBOARD_PASSWORD` | unset | Required Basic access password; access fails closed when missing. |
| `HOOKFLOW_API_URL` | `http://localhost:8000` | API origin used by the Next.js server. |
| `HOOKFLOW_API_KEY` | unset | Tenant API key for tenant-scoped views. |
| `HOOKFLOW_TENANT_ID` | unset | Tenant whose API keys are displayed. |
| `HOOKFLOW_ADMIN_TOKEN` | unset | Optional dashboard-side admin credential for API-key management; use the API's admin token. |

`HOOKFLOW_API_URL`, `HOOKFLOW_API_KEY`, `HOOKFLOW_TENANT_ID`, and the dashboard's copy of `HOOKFLOW_ADMIN_TOKEN` are dashboard-only settings. The API and worker do not read them. The API separately needs its own admin-token setting to guard provisioning.

```bash
cd dashboard
cp .env.example .env.local
npm ci
npm run build
npm start
```

Never use a `NEXT_PUBLIC_` prefix for any dashboard credential. In production, serve the dashboard only over **HTTPS** behind a TLS-terminating proxy; HTTP Basic credentials must not cross an untrusted network in plaintext. Direct HTTP is appropriate only for loopback development. Restrict the dashboard origin to operators even though the Basic gate is enabled.

For Compose, set `HOOKFLOW_API_KEY` and `HOOKFLOW_TENANT_ID` in the shell, provide a strong `DASHBOARD_PASSWORD`, and enable the `dashboard` profile from the repository root:

```bash
read -rsp "Dashboard password: " DASHBOARD_PASSWORD; echo
export DASHBOARD_PASSWORD
docker compose -f docker/docker-compose.yml --profile dashboard up --build -d dashboard
```

`DASHBOARD_PASSWORD` is required for the dashboard Compose profile, and `DASHBOARD_USERNAME` defaults to `admin`. Compose publishes the dashboard on port 3000 without TLS; place it behind an HTTPS reverse proxy before exposing it beyond localhost.

## Health and monitoring

| Route | Meaning |
|---|---|
| `/health` | Process liveness only. |
| `/ready` | Database and schema reachable, Redis reachable when configured, encryption posture reported. |
| `/metrics` | Prometheus-text process counters; unauthenticated and reset on restart. |
| `/v1/stats` | Tenant-scoped delivery counts and queue depth. |

Recommended alerts:

- `/ready` failing on any API replica.
- Queue depth or oldest `retrying` age growing beyond your delivery objective.
- DLQ count increasing without operator action.
- Worker process restarts or repeated outbound validation failures.
- Redis errors or memory pressure.
- PostgreSQL connection saturation, slow commits, or backup failures.

Restrict `/metrics` and `/ready` at the proxy if their status details should not be public. Route logs should retain `X-Request-ID` and delivery IDs for investigation, with credentials and payloads redacted.

## Backup and recovery

- **Database:** use PostgreSQL automated snapshots plus a tested point-in-time recovery procedure. Record the backup time and application version.
- **Encryption key:** store `SECRET_ENCRYPTION_KEY` separately with equivalent durability and access control. A database restore without the key cannot sign future deliveries.
- **API keys:** plaintext keys are unrecoverable after creation. Keep issued keys in a secret manager; if lost, revoke and create a replacement.
- **Endpoint secrets:** receivers must retain their copy. If a receiver loses it, rotate the endpoint secret and update the receiver.
- **Redis:** contains wake-up hints and limiter counters. It can be rebuilt; flushing it may temporarily increase polling latency and resets fixed-window counters.

Restore into an isolated environment first, run readiness checks, then route traffic. HookFlow does not automate cross-region failover or backup verification.

## Scaling and availability

Multiple API and worker replicas are supported. PostgreSQL row claims keep concurrent workers from holding the same live delivery; expired leases recover crashed work. Configure Redis before scaling beyond one replica so quotas are shared.

Each worker still performs outbound requests and PostgreSQL updates. Size the worker pool against receiver limits and database capacity, not only event ingest rate. PostgreSQL remains a shared dependency; high availability, failover, and connection pooling topology are operator responsibilities.

## Data lifecycle

HookFlow has no automatic retention job. Define and operate a retention policy for `events` and `deliveries` that meets your privacy and audit needs. Endpoint deletion cascades to event and delivery history, but returns `409` while queued or retrying deliveries exist. Export required records before deletion.
