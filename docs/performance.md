# HookFlow performance

## Historical measurements

The numbers below were measured on 2026-09-27, before HookFlow 0.2.0. They are preserved as historical ingest data, not as a current benchmark, capacity commitment, or SLO. The 0.2.0 ingest quota, endpoint lifecycle, and destination validation paths have not been measured here.

The original environment used a single machine, a 1 KB payload, and one sequential client. Results came from two PostgreSQL runs and two PostgreSQL-plus-Redis runs.

## Historical method

`scripts/load_test.py` drives the ASGI application in-process with `fastapi.testclient`. It measures application logic and database cost, but excludes:

- HTTP server, socket, and TLS overhead.
- Concurrent clients and lock contention.
- Worker outbound delivery.
- Multi-replica behavior.
- The ingest quota and endpoint lifecycle controls added in 0.2.0.

The RPS column therefore means completed sequential requests per second for one waiting client, not maximum throughput.

To rerun the load script against the current code, use uv and the same database topology:

```bash
docker compose -f docker/docker-compose.yml up -d postgres redis

# SQLite
uv run python scripts/load_test.py --events 500

# PostgreSQL
uv run python scripts/load_test.py --events 2000 \
  --database-url postgresql+psycopg://hookflow:hookflow@localhost:5432/hookflow

# PostgreSQL + Redis wake-up
uv run python scripts/load_test.py --events 2000 \
  --database-url postgresql+psycopg://hookflow:hookflow@localhost:5432/hookflow \
  --redis-url redis://localhost:6379/0
```

Any new result should record date, commit, hardware, database configuration, payload size, concurrency, and whether the worker was running.

## Historical results

1 KB payload, sequential single client:

| Engine | Events | RPS | p50 | p95 | p99 | mean |
|---|---:|---:|---:|---:|---:|---:|
| SQLite (file) | 500 | 112.3 | 7.5ms | 18.9ms | 24.5ms | 8.9ms |
| PostgreSQL 15 | 2000 | 52.1 | 18.5ms | 34.0ms | 40.0ms | 19.2ms |
| PostgreSQL 15 | 2000 | 53.9 | 17.1ms | 34.1ms | 41.6ms | 18.6ms |
| PostgreSQL + Redis | 1500 | 48.3 | 19.9ms | 34.8ms | 42.7ms | 20.7ms |
| PostgreSQL + Redis | 1500 | 55.3 | 16.5ms | 35.3ms | 40.8ms | 18.1ms |

## Interpretation

In that historical setup, PostgreSQL committed roughly twice as slowly as local-file SQLite. Ingest performs one durable transaction per event, and PostgreSQL's default synchronous commit made the commit, rather than the query, the dominant cost. This does not make SQLite an appropriate production database.

Redis wake-ups added little relative to the durable commit: the historical PostgreSQL runs were approximately 48–55 RPS with Redis and 52–54 RPS without. The architectural conclusion remains that Redis is an optimization; PostgreSQL polling is the recovery path.

The main throughput lever is durable commit latency. Possible future work includes group commit or asynchronous batching. Disabling synchronous commit would trade crash durability for latency and is not compatible with HookFlow's persist-first promise unless that promise is explicitly changed. Returning before persistence would also change the acceptance guarantee. Neither is a default recommendation.

## Not yet measured

Do not cite performance numbers for the following until they are measured on the current release:

- Concurrent ingest under contention.
- Worker throughput against a stub receiver with a success, `5xx`, and timeout mix.
- End-to-end latency from ingest through receiver acknowledgement.
- Sustained p99/p999 behavior.
- PostgreSQL high-availability failover and connection-pool limits.
- Cost and latency of DNS resolution and public-IP validation in the worker.
- Replica-safe quota behavior under Redis failover.

## Measuring a deployment

Track these independently:

1. Ingest acceptance latency and `429` rate per tenant.
2. PostgreSQL commit latency, connections, and lock waits.
3. Queue depth and oldest queued/retrying age.
4. Delivery attempt latency, success rate, retry rate, and DLQ growth.
5. DNS/IP validation failures and blocked destinations.
6. Redis command errors, wake-up lag, and limiter latency.

Use the [deployment guide](deployment.md) alerting checklist and the historical method above when comparing releases.
