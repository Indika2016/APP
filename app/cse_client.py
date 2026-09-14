from __future__ import annotations

from typing import Any

import httpx

from .config import NetworkConfig


class CSEClient:
    """Thin async wrapper over the CSE endpoints documented in docs/cse-api.md.

    Undocumented internal API -- callers are responsible for validating the
    shape of whatever comes back (see app/validation.py).
    """

    def __init__(self, network: NetworkConfig):
        self._network = network
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "CSEClient":
        self._client = httpx.AsyncClient(
            base_url=self._network.base_url,
            headers={"User-Agent": self._network.user_agent},
            timeout=self._network.timeout_seconds,
        )
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def get_trade_summary(self) -> Any:
        """POST /api/tradeSummary -- the whole market in one call."""
        assert self._client is not None
        resp = await self._client.post(
            "/api/tradeSummary",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            content=b"",
        )
        resp.raise_for_status()
        return resp.json()

    async def get_all_security_code(self) -> Any:
        """GET /api/allSecurityCode -- instrument master list."""
        assert self._client is not None
        resp = await self._client.get("/api/allSecurityCode")
        resp.raise_for_status()
        return resp.json()

    async def get_market_summary(self) -> Any:
        """POST /api/marketSummery -- market totals. Note the API's own naming
        is inconsistent with tradeSummary: 'tradeVolume' here is turnover in
        LKR, not a share count (see docs/cse-api.md)."""
        assert self._client is not None
        resp = await self._client.post(
            "/api/marketSummery",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            content=b"",
        )
        resp.raise_for_status()
        return resp.json()

    async def get_last_update_time(self) -> Any:
        """GET /api/lastUpdateTime -- cheap freshness probe, doubles as the
        exchange-supplied timestamp for a market snapshot."""
        assert self._client is not None
        resp = await self._client.get("/api/lastUpdateTime")
        resp.raise_for_status()
        return resp.json()
