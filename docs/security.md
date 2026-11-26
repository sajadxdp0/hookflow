# HookFlow security model

This document describes the controls in HookFlow 0.2.0, the assumptions operators must satisfy, and the boundaries that remain. It is not a certification or a guarantee against every attack.

## Security objectives

- Keep tenants isolated and prevent unauthenticated access to delivery data.
- Protect API keys and webhook signing secrets in transit and at rest.
- Prevent the worker from being used to reach private or otherwise non-public network destinations.
- Preserve accepted events and make delivery outcomes auditable.
- Keep dashboard credentials out of browser bundles.

## Authentication and tenant isolation

### Tenant API keys

Machine callers use `Authorization: Bearer hf_<prefix>_<secret>`. The plaintext key is generated from cryptographically secure random material and returned once by `POST /v1/admin/tenants/{tenant_id}/keys`.

- Only a SHA-256 digest and a short unique lookup prefix are stored. A fast hash is appropriate for high-entropy generated keys; it would not be appropriate for user-chosen passwords.
- Lookup uses the indexed prefix, and digest comparison is constant-time.
- Unknown prefixes and incorrect secrets receive the same authentication failure.
- Every authorized request resolves to one tenant. Endpoint, event, delivery, and statistics queries are tenant-scoped.
- Cross-tenant resource access returns `404`, not `403`, to avoid confirming that an identifier exists.
- Keys can be revoked with `POST /v1/admin/keys/{key_id}/revoke`; revocation is immediate for subsequent requests.

### Admin surface

Tenant creation, key creation, key listing, and key revocation require `X-Admin-Token`. If `HOOKFLOW_ADMIN_TOKEN` is unset, these routes fail closed with `503`.

The admin token is a single shared credential. HookFlow 0.2.0 does not provide separate operator identities, roles, or an audit trail of administrative changes. Restrict admin routes to a private network or an authenticated gateway, rotate the token deliberately, and do not reuse a tenant API key as the admin token.

## Webhook signatures

Each endpoint has a signing secret. The worker sends:

```text
X-Hookflow-Signature: sha256=<hex HMAC-SHA256>
```

The MAC covers the exact raw JSON bytes in the outbound request. Receivers must verify those bytes before parsing or re-serializing the body, compare with `hmac.compare_digest`, and reject missing or invalid signatures.

```python
import hashlib
import hmac

expected = "sha256=" + hmac.new(
    secret.encode("utf-8"), raw_body, hashlib.sha256
).hexdigest()
valid = hmac.compare_digest(expected, provided_signature)
```

A valid signature proves that the sender knew the endpoint secret; it does not prove exactly-once processing. Include replay windows or idempotent business logic in the receiver when the threat model requires them.

## Secret storage and rotation

Endpoint secrets are stored as Fernet envelopes (`enc:v1:<token>`), not plaintext or one-way hashes. Hashing is unsuitable because the worker must reproduce the original bytes to sign outbound requests. Fernet provides authenticated encryption; the plaintext is decrypted only when a delivery is signed.

`SECRET_ENCRYPTION_KEY` accepts a Fernet key or a passphrase that is stretched with SHA-256. Generate a real Fernet key for production:

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

If the setting is empty, HookFlow uses a published development key so local databases survive restarts. `/ready` reports `secret_encryption: development-key`; production must supply its own key. Unknown envelope versions fail loudly instead of falling back to plaintext.

Operational requirements:

- Store `SECRET_ENCRYPTION_KEY` in a managed secret store and back it up securely.
- Back up the database and encryption key together. A database backup without the key cannot decrypt endpoint secrets; losing the key can make live secrets unrecoverable.
- Endpoint secrets are disclosed once at creation and once per rotation. Keep the receiver's copy in its own secret store.
- To rotate an endpoint secret, pause the endpoint, call `POST /v1/endpoints/{id}/rotate-secret`, update the receiver, then re-enable delivery.
- Encryption-key rotation is an operator procedure. The versioned envelope leaves room for future formats, but 0.2.0 does not automate re-encryption of existing rows.

