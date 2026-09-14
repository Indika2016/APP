from __future__ import annotations

import csv
import time
from pathlib import Path

import psycopg
from psycopg.rows import DictRow

from .cse_client import CSEClient
from .logging_utils import log_ingest

# Field names are guesses -- /api/allSecurityCode's shape was never verified
# (docs/cse-api.md marks it "GET, returns instrument master list" with no
# sample payload). We try a handful of plausible keys and fall back cleanly
# rather than assume; the tradeSummary poller upserts any instrument it sees
# regardless, so a total parse failure here just means we start empty and
# fill in from the first poll instead of from this seed.
_SYMBOL_KEYS = ("symbol", "Symbol", "securityId", "securityCode")
_NAME_KEYS = ("name", "Name", "companyName", "securityName")


def _now_ms() -> int:
    return int(time.time() * 1000)


async def seed_from_watchlist(conn: psycopg.AsyncConnection[DictRow], csv_path: Path) -> int:
    now_ms = _now_ms()
    count = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            symbol = row["symbol"].strip()
            await conn.execute(
                """
                INSERT INTO instruments (symbol, short_code, name, sector, in_watchlist, first_seen_ms, updated_ms)
                VALUES (%(symbol)s, %(short_code)s, %(name)s, %(sector)s, 1, %(now_ms)s, %(now_ms)s)
                ON CONFLICT (symbol) DO UPDATE SET
                    short_code = EXCLUDED.short_code,
                    name = EXCLUDED.name,
                    sector = EXCLUDED.sector,
                    in_watchlist = 1,
                    updated_ms = EXCLUDED.updated_ms
                """,
                {
                    "symbol": symbol,
                    "short_code": row["short_code"].strip(),
                    "name": row["name"].strip(),
                    "sector": (row.get("sector") or "").strip() or None,
                    "now_ms": now_ms,
                },
            )
            count += 1
    return count


def _extract_records(payload: object) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list):
                return value
    raise ValueError(f"unrecognized allSecurityCode shape: {type(payload).__name__}")


def _first(rec: dict, keys: tuple) -> str | None:
    for key in keys:
        value = rec.get(key)
        if value:
            return str(value).strip()
    return None


async def seed_from_all_security_code(
    conn: psycopg.AsyncConnection[DictRow], client: CSEClient
) -> tuple[int, int]:
    """Best-effort seed from /api/allSecurityCode. Never raises: on any failure
    or unrecognized shape it logs to ingest_log and returns (0, 0), per rule 5
    (log the bad schema, keep going, don't crash)."""
    now_ms = _now_ms()
    t0 = time.monotonic()
    try:
        payload = await client.get_all_security_code()
        records = _extract_records(payload)
    except Exception as e:
        await log_ingest(
            conn,
            source="rest",
            endpoint="/api/allSecurityCode",
            ok=False,
            rows=0,
            latency_ms=int((time.monotonic() - t0) * 1000),
            error=f"{e} -- falling back to watchlist.csv + tradeSummary discovery",
        )
        return 0, 0

    inserted = 0
    skipped = 0
    for rec in records:
        symbol = _first(rec, _SYMBOL_KEYS) if isinstance(rec, dict) else None
        if not symbol:
            skipped += 1
            continue
        name = _first(rec, _NAME_KEYS) if isinstance(rec, dict) else None
        await conn.execute(
            """
            INSERT INTO instruments (symbol, short_code, name, in_watchlist, first_seen_ms, updated_ms)
            VALUES (%(symbol)s, %(short_code)s, %(name)s, 0, %(now_ms)s, %(now_ms)s)
            ON CONFLICT (symbol) DO UPDATE SET
                name = EXCLUDED.name,
                updated_ms = EXCLUDED.updated_ms
            """,
            {
                "symbol": symbol,
                "short_code": symbol.split(".")[0],
                "name": name or symbol,
                "now_ms": now_ms,
            },
        )
        inserted += 1

    await log_ingest(
        conn,
        source="rest",
        endpoint="/api/allSecurityCode",
        ok=True,
        rows=inserted,
        latency_ms=int((time.monotonic() - t0) * 1000),
        error=f"skipped {skipped} unrecognized records" if skipped else None,
    )
    return inserted, skipped
