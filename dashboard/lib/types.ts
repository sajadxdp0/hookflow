export type Endpoint = {
  id: string;
  url: string;
  rate_limit_per_minute: number;
  enabled: boolean;
  created_at: string;
};

export type EndpointPatch = {
  url?: string;
  rate_limit_per_minute?: number;
  enabled?: boolean;
};

export type Delivery = {
  id: string;
  event_id: string;
  endpoint_id: string;
  status: "queued" | "success" | "retrying" | "dlq";
  attempts: number;
  next_attempt_at: string | null;
  last_status_code: number | null;
  last_error: string | null;
  latency_ms: number | null;
};

export type Stats = {
  by_status: Record<string, number>;
  queue_depth: number;
  redis: string;
};

export type ApiKey = {
  id: string;
  tenant_id: string;
  label: string;
  key_prefix: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
};
