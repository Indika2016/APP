import type { Handler } from "@netlify/functions";
import { getPool } from "./lib/db";

// Mirrors collector/app/collector.py's is_market_open() and
// collector/config.toml's [market] section (Mon-Fri 09:30-14:30 Asia/Colombo).
// Two runtimes, so this rule is necessarily duplicated -- keep both in sync
// if the trading hours ever change.
function isMarketOpen(now: Date): boolean {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Colombo",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(now);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  const weekday = get("weekday");
  if (weekday === "Sat" || weekday === "Sun") return false;

  const hour = Number(get("hour"));
  const minute = Number(get("minute"));
  const minutesNow = hour * 60 + minute;
  return minutesNow >= 9 * 60 + 30 && minutesNow <= 14 * 60 + 30;
}

export const handler: Handler = async () => {
  try {
    const pool = getPool();
    const [snapshot, since] = await Promise.all([
      pool.query(
        `SELECT ts_ms, status, aspi, snp_sl20, turnover, share_volume, trades
         FROM market_snapshots ORDER BY ts_ms DESC LIMIT 1`
      ),
      pool.query(`SELECT MIN(ts_exchange_ms) AS m FROM ticks`),
    ]);
    const row = snapshot.rows[0];

    return {
      statusCode: 200,
      headers: { "content-type": "application/json", "cache-control": "no-store" },
      body: JSON.stringify({
        status: isMarketOpen(new Date()) ? "OPEN" : "CLOSED",
        aspi: row?.aspi ?? null,
        snp_sl20: row?.snp_sl20 ?? null,
        turnover: row?.turnover ?? null,
        share_volume: row?.share_volume != null ? Number(row.share_volume) : null,
        trades: row?.trades ?? null,
        as_of_exchange_ms: row?.ts_ms != null ? Number(row.ts_ms) : null,
        records_since_ms: since.rows[0]?.m != null ? Number(since.rows[0].m) : null,
      }),
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
