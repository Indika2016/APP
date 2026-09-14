# CSE API reference (reverse-engineered)

Verified against www.cse.lk on 12 September 2026 (data from the Friday 11 Sep session).
**Undocumented internal API. No stability guarantee. Assert everything.**

Base: `https://www.cse.lk`

Throughout this document `\0` means a single NUL byte (`chr(0)`), the STOMP frame terminator.

---

## 1. Verified vs. inferred — read this first

| Item | Status |
|---|---|
| All REST endpoints in section 2 | **Verified** — called, real payloads received |
| SockJS handshake + STOMP CONNECT/CONNECTED | **Verified** — socket opened, `o` then `CONNECTED` received |
| Topic and `/app/` destination names | **Verified** — extracted from the site's own JS bundles |
| A SUBSCRIBE actually delivering live ticks | **NOT verified** — the market was closed at the time |

Build the REST poller first. It is fully proven. Treat the socket as an enhancement and confirm
it delivers during market hours before relying on it. If SUBSCRIBE yields nothing, the poller
alone is a complete solution.

---

## 2. REST endpoints

`POST` with `Content-Type: application/x-www-form-urlencoded` unless marked GET.

### `POST /api/tradeSummary` — body: *(empty)*
**The workhorse.** Entire market, 284 rows, one call. This is what you poll.

```json
{"reqTradeSummery":[{
  "id": 297,
  "name": "JOHN KEELLS HOLDINGS PLC",
  "symbol": "JKH.N0000",
  "price": 19.3,
  "previousClose": 19.4,
  "open": 19.4,
  "high": 19.5,
  "low": 19.3,
  "change": -0.1,
  "percentageChange": -0.5154639175257731,
  "turnover": 68602314.2,
  "sharevolume": 3542731,
  "tradevolume": 642,
  "crossingVolume": 10542731,
  "crossingTradeVol": 644,
  "marketCap": 342386109549,
  "lastTradedTime": 1789117154826,
  "status": 0,
  "logoUrl": "upload_logo/....jpeg",
  "issueDate": "23/OCT/1986"
}]}
```

Note `sharevolume` (3.5M) against `crossingVolume` (10.5M) on the same row — see CLAUDE.md rule 1.
Logos resolve at `https://cdn.cse.lk/{logoUrl}`.

### `POST /api/companyInfoSummery` — body: `symbol=JKH.N0000`
Per-symbol detail. Use for the instrument master and reference stats. Too slow to poll in a loop.

`reqSymbolInfo`: `symbol`, `name`, `isin`, `quantityIssued`, `parValue`, `lastTradedPrice`,
`previousClose`, `hiTrade`, `lowTrade`, `closingPrice`, `marketCap`, `marketCapPercentage`,
`change`, `changePercentage`, `foreignHoldings`, `foreignPercentage`, plus rolling windows
`wtd`/`mtd`/`ytd`/`p12` crossed with `HiPrice`, `LowPrice`, `ShareVolume`, `TradeVolume`, `Turnover`.

Warning: `p12Turnover` and `p12TradeVolume` return **0** — unpopulated. `p12ShareVolume`,
`p12HiPrice` and `p12LowPrice` are populated and reliable.

`reqSymbolBetaInfo`: `triASIBetaValue` (beta vs ASPI), `betaValueSPSL` (beta vs S&P SL20),
`triASIBetaPeriod`, `quarter`.

### `GET /api/allSecurityCode`
Instrument master list. Seed the `instruments` table from this.

### `GET /api/lastUpdateTime`
Returns `{"id":37070194,"lastUpdatedTime":1789119060332}`. A cheap freshness probe — poll this
to decide whether a full `tradeSummary` fetch is warranted.

### `GET /api/previousUpdateTime`
Returns `{"id":1,"previousDate":"2026-09-11 00:00:00"}`.

### `POST /api/marketSummery` — body: *(empty)*
Returns `{"id":37065784,"tradeVolume":1.1298180611E9,"shareVolume":57727315,"tradeDate":1789119060332,"trades":12454}`.
Here `tradeVolume` is **turnover in LKR** and `trades` is the trade count. The naming is
inconsistent with `tradeSummary` — do not assume field meanings across endpoints.

### `POST /api/financials` — body: `symbol=JKH.N0000`
`infoAnnualData[]`, `infoQuarterlyData[]`, `infoOtherData[]`; each entry
`{id, path, fileText, manualDate, uploadedDate}`. Download at `https://cdn.cse.lk/{path}`.
`manualDate` is the period end. Ignore `reqFinancial` — 159 identical rows of the string
"Financial Statements Summary".

