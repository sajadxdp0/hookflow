import type { Metadata } from "next";
import { EmptyState, ErrorNote, PageHeader } from "@/components/ui";
import { getMetrics } from "@/lib/hookflow";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Metrics" };

function parse(text: string) {
  const rows: { key: string; name: string; labels: string; help?: string; value: number }[] = [];
  const help: Record<string, string> = {};
  for (const line of text.split("\n")) {
    if (line.startsWith("# HELP ")) {
      const [, , name, ...rest] = line.split(" ");
      help[name] = rest.join(" ");
    }
    if (line.startsWith("#") || !line.trim()) continue;
    const match = line.trim().match(/^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{.*\})?\s+([^\s]+)/);
    if (!match) continue;
    const [, name, labels = "", rawValue] = match;
    const value = Number(rawValue);
    if (!Number.isFinite(value)) continue;
    rows.push({ key: `${name}${labels}`, name, labels, help: help[name], value });
  }
  return rows;
}

export default async function MetricsPage() {
  const heading = (
    <PageHeader
      title="Metrics"
      description="Prometheus text exposition from /metrics. Scrape the API directly for alerting; this view is for operator inspection."
    />
  );

  let text: string;
  try {
    const response = await getMetrics();
    if (!response.ok) throw new Error(`Metrics endpoint returned ${response.status}.`);
    text = await response.text();
  } catch (error) {
    return (
      <div className="space-y-6">
        {heading}
        <ErrorNote error={error} />
      </div>
    );
  }

  const rows = parse(text);
  return (
    <div className="space-y-6">
      {heading}
      {rows.length === 0 ? (
        <EmptyState
          title="No metrics reported yet"
          description="Metrics will appear after the API handles traffic."
        />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {rows.map((metric) => (
            <div key={metric.key} className="panel p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="break-all font-mono text-sm text-slate-200">{metric.name}</div>
                  {metric.labels ? (
                    <div className="mt-1 break-all font-mono text-[11px] text-slate-500">
                      {metric.labels}
                    </div>
                  ) : null}
                </div>
                <span className="shrink-0 font-mono text-lg text-slate-100">{metric.value}</span>
              </div>
              {metric.help ? (
                <p className="mt-2 text-xs leading-5 text-slate-500">{metric.help}</p>
              ) : null}
            </div>
          ))}
        </div>
      )}
      <details className="panel p-4">
        <summary className="w-fit rounded font-mono text-xs text-slate-400 hover:text-slate-200">
          Raw exposition
        </summary>
        <pre className="mt-3 overflow-x-auto font-mono text-xs leading-5 text-slate-400">
          {text}
        </pre>
      </details>
    </div>
  );
}
