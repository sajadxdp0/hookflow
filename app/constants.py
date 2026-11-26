"""Shared vocabulary for delivery state transitions."""

from __future__ import annotations

STATUS_QUEUED = "queued"
STATUS_RETRYING = "retrying"
STATUS_SUCCESS = "success"
STATUS_DLQ = "dlq"

# States the worker will attempt to deliver.
RETRYABLE_STATUSES = (STATUS_QUEUED, STATUS_RETRYING)

# Only terminal dead letters may be replayed. Requeueing active work races an
# in-flight HTTP request and can duplicate receiver side effects.
REQUEUEABLE_STATUSES = (STATUS_DLQ,)
