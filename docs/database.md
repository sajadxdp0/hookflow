# HookFlow database guide

HookFlow uses SQLite for local development and tests and PostgreSQL for production (`postgresql+psycopg://user:password@host:5432/hookflow`). PostgreSQL 15 is the reference deployment version used by the development stack.

Schema is owned by Alembic. The application does not call `create_all` at boot: implicit DDL lets replicas race and hides missing migrations. Apply schema as a one-shot deployment step.

```bash
uv run alembic upgrade head
uv run alembic check
uv run alembic downgrade base  # destructive; use only in a disposable database
```

`alembic.ini` does not hard-code a database URL. `migrations/env.py` reads the same `DATABASE_URL` setting as the application, so schema and runtime should not silently target different databases.

## Tables in 0.2.0

| Table | Important columns |
|---|---|
| `tenants` | `id`, unique `name`, `created_at` |
| `api_keys` | `id`, `tenant_id`, unique `key_prefix`, `key_hash`, `label`, `created_at`, `last_used_at`, `revoked_at` |
| `endpoints` | `id`, `tenant_id`, `url`, encrypted `secret`, `rate_limit_per_minute`, `enabled`, `created_at` |
| `events` | `id`, `endpoint_id`, nullable `idempotency_key`, raw JSON `payload`, `created_at` |
| `deliveries` | `id`, `event_id`, `endpoint_id`, `status`, `attempts`, `next_attempt_at`, `last_status_code`, `last_error`, `latency_ms`, `claim_token`, `claimed_at`, `created_at`, `updated_at` |

`endpoints.enabled` is a non-null boolean and defaults to true. Existing endpoints remain enabled when the 0.2.0 migration is applied.

`endpoints.secret` is `TEXT`, not a narrow `VARCHAR`: it contains a Fernet envelope (`enc:v1:<token>`), which is longer than the original plaintext hex secret. PostgreSQL enforces string widths that SQLite ignores.

Delivery statuses are:

- `queued`: eligible for dispatch when due and the endpoint is enabled.
- `retrying`: a prior attempt failed; `next_attempt_at` controls the next eligible time.
- `success`: the receiver returned `2xx`.
- `dlq`: retries are exhausted or an unrecoverable delivery condition occurred; explicit requeue is required.

## Constraints and indexes

- `UNIQUE(endpoint_id, idempotency_key)` prevents concurrent duplicate acceptance. `NULL` keys are exempt in both SQLite and PostgreSQL. Application logic compares payloads so a reused key with different content returns `409` rather than a false deduplication.
- `INDEX deliveries(status, next_attempt_at)` supports the worker's due-row query.
- `INDEX deliveries(claim_token, claimed_at)` supports live and expired lease predicates.
- `INDEX deliveries(endpoint_id, created_at)` and `INDEX deliveries(event_id)` support history and event inspection.
- `INDEX events(endpoint_id, created_at)` supports endpoint history.
- `INDEX endpoints(tenant_id)` and `INDEX api_keys(tenant_id)` support tenant-scoped access.
- `UNIQUE api_keys.key_prefix` makes bearer-key lookup an indexed single-row operation.
- `UNIQUE tenants.name` prevents ambiguous tenant provisioning.
- Tenant, endpoint, event, and delivery foreign keys use cascading deletion where ownership requires it.

## Ownership and deletion

Every endpoint belongs to a tenant. Events belong to endpoints, and deliveries reference both an event and an endpoint. Tenant-owned queries must filter by `tenant_id`; a resource from another tenant is indistinguishable from a missing one and returns `404`.

Deleting an endpoint cascades to its events and deliveries. The API refuses deletion with `409` while any queued or retrying deliveries remain. Successfully deleted endpoint history cannot be recovered through the API; export required records first.

There is no automatic retention or pruning policy. Operators must define retention for event payloads, delivery errors, and dead letters.

## Migration history

| Revision | Change |
|---|---|
| `68f2ffddab42` | Initial `endpoints`, `events`, and `deliveries` schema. |
| `5d66ae57cfaa` | Widened `endpoints.secret` to `TEXT` for Fernet envelopes. |
| `867af545e9dd` | Added worker claim fields and their index. |
| `6c7e46e98ca0` | Added `tenants` and `api_keys`; backfilled endpoints onto a `legacy` tenant and enforced tenant ownership. |
| 0.2.0 migration | Added endpoint lifecycle support, including `enabled`. |

The tenant migration is intentionally hand-written. It adds the ownership column as nullable, creates the legacy tenant, backfills existing endpoints, then adds the foreign key and enforces `NOT NULL`. Autogenerate can infer DDL but cannot design safe data backfills.

## One-shot migrations

Run migrations before rolling application or worker replicas:

```bash
uv run alembic upgrade head
```

Do not let every replica migrate at startup. A dedicated deployment job or init container should apply the chain exactly once and fail the release if it cannot reach the head revision. `/ready` returns `503` when the schema is missing or unreachable.

For rolling releases, make schema changes compatible with the previous application version. Additive, defaulted changes are safer than immediate drops or type changes. Test both upgrade and rollback paths in a disposable copy of production-like data.

## SQLite is not PostgreSQL

SQLite is useful for fast tests, but it differs from production in important ways:

- Foreign keys are disabled by default; HookFlow enables `PRAGMA foreign_keys=ON` for each SQLite connection.
- `VARCHAR` length constraints are not enforced, which previously hid a secret-envelope truncation bug that failed on PostgreSQL.
- Locking and concurrent writer behavior differ. PostgreSQL claim tests are required evidence for replica-safe workers.
- Timestamp and transaction semantics should be verified against PostgreSQL before release.

Run migration and correctness checks against PostgreSQL and Redis before merging changes that affect schema, claims, idempotency, or quotas.

## Adding a migration

```bash
uv run alembic revision --autogenerate -m "describe the schema change"
```

Review the generated file before committing. Add explicit backfills, constraints, and indexes when needed, then verify upgrade, application behavior, and downgrade on disposable data:

```bash
uv run alembic upgrade head
uv run alembic check
uv run pytest
```

CI should reject model/migration drift. Never edit an already-applied production migration in place; add a new revision instead.
