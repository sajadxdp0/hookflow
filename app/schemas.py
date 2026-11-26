"""Pydantic request and response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from .egress import validate_endpoint_url


class EndpointCreate(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    secret: str | None = Field(default=None, min_length=1, max_length=128)
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=10000)

    @field_validator("url")
    @classmethod
    def public_http_url(cls, value: str) -> str:
        return validate_endpoint_url(value)


class EndpointPatch(BaseModel):
    url: str | None = Field(default=None, min_length=8, max_length=2000)
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=10000)
    enabled: bool | None = None

    @field_validator("url")
    @classmethod
    def public_http_url(cls, value: str | None) -> str | None:
        return validate_endpoint_url(value) if value is not None else None

    @model_validator(mode="after")
    def at_least_one_change(self) -> EndpointPatch:
        if not self.model_fields_set:
            raise ValueError("provide at least one field to update")
        if any(
            field in self.model_fields_set and getattr(self, field) is None
            for field in ("url", "rate_limit_per_minute", "enabled")
        ):
            raise ValueError("endpoint patch fields must not be null")
        return self


class EndpointOut(BaseModel):
    id: str
    url: str
    rate_limit_per_minute: int
    enabled: bool
    created_at: str


class EndpointCreated(EndpointOut):
    """Creation response carrying the plaintext signing secret exactly once."""

    secret: str


class EndpointRotated(BaseModel):
    id: str
    secret: str


class EventCreate(BaseModel):
    endpoint_id: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any]
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)


class EventOut(BaseModel):
    id: str
    endpoint_id: str
    delivery_id: str
    deduplicated: bool = False


class DeliveryOut(BaseModel):
    id: str
    event_id: str
    endpoint_id: str
    status: str
    attempts: int
    next_attempt_at: str | None
    last_status_code: int | None
    last_error: str | None
    latency_ms: int | None
