import type { Handler } from "@netlify/functions";
import { getPool } from "./lib/db";

const QUOTES_SQL = `
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
  WHERE ($1::int = 0 OR i.in_watchlist = 1)
  ORDER BY i.symbol
`;

export const handler: Handler = async (event) => {
  const watchlistParam = event.queryStringParameters?.watchlist;
  // Matches the old FastAPI route's default (watchlist=true when omitted).
  const watchlistOnly = watchlistParam !== "false" && watchlistParam !== "0";

  try {
    const pool = getPool();
    const result = await pool.query(QUOTES_SQL, [watchlistOnly ? 1 : 0]);
    const rows = result.rows.map((r) => ({
      ...r,
      share_volume: r.share_volume != null ? Number(r.share_volume) : null,
      trade_volume: r.trade_volume != null ? Number(r.trade_volume) : null,
      crossing_volume: r.crossing_volume != null ? Number(r.crossing_volume) : null,
      crossing_trades: r.crossing_trades != null ? Number(r.crossing_trades) : null,
      ts_exchange_ms: r.ts_exchange_ms != null ? Number(r.ts_exchange_ms) : null,
    }));

    return {
      statusCode: 200,
      headers: { "content-type": "application/json", "cache-control": "no-store" },
      body: JSON.stringify(rows),
    };
  } catch (err) {
    console.error(err);
    return {
      statusCode: 500,
      headers: { "content-type": "application/json", "cache-control": "no-store" },
      body: JSON.stringify({ error: "internal error" }),
    };
  }
};
