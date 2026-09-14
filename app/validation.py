from __future__ import annotations

from typing import Any


class PayloadShapeError(ValueError):
    """Raised when an upstream response doesn't match the shape docs/cse-api.md documents."""


def extract_trade_summary_rows(payload: Any) -> list[Any]:
    """Validate the top-level shape of POST /api/tradeSummary and return its row list.

    Expected: {"reqTradeSummery": [ {...}, ... ]}
    """
    if not isinstance(payload, dict):
        raise PayloadShapeError(f"expected a JSON object, got {type(payload).__name__}")
    rows = payload.get("reqTradeSummery")
    if not isinstance(rows, list):
        raise PayloadShapeError("response missing a 'reqTradeSummery' list")
    return rows


def normalize_row(row: Any) -> dict | None:
    """Turn one tradeSummary row into a flat dict matching the ticks table columns.

    Returns None if the row is missing something we can't do without (symbol,
    a numeric price, or an exchange timestamp) -- callers should count these as
    skipped/malformed rather than crash the whole poll over one bad row.
    """
    if not isinstance(row, dict):
        return None

    symbol = row.get("symbol")
    if not symbol or not isinstance(symbol, str):
        return None

    try:
        ts_exchange_ms = _int(row.get("lastTradedTime"))
        if ts_exchange_ms is None:
            return None
        return {
            "symbol": symbol,
            "name": row.get("name"),
            "price": _num(row.get("price")),
            "prev_close": _num(row.get("previousClose")),
            "open": _num(row.get("open")),
            "high": _num(row.get("high")),
            "low": _num(row.get("low")),
            "change": _num(row.get("change")),
            "pct_change": _num(row.get("percentageChange")),
            "turnover": _num(row.get("turnover")),
            "share_volume": _int(row.get("sharevolume")),
            "trade_volume": _int(row.get("tradevolume")),
            "crossing_volume": _int(row.get("crossingVolume")),
            "crossing_trades": _int(row.get("crossingTradeVol")),
            "market_cap": _num(row.get("marketCap")),
            "status": _int(row.get("status")),
            "ts_exchange_ms": ts_exchange_ms,
        }
    except (TypeError, ValueError):
        return None


def normalize_market_snapshot(summary: Any, last_update: Any) -> dict | None:
    """Combine POST /api/marketSummery and GET /api/lastUpdateTime into one
    market_snapshots row. Returns None (skip, don't write garbage) if either
    shape is unrecognized. There is no verified REST source for the ASPI /
    S&P SL20 index *level* -- docs/cse-api.md only turned up a year-over-year
    delta (/api/aspi/year) and a bare status flag (/api/returnAspiSnp), not the
    live index value. Those columns stay NULL here; the real fix is the
    /topic/aspi and /topic/snp websocket topics in Phase 5.
    """
    if not isinstance(summary, dict) or not isinstance(last_update, dict):
        return None
    try:
        ts_ms = _int(last_update.get("lastUpdatedTime"))
        if ts_ms is None:
            return None
        return {
            "ts_ms": ts_ms,
            "turnover": _num(summary.get("tradeVolume")),
            "share_volume": _int(summary.get("shareVolume")),
            "trades": _int(summary.get("trades")),
        }
    except (TypeError, ValueError):
        return None


def _num(value: Any) -> float | None:
    return None if value is None else float(value)


def _int(value: Any) -> int | None:
    return None if value is None else int(value)
