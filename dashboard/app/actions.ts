"use server";

import { revalidatePath } from "next/cache";
import {
  createEndpoint,
  deleteEndpoint,
  getApiKeys,
  requeue,
  revokeApiKey,
  rotateEndpointSecret,
  updateEndpoint,
} from "@/lib/hookflow";
import type { ActionResult } from "@/lib/action-result";

function failure(error: unknown): ActionResult {
  return {
    ok: false,
    error: error instanceof Error ? error.message : String(error),
  };
}

function revalidateOperationalViews() {
  revalidatePath("/");
  revalidatePath("/endpoints");
  revalidatePath("/deliveries");
  revalidatePath("/dlq");
}

function readRateLimit(formData: FormData): number | undefined {
  const raw = String(formData.get("rate_limit_per_minute") ?? "").trim();
  if (!raw) return undefined;
  const value = Number(raw);
  if (!Number.isInteger(value) || value < 1 || value > 10000) {
    throw new Error("Rate limit must be a whole number between 1 and 10,000.");
  }
  return value;
}

function readUrl(formData: FormData): string {
  const url = String(formData.get("url") ?? "").trim();
  if (!url) throw new Error("Destination URL is required.");
  return url;
}

export async function createEndpointAction(
  formData: FormData,
): Promise<ActionResult> {
  try {
    const endpoint = await createEndpoint({
      url: readUrl(formData),
      rateLimit: readRateLimit(formData),
    });
    revalidateOperationalViews();
    return {
      ok: true,
      message: "Endpoint created. Store its signing secret now.",
      secret: endpoint.secret,
    };
  } catch (error) {
    return failure(error);
  }
}

export async function updateEndpointAction(
  formData: FormData,
): Promise<ActionResult> {
  try {
    const endpointId = String(formData.get("endpoint_id") ?? "");
    if (!endpointId) throw new Error("Endpoint id is missing.");
    const rateLimit = readRateLimit(formData);
    if (rateLimit == null) {
      throw new Error("Rate limit is required when editing an endpoint.");
    }
    await updateEndpoint(endpointId, {
      url: readUrl(formData),
      rate_limit_per_minute: rateLimit,
    });
    return { ok: true, message: "Endpoint settings updated." };
  } catch (error) {
    return failure(error);
  }
}

export async function setEndpointEnabledAction(
  formData: FormData,
): Promise<ActionResult> {
  try {
    const endpointId = String(formData.get("endpoint_id") ?? "");
    if (!endpointId) throw new Error("Endpoint id is missing.");
    const enabled = formData.get("enabled") === "true";
    await updateEndpoint(endpointId, { enabled });
    revalidateOperationalViews();
    return {
      ok: true,
      message: enabled ? "Endpoint enabled." : "Endpoint disabled.",
    };
  } catch (error) {
    return failure(error);
  }
}

export async function rotateEndpointSecretAction(
  formData: FormData,
): Promise<ActionResult> {
  try {
    const endpointId = String(formData.get("endpoint_id") ?? "");
    if (!endpointId) throw new Error("Endpoint id is missing.");
    const rotated = await rotateEndpointSecret(endpointId);
    return {
      ok: true,
      message: "Signing secret rotated. Store the new secret now.",
      secret: rotated.secret,
    };
  } catch (error) {
    return failure(error);
  }
}

export async function deleteEndpointAction(
  formData: FormData,
): Promise<ActionResult> {
  try {
    const endpointId = String(formData.get("endpoint_id") ?? "");
    if (!endpointId) throw new Error("Endpoint id is missing.");
    await deleteEndpoint(endpointId);
    revalidateOperationalViews();
    return { ok: true, message: "Endpoint deleted." };
  } catch (error) {
    return failure(error);
  }
}

export async function replayDelivery(deliveryId: string): Promise<ActionResult> {
  try {
    await requeue(deliveryId);
    revalidateOperationalViews();
    return { ok: true, message: "Delivery returned to the queue." };
  } catch (error) {
    return failure(error);
  }
}

export async function revokeApiKeyAction(
  formData: FormData,
): Promise<ActionResult> {
  try {
    const tenantId = process.env.HOOKFLOW_TENANT_ID;
    if (!tenantId || !process.env.HOOKFLOW_ADMIN_TOKEN) {
      throw new Error(
        "Set HOOKFLOW_TENANT_ID and HOOKFLOW_ADMIN_TOKEN to revoke API keys.",
      );
    }
    const keyId = String(formData.get("key_id") ?? "");
    const keyTenantId = String(formData.get("tenant_id") ?? "");
    if (!keyId) throw new Error("API key id is missing.");
    if (keyTenantId !== tenantId) {
      throw new Error("API key does not belong to the configured tenant.");
    }
    const tenantKeys = await getApiKeys(tenantId);
    if (!tenantKeys.some((key) => key.id === keyId)) {
      throw new Error("API key not found for the configured tenant.");
    }
    await revokeApiKey(keyId);
    revalidatePath("/keys");
    return { ok: true, message: "API key revoked. It can no longer authenticate." };
  } catch (error) {
    return failure(error);
  }
}
