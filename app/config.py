from __future__ import annotations

from dataclasses import dataclass
from datetime import time as dtime
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.toml"


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
class DatabaseConfig:
    path: Path


@dataclass(frozen=True)
class Config:
    market: MarketConfig
    network: NetworkConfig
    database: DatabaseConfig
    watchlist_csv: Path


def _parse_time(value: str) -> dtime:
    hour, minute = value.split(":")
    return dtime(int(hour), int(minute))


def load_config(path: Path | None = None) -> Config:
    cfg_path = path or DEFAULT_CONFIG_PATH
    with open(cfg_path, "rb") as f:
        raw = tomllib.load(f)

    project_root = cfg_path.parent
    market = raw["market"]
    network = raw["network"]
    database = raw["database"]
    paths = raw["paths"]

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
        database=DatabaseConfig(path=project_root / database["path"]),
        watchlist_csv=project_root / paths["watchlist_csv"],
    )
