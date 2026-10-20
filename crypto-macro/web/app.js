const TZ = "Europe/London";
const $ = (sel) => document.querySelector(sel);

const store = {
  get(key, fallback) {
    try { const v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v); }
    catch { return fallback; }
  },
  set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode */ } },
};

const state = {
  currencies: new Set(store.get("currencies", ["USD"])),
  minImpact: store.get("minImpact", "high"),
  week: 0,
  data: null,
};

const londonDate = (d) => new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(d);
const londonTime = (d) => new Intl.DateTimeFormat("en-GB", {
  timeZone: TZ, hour: "2-digit", minute: "2-digit" }).format(d);

async function api(path, options) {
  const resp = await fetch(path, { credentials: "same-origin", ...options });
  if (resp.status === 401) { showLogin(); throw new Error("login required"); }
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

// --- theme -------------------------------------------------------------

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]').content = theme === "light" ? "#f4f5f7" : "#0f1216";
}
applyTheme(store.get("theme", "dark"));
$("#theme-toggle").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  store.set("theme", next);
  applyTheme(next);
});

// --- login -------------------------------------------------------------

function showLogin() {
  const dlg = $("#login");
  if (!dlg.open) dlg.showModal();
}
$("#login-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const resp = await fetch("/api/login", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ passcode: $("#passcode").value }),
  });
  if (!resp.ok) { $("#login-error").textContent = "Wrong passcode"; return; }
  $("#login").close();
  await start();
});

// --- filters -----------------------------------------------------------

async function renderCurrencyChips() {
  const { currencies } = await api("/api/currencies");
  const box = $("#currency-chips");
  box.replaceChildren();
  for (const code of currencies) {
    const b = document.createElement("button");
    b.className = "chip";
    b.textContent = code;
    b.setAttribute("aria-pressed", state.currencies.has(code));
    b.addEventListener("click", () => {
      state.currencies.has(code) ? state.currencies.delete(code) : state.currencies.add(code);
      b.setAttribute("aria-pressed", state.currencies.has(code));
      store.set("currencies", [...state.currencies]);
      load();
    });
    box.append(b);
  }
}

for (const b of document.querySelectorAll("[data-impact]")) {
  b.addEventListener("click", () => {
    state.minImpact = b.dataset.impact;
    store.set("minImpact", state.minImpact);
    syncImpactChips();
    load();
  });
}
function syncImpactChips() {
  for (const b of document.querySelectorAll("[data-impact]")) {
    b.setAttribute("aria-pressed", b.dataset.impact === state.minImpact);
  }
}

$("#prev-week").addEventListener("click", () => { state.week -= 1; load(); });
$("#next-week").addEventListener("click", () => { state.week += 1; load(); });

// --- rendering ---------------------------------------------------------

function weekLabel(weekStart) {
  if (state.week === 0) return "This week";
  if (state.week === -1) return "Last week";
  if (state.week === 1) return "Next week";
  const d = new Date(`${weekStart}T12:00:00Z`);
  return "Week of " + d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function renderCalendar(data) {
  const main = $("#calendar");
  main.replaceChildren();
  $("#week-label").textContent = weekLabel(data.week_start);
  $("#next-week").disabled = state.week >= 1;

  if (!data.events.length) {
    const p = document.createElement("p");
    p.className = "empty";
    p.textContent = state.week > 0
      ? "Next week's events appear when the feed rolls over at the weekend."
      : "No events match these filters.";
    main.append(p);
    return;
  }

  const today = londonDate(new Date());
  const tpl = $("#row-tpl").content;
  let day = null, lastTime = null;
  for (const ev of data.events) {
    if (ev.london_date !== day) {
      day = ev.london_date;
      lastTime = null;
      const h = document.createElement("h3");
      h.className = "day" + (day === today ? " today" : "");
      h.textContent = ev.london_day + (day === today ? " · Today" : "");
      main.append(h);
    }
    const row = tpl.firstElementChild.cloneNode(true);
    const time = ev.all_day ? "All Day" : ev.london_time;
    // Like Forex Factory, only show a time when it changes.
    row.querySelector(".time").textContent = time === lastTime ? "" : time;
    lastTime = time;
    row.querySelector(".cur").textContent = ev.country;
    const imp = row.querySelector(".impact");
    imp.classList.add(ev.impact);
    imp.title = `${ev.impact} impact`;
    row.querySelector(".name").textContent = ev.title;
    row.querySelector(".actual").textContent = ev.actual ?? "—";
    row.querySelector(".forecast").textContent = ev.forecast ?? "—";
    row.querySelector(".previous").textContent = ev.previous ?? "—";
    if (ev.is_past) row.classList.add("past");
    if (ev.actual) row.classList.add("released");
    if (data.next_event && ev.id === data.next_event.id) row.classList.add("next-up");
    main.append(row);
  }
}

function renderFeedStatus(feed) {
  const parts = [];
  if (feed.last_success_at) {
    const d = new Date(feed.last_success_at);
    parts.push(`Calendar updated ${londonDate(d) === londonDate(new Date()) ? "" : d.toLocaleDateString("en-GB", { timeZone: TZ, day: "numeric", month: "short" }) + " "}${londonTime(d)}`);
  } else {
    parts.push("Calendar not fetched yet");
  }
  if (feed.last_error) parts.push(`last attempt failed: ${feed.last_error}`);
  $("#feed-status").textContent = parts.join(" · ");
}

// --- countdown ---------------------------------------------------------

function formatCountdown(ms) {
  if (ms <= 0) return "now";
  const s = Math.floor(ms / 1000);
  const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600),
        m = Math.floor(s % 3600 / 60), sec = s % 60;
  const pad = (n) => String(n).padStart(2, "0");
  if (d > 0) return `${d}d ${h}h ${pad(m)}m`;
  if (h > 0) return `${h}h ${pad(m)}m ${pad(sec)}s`;
  return `${m}m ${pad(sec)}s`;
}

function tickCountdown() {
  const next = state.data?.next_event;
  $("#next").hidden = !next;
  if (!next) return;
  const ms = new Date(next.starts_at) - Date.now();
  $("#next-countdown").textContent = formatCountdown(ms);
  if (ms < -60_000) load(); // event has passed; pick up the following one
}

function renderNext(next) {
  if (!next) return;
  $("#next-impact").className = `impact ${next.impact}`;
  $("#next-name").textContent = `${next.country} ${next.title}`;
  $("#next-when").textContent = `${next.london_day} · ${next.london_time} UK`;
}

// --- load loop ---------------------------------------------------------

let loading = null;
async function load() {
  const params = new URLSearchParams({
    currencies: state.currencies.size ? [...state.currencies].join(",") : "ALL",
    min_impact: state.minImpact,
    week: state.week,
  });
  const req = api(`/api/events?${params}`);
  loading = req;
  const data = await req;
  if (loading !== req) return; // a newer request superseded this one
  state.data = data;
  renderCalendar(data);
  renderNext(data.next_event);
  renderFeedStatus(data.feed);
  tickCountdown();
}

let started = false;
async function start() {
  syncImpactChips();
  await renderCurrencyChips();
  await load();
  if (started) return;
  started = true;
  setInterval(tickCountdown, 1000);
  setInterval(() => load().catch(() => {}), 5 * 60_000);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") load().catch(() => {});
  });
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch((err) => console.warn("SW registration failed", err));
}

(async () => {
  const auth = await (await fetch("/api/auth", { credentials: "same-origin" })).json();
  if (auth.required && !auth.authenticated) showLogin();
  else start().catch((err) => console.error(err));
})();
