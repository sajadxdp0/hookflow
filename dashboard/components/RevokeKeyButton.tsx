"use client";

import { useState, useTransition } from "react";
import { revokeApiKeyAction } from "@/app/actions";
import { ActionFeedback } from "@/components/ActionFeedback";
import type { ActionResult } from "@/lib/action-result";
export function RevokeKeyButton({
  keyId,
  prefix,
  tenantId,
  dashboardCredential,
}: {
  keyId: string;
  prefix: string;
  tenantId: string;
  dashboardCredential: boolean;
}) {
  const [result, setResult] = useState<ActionResult | null>(null);
  const [pending, startTransition] = useTransition();

  function revoke(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const warning = dashboardCredential
      ? `Revoke hf_${prefix}_…? This is the dashboard's configured HOOKFLOW_API_KEY. The dashboard will immediately lose API access until you deploy a replacement key.`
      : `Revoke hf_${prefix}_…? Every client using this key will immediately lose API access. This cannot be undone.`;
    if (!window.confirm(warning)) return;
    setResult(null);
    startTransition(async () => {
      setResult(await revokeApiKeyAction(new FormData(form)));
    });
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <form onSubmit={revoke}>
        <input type="hidden" name="key_id" value={keyId} />
        <input type="hidden" name="tenant_id" value={tenantId} />
        <button type="submit" disabled={pending} className="button-danger">
          {pending ? "Revoking…" : "Revoke"}
        </button>
      </form>
      <ActionFeedback result={result} />
    </div>
  );
}
