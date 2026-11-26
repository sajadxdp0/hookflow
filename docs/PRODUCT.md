# HookFlow product guide

HookFlow 0.2.0 is a self-hosted webhook and event delivery service for backend teams. It separates event acceptance from receiver availability: producers get a durable acknowledgment, while a worker handles signing, retries, rate limits, and delivery history.

## Who it is for

Use HookFlow when a producer cannot safely call a customer receiver inline because receivers time out, return errors, deploy mid-request, or need a replayable audit trail. Typical users are platform teams adding outbound webhooks to an existing product.

HookFlow is infrastructure software, not a hosted service. The operator supplies PostgreSQL, Redis, TLS termination, backups, monitoring, and receiver access policy.

## Core workflow

1. An administrator provisions a tenant and API key through the token-guarded admin API.
2. The tenant registers a public HTTP(S) endpoint. HookFlow returns its signing secret once.
3. The producer posts an event with an endpoint ID and an idempotency key.
4. HookFlow commits the event and initial delivery before returning `201`, then wakes a worker through Redis when available.
5. The worker validates the destination, signs the raw JSON body, and sends the request.
6. Successful deliveries are recorded; failures retry with backoff and eventually move to the DLQ.
7. Operators inspect history and replay only dead-lettered deliveries.

## Capabilities

- **Durable acceptance:** committed events survive Redis loss, API restarts, and worker crashes.
- **At-least-once delivery:** leased workers, bounded retries, and explicit dead-letter replay.
- **HMAC-SHA256 signing:** per-endpoint secrets over exact outbound bytes, encrypted at rest with Fernet.
- **Idempotent ingest:** endpoint-scoped keys return the original event; conflicting payloads return `409`.
- **Tenant isolation:** API keys resolve to one tenant, and cross-tenant identifiers return `404`.
- **Endpoint lifecycle:** enabled state, URL and rate-limit updates, secret rotation, and guarded deletion.
- **Abuse controls:** per-tenant ingest quota, per-endpoint delivery quota, payload limits, and an endpoint cap.
- **Safe egress:** public destinations only, delivery-time IP checks, and no redirect following.
- **Operator tooling:** delivery history, queue statistics, readiness, Prometheus-format counters, and a server-rendered dashboard.

## API surface

| Route | Purpose |
|---|---|
| `POST /v1/admin/tenants` | Create a tenant; requires the admin token. |
| `POST /v1/admin/tenants/{id}/keys` | Create a tenant API key; plaintext returned once. |
| `POST /v1/endpoints` | Create an endpoint; secret returned once. |
| `GET /v1/endpoints` | List tenant endpoints without secrets. |
| `PATCH /v1/endpoints/{id}` | Update URL, delivery rate limit, or enabled state. |
| `POST /v1/endpoints/{id}/rotate-secret` | Replace the signing secret; plaintext returned once. |
| `DELETE /v1/endpoints/{id}` | Delete an idle endpoint; `409` if queued/retrying work exists. |
| `POST /v1/events` | Durably accept an event and create its delivery. |
| `GET /v1/events/{id}` | Inspect an event, payload, and delivery history. |
| `GET /v1/deliveries` | List tenant deliveries with status and endpoint filters. |
| `POST /v1/deliveries/{id}/requeue` | Replay a `dlq` delivery; other states return `409`. |
| `GET /v1/stats` | Tenant-scoped counts by status and queue depth. |

Tenant API routes use `Authorization: Bearer <api-key>`. Admin routes use `X-Admin-Token`. See the [README](../README.md#api-examples) for complete curl and signature-verification examples.

## Delivery behavior

The default policy makes five attempts. Retry delays are 60 seconds, 5 minutes, 30 minutes, 2 hours, and 12 hours. A receiver `2xx` marks success. Network errors, timeouts, `5xx`, and `408`/`409`/`425`/`429` retry; other `4xx` responses dead-letter immediately. Exhausted deliveries remain queryable in the DLQ.

Requeue resets the attempt count. It is intentionally unavailable for already successful or currently active deliveries. Disabled endpoints are not dispatched, and an endpoint cannot be deleted while queued or retrying deliveries exist.

## Operational contract

- Use PostgreSQL in production and apply Alembic migrations once before rolling replicas.
- Configure Redis for replica-safe ingest and delivery quotas. Without it, each process has an independent counter budget; database polling still recovers deliveries.
- Set `HOOKFLOW_ENVIRONMENT=production`, a real `SECRET_ENCRYPTION_KEY`, and a strong `HOOKFLOW_ADMIN_TOKEN`.
- Terminate TLS at the API and dashboard boundary.
- Permit worker egress to public HTTP(S) receivers only.
- Back up PostgreSQL and the encryption key together. One-time API keys and endpoint secrets cannot be retrieved later.
- Restrict operational routes and the dashboard to trusted networks or an identity-aware gateway.

The default ingest quota is 600 requests per tenant per minute, and the default endpoint cap is 100. Rejected ingest requests return `429` with `Retry-After`.

## Receiver responsibilities

HookFlow guarantees at-least-once delivery, not exactly-once effects or ordering. A receiver should:

1. Verify `X-Hookflow-Signature` against the raw body before parsing.
2. Reject invalid signatures.
3. Deduplicate side effects using the HookFlow event ID or a stable business key.
4. Acknowledge only after it has durably accepted the work.
5. Return success promptly and perform slow work asynchronously.

## Dashboard

The Next.js dashboard provides server-rendered views for endpoints, delivery history, DLQ replay, API keys, metrics, and readiness. `HOOKFLOW_API_KEY` and `HOOKFLOW_ADMIN_TOKEN` stay in the server environment and must never use a `NEXT_PUBLIC_` prefix.

Every non-static dashboard route is protected by a fail-closed HTTP Basic gate using `DASHBOARD_USERNAME` and `DASHBOARD_PASSWORD`. TLS is mandatory outside loopback development. This is a single operator access gate, not per-user identity or role-based authorization.

## Limitations and roadmap direction

- No exactly-once delivery, global ordering, or delivery SLO.
- No API-key expiry, per-operator admin identity, role-based access, or admin audit trail.
- No automatic retention, managed high availability, built-in TLS, or automatic disaster recovery.
- Process-local metrics and unauthenticated operational routes require external controls.
- SQLite is not supported for production.

Likely future investments include group commit for ingest throughput, key expiry and operator identity, managed retention controls, and current-release concurrency and end-to-end delivery benchmarks. These are directions, not shipped guarantees.

## Documentation

- [Architecture](architecture.md)
- [Security model](security.md)
- [Deployment](deployment.md)
- [Database and migrations](database.md)
- [Historical performance](performance.md)
- [Contributing](../CONTRIBUTING.md)
- [Changelog](../CHANGELOG.md)
