import type { Metadata } from "next";
import { ReplayButton } from "@/components/ReplayButton";
import { EmptyState, ErrorNote, PageHeader, Table } from "@/components/ui";
import { shortId } from "@/lib/format";
import { getDeliveries } from "@/lib/hookflow";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Dead letter queue" };

export default async function DlqPage() {
  const heading = (
    <PageHeader
      title="Dead letter queue"
      description="Deliveries that exhausted the retry schedule. Nothing is discarded automatically: investigate the receiver, then replay when it is ready."
    />
  );

  try {
    const { items } = await getDeliveries("dlq");
    return (
      <div className="space-y-6">
        {heading}
        {items.length === 0 ? (
          <EmptyState
            title="The dead letter queue is clear"
            description="There are no exhausted deliveries waiting for operator action."
          />
        ) : (
          <Table head={["ID", "Endpoint", "Attempts", "Receiver code", "Last error", "Action"]}>
            {items.map((delivery) => (
              <tr key={delivery.id}>
                <td className="px-4 py-3 font-mono text-xs" title={delivery.id}>
                  {shortId(delivery.id)}
                </td>
                <td
                  className="px-4 py-3 font-mono text-xs text-slate-400"
                  title={delivery.endpoint_id}
                >
                  {shortId(delivery.endpoint_id)}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-slate-300">
                  {delivery.attempts}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-rose-300">
                  {delivery.last_status_code ?? "—"}
                </td>
                <td
                  className="max-w-sm truncate px-4 py-3 font-mono text-xs text-slate-500"
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
