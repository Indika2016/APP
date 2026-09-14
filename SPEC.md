# SPEC — CSE Live

Record Colombo Stock Exchange price data to a local database and serve a web GUI with a
**live feed** and **historical trends**.

Read `CLAUDE.md` first, and `docs/cse-api.md` before any network code.

---

## 1. What the user wants

1. A collector that runs during market hours and captures price data accurately.
2. A browser GUI at `http://localhost:8000` showing the live market.
3. History: how a stock has moved over time, charted.

Single user, own machine. No auth, no multi-tenancy, no cloud.

---

## 2. Architecture

```
                  +-- SockJS/STOMP subscriber (live, best effort)
   collector  ----+
                  +-- REST poller /api/tradeSummary (authoritative, always on)
                          |
                          v
                   normaliser + change-detect
                          |
                          v
                  SQLite (WAL)  data/cse.db
                          |
           +--------------+--------------+
           |                             |
     FastAPI JSON API            FastAPI WebSocket /ws/live
           |                             |
           +--------- static GUI --------+
```

One process. `python -m app` starts collector and server together.
`python -m app --collector-only` and `--server-only` for debugging.

**The REST poller is the source of truth.** The socket is a latency improvement layered on top.
If they disagree, the poller wins and the discrepancy is logged.

---

## 3. Database schema

SQLite, WAL, `data/cse.db`. Migrations in `app/migrations/NNN_*.sql`, applied on startup.

```sql
CREATE TABLE instruments (
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

CREATE TABLE ticks (
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
CREATE INDEX ix_ticks_sym_ts ON ticks(symbol, ts_exchange_ms);
CREATE UNIQUE INDEX ux_ticks_dedup ON ticks(symbol, ts_exchange_ms, price, share_volume, turnover);

CREATE TABLE daily_bars (
  symbol            TEXT NOT NULL REFERENCES instruments(symbol),
  trade_date        TEXT NOT NULL,         -- 'YYYY-MM-DD' Asia/Colombo
  open REAL, high REAL, low REAL, close REAL, prev_close REAL,
  turnover REAL, share_volume INTEGER, trade_volume INTEGER, crossing_volume INTEGER,
  is_final          INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (symbol, trade_date)
);

CREATE TABLE corporate_actions (
  id          INTEGER PRIMARY KEY,
  symbol      TEXT NOT NULL REFERENCES instruments(symbol),
  ex_date     TEXT NOT NULL,               -- 'YYYY-MM-DD'
  kind        TEXT NOT NULL,               -- 'split' | 'bonus' | 'rights' | 'dividend'
  ratio_from  REAL, ratio_to REAL,         -- split 1->10 is from=1 to=10
  cash_amount REAL,
  note        TEXT,
  source      TEXT                         -- 'manual' | 'detected'
);

CREATE TABLE market_snapshots (
  ts_ms        INTEGER PRIMARY KEY,
  status       TEXT,
  aspi         REAL,
  snp_sl20     REAL,
  turnover     REAL,
  share_volume INTEGER,
  trades       INTEGER
);

CREATE TABLE ingest_log (
  id         INTEGER PRIMARY KEY,
  ts_ms      INTEGER NOT NULL,
  source     TEXT NOT NULL,
  endpoint   TEXT,
  ok         INTEGER NOT NULL,
  rows       INTEGER,
  latency_ms INTEGER,
  error      TEXT
);
```

Seed `instruments.in_watchlist = 1` from `watchlist.csv` (the 50 companies already researched).

### Change detection
Before inserting a tick, compare against the last row for that symbol. Insert only if
`price`, `share_volume`, `turnover` or `trade_volume` differs. The unique index is a backstop,
not the primary mechanism — check in code so you can count suppressed duplicates.

### Split detection (assist, never automatic)
On each poll, if `price` moves more than 40% against `prev_close` while `quantity_issued` changes,
write a row to `corporate_actions` with `source='detected'` and `kind='split'`, and **surface it in
the UI for the user to confirm**. Never silently adjust stored prices.

---

## 4. Backend API

| Route | Returns |
|---|---|
| `GET /api/market` | latest market snapshot: status, ASPI, SL20, totals, last update |
| `GET /api/quotes?watchlist=true` | latest tick per symbol, joined to instruments |
| `GET /api/quote/{symbol}` | latest tick + reference data for one symbol |
| `GET /api/history/{symbol}?range=1M|3M|1Y|ALL&adjusted=true` | daily bars |
| `GET /api/intraday/{symbol}?date=YYYY-MM-DD` | ticks for one session |
| `GET /api/health` | collector status, last successful poll, socket state, rows today |
| `GET /api/corporate-actions` / `POST /api/corporate-actions` | list / add |
| `WS /ws/live` | broadcasts normalised tick batches as they land |

