import type { Metadata } from "next";
import { RevokeKeyButton } from "@/components/RevokeKeyButton";
import { EmptyState, ErrorNote, PageHeader, StatusBadge, Table } from "@/components/ui";
import { formatUtc } from "@/lib/format";
import { getApiKeys } from "@/lib/hookflow";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "API keys" };

export default async function KeysPage() {
  const heading = (
    <PageHeader
      title="API keys"
      description="Review tenant credentials and revoke compromised keys. Plaintext keys are shown only when created and cannot be recovered."
    />
  );
  const tenantId = process.env.HOOKFLOW_TENANT_ID;

  if (!tenantId || !process.env.HOOKFLOW_ADMIN_TOKEN) {
    return (
      <div className="space-y-6">
        {heading}
        <EmptyState
          title="Admin access is not configured"
          description="Set HOOKFLOW_TENANT_ID and HOOKFLOW_ADMIN_TOKEN in dashboard/.env.local, then restart the dashboard to list and revoke this tenant's keys."
        />
      </div>
    );
  }

  try {
    const keys = await getApiKeys(tenantId);
    return (
      <div className="space-y-6">
        {heading}
        {keys.length === 0 ? (
          <EmptyState
            title="No API keys found"
            description="Provision a key through the admin API. Its plaintext value will be returned once at creation."
          />
        ) : (
          <Table head={["Prefix", "Label", "Created", "Last used", "State", "Action"]}>
            {keys.map((key) => {
              const dashboardCredential = process.env.HOOKFLOW_API_KEY?.startsWith(
                `hf_${key.key_prefix}_`,
              );
              return (
                <tr key={key.id}>
                  <td className="px-4 py-3 font-mono text-xs text-slate-200">
                    hf_{key.key_prefix}_…
                    {dashboardCredential && !key.revoked_at ? (
                      <span className="ml-2 rounded border border-sky-400/20 bg-sky-400/10 px-1.5 py-0.5 text-[10px] text-sky-300">
                        dashboard
                      </span>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-300">{key.label || "—"}</td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-500">
                    {formatUtc(key.created_at, false)}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-500">
                    {key.last_used_at ? `${formatUtc(key.last_used_at)} UTC` : "never"}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={key.revoked_at ? "revoked" : "active"} />
                  </td>
                  <td className="px-4 py-3">
                    {key.revoked_at ? (
                      <span className="text-xs text-slate-600">—</span>
                    ) : (
                      <RevokeKeyButton
                        keyId={key.id}
                        prefix={key.key_prefix}
                        tenantId={key.tenant_id}
                        dashboardCredential={Boolean(dashboardCredential)}
                      />
                    )}
                  </td>
                </tr>
              );
            })}
          </Table>
        )}
        <p className="text-xs leading-5 text-slate-500">
          Revocation is immediate. If you revoke the key marked &ldquo;dashboard&rdquo;,
          this console will lose API access until its server-side key is replaced.
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
