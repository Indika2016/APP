from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import DictRow

from . import db, seed
from .config import Config, load_config
from .cse_client import CSEClient
from .logging_utils import log_ingest
from .validation import extract_trade_summary_rows, normalize_market_snapshot, normalize_row

# (price, share_volume, turnover, trade_volume) -- the fields rule 4 says must
# change before we write a new tick.
TickSignature = tuple


@dataclass
class Stats:
    polls: int = 0
    failures: int = 0
    inserted: int = 0
    duplicates: int = 0
    malformed: int = 0
    reconnects: int = 0

    def print_summary(self) -> None:
        print("\n--- collector summary ---")
        print(f"polls attempted        : {self.polls}")
        print(f"polls failed           : {self.failures}")
        print(f"ticks inserted         : {self.inserted}")
        print(f"duplicates suppressed  : {self.duplicates}")
        print(f"malformed rows skipped : {self.malformed}")
        print(f"DB reconnects          : {self.reconnects}")


def is_market_open(now: datetime, cfg: Config) -> bool:
    if now.weekday() >= 5:  # Sat, Sun
        return False
    return cfg.market.open_time <= now.time() <= cfg.market.close_time


def poll_interval_seconds(cfg: Config) -> int:
    now = datetime.now(ZoneInfo(cfg.market.timezone))
    if is_market_open(now, cfg):
        return cfg.market.poll_interval_open_seconds
    return cfg.market.poll_interval_closed_seconds


async def _ensure_connection(
    conn: psycopg.AsyncConnection[DictRow], database_url: str, stats: Stats
) -> psycopg.AsyncConnection[DictRow]:
    """Supabase's pooled connections can be dropped after idle periods (our
    slow-market cadence is up to 15 minutes between polls). Ping before each
    cycle and transparently reconnect rather than letting the whole process die."""
    try:
        await conn.execute("SELECT 1")
        return conn
    except Exception:
        try:
            await conn.close()
        except Exception:
            pass
        print("DB connection lost -- reconnecting...")
        stats.reconnects += 1
        return await db.get_connection(database_url)


async def load_watchlist_symbols(conn: psycopg.AsyncConnection[DictRow]) -> set[str]:
    rows = await db.fetchall(conn, "SELECT symbol FROM instruments WHERE in_watchlist = 1")
    return {r["symbol"] for r in rows}


async def load_tick_state(conn: psycopg.AsyncConnection[DictRow]) -> dict[str, TickSignature]:
    """Rebuild the last-seen-signature cache from the DB so restarts don't
    reinsert rows that are unchanged from before the process stopped."""
    rows = await db.fetchall(
        conn,
        """
        SELECT symbol, price, share_volume, turnover, trade_volume
        FROM ticks
        WHERE id IN (SELECT MAX(id) FROM ticks GROUP BY symbol)
        """,
    )
    return {
        r["symbol"]: (r["price"], r["share_volume"], r["turnover"], r["trade_volume"])
        for r in rows
    }


async def _upsert_instrument_from_tick(
    conn: psycopg.AsyncConnection[DictRow],
    symbol: str,
    name: str | None,
    watchlist_symbols: set[str],
    now_ms: int,
) -> None:
    await conn.execute(
        """
        INSERT INTO instruments (symbol, short_code, name, in_watchlist, first_seen_ms, updated_ms)
        VALUES (%(symbol)s, %(short_code)s, %(name)s, %(in_watchlist)s, %(now_ms)s, %(now_ms)s)
        ON CONFLICT (symbol) DO UPDATE SET
            name = EXCLUDED.name,
            updated_ms = EXCLUDED.updated_ms
        """,
        {
            "symbol": symbol,
            "short_code": symbol.split(".")[0],
            "name": name or symbol,
            "in_watchlist": 1 if symbol in watchlist_symbols else 0,
            "now_ms": now_ms,
        },
    )


async def process_poll(
    conn: psycopg.AsyncConnection[DictRow],
    payload: object,
    state: dict[str, TickSignature],
    watchlist_symbols: set[str],
) -> tuple[int, int, int]:
    """Validate + apply one tradeSummary payload. Returns (inserted, duplicates, malformed).

    Raises PayloadShapeError if the top-level shape doesn't match docs/cse-api.md
    -- callers must catch that, log it, and keep last good data (rule 5).
    """
    rows = extract_trade_summary_rows(payload)
    now_ms = int(time.time() * 1000)
    inserted = duplicates = malformed = 0

    async with conn.transaction():
        for raw in rows:
            norm = normalize_row(raw)
            if norm is None:
                malformed += 1
                continue

            symbol = norm["symbol"]
            signature: TickSignature = (
                norm["price"],
                norm["share_volume"],
                norm["turnover"],
                norm["trade_volume"],
            )
            if state.get(symbol) == signature:
                duplicates += 1
                continue

            name = norm.pop("name")
            await _upsert_instrument_from_tick(conn, symbol, name, watchlist_symbols, now_ms)

            cur = await conn.execute(
                """
                INSERT INTO ticks (
                    symbol, ts_exchange_ms, ts_ingest_ms, price, prev_close, open, high, low,
                    change, pct_change, turnover, share_volume, trade_volume,
                    crossing_volume, crossing_trades, market_cap, status, source
                ) VALUES (
                    %(symbol)s, %(ts_exchange_ms)s, %(ts_ingest_ms)s, %(price)s, %(prev_close)s,
                    %(open)s, %(high)s, %(low)s, %(change)s, %(pct_change)s, %(turnover)s,
                    %(share_volume)s, %(trade_volume)s, %(crossing_volume)s, %(crossing_trades)s,
                    %(market_cap)s, %(status)s, 'rest'
                )
                ON CONFLICT (symbol, ts_exchange_ms, price, share_volume, turnover) DO NOTHING
                """,
                {**norm, "ts_ingest_ms": now_ms},
            )
            if cur.rowcount:
                inserted += 1
                state[symbol] = signature
            else:
                # Unique-index backstop caught what the in-memory check missed.
                duplicates += 1

    return inserted, duplicates, malformed


