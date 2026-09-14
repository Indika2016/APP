from __future__ import annotations

import datetime
import time

import psycopg
from psycopg.rows import DictRow


async def log_ingest(
    conn: psycopg.AsyncConnection[DictRow],
    *,
    source: str,
    endpoint: str | None,
    ok: bool,
    rows: int | None,
    latency_ms: int | None,
    error: str | None,
) -> None:
    """Log to the ingest_log table (rule: log to stdout AND ingest_log)."""
    ts_ms = int(time.time() * 1000)
    await conn.execute(
        "INSERT INTO ingest_log (ts_ms, source, endpoint, ok, rows, latency_ms, error) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (ts_ms, source, endpoint, 1 if ok else 0, rows, latency_ms, error),
    )
    status = "OK" if ok else "FAIL"
    line = f"[{_fmt(ts_ms)}] {source} {endpoint} {status} rows={rows} latency={latency_ms}ms"
    if error:
        line += f" error={error}"
    print(line)


def _fmt(ts_ms: int) -> str:
    return datetime.datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
