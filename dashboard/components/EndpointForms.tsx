"use client";

import { useId, useState, useTransition } from "react";
import {
  createEndpointAction,
  deleteEndpointAction,
  rotateEndpointSecretAction,
  setEndpointEnabledAction,
  updateEndpointAction,
} from "@/app/actions";
import { ActionFeedback, SecretReveal } from "@/components/ActionFeedback";
import { StatusBadge } from "@/components/ui";
import { formatUtc, shortId } from "@/lib/format";
import type { ActionResult } from "@/lib/action-result";
import type { Endpoint } from "@/lib/types";

export function CreateEndpointForm() {
  const urlId = useId();
  const rateId = useId();
  const [result, setResult] = useState<ActionResult | null>(null);
  const [pending, startTransition] = useTransition();

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setResult(null);
    startTransition(async () => {
      const next = await createEndpointAction(new FormData(form));
      setResult(next);
      if (next.ok) form.reset();
    });
  }

  return (
    <section className="panel p-5 sm:p-6" aria-labelledby={`${urlId}-heading`}>
      <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
        <div>
          <h2 id={`${urlId}-heading`} className="text-base font-semibold text-white">
            Register an endpoint
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            Public HTTP(S) destinations only. HookFlow generates a signing secret.
          </p>
        </div>
        <span className="w-fit rounded-md border border-white/10 px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-slate-500">
          POST /v1/endpoints
        </span>
      </div>
      <form onSubmit={submit} className="mt-5 space-y-4">
        <div>
          <label htmlFor={urlId} className="field-label">
            Destination URL
          </label>
          <input
            id={urlId}
            name="url"
            type="url"
            required
            maxLength={2000}
            placeholder="https://api.example.com/hooks/hookflow"
            className="field font-mono text-sm"
            autoComplete="url"
            aria-describedby={`${urlId}-hint`}
          />
          <p id={`${urlId}-hint`} className="mt-1.5 text-xs text-slate-500">
            Loopback, private, link-local and reserved addresses are blocked.
          </p>
        </div>
        <div className="max-w-xs">
          <label htmlFor={rateId} className="field-label">
            Rate limit <span className="font-normal text-slate-500">(optional)</span>
          </label>
          <div className="flex items-center gap-2">
            <input
              id={rateId}
              name="rate_limit_per_minute"
              type="number"
              min={1}
              max={10000}
              step={1}
              inputMode="numeric"
              placeholder="60"
              className="field font-mono text-sm"
            />
            <span className="shrink-0 text-sm text-slate-500">requests/min</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" disabled={pending} className="button-primary">
            {pending ? "Creating…" : "Create endpoint"}
          </button>
          <span className="text-xs text-slate-500">
            Tenant endpoint limits are enforced by the API.
          </span>
        </div>
        <ActionFeedback result={result && !(result.ok && result.secret) ? result : null} />
      </form>
      {result?.ok && result.secret ? (
        <div className="mt-5">
          <SecretReveal
            secret={result.secret}
            purpose="created"
            onDismiss={() =>
              setResult({
                ok: true,
                message: "Endpoint created. Confirm the signing secret is stored.",
              })
            }
          />
        </div>
      ) : null}
    </section>
  );
}