### Others (verified 200)
`POST /api/alphabetical`, `POST /api/allSectors`, `POST /api/aspi/year`, `GET /api/returnAspiSnp`,
`POST /api/approvedAnnouncement`, `GET /api/news/web?top=false&type=BN&security={secId}`,
`GET /api/notifications`, `POST /api/security_trading_statistics`.

### Known dead (do not retry)
404: `historicalData`, `dailyMarketSummary`, `financialRatios`, `fundamentals`, `keyRatios`, `companyChart`.
405: `marketStatus`, `dailyMarketSummery`.
400 with every parameter shape tried: `chartData`.

**There is no per-symbol historical price endpoint.** Daily history must be accumulated by your
own collector from today forward. Say so plainly in the UI rather than implying deep history exists.

---

## 3. Live feed — SockJS + STOMP

### Handshake probe
```
GET /api/ws/info
-> {"entropy":1506636913,"origins":["*:*"],"cookie_needed":true,"websocket":true}
```
`cookie_needed: true` means keep a cookie jar (JSESSIONID) across the probe and the socket.

### Socket URL
```
wss://www.cse.lk/api/ws/{server}/{session}/websocket
```
`{server}` = 3 random digits, `{session}` = 8 random alphanumerics. Standard SockJS.

### Frame protocol
| Frame | Meaning |
|---|---|
| `o` | open — server sends immediately on connect |
| `h` | heartbeat — ignore |
| `a[...]` | JSON array of STOMP frame strings |
| `c[code,"reason"]` | close |

The client sends a **JSON array of strings**, each string a STOMP frame ending with `\0`.

### Verified exchange
```
send: ["CONNECT\naccept-version:1.1,1.0\nheart-beat:10000,10000\n\n\0"]
recv: o
recv: a["CONNECTED\nversion:1.1\nheart-beat:0,0\n\n\0"]
```
The server advertises `heart-beat:0,0` — it will not send STOMP heartbeats, though SockJS `h`
frames still arrive. Do not treat silence as a dead connection outside market hours.

### Subscribe
```
send: ["SUBSCRIBE\nid:sub-0\ndestination:/topic/today-sharePrice\n\n\0"]
```
Expect: `a["MESSAGE\ndestination:/topic/today-sharePrice\ncontent-type:application/json\nsubscription:sub-0\nmessage-id:...\n\n<JSON>\0"]`

### Topics
| Destination | Contents |
|---|---|
| `/topic/today-sharePrice` | **per-symbol live prices — the primary feed** |
| `/topic/most-active-trades` | most active |
| `/topic/daytrade` | day trade feed |
| `/topic/summary` | market totals |
| `/topic/aspi` | ASPI index |
| `/topic/snp` | S&P SL20 index |
| `/topic/status` | market open/closed |
| `/topic/top-gainers` | gainers |
| `/topic/top-looses` | losers — **the misspelling is theirs; use it verbatim** |

Each also exists as `/user/topic/{name}` for the per-session reply to a request.

### Forcing an immediate push
```
send: ["SEND\ndestination:/app/request-today-sharePrice\n\n\0"]
```
Available: `request-today-sharePrice`, `request-most-active-trades`, `request-daytrade`,
`request-summary`, `request-aspi`, `request-snp`, `request-status`, `request-top-gainers`,
`request-top-looses`.

**Payload shapes on these topics were not observed.** Log the first messages raw to
`data/raw_frames.log`, inspect them, then write the parser. Expect shapes close to the REST ones.

---

## 4. Timing

- Market: Mon-Fri, roughly 09:30-14:30 **Asia/Colombo (UTC+5:30)**.
- All timestamps are epoch **milliseconds**, UTC.
- Worked example: read on Sat 12 Sep, `lastUpdateTime` = 1789119060332 = Fri 11 Sep 15:01 Colombo;
  JKH `lastTradedTime` = 1789117154826 = Fri 11 Sep 14:29:14 Colombo, one minute before close.

## 5. Etiquette and legal

- Check the CSE terms of use for automated collection before running continuously.
- `tradeSummary` returns the whole market in one request — never loop per-symbol for live data.
  Poll 30-60s during market hours, 15 min outside.
- Use `lastUpdateTime` (tiny) to decide whether the big call is needed.
- Set a descriptive User-Agent. Back off exponentially on 429/5xx.
- This is the public website feed and may lag the matching engine. It is not a licensed tick
  feed. State that in the UI footer.
