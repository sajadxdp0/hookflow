import Link from "next/link";
import type { Metadata } from "next";
import { ReplayButton } from "@/components/ReplayButton";
import { EmptyState, ErrorNote, PageHeader, StatusBadge, Table } from "@/components/ui";
import { formatUtc, shortId } from "@/lib/format";
import { getDeliveries } from "@/lib/hookflow";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Deliveries" };

export default async function DeliveriesPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const { status } = await searchParams;
  const filter = status ?? "";
  const heading = (
    <PageHeader
      title="Deliveries"
      description="Inspect delivery attempts and receiver responses. Only dead-lettered deliveries can be replayed; successful deliveries are never duplicated."
      actions={
        <Link href="/dlq" className="button-secondary">
          Open dead letter queue
        </Link>
      }
    />
  );
  const tabs = [
    { key: "", label: "All" },
    { key: "queued", label: "Queued" },
    { key: "retrying", label: "Retrying" },
    { key: "success", label: "Succeeded" },
    { key: "dlq", label: "Dead letters" },
  ];

  try {
    const { items } = await getDeliveries(filter || undefined);
    return (
      <div className="space-y-6">
        {heading}
        <nav aria-label="Filter deliveries" className="flex flex-wrap gap-2">
          {tabs.map((tab) => (
            <Link
              key={tab.key}
              href={tab.key ? `/deliveries?status=${tab.key}` : "/deliveries"}
              aria-current={filter === tab.key ? "page" : undefined}
              className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${
                filter === tab.key
                  ? "border-teal-400/30 bg-teal-400/10 text-teal-200"
                  : "border-white/10 text-slate-400 hover:border-white/20 hover:text-slate-100"
              }`}
            >
              {tab.label}
            </Link>
          ))}
        </nav>

        {items.length > 0 ? (
          <Table
            head={["ID", "Status", "Attempts", "Next attempt (UTC)", "Code", "Latency", "Last error", "Action"]}
          >
            {items.map((delivery) => (
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
                <td className="px-4 py-3 font-mono text-xs text-slate-400">
                  {formatUtc(delivery.next_attempt_at)}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-slate-300">
                  {delivery.last_status_code ?? "—"}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-slate-300">
                  {delivery.latency_ms == null ? "—" : `${delivery.latency_ms}ms`}
                </td>
                <td
                  className="max-w-xs truncate px-4 py-3 font-mono text-xs text-slate-500"
                  title={delivery.last_error ?? undefined}
                >
                  {delivery.last_error ?? "—"}
                </td>
                <td className="px-4 py-3">
                  <ReplayButton deliveryId={delivery.id} status={delivery.status} />
                </td>
              </tr>
            ))}
          </Table>
        ) : (
          <EmptyState
            title="No deliveries match this filter"
            description="Try another status, or send an event to a registered endpoint."
            action={
              <Link href="/deliveries" className="button-secondary">
                Clear filter
              </Link>
            }
          />
        )}
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