`adjusted=true` applies cumulative split factors from `corporate_actions` at read time.

---

## 5. The GUI

Served from `app/static/`. Three views, one page, tab-switched. Dark theme suits a trading screen.

### Header (always visible)
Market status pill (OPEN green / CLOSED grey), ASPI and S&P SL20 with change, total turnover,
"data as of <exchange time>", and a **connection dot**: green = socket live, amber = REST only,
red = stale. Also show "records since <date>" so the user knows how deep their own history is.

### View 1 — Live board (default)
Sortable table, watchlist by default with a toggle for all 284.
Columns: symbol, name, price, change, change %, on-market volume, turnover, trades,
**crossings (separate column)**, last traded time.
- Row background flashes green/red for ~600ms on change.
- Client-side filter box.
- Click a row to open View 2 for that symbol.

### View 2 — Symbol detail
- TradingView Lightweight Charts: price line/candles on top, volume histogram beneath.
- Range selector 1D / 1M / 3M / 1Y / ALL. 1D reads `/api/intraday`, the rest `/api/history`.
- **"Split adjusted" toggle**, default on; when corporate actions exist for the symbol, show
  markers on the chart at the ex-dates.
- Stat strip: open, high, low, prev close, day range %, 12M high/low, market cap, shares issued.

### View 3 — History and trends
- Multi-symbol comparison: pick up to 5, plot **normalised to 100** at the range start so
  different price levels are comparable.
- A table of daily bars for the selected symbol with CSV export.

### Honesty requirements in the UI
- Footer: "Public CSE website feed. May lag the matching engine. Not a licensed tick feed.
  Not investment advice."
- Where history is shallow because collection only started recently, say so on the chart rather
  than showing a stub line as if it were the full record.

---

## 6. Build phases — make each one runnable before moving on

**Phase 1 — REST collector + storage.** Migrations, instrument seed from `allSecurityCode`,
poller on `tradeSummary` with change detection, `ingest_log`. Prove it: run 10 minutes, show row
counts and that duplicates are suppressed. *No UI yet.*

**Phase 2 — API + live board.** FastAPI, `/api/quotes`, `/api/market`, static page with the
sortable table, polling the API every 5s. This is the first thing the user can look at.

**Phase 3 — Browser WebSocket.** `/ws/live` push, row flash, connection dot. Replace client polling.

**Phase 4 — History.** End-of-session rollup into `daily_bars`, `/api/history`, Lightweight Charts,
range selector, intraday view.

**Phase 5 — Upstream socket.** SockJS/STOMP subscriber per `docs/cse-api.md` section 3. Log raw
frames first, inspect, then parse. Must degrade cleanly to REST-only. **Verify during market hours.**

**Phase 6 — Corporate actions + comparison view.** Manual entry UI, split-adjusted charts,
normalised multi-symbol comparison, CSV export.

---

## 7. Acceptance criteria

- [ ] `pip install -r requirements.txt && python -m app` starts everything; GUI at `localhost:8000`.
- [ ] Collector survives a network outage: retries with backoff, logs to `ingest_log`, resumes.
- [ ] Malformed or changed upstream payload does not crash the process and does not write
      partial rows; it logs and keeps last good state.
- [ ] No duplicate ticks when the market is closed and the same snapshot is fetched repeatedly.
- [ ] `sharevolume` and `crossingVolume` are stored and displayed separately, never summed.
- [ ] Raw prices are never mutated; adjustment is applied at read time only.
- [ ] All stored timestamps are exchange-supplied epoch ms; display converts to Asia/Colombo.
- [ ] Live board updates without a page refresh while the market is open.
- [ ] A symbol chart renders both intraday and daily history, with a working range selector.
- [ ] `/api/health` reports last poll time, socket state and today's row count.
- [ ] Outside market hours the app runs quietly and the GUI says CLOSED with the last session's data.
- [ ] README explains how to run it, where the DB lives, and how to back it up.

---

## 8. Out of scope

No order placement, no broker integration, no auth, no alerts/notifications (a later phase),
no ML price prediction. Record accurately first.

---

## 9. Notes for whoever builds this

- `docs/cse-api.md` is the product of a full reverse-engineering session. Trust it, but verify the
  live-socket payload shapes yourself — that is the one part that could not be confirmed.
- There is **no historical price API**. Depth of history is whatever this collector accumulates,
  so get Phase 1 running and leave it running.
- `watchlist.csv` holds 50 companies already screened for liquidity and dividends; the analysis
  behind it lives in the parent folder's project docs.
