from __future__ import annotations

import datetime

from .config import load_config
from .db import get_connection


def print_report() -> None:
    """Print instrument/tick counts and the tail of ingest_log -- the proof
    Phase 1 asks for: rows inserted, duplicates suppressed (via ingest_log),
    and ingest_log's own contents."""
    cfg = load_config()
    if not cfg.database.path.exists():
        print(f"no database found at {cfg.database.path} -- run `python -m app` first")
        return

    conn = get_connection(cfg.database.path)

    total_instruments = conn.execute("SELECT COUNT(*) c FROM instruments").fetchone()["c"]
    watchlist_instruments = conn.execute(
        "SELECT COUNT(*) c FROM instruments WHERE in_watchlist = 1"
    ).fetchone()["c"]
    total_ticks = conn.execute("SELECT COUNT(*) c FROM ticks").fetchone()["c"]
    symbols_with_ticks = conn.execute("SELECT COUNT(DISTINCT symbol) c FROM ticks").fetchone()["c"]

    print("=== instruments ===")
    print(f"total: {total_instruments}  (watchlist: {watchlist_instruments})")

    print("\n=== ticks ===")
    print(f"total rows: {total_ticks}  (symbols with at least one tick: {symbols_with_ticks})")

    print("\n=== last 20 ingest_log rows ===")
    rows = conn.execute(
        "SELECT ts_ms, source, endpoint, ok, rows, latency_ms, error "
        "FROM ingest_log ORDER BY id DESC LIMIT 20"
    ).fetchall()
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

    conn.close()
