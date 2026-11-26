import Link from "next/link";
import type { Metadata } from "next";
import { getDeliveries, getEndpoints, getReady, getStats } from "@/lib/hookflow";
import { EmptyState, ErrorNote, PageHeader, Stat, StatusBadge, Table } from "@/components/ui";
import { formatUtc, shortId } from "@/lib/format";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Overview" };

export default async function OverviewPage() {
  const heading = (
    <PageHeader
      title="Overview"
      description="Live delivery health, queue pressure and readiness for this tenant."
      actions={
        <Link href="/endpoints" className="button-primary">
          Manage endpoints
        </Link>
      }
    />
  );

  try {
    const [stats, endpoints, recent, ready] = await Promise.all([
      getStats(),
      getEndpoints(),
      getDeliveries(),
      getReady(),
    ]);

    const byStatus = stats.by_status ?? {};
    const latencies = recent.items
      .filter((delivery) => delivery.latency_ms != null)
      .map((delivery) => delivery.latency_ms as number)
      .sort((a, b) => a - b);
    const p95 =
      latencies.length > 0
        ? latencies[Math.max(0, Math.ceil(latencies.length * 0.95) - 1)]
        : null;
    const readiness = Object.entries(ready);

    return (
      <div className="space-y-8">
        {heading}

        <section aria-label="Delivery summary">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Stat
              label="Queue depth"
              value={stats.queue_depth}
              tone={stats.queue_depth > 100 ? "warn" : "neutral"}
              hint="queued + retrying"
            />
            <Stat label="Succeeded" value={byStatus.success ?? 0} tone="good" />
            <Stat
              label="Retrying"
              value={byStatus.retrying ?? 0}
              tone={byStatus.retrying ? "warn" : "neutral"}
              hint="automatic retries in progress"
            />
            <Stat
              label="Dead lettered"
              value={byStatus.dlq ?? 0}
              tone={byStatus.dlq ? "bad" : "good"}
              hint="requires operator action"
            />
          </div>
        </section>

        <section aria-label="Tenant summary">
          <div className="grid gap-3 sm:grid-cols-3">
            <Stat label="Endpoints" value={endpoints.items.length} hint="registered destinations" />
            <Stat
              label="p95 delivery latency"
              value={p95 == null ? "—" : `${p95}ms`}
              hint="from the latest 100 deliveries"
            />
            <Stat
              label="Redis wake-up"
              value={stats.redis === "configured" ? "Configured" : "Database polling"}
              tone={stats.redis === "configured" ? "good" : "neutral"}
              hint="best effort; the database is authoritative"
            />
          </div>
        </section>

        <section className="space-y-3" aria-labelledby="readiness-heading">
          <div className="flex items-center justify-between gap-3">
            <h2 id="readiness-heading" className="text-sm font-semibold text-slate-200">
              Readiness
            </h2>
            <span className="font-mono text-xs text-slate-600">GET /ready</span>
          </div>
          {readiness.length > 0 ? (
            <Table head={["Check", "Status"]}>
              {readiness.map(([check, status]) => (
                <tr key={check}>
                  <td className="px-4 py-3 font-mono text-xs text-slate-300">{check}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={status} />
                  </td>
                </tr>
              ))}
            </Table>
          ) : (
            <EmptyState
              title="No readiness checks reported"
              description="The API returned an empty readiness document."
            />
          )}
        </section>

        <section className="space-y-3" aria-labelledby="recent-heading">
          <div className="flex items-center justify-between gap-3">
            <h2 id="recent-heading" className="text-sm font-semibold text-slate-200">
              Recent deliveries
            </h2>
            <Link href="/deliveries" className="text-sm text-teal-300 hover:text-teal-200">
              View all deliveries →
            </Link>
          </div>
          {recent.items.length > 0 ? (
            <Table head={["ID", "Status", "Attempts", "Latency", "Last error"]}>
              {recent.items.slice(0, 15).map((delivery) => (
                <tr key={delivery.id}>
                  <td className="px-4 py-3 font-mono text-xs" title={delivery.id}>
                    {shortId(delivery.id)}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={delivery.status} />
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-300">
                    {delivery.attempts}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-300">
                    {delivery.latency_ms == null ? "—" : `${delivery.latency_ms}ms`}
                  </td>
                  <td className="max-w-xs truncate px-4 py-3 font-mono text-xs text-slate-500" title={delivery.last_error ?? undefined}>
                    {delivery.last_error ?? "—"}
                  </td>
                </tr>
              ))}
            </Table>
          ) : (
            <EmptyState
              title="No deliveries yet"
              description="Once events are ingested, their delivery state will appear here."
              action={
                <Link href="/endpoints" className="button-secondary">
                  Review endpoints
                </Link>
              }
            />
          )}
        </section>

        <p className="text-xs text-slate-600">
          Latest delivery activity at {formatUtc(new Date().toISOString())} UTC.
        </p>
      </div>
    );
  } catch (error) {
    return (
      <div className="space-y-6">
        {heading}
        <ErrorNote error={error} />
      </div>
    );
  }
}
