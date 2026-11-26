/**
 * Typed client for the HookFlow API.
 *
 * This module is server-only. The tenant and admin credentials are read from
 * the Node environment and must never be imported into a client component or
 * prefixed with NEXT_PUBLIC_.
 */

import type { ApiKey, Delivery, Endpoint, EndpointPatch, Stats } from "@/lib/types";

const BASE = process.env.HOOKFLOW_API_URL ?? "http://localhost:8000";

export class HookflowError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "HookflowError";
  }
}

function errorDetail(body: unknown, fallback: string): string {
  if (typeof body === "string") return body;
  if (body && typeof body === "object" && "detail" in body) {
    const detail = body.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map(String).join("; ");
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const apiKey = process.env.HOOKFLOW_API_KEY;
  if (!apiKey) {
    throw new HookflowError(
      "HOOKFLOW_API_KEY is not set. Set it in dashboard/.env.local and restart.",
      500,
    );
  }

  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${apiKey}`);
  headers.set("Content-Type", "application/json");

  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers,
    // Operational state must never come from a framework or CDN cache.
    cache: "no-store",
  });

  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = undefined;
    }
    const retryAfter = res.headers.get("Retry-After");
    throw new HookflowError(
      `${res.status} ${errorDetail(body, res.statusText)}${retryAfter ? ` (Retry-After: ${retryAfter})` : ""}`,
      res.status,
    );
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function adminRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const adminToken = process.env.HOOKFLOW_ADMIN_TOKEN;
  if (!adminToken) {
    throw new HookflowError(
      "HOOKFLOW_ADMIN_TOKEN is not set. Admin API operations are disabled.",
      503,
    );
  }

  const headers = new Headers(init?.headers);
  headers.set("X-Admin-Token", adminToken);
  headers.set("Content-Type", "application/json");
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });

  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = undefined;
    }
    const retryAfter = res.headers.get("Retry-After");
    throw new HookflowError(
      `${res.status} ${errorDetail(body, res.statusText)}${retryAfter ? ` (Retry-After: ${retryAfter})` : ""}`,
      res.status,
    );
  }
  return (await res.json()) as T;
}

export const getEndpoints = () =>
  request<{ items: Endpoint[] }>("/v1/endpoints?limit=200");

export const getDeliveries = (status?: string) => {
  const query = new URLSearchParams({ limit: "100" });
  if (status) query.set("status", status);
  return request<{ items: Delivery[] }>(`/v1/deliveries?${query.toString()}`);
};

export const getStats = () => request<Stats>("/v1/stats");

export const getReady = () => request<Record<string, string>>("/ready");

export const getMetrics = () => fetch(`${BASE}/metrics`, { cache: "no-store" });

export const getApiKeys = (tenantId: string) =>
  adminRequest<ApiKey[]>(`/v1/admin/tenants/${encodeURIComponent(tenantId)}/keys`);

export const createEndpoint = (input: {
  url: string;
  rateLimit?: number;
}) =>
  request<Endpoint & { secret: string }>("/v1/endpoints", {
    method: "POST",
    body: JSON.stringify({
      url: input.url,
      ...(input.rateLimit == null
        ? {}
        : { rate_limit_per_minute: input.rateLimit }),
    }),
  });

export const updateEndpoint = (endpointId: string, patch: EndpointPatch) =>
  request<Endpoint>(`/v1/endpoints/${encodeURIComponent(endpointId)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });

export const rotateEndpointSecret = (endpointId: string) =>
  request<{ id: string; secret: string }>(
    `/v1/endpoints/${encodeURIComponent(endpointId)}/rotate-secret`,
    { method: "POST" },
  );

export const deleteEndpoint = (endpointId: string) =>
  request<void>(`/v1/endpoints/${encodeURIComponent(endpointId)}`, {
    method: "DELETE",
  });

export const revokeApiKey = (keyId: string) =>
  adminRequest<ApiKey>(`/v1/admin/keys/${encodeURIComponent(keyId)}/revoke`, {
    method: "POST",
  });

export const requeue = (deliveryId: string) =>
  request<Delivery>(`/v1/deliveries/${encodeURIComponent(deliveryId)}/requeue`, {
    method: "POST",
  });
