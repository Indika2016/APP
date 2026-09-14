-- Postgres/Supabase port of the SQLite schema from SPEC.md section 3.
-- Run this once in the Supabase SQL editor (or via `psql`) against a fresh project.
--
-- Notable differences from the SQLite version:
--   * epoch-millisecond columns are BIGINT, not INTEGER -- Postgres INTEGER is
--     32-bit (max ~2.1B) and current epoch-ms values are already ~1.7 trillion.
--   * REAL -> DOUBLE PRECISION (SQLite's REAL is already an 8-byte float, so
--     this is a direct port, not a precision change).
--   * auto-increment ids use `GENERATED ALWAYS AS IDENTITY` (modern Postgres)
--     instead of SQLite's INTEGER PRIMARY KEY rowid alias.
--   * `INSERT OR IGNORE` becomes `ON CONFLICT ... DO NOTHING` in application code.
--
-- RLS is intentionally left disabled: nothing here is ever queried through
-- Supabase's public PostgREST/anon-key API. Only the Python collector and the
-- Netlify functions connect, both using a server-side-only connection string
-- (Supabase's pooled "Transaction" connection string, kept in env vars, never
-- shipped to the browser).

CREATE TABLE IF NOT EXISTS instruments (
  symbol            TEXT PRIMARY KEY,      -- 'JKH.N0000'
  short_code        TEXT NOT NULL,         -- 'JKH'
  name              TEXT NOT NULL,
  isin              TEXT,
  sector            TEXT,
  quantity_issued   BIGINT,
  in_watchlist      INTEGER NOT NULL DEFAULT 0,
  first_seen_ms     BIGINT NOT NULL,
  updated_ms        BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS ticks (
  id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  symbol            TEXT NOT NULL REFERENCES instruments(symbol),
  ts_exchange_ms    BIGINT NOT NULL,       -- lastTradedTime from the API
  ts_ingest_ms      BIGINT NOT NULL,       -- our clock, for latency analysis
  price             DOUBLE PRECISION,
  prev_close        DOUBLE PRECISION,
  open              DOUBLE PRECISION,
  high              DOUBLE PRECISION,
  low               DOUBLE PRECISION,
  change            DOUBLE PRECISION,
  pct_change        DOUBLE PRECISION,
  turnover          DOUBLE PRECISION,      -- LKR, on-market
  share_volume      BIGINT,                -- on-market
  trade_volume      BIGINT,                -- number of trades
  crossing_volume   BIGINT,                -- block trades: KEEP SEPARATE
  crossing_trades   BIGINT,
  market_cap        DOUBLE PRECISION,
  status            INTEGER,
  source            TEXT NOT NULL          -- 'rest' | 'ws'
);
CREATE INDEX IF NOT EXISTS ix_ticks_sym_ts ON ticks(symbol, ts_exchange_ms);
CREATE UNIQUE INDEX IF NOT EXISTS ux_ticks_dedup ON ticks(symbol, ts_exchange_ms, price, share_volume, turnover);

CREATE TABLE IF NOT EXISTS daily_bars (
  symbol            TEXT NOT NULL REFERENCES instruments(symbol),
  trade_date        TEXT NOT NULL,         -- 'YYYY-MM-DD' Asia/Colombo
  open DOUBLE PRECISION, high DOUBLE PRECISION, low DOUBLE PRECISION,
  close DOUBLE PRECISION, prev_close DOUBLE PRECISION,
  turnover DOUBLE PRECISION, share_volume BIGINT, trade_volume BIGINT, crossing_volume BIGINT,
  is_final          INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (symbol, trade_date)
);

CREATE TABLE IF NOT EXISTS corporate_actions (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  symbol      TEXT NOT NULL REFERENCES instruments(symbol),
  ex_date     TEXT NOT NULL,               -- 'YYYY-MM-DD'
  kind        TEXT NOT NULL,               -- 'split' | 'bonus' | 'rights' | 'dividend'
  ratio_from  DOUBLE PRECISION, ratio_to DOUBLE PRECISION,   -- split 1->10 is from=1 to=10
  cash_amount DOUBLE PRECISION,
  note        TEXT,
  source      TEXT                         -- 'manual' | 'detected'
);

CREATE TABLE IF NOT EXISTS market_snapshots (
  ts_ms        BIGINT PRIMARY KEY,
  status       TEXT,
  aspi         DOUBLE PRECISION,
  snp_sl20     DOUBLE PRECISION,
  turnover     DOUBLE PRECISION,
  share_volume BIGINT,
  trades       INTEGER
);

CREATE TABLE IF NOT EXISTS ingest_log (
  id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ts_ms      BIGINT NOT NULL,
  source     TEXT NOT NULL,
  endpoint   TEXT,
  ok         INTEGER NOT NULL,
  rows       INTEGER,
  latency_ms INTEGER,
  error      TEXT
);

CREATE TABLE IF NOT EXISTS schema_migrations (
  filename    TEXT PRIMARY KEY,
  applied_ms  BIGINT NOT NULL
);
