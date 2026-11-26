"use client";

import { useState } from "react";
import type { ActionResult } from "@/lib/action-result";

export function ActionFeedback({ result }: { result: ActionResult | null }) {
  if (!result) return null;
  if (result.ok) {
    return result.message ? (
      <p role="status" className="text-sm leading-6 text-teal-300">
        {result.message}
      </p>
    ) : null;
  }
  return (
    <p role="alert" className="text-sm leading-6 text-rose-300">
      {result.error}
    </p>
  );
}

export function SecretReveal({
  secret,
  purpose,
  onDismiss,
}: {
  secret: string;
  purpose: "created" | "rotated";
  onDismiss: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState<string | null>(null);

  async function copySecret() {
    setCopyError(null);
    try {
      await navigator.clipboard.writeText(secret);
      setCopied(true);
    } catch {
      setCopyError("Clipboard access was denied. Select and copy the secret manually.");
    }
  }

  return (
    <section
      aria-live="polite"
      className="rounded-xl border border-amber-300/25 bg-amber-300/[0.06] p-5"
    >
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
        <div>
          <h3 className="text-sm font-semibold text-amber-100">
            {purpose === "created" ? "Endpoint signing secret" : "New signing secret"}
          </h3>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-amber-100/70">
            This secret is shown only once. Store it in your secret manager now.
            {purpose === "rotated"
              ? " Rotation immediately invalidates the previous secret; update the receiver before sending more events."
              : " The receiver must use it to verify HookFlow signatures."}
          </p>
        </div>
        <span className="w-fit rounded-md border border-amber-300/20 px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-amber-200">
          shown once
        </span>
      </div>
      <div className="mt-4 flex flex-col gap-3 sm:flex-row">
        <code className="min-w-0 flex-1 overflow-x-auto rounded-lg border border-amber-300/15 bg-black/30 px-3 py-2.5 font-mono text-xs break-all text-amber-100">
          {secret}
        </code>
        <div className="flex gap-2">
          <button type="button" onClick={copySecret} className="button-secondary">
            {copied ? "Copied" : "Copy secret"}
          </button>
          <button type="button" onClick={onDismiss} className="button-primary">
            Done
          </button>
        </div>
      </div>
      {copyError ? (
        <p role="alert" className="mt-2 text-xs text-rose-300">
          {copyError}
        </p>
      ) : null}
    </section>
  );
}
