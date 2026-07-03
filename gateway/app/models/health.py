from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PublicHealthResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    status: str
    version: str
    db: str
    detail: str | None = None


class TenantHealthResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    status: str
    tenant_id: str
