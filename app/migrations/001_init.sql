CREATE TABLE IF NOT EXISTS instruments (
  symbol            TEXT PRIMARY KEY,      -- 'JKH.N0000'
  short_code        TEXT NOT NULL,         -- 'JKH'
  name              TEXT NOT NULL,
  isin              TEXT,
  sector            TEXT,
  quantity_issued   INTEGER,
  in_watchlist      INTEGER NOT NULL DEFAULT 0,
  first_seen_ms     INTEGER NOT NULL,
  updated_ms        INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ticks (
  id                INTEGER PRIMARY KEY,
  symbol            TEXT NOT NULL REFERENCES instruments(symbol),
  ts_exchange_ms    INTEGER NOT NULL,      -- lastTradedTime from the API
  ts_ingest_ms      INTEGER NOT NULL,      -- our clock, for latency analysis
  price             REAL,
  prev_close        REAL,
  open              REAL,
  high              REAL,
  low               REAL,
  change            REAL,
  pct_change        REAL,
  turnover          REAL,                  -- LKR, on-market
  share_volume      INTEGER,               -- on-market
  trade_volume      INTEGER,               -- number of trades
  crossing_volume   INTEGER,               -- block trades: KEEP SEPARATE
  crossing_trades   INTEGER,
  market_cap        REAL,
  status            INTEGER,
  source            TEXT NOT NULL          -- 'rest' | 'ws'
);
CREATE INDEX IF NOT EXISTS ix_ticks_sym_ts ON ticks(symbol, ts_exchange_ms);
CREATE UNIQUE INDEX IF NOT EXISTS ux_ticks_dedup ON ticks(symbol, ts_exchange_ms, price, share_volume, turnover);

CREATE TABLE IF NOT EXISTS daily_bars (
  symbol            TEXT NOT NULL REFERENCES instruments(symbol),
  trade_date        TEXT NOT NULL,         -- 'YYYY-MM-DD' Asia/Colombo
  open REAL, high REAL, low REAL, close REAL, prev_close REAL,
  turnover REAL, share_volume INTEGER, trade_volume INTEGER, crossing_volume INTEGER,
  is_final          INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (symbol, trade_date)
);

CREATE TABLE IF NOT EXISTS corporate_actions (
  id          INTEGER PRIMARY KEY,
  symbol      TEXT NOT NULL REFERENCES instruments(symbol),
  ex_date     TEXT NOT NULL,               -- 'YYYY-MM-DD'
  kind        TEXT NOT NULL,               -- 'split' | 'bonus' | 'rights' | 'dividend'
  ratio_from  REAL, ratio_to REAL,         -- split 1->10 is from=1 to=10
  cash_amount REAL,
  note        TEXT,
  source      TEXT                         -- 'manual' | 'detected'
);

CREATE TABLE IF NOT EXISTS market_snapshots (
  ts_ms        INTEGER PRIMARY KEY,
  status       TEXT,
  aspi         REAL,
  snp_sl20     REAL,
  turnover     REAL,
  share_volume INTEGER,
  trades       INTEGER
);

CREATE TABLE IF NOT EXISTS ingest_log (
  id         INTEGER PRIMARY KEY,
  ts_ms      INTEGER NOT NULL,
  source     TEXT NOT NULL,
  endpoint   TEXT,
  ok         INTEGER NOT NULL,
  rows       INTEGER,
  latency_ms INTEGER,
  error      TEXT
);