export function EndpointCard({ endpoint }: { endpoint: Endpoint }) {
  const formId = useId();
  const [editing, setEditing] = useState(false);
  const [result, setResult] = useState<ActionResult | null>(null);
  const [pending, startTransition] = useTransition();

  function updateSettings(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setResult(null);
    startTransition(async () => {
      const next = await updateEndpointAction(new FormData(form));
      setResult(next);
      if (next.ok) setEditing(false);
    });
  }

  function toggle(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    setResult(null);
    startTransition(async () => {
      setResult(await setEndpointEnabledAction(formData));
    });
  }

  function rotate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      !window.confirm(
        `Rotate the signing secret for ${endpoint.url}? The current secret will stop working immediately.`,
      )
    ) {
      return;
    }
    const formData = new FormData(event.currentTarget);
    setResult(null);
    startTransition(async () => {
      setResult(await rotateEndpointSecretAction(formData));
    });
  }

  function remove(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      !window.confirm(
        `Delete ${endpoint.url}? This cannot be undone. Endpoints with queued or retrying deliveries cannot be deleted.`,
      )
    ) {
      return;
    }
    const formData = new FormData(event.currentTarget);
    setResult(null);
    startTransition(async () => {
      setResult(await deleteEndpointAction(formData));
    });
  }

  return (
    <article className="panel overflow-hidden">
      <div className="p-5 sm:p-6">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={endpoint.enabled ? "enabled" : "disabled"} />
              <span
                className="font-mono text-[11px] text-slate-500"
                title={endpoint.id}
              >
                {shortId(endpoint.id)}
              </span>
            </div>
            <a
              href={endpoint.url}
              target="_blank"
              rel="noreferrer"
              className="mt-3 block break-all font-mono text-sm leading-6 text-slate-100 hover:text-teal-200"
            >
              {endpoint.url}
            </a>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            <form onSubmit={toggle}>
              <input type="hidden" name="endpoint_id" value={endpoint.id} />
              <input
                type="hidden"
                name="enabled"
                value={String(!endpoint.enabled)}
              />
              <button
                type="submit"
                disabled={pending}
                className="button-secondary"
              >
                {endpoint.enabled ? "Disable" : "Enable"}
              </button>
            </form>
            <button
              type="button"
              onClick={() => setEditing((value) => !value)}
              aria-expanded={editing}
              aria-controls={formId}
              disabled={pending}
              className="button-secondary"
            >
              {editing ? "Close editor" : "Edit settings"}
            </button>
          </div>
        </div>

        <dl className="mt-5 grid gap-4 border-t border-white/6 pt-4 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-xs text-slate-500">Rate limit</dt>
            <dd className="mt-1 font-mono text-slate-200">
              {endpoint.rate_limit_per_minute}/min
            </dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Created</dt>
            <dd className="mt-1 text-slate-300">{formatUtc(endpoint.created_at)} UTC</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Delivery state</dt>
            <dd className="mt-1 text-slate-400">
              {endpoint.enabled
                ? "Accepting events"
                : "New events rejected; queued work waits"}
            </dd>
          </div>
        </dl>

        {editing ? (
          <form
            id={formId}
            onSubmit={updateSettings}
            className="mt-5 space-y-4 rounded-xl border border-white/8 bg-black/20 p-4"
          >
            <input type="hidden" name="endpoint_id" value={endpoint.id} />
            <div>
              <label htmlFor={`${formId}-url`} className="field-label">
                Destination URL
              </label>
              <input
                key={`${endpoint.id}-url-${endpoint.url}`}
                id={`${formId}-url`}
                name="url"
                type="url"
                required
                maxLength={2000}
                defaultValue={endpoint.url}
                className="field font-mono text-sm"
              />
            </div>
            <div className="max-w-xs">
              <label htmlFor={`${formId}-rate`} className="field-label">
                Rate limit (requests/min)
              </label>
              <input
                key={`${endpoint.id}-rate-${endpoint.rate_limit_per_minute}`}
                id={`${formId}-rate`}
                name="rate_limit_per_minute"
                type="number"
                min={1}
                max={10000}
                step={1}
                required
                defaultValue={endpoint.rate_limit_per_minute}
                className="field font-mono text-sm"
              />
            </div>
            <button type="submit" disabled={pending} className="button-primary">
              {pending ? "Saving…" : "Save changes"}
            </button>
          </form>
        ) : null}

        {result && !(result.ok && result.secret) ? (
          <div className="mt-4">
            <ActionFeedback result={result} />
          </div>
        ) : null}
      </div>

      <div className="flex flex-col gap-3 border-t border-white/6 bg-white/[0.015] px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs leading-5 text-slate-500">
          Rotating a secret invalidates the old secret immediately.
        </p>
        <div className="flex flex-wrap gap-2">
          <form onSubmit={rotate}>
            <input type="hidden" name="endpoint_id" value={endpoint.id} />
            <button
              type="submit"
              disabled={pending}
              className="button-secondary"
            >
              Rotate secret
            </button>
          </form>
          <form onSubmit={remove}>
            <input type="hidden" name="endpoint_id" value={endpoint.id} />
            <button
              type="submit"
              disabled={pending}
              className="button-danger"
            >
              Delete endpoint
            </button>
          </form>
        </div>
      </div>

      {result?.ok && result.secret ? (
        <div className="border-t border-white/6 p-5">
          <SecretReveal
            secret={result.secret}
            purpose="rotated"
            onDismiss={() =>
              setResult({
                ok: true,
                message: "Signing secret rotated. Confirm the receiver has the new secret.",
              })
            }
          />
        </div>
      ) : null}
    </article>
  );
}
