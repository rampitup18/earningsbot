const NTFY_SERVER = "https://ntfy.sh";
const TOPIC_KEY = "earningsbot_ntfy_topic";

const ACTION_CONFIG = {
  buy_call:    { label: "CALL",        css: "bullish" },
  call_spread: { label: "CALL SPREAD", css: "bullish" },
  go_long:     { label: "LONG",        css: "bullish" },
  buy_put:     { label: "PUT",         css: "bearish" },
  put_spread:  { label: "PUT SPREAD",  css: "bearish" },
  go_short:    { label: "SHORT",       css: "bearish" },
  skip:        { label: "SKIP",        css: "neutral" },
};

const ARROWS = { bullish: "↑", bearish: "↓", neutral: "→" };

function getTopic() { return localStorage.getItem(TOPIC_KEY) || ""; }
function setTopic(t) { localStorage.setItem(TOPIC_KEY, t); }

// Parse ntfy title: "[^] AAPL  BUY CALL"
function parseTitle(title) {
  const m = title.match(/^\[([v^-])\]\s+(\w+)\s+(.+)$/);
  if (!m) return null;
  const dir = m[1] === "^" ? "bullish" : m[1] === "v" ? "bearish" : "neutral";
  const actionMap = {
    "BUY CALL": "buy_call", "BUY PUT": "buy_put",
    "CALL DEBIT SPREAD": "call_spread", "PUT DEBIT SPREAD": "put_spread",
    "BUY SHARES (LONG)": "go_long", "SELL SHORT": "go_short",
  };
  return { ticker: m[2], direction: dir, action: actionMap[m[3].trim()] || "skip" };
}

// Parse ntfy message body into trade fields
function parseBody(body) {
  const lines = body.split("\n");
  const trade = { earningsDate: "", maxRisk: 0, contracts: 0, costPerContract: 0, strike: 0, expiry: "", thesis: "", keyFactors: [] };

  for (const line of lines) {
    const t = line.trim();
    if (t.startsWith("Earnings:")) trade.earningsDate = t.replace("Earnings:", "").trim();
    else if (/^Strike \$/.test(t)) {
      const p = t.match(/Strike \$(\d+)\s+Exp\s+(.+)/);
      if (p) { trade.strike = +p[1]; trade.expiry = p[2].trim(); }
    }
    else if (/^\d+ shares @/.test(t)) {
      const p = t.match(/^(\d+) shares @ \$(.+)/);
      if (p) { trade.contracts = +p[1]; trade.costPerContract = +p[2]; }
    }
    else if (/^\$[\d.]+\/contract/.test(t)) {
      const p = t.match(/^\$([\d.]+)\/contract x(\d+)/);
      if (p) { trade.costPerContract = +p[1]; trade.contracts = +p[2]; }
    }
    else if (t.startsWith("Max risk")) {
      const m = t.match(/\$([\d.]+)/);
      if (m) trade.maxRisk = +m[1];
    }
    else if (t.startsWith("•")) trade.keyFactors.push(t.replace(/^•\s*/, ""));
    else if (!trade.thesis && t.length > 10 && !t.startsWith("Implied") && !t.startsWith("IV/HV")) trade.thesis = t;
  }
  return trade;
}

async function fetchTrades(topic) {
  const res = await fetch(`${NTFY_SERVER}/${topic}/json?poll=1&since=7d`);
  if (!res.ok) throw new Error(`ntfy error: ${res.status}`);
  const text = await res.text();
  const msgs = text.trim().split("\n").filter(Boolean).map((l) => JSON.parse(l));

  const trades = [];
  for (const msg of msgs) {
    if (msg.event !== "message" || !msg.title || !msg.message) continue;
    const header = parseTitle(msg.title);
    if (!header || header.action === "skip") continue;
    const body = parseBody(msg.message);
    trades.push({ id: msg.id, ...header, ...body, receivedAt: new Date(msg.time * 1000) });
  }
  return trades.sort((a, b) => b.receivedAt - a.receivedAt);
}

function groupByDate(trades) {
  const groups = new Map();
  for (const t of trades) {
    const key = t.receivedAt.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(t);
  }
  return [...groups.entries()].map(([date, trades]) => ({ date, trades }));
}

