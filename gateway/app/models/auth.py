from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TokenRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    username: str
    password: str


class TokenResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    access_token: str
    token_type: str
    expires_in: int
