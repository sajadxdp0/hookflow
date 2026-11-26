export function Stat({
  label,
  value,
  tone = "neutral",
  hint,
}: {
  label: string;
  value: string | number;
  tone?: "neutral" | "good" | "warn" | "bad";
  hint?: string;
}) {
  const toneClass = {
    neutral: "text-slate-100",
    good: "text-teal-300",
    warn: "text-amber-300",
    bad: "text-rose-300",
  }[tone];

  return (
    <div className="panel p-4 sm:p-5">
      <div className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
        {label}
      </div>
      <div className={`mt-2 font-mono text-2xl font-medium ${toneClass}`}>{value}</div>
      {hint ? <div className="mt-1 text-xs text-slate-500">{hint}</div> : null}
    </div>
  );
}

const badgeTones: Record<string, string> = {
  success: "border-teal-400/20 bg-teal-400/10 text-teal-300",
  active: "border-teal-400/20 bg-teal-400/10 text-teal-300",
  enabled: "border-teal-400/20 bg-teal-400/10 text-teal-300",
  ok: "border-teal-400/20 bg-teal-400/10 text-teal-300",
  configured: "border-teal-400/20 bg-teal-400/10 text-teal-300",
  queued: "border-sky-400/20 bg-sky-400/10 text-sky-300",
  retrying: "border-amber-400/20 bg-amber-400/10 text-amber-300",
  dlq: "border-rose-400/20 bg-rose-400/10 text-rose-300",
  failed: "border-rose-400/20 bg-rose-400/10 text-rose-300",
  revoked: "border-slate-500/20 bg-slate-500/10 text-slate-400",
  disabled: "border-slate-500/20 bg-slate-500/10 text-slate-400",
  "not-configured": "border-slate-500/20 bg-slate-500/10 text-slate-400",
};

const dotTones: Record<string, string> = {
  success: "bg-teal-400",
  active: "bg-teal-400",
  enabled: "bg-teal-400",
  ok: "bg-teal-400",
  configured: "bg-teal-400",
  queued: "bg-sky-400",
  retrying: "bg-amber-400",
  dlq: "bg-rose-400",
  failed: "bg-rose-400",
};

export function StatusBadge({ status }: { status: string }) {
  const key = status.toLowerCase();
  return (
    <span
      className={`inline-flex w-fit items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[11px] whitespace-nowrap ${badgeTones[key] ?? "border-slate-500/20 bg-slate-500/10 text-slate-300"}`}
    >
      <span
        className={`size-1.5 rounded-full ${dotTones[key] ?? "bg-slate-500"}`}
        aria-hidden="true"
      />
      {status}
    </span>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
      <div className="max-w-2xl">
        <h1 className="text-2xl font-semibold tracking-tight text-white sm:text-3xl">
          {title}
        </h1>
        <p className="mt-2 text-sm leading-6 text-slate-400">{description}</p>
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap gap-2">{actions}</div> : null}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="panel flex flex-col items-center px-6 py-12 text-center">
      <div className="mb-4 flex size-11 items-center justify-center rounded-xl border border-white/10 bg-white/4 text-teal-300">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          className="size-5"
          aria-hidden="true"
        >
          <path d="M4 7h16M4 12h10M4 17h7" strokeLinecap="round" />
        </svg>
      </div>
      <h2 className="text-sm font-semibold text-slate-100">{title}</h2>
      <p className="mt-1 max-w-md text-sm leading-6 text-slate-500">{description}</p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

export function Table({
  head,
  children,
}: {
  head: string[];
  children: React.ReactNode;
}) {
  return (
    <div className="panel overflow-x-auto">
      <table className="w-full min-w-[720px] border-collapse text-left text-sm">
        <thead className="border-b border-white/8 bg-white/[0.02] text-[11px] font-medium uppercase tracking-[0.1em] text-slate-500">
          <tr>
            {head.map((heading) => (
              <th key={heading} scope="col" className="px-4 py-3 font-medium">
                {heading}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-white/6">{children}</tbody>
      </table>
    </div>
  );
}

function guidanceFor(error: unknown): string {
  if (
    typeof error === "object" &&
    error !== null &&
    "status" in error &&
    typeof error.status === "number"
  ) {
    const status = error.status;
    if (status === 401) {
      return "The API rejected a credential. Check HOOKFLOW_API_KEY, or HOOKFLOW_ADMIN_TOKEN for admin routes, in dashboard/.env.local. Replace revoked credentials and restart the dashboard.";
    }
    if (status === 403) {
      return "This credential is not allowed to perform that operation. Check the tenant and admin configuration.";
    }
    if (status === 404) {
      return "The requested resource no longer exists. Refresh the page and try again.";
    }
    if (status === 409) {
      return "The API refused this change because the resource is not in a compatible state. Refresh and review queued or retrying deliveries before deleting an endpoint.";
    }
    if (status === 429) {
      return "The API rate limit was reached. Wait for the indicated retry period before trying again.";
    }
    if (status >= 500) {
      return "The HookFlow API is unavailable or misconfigured. Check the API logs, database and Redis connectivity, then try again.";
    }
  }
  return "Confirm the API is running at HOOKFLOW_API_URL and that HOOKFLOW_API_KEY is set in dashboard/.env.local. Restart the dashboard after changing environment variables.";
}

export function ErrorNote({ error }: { error: unknown }) {
  return (
    <div
      role="alert"
      className="rounded-xl border border-rose-400/20 bg-rose-400/[0.06] p-5"
    >
      <div className="flex items-start gap-3">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          className="mt-0.5 size-5 shrink-0 text-rose-300"
          aria-hidden="true"
        >
          <path d="M12 8v5m0 3h.01" strokeLinecap="round" />
          <path d="M10.3 4.9 3.1 17a2 2 0 0 0 1.7 3h14.4a2 2 0 0 0 1.7-3L13.7 4.9a2 2 0 0 0-3.4 0Z" />
        </svg>
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-rose-200">
            Could not load HookFlow data
          </h2>
          <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-words font-mono text-xs leading-5 text-rose-200/80">
            {error instanceof Error ? error.message : String(error)}
          </pre>
          <p className="mt-3 text-sm leading-6 text-rose-100/60">{guidanceFor(error)}</p>
        </div>
      </div>
    </div>
  );
}