async def poll_market_snapshot(conn: psycopg.AsyncConnection[DictRow], client: CSEClient, cfg: Config) -> None:
    """Best-effort market totals snapshot. Independent of the tradeSummary
    poll: a failure here is logged but never affects tradeSummary's backoff,
    since it isn't the source of truth (rule: REST tradeSummary poller is)."""
    t0 = time.monotonic()
    try:
        summary, last_update = await asyncio.gather(
            client.get_market_summary(), client.get_last_update_time()
        )
        snap = normalize_market_snapshot(summary, last_update)
        if snap is None:
            raise ValueError("unrecognized marketSummery/lastUpdateTime shape")
        now = datetime.now(ZoneInfo(cfg.market.timezone))
        status = "OPEN" if is_market_open(now, cfg) else "CLOSED"
        await conn.execute(
            """
            INSERT INTO market_snapshots (ts_ms, status, aspi, snp_sl20, turnover, share_volume, trades)
            VALUES (%(ts_ms)s, %(status)s, NULL, NULL, %(turnover)s, %(share_volume)s, %(trades)s)
            ON CONFLICT (ts_ms) DO NOTHING
            """,
            {**snap, "status": status},
        )
        await log_ingest(
            conn,
            source="rest",
            endpoint="/api/marketSummery+lastUpdateTime",
            ok=True,
            rows=1,
            latency_ms=int((time.monotonic() - t0) * 1000),
            error=None,
        )
    except Exception as e:
        await log_ingest(
            conn,
            source="rest",
            endpoint="/api/marketSummery+lastUpdateTime",
            ok=False,
            rows=0,
            latency_ms=int((time.monotonic() - t0) * 1000),
            error=str(e),
        )


async def run(config_path: Path | None = None, once: bool = False) -> None:
    cfg = load_config(config_path)
    conn = await db.get_connection(cfg.database_url)
    applied = await db.apply_migrations(conn)
    if applied:
        print(f"applied migrations: {', '.join(applied)}")

    stats = Stats()

    try:
        async with CSEClient(cfg.network) as client:
            wl_count = await seed.seed_from_watchlist(conn, cfg.watchlist_csv)
            print(f"seeded/updated {wl_count} instruments from watchlist.csv")
            asc_count, asc_skipped = await seed.seed_from_all_security_code(conn, client)
            print(f"seeded/updated {asc_count} instruments from allSecurityCode (skipped {asc_skipped})")

            watchlist_symbols = await load_watchlist_symbols(conn)
            state = await load_tick_state(conn)
            print(f"loaded tick-state cache for {len(state)} symbols")

            consecutive_failures = 0

            while True:
                conn = await _ensure_connection(conn, cfg.database_url, stats)

                t0 = time.monotonic()
                try:
                    payload = await client.get_trade_summary()
                    inserted, duplicates, malformed = await process_poll(conn, payload, state, watchlist_symbols)
                    latency_ms = int((time.monotonic() - t0) * 1000)
                    error = f"skipped {malformed} malformed rows" if malformed else None
                    await log_ingest(
                        conn,
                        source="rest",
                        endpoint="/api/tradeSummary",
                        ok=True,
                        rows=inserted,
                        latency_ms=latency_ms,
                        error=error,
                    )
                    stats.polls += 1
                    stats.inserted += inserted
                    stats.duplicates += duplicates
                    stats.malformed += malformed
                    consecutive_failures = 0
                except Exception as e:
                    latency_ms = int((time.monotonic() - t0) * 1000)
                    try:
                        await log_ingest(
                            conn,
                            source="rest",
                            endpoint="/api/tradeSummary",
                            ok=False,
                            rows=0,
                            latency_ms=latency_ms,
                            error=str(e),
                        )
                    except Exception as log_err:
                        print(f"poll FAILED: {e}  (and could not write ingest_log: {log_err})")
                    stats.polls += 1
                    stats.failures += 1
                    consecutive_failures += 1

                await poll_market_snapshot(conn, client, cfg)

                if once:
                    break

                if consecutive_failures:
                    delay = min(
                        cfg.network.backoff_base_seconds * (2 ** (consecutive_failures - 1)),
                        cfg.network.backoff_max_seconds,
                    )
                else:
                    delay = poll_interval_seconds(cfg)

                await asyncio.sleep(delay)
    finally:
        stats.print_summary()
        await conn.close()
