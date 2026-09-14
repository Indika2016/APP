from __future__ import annotations

import datetime

from . import db
from .config import load_config


async def print_report() -> None:
    """Print instrument/tick counts and the tail of ingest_log."""
    cfg = load_config()
    conn = await db.get_connection(cfg.database_url)
    try:
        total_instruments = (await db.fetchone(conn, "SELECT COUNT(*) AS c FROM instruments"))["c"]
        watchlist_instruments = (
            await db.fetchone(conn, "SELECT COUNT(*) AS c FROM instruments WHERE in_watchlist = 1")
        )["c"]
        total_ticks = (await db.fetchone(conn, "SELECT COUNT(*) AS c FROM ticks"))["c"]
        symbols_with_ticks = (
            await db.fetchone(conn, "SELECT COUNT(DISTINCT symbol) AS c FROM ticks")
        )["c"]

        print("=== instruments ===")
        print(f"total: {total_instruments}  (watchlist: {watchlist_instruments})")

        print("\n=== ticks ===")
        print(f"total rows: {total_ticks}  (symbols with at least one tick: {symbols_with_ticks})")

        print("\n=== last 20 ingest_log rows ===")
        rows = await db.fetchall(
            conn,
            "SELECT ts_ms, source, endpoint, ok, rows, latency_ms, error "
            "FROM ingest_log ORDER BY id DESC LIMIT 20",
        )
        if not rows:
            print("(empty)")
        for r in reversed(rows):
            ts = datetime.datetime.fromtimestamp(r["ts_ms"] / 1000).strftime("%Y-%m-%d %H:%M:%S")
            status = "OK" if r["ok"] else "FAIL"
            line = (
                f"{ts}  {r['source']:5s} {(r['endpoint'] or ''):28s} {status:4s} "
                f"rows={r['rows']}  latency={r['latency_ms']}ms"
            )
            if r["error"]:
                line += f"  error={r['error']}"
            print(line)
    finally:
        await conn.close()
