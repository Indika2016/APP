# CSE Live — project instructions

A cloud-deployed application that records Colombo Stock Exchange price data to Supabase Postgres
and serves a web GUI (Netlify) showing a live feed and historical trends.

**Read `SPEC.md` before writing any code** — it's still the functional spec (schema, GUI, phases,
acceptance criteria); only the deployment target described below has changed, not the product.
**Read `docs/cse-api.md` before touching the network layer** — the CSE API was already
reverse-engineered and every endpoint, topic and payload shape is documented there. Do not
rediscover it, and do not scrape HTML. **Read `README.md` for the deployment/runbook.**

## Stack (already decided — do not substitute without asking)

Superseded 2026-09-14: this was originally a single local Python process (FastAPI + SQLite,
`python -m app` starting everything). The user asked to move it to the cloud (GitHub + Netlify +
Supabase); that local version is retired but stays in git history if it's ever needed again.

| Layer | Choice | Why |
|---|---|---|
| Database | Supabase (Postgres) | managed, free tier, reachable from both the collector and Netlify |
| Collector | Python 3.11+ (`collector/`), `psycopg` (async) | reuses the proven asyncio poller; deployed to a small always-on host (Railway/Fly/Render) — Netlify Functions can't run a persistent 30-60s polling loop |
| API | Node/TypeScript Netlify Functions (`web/netlify/functions/`) | Netlify's first-class, best-supported function runtime; talks to Supabase over its transaction pooler |
| Frontend | Plain HTML + vanilla JS (`web/public/`), 5s polling | unchanged from the original design — no build step, same `/api/market` + `/api/quotes` contract, now routed to Netlify Functions via `netlify.toml` redirects |
| Charts | TradingView Lightweight Charts (CDN) | purpose-built for price/volume, ~45 KB (not wired up yet — Phase 4) |
| Source control | GitHub (`Indika2016/APP`) | Netlify and the collector host both deploy from it |

No React, no bundler for the frontend itself. Two deployables now, not one process: the collector
(always-on host) and the Netlify site+functions. See `README.md` for exact setup steps.

RLS is intentionally left disabled on the Supabase tables: nothing is ever queried through
Supabase's public PostgREST/anon-key API. Only the Python collector and the Netlify functions
connect directly to Postgres, both using a connection string kept in server-side env vars, never
shipped to the browser. Do not add a Supabase anon key to the frontend without re-adding RLS
policies first.

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

- All timestamps stored as UTC epoch milliseconds/BIGINT, exactly as the API supplies them.
  Convert to Asia/Colombo only for display. (Postgres INTEGER is 32-bit — epoch-ms columns must
  be BIGINT, unlike SQLite where INTEGER auto-widened; see `collector/migrations/001_init.sql`.)
- Money in LKR. Never round stored values; round in the UI.
- Type hints throughout the Python collector. `ruff` clean.
- Non-secret config in `collector/config.toml`; secrets (`DATABASE_URL`) via environment
  variables only — see `collector/.env.example` and `web/.env.example`. Never commit a real
  connection string.
- Log to stdout and to the `ingest_log` table.
- The "is market open" rule (Mon-Fri 09:30-14:30 Asia/Colombo) is duplicated in two runtimes now
  (`collector/app/collector.py` and `web/netlify/functions/market.ts`) since the collector is
  Python and the API is Node. Keep both in sync if trading hours ever change.

## Definition of done

`SPEC.md` §7 lists the acceptance criteria (written for the original local version — read
"the app" there as "the collector + Netlify site" now). Work through the phases in `SPEC.md` §6
in order and make each phase runnable before starting the next. Phases 1-2 are done (collector +
storage, API + live board); this migration ported them to the cloud stack without changing scope.
