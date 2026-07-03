from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")


def path_from_env(name: str, default_name: str) -> Path:
    raw_path = os.getenv(name, default_name)
    path = Path(raw_path)
    return path if path.is_absolute() else BASE_DIR / path


@dataclass(frozen=True)
class Settings:
    jwt_private_key_path: Path = path_from_env("JWT_PRIVATE_KEY_PATH", "private.pem")
    jwt_public_key_path: Path = path_from_env("JWT_PUBLIC_KEY_PATH", "public.pem")
    jwt_issuer: str = os.getenv("JWT_ISSUER", "argus-gateway")
    jwt_algorithm: str = "RS256"
    access_token_ttl_seconds: int = 3600
    dev_auth_password: str = os.environ["DEV_AUTH_PASSWORD"]
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60


settings = Settings()
