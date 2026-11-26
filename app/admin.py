"""Token-guarded tenant and API-key provisioning."""

from __future__ import annotations

import hmac
from collections.abc import Callable

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import generate_api_key
from .config import get_settings
from .db import ApiKey, Tenant, as_utc_iso, new_id, utcnow

ADMIN_TOKEN_HEADER = "X-Admin-Token"


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ApiKeyCreate(BaseModel):
    label: str = Field(default="", max_length=200)


class TenantOut(BaseModel):
    id: str
    name: str
    created_at: str


class ApiKeyOut(BaseModel):
    id: str
    tenant_id: str
    label: str
    key_prefix: str
    created_at: str
    last_used_at: str | None
    revoked_at: str | None


class ApiKeyCreated(ApiKeyOut):
    """Returned once, carrying the only copy of the plaintext key."""

    api_key: str


def _api_key_out(row: ApiKey) -> ApiKeyOut:
    return ApiKeyOut(
        id=row.id,
        tenant_id=row.tenant_id,
        label=row.label,
        key_prefix=row.key_prefix,
        created_at=as_utc_iso(row.created_at),
        last_used_at=as_utc_iso(row.last_used_at) if row.last_used_at else None,
        revoked_at=as_utc_iso(row.revoked_at) if row.revoked_at else None,
    )


def require_admin(
    x_admin_token: str | None = Header(default=None, alias=ADMIN_TOKEN_HEADER),
) -> None:
    """Fail closed when the admin token is unset or does not match."""
    expected = get_settings().admin_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="admin API disabled: set HOOKFLOW_ADMIN_TOKEN to provision tenants",
        )
    if not x_admin_token or not hmac.compare_digest(
        x_admin_token.encode(), expected.encode()
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin token")


def build_admin_router(get_db: Callable[[], Session]) -> APIRouter:
    router = APIRouter(
        prefix="/v1/admin",
        tags=["admin"],
        dependencies=[Depends(require_admin)],
    )

    @router.post("/tenants", status_code=201, response_model=TenantOut)
    def create_tenant(payload: TenantCreate, db: Session = Depends(get_db)):
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="tenant name must not be blank")
        if db.query(Tenant).filter(Tenant.name == name).one_or_none():
            raise HTTPException(status_code=409, detail="tenant name already exists")
        tenant = Tenant(id=new_id(), name=name)
        db.add(tenant)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="tenant name already exists") from None
        db.refresh(tenant)
        return TenantOut(id=tenant.id, name=tenant.name, created_at=as_utc_iso(tenant.created_at))

    @router.get("/tenants", response_model=list[TenantOut])
    def list_tenants(
        limit: int = Query(default=100, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        db: Session = Depends(get_db),
    ):
        rows = db.query(Tenant).order_by(Tenant.created_at).offset(offset).limit(limit).all()
        return [
            TenantOut(id=tenant.id, name=tenant.name, created_at=as_utc_iso(tenant.created_at))
            for tenant in rows
        ]

    @router.post("/tenants/{tenant_id}/keys", status_code=201, response_model=ApiKeyCreated)
    def create_key(
        tenant_id: str,
        payload: ApiKeyCreate,
        db: Session = Depends(get_db),
    ):
        tenant = db.get(Tenant, tenant_id)
        if tenant is None:
            raise HTTPException(status_code=404, detail="tenant not found")
        plaintext, prefix, key_hash = generate_api_key()
        row = ApiKey(
            id=new_id(),
            tenant_id=tenant.id,
            key_prefix=prefix,
            key_hash=key_hash,
            label=payload.label,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return ApiKeyCreated(**_api_key_out(row).model_dump(), api_key=plaintext)

    @router.get("/tenants/{tenant_id}/keys", response_model=list[ApiKeyOut])
    def list_keys(
        tenant_id: str,
        limit: int = Query(default=100, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        db: Session = Depends(get_db),
    ):
        if db.get(Tenant, tenant_id) is None:
            raise HTTPException(status_code=404, detail="tenant not found")
        rows = (
            db.query(ApiKey)
            .filter(ApiKey.tenant_id == tenant_id)
            .order_by(ApiKey.created_at)
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [_api_key_out(row) for row in rows]

    @router.post("/keys/{key_id}/revoke", response_model=ApiKeyOut)
    def revoke_key(key_id: str, db: Session = Depends(get_db)):
        row = db.get(ApiKey, key_id)
        if row is None:
            raise HTTPException(status_code=404, detail="api key not found")
        if row.revoked_at is None:
            row.revoked_at = utcnow()
            db.add(row)
            db.commit()
            db.refresh(row)
        return _api_key_out(row)

    return router
