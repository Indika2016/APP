from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles

from .collector import is_market_open
from .config import Config, load_config
from .db import get_connection

STATIC_DIR = Path(__file__).resolve().parent / "static"

_QUOTES_SQL = """
    WITH latest AS (
        SELECT *, ROW_NUMBER() OVER (
            PARTITION BY symbol ORDER BY ts_exchange_ms DESC, id DESC
        ) AS rn
        FROM ticks
    )
    SELECT i.symbol, i.short_code, i.name, i.sector, i.in_watchlist,
           l.price, l.prev_close, l.change, l.pct_change,
           l.turnover, l.share_volume, l.trade_volume,
           l.crossing_volume, l.crossing_trades,
           l.market_cap, l.status, l.ts_exchange_ms
    FROM instruments i
    JOIN latest l ON l.symbol = i.symbol AND l.rn = 1
    WHERE (:watchlist_only = 0 OR i.in_watchlist = 1)
    ORDER BY i.symbol
"""


def create_app(cfg: Config | None = None) -> FastAPI:
    cfg = cfg or load_config()
    app = FastAPI(title="CSE Live")

    def db_conn():
        # Short-lived per-request connection; SQLite WAL handles concurrent
        # readers fine against the collector's single writer connection.
        return get_connection(cfg.database.path)

    @app.get("/api/market")
    def api_market() -> dict:
        conn = db_conn()
        try:
            row = conn.execute(
                "SELECT ts_ms, status, aspi, snp_sl20, turnover, share_volume, trades "
                "FROM market_snapshots ORDER BY ts_ms DESC LIMIT 1"
            ).fetchone()
            records_since = conn.execute("SELECT MIN(ts_exchange_ms) m FROM ticks").fetchone()["m"]
        finally:
            conn.close()

        now = datetime.now(ZoneInfo(cfg.market.timezone))
        return {
            "status": "OPEN" if is_market_open(now, cfg) else "CLOSED",
            "aspi": row["aspi"] if row else None,
            "snp_sl20": row["snp_sl20"] if row else None,
            "turnover": row["turnover"] if row else None,
            "share_volume": row["share_volume"] if row else None,
            "trades": row["trades"] if row else None,
            "as_of_exchange_ms": row["ts_ms"] if row else None,
            "records_since_ms": records_since,
        }

    @app.get("/api/quotes")
    def api_quotes(watchlist: bool = Query(default=True)) -> list[dict]:
        conn = db_conn()
        try:
            rows = conn.execute(_QUOTES_SQL, {"watchlist_only": 1 if watchlist else 0}).fetchall()
        finally:
            conn.close()
        return [dict(r) for r in rows]

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


app = create_app()
