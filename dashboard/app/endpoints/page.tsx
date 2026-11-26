import type { Metadata } from "next";
import { CreateEndpointForm, EndpointCard } from "@/components/EndpointForms";
import { EmptyState, ErrorNote, PageHeader } from "@/components/ui";
import { getEndpoints } from "@/lib/hookflow";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Endpoints" };

export default async function EndpointsPage() {
  const heading = (
    <PageHeader
      title="Endpoints"
      description="Manage delivery destinations, throttles and signing credentials. Secrets are encrypted at rest and never returned by the list API."
    />
  );

  try {
    const { items } = await getEndpoints();
    return (
      <div className="space-y-8">
        {heading}
        <CreateEndpointForm />
        <section className="space-y-3" aria-labelledby="registered-heading">
          <div className="flex items-center justify-between gap-3">
            <h2 id="registered-heading" className="text-sm font-semibold text-slate-200">
              Registered endpoints
            </h2>
            <span className="font-mono text-xs text-slate-500">{items.length} total</span>
          </div>
          {items.length > 0 ? (
            <div className="space-y-3">
              {items.map((endpoint) => (
                <EndpointCard key={endpoint.id} endpoint={endpoint} />
              ))}
            </div>
          ) : (
            <EmptyState
              title="No endpoints registered"
              description="Create your first destination above to start accepting webhook events."
            />
          )}
        </section>
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
