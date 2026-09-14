# CSE Live

Records Colombo Stock Exchange price data and serves a live web board. Three pieces:

```
watchlist.csv, docs/               shared reference data (unchanged by the cloud migration)
collector/     Python asyncio      polls the CSE every 30-60s, writes to Supabase Postgres
                                    deploy to an always-on host (Railway/Fly/Render) -- NOT Netlify
web/           Node/TS + static    Netlify Functions (/api/market, /api/quotes) + the live-board page
                                    deploy to Netlify, connected to this GitHub repo
Supabase       Postgres            the database both of the above talk to
```

Both the collector and the Netlify functions connect **directly** to Postgres with a
connection string kept in server-side environment variables. The browser never talks to
Supabase directly and never sees a Supabase key -- that's why Row Level Security is left
disabled on these tables (see `collector/migrations/001_init.sql`).

## 1. Supabase

1. Create a project at [supabase.com](https://supabase.com).
2. Open the SQL editor and run `collector/migrations/001_init.sql` once. This creates all the
   tables (`instruments`, `ticks`, `daily_bars`, `corporate_actions`, `market_snapshots`,
   `ingest_log`, `schema_migrations`).
3. Go to **Project Settings -> Database -> Connection string** and copy two different strings:
   - **Session pooler** (port 5432) -- for the collector, which holds one connection open for
     a long time.
   - **Transaction pooler** (port 6543) -- for the Netlify functions, which are many short-lived
     invocations.

You'll set both as `DATABASE_URL` in two different places below -- they are *not* the same value.

## 2. GitHub

Already done -- this repo is `Indika2016/APP`. Push your changes as normal; both Railway/Fly/Render
and Netlify will deploy from this remote.

## 3. Collector (always-on host)

The collector needs a host that stays running, not serverless -- it holds a persistent asyncio
loop and polls every 30-60s during market hours (CLAUDE.md rule 6). Using
[Railway](https://railway.app) as the concrete example (Fly.io/Render work the same way):

1. New Railway project -> **Deploy from GitHub repo** -> pick this repo.
2. Set the **Dockerfile path** to `collector/Dockerfile` and the **build context** to the repo
   root (Railway calls this the "root directory" -- leave it as `/`, the Dockerfile itself reaches
   up to `watchlist.csv`).
3. Add an environment variable: `DATABASE_URL` = the **session pooler** string from step 1.
4. Deploy. Check the logs for:
   ```
   seeded/updated 50 instruments from watchlist.csv
   seeded/updated ### instruments from allSecurityCode (skipped 0)
   [...] rest /api/tradeSummary OK rows=... latency=...ms
   ```
5. To check on it later without re-reading logs: `python -m app --report` (run it as a one-off
   command on the same host/image) prints instrument/tick counts and the `ingest_log` tail.

## 4. Netlify (frontend + API)

1. New Netlify site -> **Import from GitHub** -> pick this repo.
2. Base directory: `web`. Publish directory: `public` (Netlify will read `web/netlify.toml` for
   the rest -- functions directory, redirects). Build command: none needed (no bundler).
3. Site settings -> Environment variables: add `DATABASE_URL` = the **transaction pooler** string
   from step 1.
4. Deploy. Open the site URL -- you should see the live board. `GET /api/market` and
   `GET /api/quotes` should return JSON (check the browser devtools Network tab if the table
   stays empty).

## Local development

Collector (needs `DATABASE_URL` pointed at your Supabase project, e.g. via `.env` + your shell,
or `set`/`export` directly):

```
cd collector
pip install -r requirements.txt
python -m app --once      # one poll cycle, prints a summary
python -m app --report    # DB summary + ingest_log tail
python -m app             # runs forever, Ctrl+C to stop
```

Netlify site + functions (needs the Netlify CLI, and `DATABASE_URL` in `web/.env` --
git-ignored, copy from `web/.env.example`):

```
cd web
npm install
npx netlify dev
```

## What's implemented vs. what's next

Phases 1-2 from `SPEC.md` are done: the collector + storage, and the API + live board. Not yet
built (see `SPEC.md` §6 for the full phase list): the browser WebSocket push (Phase 3, currently
5s polling instead), end-of-session `daily_bars` rollup + symbol history charts (Phase 4), the
upstream CSE SockJS/STOMP live feed (Phase 5), and corporate actions + comparison view (Phase 6).

ASPI and S&P SL20 show as "—" in the header: there is no verified REST endpoint for the live
index *level* (see `collector/app/validation.py`'s `normalize_market_snapshot` docstring) --
only the Phase 5 websocket topics (`/topic/aspi`, `/topic/snp`) carry it.