## Outbound destination controls

Endpoint URLs must use HTTP or HTTPS. The worker validates the destination at delivery time, resolving hostnames and rejecting loopback, private, link-local, multicast, unspecified, and reserved IP ranges for IPv4 and IPv6. Redirects are disabled.

This blocks common SSRF paths, including a public URL that redirects to an internal service. It does not replace network controls:

- Permit worker egress only to the public receiver destinations you intend to use.
- Keep PostgreSQL, Redis, cloud metadata endpoints, and internal services unreachable from the worker's outbound path.
- Use HTTPS for production receivers; HookFlow does not silently upgrade HTTP to HTTPS.
- Treat public hostnames as untrusted input and monitor delivery errors for repeated DNS or connection failures.

Validation happens for each attempt because DNS answers can change. The worker then pins the connection to a validated address, preserving the original Host header and TLS server name, so a second DNS lookup cannot substitute an internal address. Operators remain responsible for egress policy and for any receiver they choose to call.

## Transport and browser exposure

HookFlow does not terminate TLS. Put the API and dashboard behind a reverse proxy or load balancer that terminates TLS, uses current cipher policy, and forwards trusted client information correctly. The supplied Compose stack is local-development only and exposes plain HTTP.

The Next.js dashboard reads `HOOKFLOW_API_KEY` and optional `HOOKFLOW_ADMIN_TOKEN` only in server-side code. Never rename them with a `NEXT_PUBLIC_` prefix and never import the server API client into a client component. Browser bundles must not contain either credential.

The dashboard has no built-in end-user authentication. Protect the dashboard origin with your identity proxy or private network policy.

## Quotas, payloads, and abuse resistance

- Ingest is rate-limited per tenant, default 600 requests/minute. A rejected request receives `429` and `Retry-After`.
- Endpoint delivery is rate-limited separately, default 60 requests/minute.
- Redis is required for shared quota state across replicas. In-memory fallback gives each process its own budget.
- Serialized payloads are limited to 256 KiB by default (`MAX_BODY_BYTES`).
- A tenant can own at most 100 endpoints by default (`MAX_ENDPOINTS_PER_TENANT`).
- URL length, idempotency-key length, rate-limit bounds, and pagination bounds are validated.

These controls bound ordinary abuse; they are not a full WAF, distributed denial-of-service shield, or billing system. Apply request-size and connection limits at the edge as well.

## Reliability and audit limits

HookFlow provides delivery history, attempt counts, last status/error, latency, queue depth, and request IDs. It records technical outcomes, not the business effects performed by a receiver.

Delivery is at-least-once. A crash or lease expiry can cause a second request after the receiver already processed the first. Consumers must deduplicate. HookFlow does not guarantee global ordering, exactly-once effects, or an operator audit log.

API keys do not expire. There is no automatic data-retention or deletion policy, so payloads and delivery records remain until an operator or cascading endpoint deletion removes them. Plan retention and privacy handling before storing personal or sensitive data.

`/health`, `/ready`, and `/metrics` are unauthenticated operational routes. Readiness may reveal dependency status; metrics are process-local and reset on restart. Do not expose these routes publicly without a gateway policy.

## Data handling recommendations

- Minimize event payloads and redact secrets before ingest.
- Encrypt database volumes and backups in addition to HookFlow's endpoint-secret encryption. Event payloads themselves are not application-layer encrypted by HookFlow.
- Restrict database access to API, worker, and migration identities; use separate credentials where practical.
- Rotate compromised API keys and endpoint secrets, and review delivery history for unexpected activity.
- Set `HOOKFLOW_ENVIRONMENT=production`, require a non-development encryption key, and test readiness before routing traffic.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub's [private vulnerability reporting](https://github.com/sajadxdp0/hookflow/security/advisories/new) and follow the repository [security policy](../SECURITY.md). Include reproduction steps, affected version, impact, and any relevant logs with credentials removed.
