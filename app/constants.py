"""Shared vocabulary for delivery state transitions."""

from __future__ import annotations

STATUS_QUEUED = "queued"
STATUS_RETRYING = "retrying"
STATUS_SUCCESS = "success"
STATUS_DLQ = "dlq"

# States the worker will attempt to deliver.
RETRYABLE_STATUSES = (STATUS_QUEUED, STATUS_RETRYING)

# States a caller may replay via the requeue endpoint. A successful delivery is
# excluded: replaying it would duplicate a side effect at the receiver.
REQUEUEABLE_STATUSES = (STATUS_DLQ, STATUS_RETRYING, STATUS_QUEUED)
