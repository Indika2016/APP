# START HERE

> **Update (2026-09-14):** this file describes how Phase 1 was originally built as a local
> single-process app. That local version is retired -- the project now runs on Supabase +
> Netlify + a separately-hosted collector. For current setup/deployment steps, see `README.md`.
> The phase-by-phase build plan below (and `SPEC.md` §6) is still accurate; only *where it runs*
> changed. Kept as-is for history.

Four files are already in this folder. Claude Code reads `CLAUDE.md` automatically.

| File | What it is |
|---|---|
| `CLAUDE.md` | Project instructions: stack decisions and six correctness rules that must not be broken |
| `SPEC.md` | The full build spec: architecture, DB schema, API routes, GUI, phases, acceptance criteria |
| `docs/cse-api.md` | The CSE API, already reverse-engineered. Endpoints, WebSocket topics, payload shapes, dead ends |
| `watchlist.csv` | The 50 screened companies, with per-symbol warnings |

## Paste this into Claude Code

> Read CLAUDE.md, SPEC.md and docs/cse-api.md in full before writing any code.
>
> Build Phase 1 only: the REST collector and SQLite storage. Nothing else, no UI yet.
>
> That means: the migrations and schema from SPEC.md section 3, seeding `instruments` from
> `/api/allSecurityCode` and `watchlist.csv`, and a poller on `POST /api/tradeSummary` with
> change detection so repeated identical snapshots do not create duplicate rows.
>
> When it runs, show me: rows inserted, duplicates suppressed, and the contents of `ingest_log`.
> Do not start Phase 2 until I have seen that working.

Then work through Phases 2 to 6 in `SPEC.md` section 6, one at a time.

## Two things to tell it if it gets them wrong

**There is no historical price API on the CSE.** Depth of history is only what this collector
accumulates from the day you start it. If it claims to backfill years of data, it is inventing
an endpoint that does not exist. Get Phase 1 running early and leave it running.

**The live WebSocket was only half-verified.** The handshake was confirmed; an actual subscription
delivering ticks was not, because the market was closed. The REST poller is proven and is the
source of truth. If the socket turns out to deliver nothing, the app still works.

## Best time to test

Market hours are Monday to Friday, roughly 09:30 to 14:30 Colombo time. Outside those hours the
feed is static and you will only see the previous session's closing data — which is correct
behaviour, not a bug.

## A note on running it continuously

`docs/cse-api.md` section 5 covers etiquette: one call returns the whole market, so a 30 to 60
second poll is gentle. Worth checking the CSE's terms of use on automated collection before
leaving it running permanently.
