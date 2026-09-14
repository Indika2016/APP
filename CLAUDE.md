# CSE Live — project instructions

A local application that records Colombo Stock Exchange price data to a local database
and serves a web GUI showing a live feed and historical trends.

**Read `SPEC.md` before writing any code. Read `docs/cse-api.md` before touching the network layer —
the CSE API was already reverse-engineered and every endpoint, topic and payload shape is documented
there. Do not rediscover it, and do not scrape HTML.**

## Stack (already decided — do not substitute without asking)

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | asyncio, one runtime for collector + server |
| Web server | FastAPI + uvicorn | serves the JSON API, the browser WebSocket and the static GUI from one process |
| DB | SQLite, WAL mode | single user, 284 symbols, trivial volume; zero ops |
| Upstream live feed | `websockets` + hand-rolled SockJS/STOMP framing | see docs/cse-api.md §3 |
| Upstream polling | `httpx` (async) | safety net and backfill |
| Charts | TradingView Lightweight Charts (CDN) | purpose-built for price/volume, ~45 KB |
| Frontend | Plain HTML + vanilla JS | no build step; the user runs one command |

No React, no bundler, no Docker. `python -m app` must start everything.

## Non-negotiable correctness rules

These come from real errors already made against this data. Violating any of them produces
silently wrong analysis.

1. **`sharevolume` and `crossingVolume` are different things.** Crossings are negotiated block
   trades, not order-book flow. Store both in separate columns. Default every liquidity view to
   on-market volume. Never add them together.
2. **Never overwrite raw prices.** Splits are not flagged in the feed. Keep a
   `corporate_actions` table and apply adjustment at read time, behind a toggle.
3. **Use the exchange's `lastTradedTime`, never `datetime.now()`,** as the event time.
   Store your ingest time separately.
4. **Write a tick only when something changed** (price, volumes, or turnover) versus the last
   stored row for that symbol. Otherwise the table fills with identical rows.
5. **Assert the payload shape on every response.** This is an undocumented API. On an unexpected
   schema, log to `ingest_log` and keep the last good data — do not crash, do not write garbage.
6. **Gate collection on market status.** Mon–Fri ~09:30–14:30 Asia/Colombo. Outside that, poll
   slowly (once every 15 min) just to catch end-of-session corrections.

## Conventions

- All timestamps stored as UTC epoch milliseconds (integers), exactly as the API supplies them.
  Convert to Asia/Colombo only for display.
- Money in LKR. Never round stored values; round in the UI.
- Type hints throughout. `ruff` clean.
- Config in `config.toml`, not hardcoded constants scattered through modules.
- Log to stdout and to the `ingest_log` table.

## Definition of done

`SPEC.md` §7 lists the acceptance criteria. Work through the phases in §6 in order and make each
phase runnable before starting the next — the user wants to see something working early.
