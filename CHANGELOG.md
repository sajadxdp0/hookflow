# Changelog

All notable changes to HookFlow are documented here. The project follows [Semantic Versioning](https://semver.org/).

## [0.2.0] — 2026-11-25

A product-focused release that adds endpoint lifecycle controls, tenant ingest quotas, and stronger outbound destination safety while preserving persist-first, at-least-once delivery.

### Added

- Endpoint `enabled` state in JSON responses, with `PATCH /v1/endpoints/{id}` support for `url`, `rate_limit_per_minute`, and `enabled`.
- `POST /v1/endpoints/{id}/rotate-secret`, returning `{id, secret}` once so receivers can rotate verification secrets safely.
- `DELETE /v1/endpoints/{id}`, returning `204` and refusing deletion with `409` while queued or retrying deliveries exist.
- A configurable per-tenant endpoint cap through `MAX_ENDPOINTS_PER_TENANT` (default 100).
- Per-tenant ingest rate limiting through `INGEST_RATE_LIMIT_PER_MINUTE` (default 600), with `429` and `Retry-After` responses.
- Delivery-time public-destination validation for IPv4 and IPv6. Loopback, private, link-local, multicast, unspecified, and reserved addresses are rejected.
- Redirects disabled on outbound delivery requests.
- `HOOKFLOW_ENVIRONMENT` with `development` and `production` modes.
- An original HookFlow logo, repository social card, issue forms, pull-request checklist, security policy, and contribution guide.
- Product, architecture, security, deployment, database, and performance documentation for the 0.2.0 contract.

### Changed

- Idempotency replays now require the same payload. Reusing an endpoint-scoped key with different content returns `409` instead of silently returning the original event.
- The operator dashboard documents server-only credential handling and supports the expanded endpoint lifecycle.
- uv and the committed lockfile are the supported Python dependency workflow.
- Historical performance numbers are explicitly labeled as pre-0.2.0 measurements rather than current capacity claims.

### Fixed

- Redis queue reads no longer use an infinite blocking timeout, so due retries continue processing when no wake-up arrives.
- Worker leases are renewed immediately before each outbound request, and settlement is conditional on the claim token so stale workers cannot overwrite a new owner's result.
- Redis wake-up failures no longer turn committed events into apparent API failures; queue and limiter clients use finite timeouts, and limiter increments plus expiry are atomic.
- Request bodies are bounded before JSON parsing, non-finite JSON is rejected, and API responses include baseline security headers.
- Permanent `4xx` delivery failures dead-letter without waiting for the full retry schedule; transient client statuses still retry.
- The dashboard now fails closed behind HTTP Basic authentication and loads its global styles.
- Python and dashboard dependencies were updated to patched lockfile versions.

### Breaking changes

- `POST /v1/deliveries/{id}/requeue` now accepts only `dlq` deliveries. `queued`, `retrying`, and `success` return `409`.
- Reusing an idempotency key with a different payload returns `409`.
- Outbound delivery to non-public destinations is rejected at delivery time, and redirects are not followed.
- Production deployments must supply a non-development `SECRET_ENCRYPTION_KEY`, terminate TLS externally, use PostgreSQL, and configure Redis for replica-safe quotas.

### Security and operations

- Endpoint JSON no longer exposes signing secrets after creation or rotation.
- Production guidance now covers public egress policy, one-shot migrations, encryption-key and database backups, one-time credential handling, and receiver idempotency.
- The admin surface continues to fail closed when its token is unset.

### Known limitations

- Delivery remains at-least-once, with no exactly-once effects or global ordering guarantee.
- API keys do not expire; the admin surface has one shared token and no per-operator audit trail.
- Quota enforcement is replica-safe only when Redis is configured.
- There is no automatic retention, built-in TLS termination, managed high availability, or delivery SLO.

## [0.1.0]

Initial release with persist-first event ingest, tenant-scoped API keys, HMAC-SHA256 delivery signatures, encrypted endpoint secrets, leased workers, exponential backoff, dead-letter replay, delivery history, operational probes, and a server-rendered dashboard.