function renderCard(trade) {
  const cfg = ACTION_CONFIG[trade.action] || ACTION_CONFIG.skip;
  const arrow = ARROWS[trade.direction] || "→";
  const isEquity = trade.action === "go_long" || trade.action === "go_short";
  const time = trade.receivedAt.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });

  const factorsHtml = trade.keyFactors.length
    ? `<div class="factors">
        <div class="factors-title">Key Factors</div>
        ${trade.keyFactors.map((f) => `<div class="factor"><span class="factor-bullet">&bull;</span><span class="factor-text">${esc(f)}</span></div>`).join("")}
       </div>`
    : "";

  const statsHtml = isEquity
    ? `<div class="stat"><div class="stat-label">Risk</div><div class="stat-value">$${trade.maxRisk.toLocaleString()}</div></div>
       <div class="stat"><div class="stat-label">Shares</div><div class="stat-value">${trade.contracts}</div></div>
       <div class="stat"><div class="stat-label">Earnings</div><div class="stat-value">${esc(trade.earningsDate)}</div></div>`
    : `<div class="stat"><div class="stat-label">Risk</div><div class="stat-value">$${trade.maxRisk.toLocaleString()}</div></div>
       <div class="stat"><div class="stat-label">Strike</div><div class="stat-value">$${trade.strike}</div></div>
       <div class="stat"><div class="stat-label">Contracts</div><div class="stat-value">${trade.contracts}</div></div>
       <div class="stat"><div class="stat-label">Earnings</div><div class="stat-value">${esc(trade.earningsDate)}</div></div>`;

  return `<div class="card" onclick="this.classList.toggle('expanded')">
    <div class="card-header">
      <div class="ticker-row">
        <span class="ticker">${esc(trade.ticker)}</span>
        <span class="arrow" style="color:${cfg.css === 'bullish' ? 'var(--green)' : cfg.css === 'bearish' ? 'var(--red)' : '#757575'}">${arrow}</span>
      </div>
      <span class="badge badge-${cfg.css}">${cfg.label}</span>
    </div>
    <div class="thesis">${esc(trade.thesis)}</div>
    <div class="stats-row">${statsHtml}</div>
    ${factorsHtml}
    <div class="card-footer">
      <span class="time">${time}</span>
      <span class="expand-hint">tap for details</span>
    </div>
  </div>`;
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

// Main render
const $content = () => document.getElementById("content");
const $subtitle = () => document.getElementById("subtitle");

async function loadTrades() {
  const topic = getTopic();
  if (!topic) {
    $content().innerHTML = `<div class="center-state"><h2>No topic configured</h2><p>Tap the gear icon to enter your ntfy topic</p></div>`;
    return;
  }

  $content().innerHTML = `<div class="center-state"><div class="spinner"></div></div>`;

  try {
    const trades = await fetchTrades(topic);

    if (trades.length === 0) {
      $content().innerHTML = `<div class="center-state"><h2>No trades yet</h2><p>Pull down to refresh, or wait for the next morning scan</p></div>`;
      $subtitle().textContent = "Pre-earnings trade scanner";
      return;
    }

    const bull = trades.filter((t) => t.direction === "bullish").length;
    const bear = trades.filter((t) => t.direction === "bearish").length;
    $subtitle().textContent = `${trades.length} trades  ·  ${bull} bullish  ·  ${bear} bearish`;

    const groups = groupByDate(trades);
    let html = "";
    for (const g of groups) {
      html += `<div class="date-header">${esc(g.date)}</div>`;
      for (const t of g.trades) html += renderCard(t);
    }
    html += `<div class="pull-hint">Showing last 7 days</div>`;
    $content().innerHTML = html;
  } catch (e) {
    $content().innerHTML = `<div class="center-state"><h2>Error</h2><p>${esc(e.message)}</p><button class="retry-btn" onclick="loadTrades()">Retry</button></div>`;
  }
}

// Settings modal
function openSettings() {
  document.getElementById("settings-input").value = getTopic();
  document.getElementById("settings-modal").classList.remove("hidden");
}
function closeSettings() {
  document.getElementById("settings-modal").classList.add("hidden");
}
function saveSettings() {
  const val = document.getElementById("settings-input").value.trim();
  setTopic(val);
  closeSettings();
  loadTrades();
}

// Pull to refresh
let touchStart = 0;
document.addEventListener("touchstart", (e) => { touchStart = e.touches[0].clientY; });
document.addEventListener("touchend", (e) => {
  if (window.scrollY === 0 && e.changedTouches[0].clientY - touchStart > 80) loadTrades();
});

// Init
if ("serviceWorker" in navigator) navigator.serviceWorker.register("./sw.js");
window.addEventListener("load", () => {
  if (!getTopic()) openSettings();
  else loadTrades();
});
