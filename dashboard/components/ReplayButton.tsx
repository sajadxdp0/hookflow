"use client";

import { useState, useTransition } from "react";
import { replayDelivery } from "@/app/actions";

export function ReplayButton({
  deliveryId,
  status,
}: {
  deliveryId: string;
  status: string;
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const replayable = status === "dlq";

  return (
    <div className="flex flex-col items-start gap-1">
      <button
        type="button"
        disabled={!replayable || pending}
        onClick={() =>
          startTransition(async () => {
            setError(null);
            const result = await replayDelivery(deliveryId);
            if (!result.ok) {
              setError(result.error ?? "Replay failed.");
            }
          })
        }
        title={
          replayable
            ? "Return this delivery to the queue"
            : "Only dead-lettered deliveries can be replayed"
        }
        className="button-secondary"
      >
        {pending ? "Replaying…" : "Replay"}
      </button>
      {error ? (
        <span role="alert" className="max-w-xs text-xs leading-5 text-rose-300">
          {error}
        </span>
      ) : null}
    </div>
  );
}
