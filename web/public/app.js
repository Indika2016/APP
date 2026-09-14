const POLL_MS = 5000;

const state = {
  lastQuotes: new Map(), // symbol -> previously rendered row, for flash detection
  lastFetchedRows: [],
  sortKey: "symbol",
  sortDir: 1,
  watchlistOnly: true,
  filter: "",
};

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[c]);
}

function fmtNumber(n, opts = {}) {
  if (n === null || n === undefined) return "—";
  return Number(n).toLocaleString("en-US", opts);
}

function fmtMoney(n) {
  if (n === null || n === undefined) return "—";
  return Number(n).toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function fmtPct(n) {
  if (n === null || n === undefined) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function fmtTimeColombo(ms) {
  if (!ms) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Colombo",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(ms));
}

function fmtDateColombo(ms) {
  if (!ms) return "—";
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Colombo" }).format(new Date(ms));
}

function setConn(status, title) {
  const dot = document.getElementById("conn-dot");
  dot.className = "dot dot-" + status;
  if (title) dot.title = title;
}

async function fetchJSON(url) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`${url} -> ${resp.status}`);
  return resp.json();
}

async function refreshMarket() {
  try {
    const m = await fetchJSON("/api/market");
    const pill = document.getElementById("market-pill");
    const statusText = m.status || "UNKNOWN";
    pill.textContent = statusText;
    pill.className = "pill pill-" + statusText.toLowerCase();
    document.getElementById("aspi-value").textContent = fmtNumber(m.aspi, { maximumFractionDigits: 2 });
    document.getElementById("snp-value").textContent = fmtNumber(m.snp_sl20, { maximumFractionDigits: 2 });
    document.getElementById("turnover-value").textContent = "LKR " + fmtMoney(m.turnover);
    document.getElementById("as-of").textContent = "data as of " + fmtTimeColombo(m.as_of_exchange_ms);
    if (m.records_since_ms) {
      document.getElementById("records-since").textContent =
        " Records since " + fmtDateColombo(m.records_since_ms) + ".";
    }
  } catch (e) {
    console.error(e);
  }
}

function applyFilterAndSort(rows) {
  let out = rows;
  const f = state.filter.trim().toLowerCase();
  if (f) {
    out = out.filter(
      (r) =>
        r.symbol.toLowerCase().includes(f) ||
        (r.name || "").toLowerCase().includes(f) ||
        (r.short_code || "").toLowerCase().includes(f)
    );
  }
  const key = state.sortKey;
  const dir = state.sortDir;
  out = [...out].sort((a, b) => {
    let av = a[key];
    let bv = b[key];
    if (typeof av === "string" || typeof bv === "string") {
      return (av || "").toString().localeCompare((bv || "").toString()) * dir;
    }
    av = av ?? -Infinity;
    bv = bv ?? -Infinity;
    return (av - bv) * dir;
  });
  return out;
}

function renderRows(rows) {
  const tbody = document.getElementById("quotes-body");
  tbody.innerHTML = "";
  const nextQuotes = new Map();

  for (const r of rows) {
    const prev = state.lastQuotes.get(r.symbol);
    const changeClass = r.change > 0 ? "up" : r.change < 0 ? "down" : "";
    const pctClass = r.pct_change > 0 ? "up" : r.pct_change < 0 ? "down" : "";

    const tr = document.createElement("tr");
    tr.dataset.symbol = r.symbol;
    tr.innerHTML = `
      <td title="${escapeHtml(r.symbol)}">${escapeHtml(r.short_code)}</td>
      <td>${escapeHtml(r.name)}</td>
      <td class="num">${fmtNumber(r.price, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
      <td class="num ${changeClass}">${fmtNumber(r.change, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
      <td class="num ${pctClass}">${fmtPct(r.pct_change)}</td>
      <td class="num">${fmtNumber(r.share_volume)}</td>
      <td class="num">${fmtMoney(r.turnover)}</td>
      <td class="num">${fmtNumber(r.trade_volume)}</td>
      <td class="num">${fmtNumber(r.crossing_volume)}</td>
      <td class="num">${fmtTimeColombo(r.ts_exchange_ms)}</td>
    `;

    if (prev && prev.price !== r.price) {
      tr.classList.add(r.price > prev.price ? "flash-up" : "flash-down");
    }

    tbody.appendChild(tr);
    nextQuotes.set(r.symbol, r);
  }

  state.lastQuotes = nextQuotes;
  document.getElementById("row-count").textContent = `${rows.length} shown`;
}

function rerenderFromCache() {
  renderRows(applyFilterAndSort(state.lastFetchedRows));
}

async function refreshQuotes() {
  try {
    const url = `/api/quotes?watchlist=${state.watchlistOnly}`;
    const rows = await fetchJSON(url);
    state.lastFetchedRows = rows;
    renderRows(applyFilterAndSort(rows));
    setConn("rest", "REST polling every 5s (no live socket yet)");
  } catch (e) {
    console.error(e);
    setConn("stale", "last refresh failed: " + e.message);
  }
}

document.getElementById("watchlist-toggle").addEventListener("change", (e) => {
  state.watchlistOnly = e.target.checked;
  refreshQuotes();
});

document.getElementById("filter-box").addEventListener("input", (e) => {
  state.filter = e.target.value;
  rerenderFromCache();
});

document.querySelectorAll("#quotes-table thead th").forEach((th) => {
  th.addEventListener("click", () => {
    const key = th.dataset.key;
    if (state.sortKey === key) {
      state.sortDir *= -1;
    } else {
      state.sortKey = key;
      state.sortDir = 1;
    }
    document.querySelectorAll("#quotes-table thead th").forEach((h) => h.classList.remove("sorted"));
    th.classList.add("sorted");
    rerenderFromCache();
  });
});

async function tick() {
  await Promise.all([refreshMarket(), refreshQuotes()]);
}

tick();
setInterval(tick, POLL_MS);
