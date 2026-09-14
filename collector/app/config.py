from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time as dtime
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.toml"

# collector/app/config.py -> collector/app -> collector -> repo root.
# Kept as a fixed relative layout (not a config.toml setting) because it's a
# repo-structure fact, not something that varies between environments; the
# Dockerfile mirrors this same depth when it copies watchlist.csv into the image.
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WATCHLIST_CSV = _REPO_ROOT / "watchlist.csv"


@dataclass(frozen=True)
class MarketConfig:
    timezone: str
    open_time: dtime
    close_time: dtime
    poll_interval_open_seconds: int
    poll_interval_closed_seconds: int


@dataclass(frozen=True)
class NetworkConfig:
    base_url: str
    user_agent: str
    timeout_seconds: float
    backoff_base_seconds: float
    backoff_max_seconds: float


@dataclass(frozen=True)
class Config:
    market: MarketConfig
    network: NetworkConfig
    database_url: str
    watchlist_csv: Path


def _parse_time(value: str) -> dtime:
    hour, minute = value.split(":")
    return dtime(int(hour), int(minute))


def load_config(path: Path | None = None) -> Config:
    cfg_path = path or DEFAULT_CONFIG_PATH
    with open(cfg_path, "rb") as f:
        raw = tomllib.load(f)

    market = raw["market"]
    network = raw["network"]

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set -- point it at Supabase's session/direct "
            "Postgres connection string (Project Settings -> Database -> "
            "Connection string -> Session pooler). See .env.example. Never "
            "commit this value."
        )

    return Config(
        market=MarketConfig(
            timezone=market["timezone"],
            open_time=_parse_time(market["open_time"]),
            close_time=_parse_time(market["close_time"]),
            poll_interval_open_seconds=int(market["poll_interval_open_seconds"]),
            poll_interval_closed_seconds=int(market["poll_interval_closed_seconds"]),
        ),
        network=NetworkConfig(
            base_url=network["base_url"],
            user_agent=network["user_agent"],
            timeout_seconds=float(network["timeout_seconds"]),
            backoff_base_seconds=float(network["backoff_base_seconds"]),
            backoff_max_seconds=float(network["backoff_max_seconds"]),
        ),
        database_url=database_url,
        watchlist_csv=DEFAULT_WATCHLIST_CSV,
    )
