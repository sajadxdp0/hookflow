# HookFlow dashboard

The HookFlow operator console for monitoring webhook deliveries, managing
endpoints and responding to failures. It is a server-rendered Next.js app that
talks to the HookFlow API; it does not mock operational data.

## Security model

The dashboard holds a privileged tenant API key and can call admin routes when
configured. Three boundaries keep those credentials server-side:

- `HOOKFLOW_API_KEY`, `HOOKFLOW_ADMIN_TOKEN` and `HOOKFLOW_TENANT_ID` are read
  only in server components, server actions and `lib/hookflow.ts`. Never import
  that client into a `"use client"` module or expose these values through
  `NEXT_PUBLIC_*`.
- Operational pages use `cache: "no-store"`. Mutations use server actions, not
  browser-side API requests.
- The Next.js `proxy.ts` access gate protects every non-static route with HTTP
  Basic authentication. Credential digests are compared with a constant-time
  Web Crypto byte loop.

**TLS is mandatory in production.** The dashboard does not terminate TLS.
Terminate HTTPS at a trusted reverse proxy or load balancer and forward the
`Authorization` header. HTTP Basic credentials are otherwise exposed in transit.

`DASHBOARD_PASSWORD` has no fallback. If it is absent, the dashboard returns
503 and fails closed in every environment. It is mandatory in production.
`DASHBOARD_USERNAME` defaults to `admin` when unset.

## Local development
Use Node.js 22 or newer. From this directory:

```bash
cp .env.example .env.local
# Fill in HOOKFLOW_API_KEY and choose DASHBOARD_PASSWORD.
npm ci
npm run dev
```

Open <http://localhost:3000> and authenticate with the configured dashboard
username and password. The API must be reachable at `HOOKFLOW_API_URL`.

For a production-style local run, set `HOOKFLOW_ENVIRONMENT=production`, supply
a strong `DASHBOARD_PASSWORD`, and put HTTPS in front of the app.

## Configuration

| Variable | Required | Purpose |
|---|---|---|
| `HOOKFLOW_API_URL` | no | API origin; defaults to `http://localhost:8000` |
| `HOOKFLOW_API_KEY` | **yes** | Tenant API key. Server-side only. |
| `HOOKFLOW_ENVIRONMENT` | no | `development` (default) or `production`; production requires a dashboard password |
| `DASHBOARD_USERNAME` | no | Basic-auth username; defaults to `admin` |
| `DASHBOARD_PASSWORD` | production | Basic-auth password; absent in production fails closed |
| `HOOKFLOW_ADMIN_TOKEN` | no | Admin token used to list and revoke API keys |
| `HOOKFLOW_TENANT_ID` | with admin token | Tenant whose keys are displayed |

Both `HOOKFLOW_ADMIN_TOKEN` and `HOOKFLOW_TENANT_ID` must be set to enable key
management. The API's `INGEST_RATE_LIMIT_PER_MINUTE` and
`MAX_ENDPOINTS_PER_TENANT` settings are enforced by the API, not this dashboard.

## Operator flows

| Route | Capabilities |
|---|---|
| `/` | Queue depth, outcomes, p95 latency, readiness and recent deliveries |
| `/endpoints` | Create, edit URL/rate limit, enable/disable, rotate secret, delete |
| `/deliveries` | Filter by status and replay dead-lettered deliveries |
| `/dlq` | Investigate exhausted deliveries and return them to the queue |
| `/keys` | Inspect key prefixes and revoke active tenant keys |
| `/metrics` | Read parsed Prometheus samples and raw exposition |

Endpoint creation and secret rotation return a plaintext signing secret exactly
once. Copy it into a secret manager before dismissing the panel. Rotation
invalidates the previous secret immediately; update the receiver before sending
more events.

Deletion asks for confirmation and is refused with `409` while an endpoint has
queued or retrying deliveries. Replay is accepted only for `dlq` deliveries.
Revoking an API key is immediate and cannot be undone. The UI identifies the key
currently configured as the dashboard credential and warns before revoking it.

## Docker

The Dockerfile uses a Node 22 multi-stage build with `npm ci`, standalone Next
output and a non-root runtime user. Build with the repository root as context:

```bash
docker build -f dashboard/Dockerfile -t hookflow-dashboard .
docker run --rm -p 3000:3000 --env-file dashboard/.env.local hookflow-dashboard
```

The image listens on port 3000. Set `HOOKFLOW_ENVIRONMENT=production` and provide
`DASHBOARD_PASSWORD` at runtime. Publish it only behind HTTPS.

## Checks

```bash
npm run typecheck
npm run build
```
