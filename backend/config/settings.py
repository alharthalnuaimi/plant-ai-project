"""
Centralised runtime settings loaded from environment / .env file.

Keeps secrets out of code, gives services a single import-point for
config, and makes it trivial to swap persistence backends without
touching business logic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .paths import REPO_ROOT


def _load_dotenv_if_present() -> None:
    """Tiny .env loader (no extra dependency).

    Falls back silently if `python-dotenv` is not installed and `.env` is
    missing. Only assigns variables that are not already in os.environ so
    real env vars always win.
    """

    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        # silently ignore — production deployments will use real env vars
        return


_load_dotenv_if_present()


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _str(name: str, default: str) -> str:
    val = os.environ.get(name)
    return val if val is not None and val != "" else default


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    persistence_backend: Literal["postgres", "memory"]
    database_url: str
    postgres_host: str
    postgres_port: int
    postgres_user: str
    postgres_password: str
    postgres_db: str
    persist_events: bool
    persist_sensor_history: bool
    persist_scan_history: bool

    @property
    def use_postgres(self) -> bool:
        return self.persistence_backend == "postgres"


def _build_database_url(
    user: str, password: str, host: str, port: int, db: str
) -> str:
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def load_settings() -> Settings:
    backend = _str("PERSISTENCE_BACKEND", "memory").lower()
    if backend not in {"postgres", "memory"}:
        backend = "memory"
    user = _str("POSTGRES_USER", "postgres")
    password = _str("POSTGRES_PASSWORD", "plantvision_dev")
    db = _str("POSTGRES_DB", "plantvision")
    host = _str("POSTGRES_HOST", "localhost")
    port = _int("POSTGRES_PORT", 54322)
    database_url = _str(
        "DATABASE_URL",
        _build_database_url(user, password, host, port, db),
    )
    return Settings(
        persistence_backend=backend,  # type: ignore[arg-type]
        database_url=database_url,
        postgres_host=host,
        postgres_port=port,
        postgres_user=user,
        postgres_password=password,
        postgres_db=db,
        persist_events=_bool("PERSIST_EVENTS", True),
        persist_sensor_history=_bool("PERSIST_SENSOR_HISTORY", True),
        persist_scan_history=_bool("PERSIST_SCAN_HISTORY", True),
    )


# Single instance imported across the backend.
SETTINGS = load_settings()
