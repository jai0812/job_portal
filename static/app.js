/* ===== JAI SHARMA watermark =====
    ,,,,,,,    ,,,    ,,,,,,         ,,,,,   ,,   ,,    ,,,    ,,,,,,   ,,   ,,    ,,,
        ,,    ,, ,,     ,,          ,,   ,,  ,,   ,,   ,, ,,   ,,   ,,  ,,, ,,,   ,, ,,
        ,,   ,,   ,,    ,,          ,,       ,,   ,,  ,,   ,,  ,,   ,,  ,,,,,,,  ,,   ,,
        ,,   ,,   ,,    ,,           ,,,,,   ,,,,,,,  ,,   ,,  ,,,,,,   ,, , ,,  ,,   ,,
        ,,   ,,,,,,,    ,,               ,,  ,,   ,,  ,,,,,,,  ,, ,,    ,,   ,,  ,,,,,,,
    ,,  ,,   ,,   ,,    ,,          ,,   ,,  ,,   ,,  ,,   ,,  ,,  ,,   ,,   ,,  ,,   ,,
     ,,,,    ,,   ,,  ,,,,,,         ,,,,,   ,,   ,,  ,,   ,,  ,,   ,,  ,,   ,,  ,,   ,,

                                                     J       A
                        IS                           HA     RM
                      AJAISH                         ARMAJAISHAR
                    MAJAISHARM                      AJAI00SHARMAJAI
                  SHARMAJAISHARM                   AJAISHARMAJAISHARMAJ
                AISHARMAJAISHARMAJ                AISHARMAJAISHARMAJAISHAR
              MAJAISHARMAJAISHARMAJA             ISHARMAJAISHARMA  JA  IS H
            ARMAJAISHARMAJAISHARMAJAIS          HARMAJAISHAR   MA  JA
          ISHARMAJAISHARMAJAISHARMAJAISH       ARMAJAISHAR
              MAJAISHARMAJAISHARMAJAISHARM    AJAISHARMA
     J           AISHARMAJAISHARMAJAISHARMAJAISHARM
     AJ        AISHARMAJAISHARMAJAISHARMAJAISHARMA
     JAI     SHARMAJAISHARMAJAISHARMAJAISHARMAJA
      ISHA  RMAJAISHARMAJAISHARMAJAISHARMAJAISH
       ARMAJAISHARMAJAISHARMAJAISHARMAJAISHAR
         MAJAISHARMAJAISHARMAJAISHARMAJAISH
            ARMAJAISHAR  MAJAISHA   RMAJAISH
                         ARMAJ      AISHA
                         RMAJAI     SHARMA
                        JAI SHAR   MAJ AISH

                ~ built by JAI SHARMA ~
   ============================== */
// Job Portal front-end. Plain JS, no build step.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts = {}) {
  const init = { ...opts };
  init.headers = { "X-Portal": "1" };  // marks requests as coming from the portal's own page
  if (opts.body && !(opts.body instanceof FormData)) {
    init.body = JSON.stringify(opts.body);
    init.headers["Content-Type"] = "application/json";
  }
  const r = await fetch(path, init);
  if (r.status === 401) { location.href = "/login"; throw new Error("Please sign in"); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || r.statusText);
  return data;
}

function toast(msg, ms = 2600) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.remove("show"), ms);
}

let STATUS = {};

// ------------------------------------------------------------------ tabs
const REGION_TABS = { jobs: "us", india: "india", world: "other" };
function showTab(name) {
  $$("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  const section = name in REGION_TABS ? "jobs" : name;
  $$(".tab").forEach((t) => t.classList.toggle("active", t.id === `tab-${section}`));
  if (name in REGION_TABS && F.region !== REGION_TABS[name]) {
    F.region = REGION_TABS[name];
    F.place = "";
    SHOWN = 200;
    if (JOBS.length) renderJobs();
  }
  if (name === "analytics") loadAnalytics();
  location.hash = name;
}
$$("#tabs button").forEach((b) => (b.onclick = () => showTab(b.dataset.tab)));
window.addEventListener("hashchange", () => { const t = location.hash.slice(1); if ($(`#tab-${t}`) || t in REGION_TABS) showTab(t); });

// ------------------------------------------------------------------ status
async function loadStatus() {
  STATUS = await api("/api/status");
  $("#llm-pills").innerHTML = STATUS.llms
    .filter((l) => l.configured || ["chatgpt", "claude"].includes(l.id))
    .map((l) => `<span class="pill ${l.configured ? "on" : ""}" title="${esc(l.model)}">${l.configured ? "●" : "○"} ${esc(l.label)}</span>`)
    .join("") + (STATUS.auth ? `<button id="signout" title="Sign out of the portal">Sign out</button>` : "");
  if (STATUS.auth) $("#signout").onclick = async () => { await api("/api/logout", { method: "POST" }); location.href = "/login"; };
  renderSettings();
  renderAskProviders();
}

// ------------------------------------------------------------------ JOBS
const CATS = [["", "All"], ["swe", "Software Engineering"], ["finance", "Finance & Banks"], ["data", "Data Science & ML"], ["other", "Other"]];
const LEVELS = [["", "All levels"], ["internship", "Internship"], ["early_career", "Early career / New grad"], ["experienced", "Experienced"], ["unspecified", "Unspecified"]];
const AGES = [["", "Any time"], [6, "≤ 6h"], [24, "≤ 24h"], [48, "≤ 2d"], [72, "≤ 3d"], [168, "≤ 7d"], [336, "≤ 14d"], [720, "≤ 30d"]];
const H1B_LABEL = { yes: "Sponsors", likely: "Likely", no: "No sponsorship", citizen: "US citizens", unknown: "Unknown" };
const LEVEL_LABEL = { internship: "Intern", early_career: "Early career", experienced: "Experienced", unspecified: "—" };
const CAT_LABEL = { swe: "SWE", finance: "Finance", data: "DS/ML", other: "Other" };

const F = { region: "us", place: "", cat: "", level: "", age: "", stype: "", fin: "", q: "", h1b: "", cap: false, top: false, source: "", status: "active" };
const REGION_INFO = {
  us: ["🇺🇸 United States", "US jobs from GitHub lists, LinkedIn and employers' own career sites (finance firms, FAANG / MAANG, big tech and top tech companies)."],
  india: ["🇮🇳 India", "Jobs in India from Indian tech & fintech companies, big tech India teams (Amazon, NVIDIA, Salesforce, Adobe, Intel, Target), global banks & finance firms' India offices, and LinkedIn India searches."],
  other: ["🌍 Other countries", "Jobs outside the US and India, mostly from global banks, finance firms and tech companies' own career sites."],
};
// India: group cities into metro areas; other countries: by country.
const INDIA_CITIES = [["Bengaluru", /Bengaluru|Bangalore|Karnataka|KA,/i], ["Hyderabad", /Hyderabad|Telang/i], ["Pune", /Pune/i],
  ["Mumbai", /Mumbai|Navi Mumbai|Thane/i], ["Delhi NCR", /Delhi|Gurgaon|Gurugram|Noida|Haryana|Uttar Pradesh/i],
  ["Chennai", /Chennai|Tamil Nadu/i], ["Kolkata", /Kolkata/i], ["Ahmedabad", /Ahmedabad|Gujarat/i]];
function placesOf(j) {
  if (F.region === "india") return INDIA_CITIES.filter(([, rx]) => rx.test(j.location)).map(([n]) => n);
  if (F.region === "other") return (j.countries || []).filter((c) => c !== "United States" && c !== "India");
  return [];
}
const STYPES = [["", "All sources"], ["github", "GitHub lists"], ["company", "Company career sites"], ["apify", "Apify · LinkedIn"], ["manual", "Added by you"]];
let FIN_SEGMENTS = [];  // filled from /api/finance

// H-1B: the posting's own words win; otherwise real USCIS FY2023 approval counts; otherwise our hand list.
function h1bCell(j) {
  if (j.h1b === "no" || j.h1b === "citizen") return `<span class="tag ${j.h1b}">${H1B_LABEL[j.h1b]}</span><span class="age-date">per the posting</span>`;
  if (j.h1b === "yes") return `<span class="tag yes">Sponsors</span><span class="age-date">per the posting${j.h1b_fy23 ? ` · ${j.h1b_fy23.toLocaleString()} in FY23` : ""}</span>`;
  if (j.h1b_fy23) return `<span class="tag yes" title="USCIS H-1B Employer Data Hub, FY2023 initial + continuing approvals">✓ Has sponsored</span><span class="age-date">${j.h1b_fy23.toLocaleString()} approvals FY23</span>`;
  if (j.h1b === "likely") return `<span class="tag likely">Likely</span><span class="age-date">known sponsor list</span>`;
  return `<span class="tag unknown">Unknown</span><span class="age-date">no FY23 record</span>`;
}
const hasSponsored = (j) => !["no", "citizen"].includes(j.h1b) && (j.h1b === "yes" || j.h1b === "likely" || j.h1b_fy23 > 0);
function finCell(j) {
  if (!j.fin) return `<td class="fin muted">—</td>`;
  return `<td class="fin"><span class="seg seg-${j.fin.segment}">${esc(j.fin.segment_label)}</span><span class="sname">${esc(j.fin.name)}</span></td>`;
}
let JOBS = [], NOW = 0, SORT = { key: "posted", asc: false }, SHOWN = 200;
const STATUSES = ["new", "saved", "applied", "interviewing", "offer", "rejected", "hidden"];
const APPLIED = new Set(["applied", "interviewing", "offer", "rejected"]);
const statusSelect = (j) => `<select data-act="status" title="Stage">${STATUSES.map((s) => `<option ${s === j.status ? "selected" : ""}>${s}</option>`).join("")}</select>`;
const appliedBox = (j) => `<td class="cb-col"><input type="checkbox" class="applied-cb" data-act="applied" ${APPLIED.has(j.status) ? "checked" : ""}
  title="${APPLIED.has(j.status) ? `Applied ${j.applied_at ? new Date(j.applied_at * 1000).toLocaleDateString() : ""}` : "Tick when you've applied"}" aria-label="Applied"></td>`;
const rowClass = (j) => (APPLIED.has(j.status) ? "is-applied" : j.status);

function ageOf(j) {
  return NOW - (j.posted_at || j.first_seen);
}
function ageText(sec) {
  const m = Math.max(0, Math.floor(sec / 60));
  if (m < 1) return "now";
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  const d = Math.floor(h / 24);
  return d < 60 ? `${d}d` : `${Math.floor(d / 30)}mo`;
}
const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
const fmtDate = (ts, withTime) => new Date(ts * 1000).toLocaleString(undefined, withTime
  ? { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" } : { month: "short", day: "numeric", year: "numeric" });

// "3h" + "3 hours ago" + "Sep 24, 11:02 AM". Sources that only give the day ("Posted Today", "3d")
// are shown as Today / Yesterday / N days ago instead of a made-up time.
function posted(j) {
  const ts = j.posted_at;
  if (!ts) {
    const s = NOW - j.first_seen;
    return { short: ageText(s), long: "date not given", date: `found ${fmtDate(j.first_seen, true)}`, fresh: s < 86400 };
  }
  const sec = Math.max(0, NOW - ts);
  if (j.posted_precision === "day") {
    const today = new Date(NOW * 1000); today.setHours(0, 0, 0, 0);
    const days = Math.max(0, Math.round((today.getTime() / 1000 - ts) / 86400));
    return { short: `${days}d`, long: days === 0 ? "Today" : days === 1 ? "Yesterday" : `${days} days ago`, date: fmtDate(ts, false), fresh: days === 0 };
  }
  const m = Math.floor(sec / 60), h = Math.floor(sec / 3600), d = Math.floor(sec / 86400);
  const about = j.posted_precision === "hour" ? "about " : "";
  const long = m < 1 ? "just now" : m < 60 ? `${plural(m, "min")} ago` : h < 24 ? `${about}${plural(h, "hour")} ago` : `${plural(d, "day")} ago`;
  return { short: ageText(sec), long, date: fmtDate(ts, true), fresh: sec < 86400 };
}
function postedCell(j) {
  const p = posted(j);
  return `<td class="age ${p.fresh ? "fresh" : ""}"><b>${p.short}</b><span class="age-long">${esc(p.long)}</span><span class="age-date">${esc(p.date)}</span></td>`;
}

const STYPE = { github: "GitHub", apify: "Apify · LinkedIn", university: "University site", company: "Company site", manual: "Added by you" };
function sourceCell(j) {
  const all = (j.sources || j.source_name || "").split("|").filter(Boolean);
  const others = all.filter((s) => s !== j.source_name);
  return `<td class="src"><span class="stype ${j.source_type}">${STYPE[j.source_type] || esc(j.source_type)}</span>
    <span class="sname">${esc(j.source_name)}</span>
    ${others.length ? `<span class="also" title="Also listed on: ${esc(others.join(", "))}">+ ${plural(others.length, "more list")}</span>` : ""}
    <span class="age-date">found ${ageText(NOW - j.first_seen)} ago</span></td>`;
}

async function loadJobs() {
  const data = await api("/api/jobs");
  JOBS = data.jobs;
  NOW = data.now;
  LAST_FETCH = Math.max(0, ...(STATUS.log || []).map((l) => l.last_run));
  const sources = [...new Set(JOBS.map((j) => j.source_name))].sort();
  const sel = $("#f-source");
  sel.innerHTML = `<option value="">All</option>` + sources.map((s) => `<option ${s === F.source ? "selected" : ""}>${esc(s)}</option>`).join("");
  renderJobs();
  renderUnis();
}

function matches(j, skip) {
  if (j.source_type === "university") return false; // these live on the Universities tab
  if (!(j.regions || ["us"]).includes(F.region)) return false;
  if (skip !== "place" && F.place && !placesOf(j).includes(F.place)) return false;
  if (skip !== "cat" && F.cat && !j.categories.split(",").includes(F.cat)) return false;
  if (skip !== "level" && F.level && j.level !== F.level) return false;
  if (skip !== "age" && F.age && ageOf(j) > F.age * 3600) return false;
  if (skip !== "stype" && F.stype && j.source_type !== F.stype) return false;
  if (skip !== "fin" && F.fin && !(F.fin === "any" ? j.fin : j.fin && j.fin.segment === F.fin)) return false;
  if (F.source && j.source_name !== F.source) return false;
  if (F.cap && !j.cap_exempt) return false;
  if (F.top && !j.top_company) return false;
  if (F.h1b === "sponsor" && !hasSponsored(j)) return false;
  if (F.h1b === "yes" && j.h1b !== "yes") return false;
  if (F.h1b === "not-no" && ["no", "citizen"].includes(j.h1b)) return false;
  if (F.status === "active" ? j.status === "hidden"
    : F.status === "todo" ? (APPLIED.has(j.status) || j.status === "hidden")
    : F.status === "applied-any" ? !APPLIED.has(j.status)
    : j.status !== F.status) return false;
  if (F.q) {
    const hay = `${j.company} ${j.title} ${j.location}`.toLowerCase();
    if (!F.q.toLowerCase().split(/\s+/).every((w) => hay.includes(w))) return false;
  }
  return true;
}

function chips(el, items, key, counter) {
  el.innerHTML = items
    .map(([v, label]) => {
      const n = counter(v);
      return `<button class="chip ${String(F[key]) === String(v) ? "on" : ""}" data-v="${v}">${esc(label)}<small>${n}</small></button>`;
    })
    .join("");
  $$("button", el).forEach((b) => (b.onclick = () => { F[key] = b.dataset.v === "" ? "" : isNaN(b.dataset.v) ? b.dataset.v : Number(b.dataset.v); SHOWN = 200; renderJobs(); }));
}

const sorters = {
  posted: (j) => ageOf(j), company: (j) => j.company.toLowerCase(), title: (j) => j.title.toLowerCase(),
  location: (j) => j.location.toLowerCase(), level: (j) => j.level, source: (j) => j.source_name,
  h1b: (j) => (["no", "citizen"].includes(j.h1b) ? -1 : j.h1b === "yes" ? 1e9 : j.h1b_fy23 || (j.h1b === "likely" ? 0.5 : 0)) * -1,
  fin: (j) => (j.fin ? j.fin.segment_label + " " + j.fin.name : "~"),
};

function renderJobs() {
  const base = (skip) => JOBS.filter((j) => matches(j, skip));
  const forCat = base("cat"), forLevel = base("level"), forAge = base("age"), forSt = base("stype"), forFin = base("fin");
  const [rtitle, rdesc] = REGION_INFO[F.region];
  $("#region-head").innerHTML = F.region === "us" ? "" : `<h2>${rtitle}</h2><p class="muted">${esc(rdesc)}</p>`;
  if (F.region === "us") $("#f-place").innerHTML = "";
  else {
    const forPlace = base("place"), counts = {};
    forPlace.forEach((j) => placesOf(j).forEach((p) => (counts[p] = (counts[p] || 0) + 1)));
    const places = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 18).map(([p]) => [p, p]);
    chips($("#f-place"), [["", F.region === "india" ? "All cities" : "All countries"], ...places], "place",
      (v) => (v ? counts[v] || 0 : forPlace.length));
  }
  $("#jobs thead th[data-sort=h1b]").classList.toggle("hidden", F.region !== "us");
  chips($("#f-fin"), [["", "All companies"], ["any", "Any finance firm"], ...FIN_SEGMENTS], "fin",
    (v) => (v === "" ? forFin.length : forFin.filter((j) => j.fin && (v === "any" || j.fin.segment === v)).length));
  chips($("#f-stype"), STYPES, "stype", (v) => (v ? forSt.filter((j) => j.source_type === v).length : forSt.length));
  chips($("#f-cat"), CATS, "cat", (v) => (v ? forCat.filter((j) => j.categories.split(",").includes(v)).length : forCat.length));
  chips($("#f-level"), LEVELS, "level", (v) => (v ? forLevel.filter((j) => j.level === v).length : forLevel.length));
  chips($("#f-age"), AGES, "age", (v) => (v ? forAge.filter((j) => ageOf(j) <= v * 3600).length : forAge.length));

  const rows = base();
  const k = sorters[SORT.key];
  rows.sort((a, b) => { const x = k(a), y = k(b); return (x < y ? -1 : x > y ? 1 : 0) * (SORT.asc ? 1 : -1) * (SORT.key === "posted" ? -1 : 1); });
  $$("#jobs th").forEach((th) => { th.classList.toggle("sorted", th.dataset.sort === SORT.key); th.classList.toggle("asc", SORT.asc); });
  $("#count").textContent = `${rows.length.toLocaleString()} jobs`;

  const jr = STATUS.jobright_url || "https://jobright.ai/jobs/search?value={q}";
  $("#jobs tbody").innerHTML = rows.slice(0, SHOWN).map((j) => {
    const cats = j.categories.split(",").map((c) => `<span class="tag">${CAT_LABEL[c] || c}</span>`).join("");
    const badges = (j.top_company ? `<span class="tag top">★ Top</span>` : "") + (j.cap_exempt ? `<span class="tag cap">Cap-exempt</span>` : "");
    const jrUrl = jr.replace("{q}", encodeURIComponent(`${j.title} ${j.company}`));
    return `<tr class="${rowClass(j)}" data-id="${j.id}">
      ${appliedBox(j)}
      ${postedCell(j)}
      <td class="company">${esc(j.company)}<br>${badges}</td>
      ${finCell(j)}
      <td>${esc(j.title)}${j.salary ? `<br><span class="muted">${esc(j.salary)}</span>` : ""}</td>
      <td class="loc">${esc(j.location)}${F.region === "other" ? `<span class="age-date">${esc(placesOf(j).join(", "))}</span>` : ""}</td>
      <td>${cats}</td>
      <td>${LEVEL_LABEL[j.level] || j.level}</td>
      ${F.region === "us" ? `<td class="h1b">${h1bCell(j)}</td>` : ""}
      ${sourceCell(j)}
      <td><div class="actions">
        ${j.url ? `<a class="btn primary-link" href="${esc(j.url)}" target="_blank" rel="noopener">Apply ↗</a>` : ""}
        <a class="btn" href="${esc(jrUrl)}" target="_blank" rel="noopener" title="Look up on JobRight">JR</a>
        ${statusSelect(j)}
      </div></td></tr>`;
  }).join("");
  $("#more").classList.toggle("hidden", rows.length <= SHOWN);
}

function bindRowActions(tbody) {
tbody.addEventListener("change", async (e) => {
  const act = e.target.dataset.act;
  if (act !== "status" && act !== "applied") return;
  const id = e.target.closest("tr").dataset.id;
  const status = act === "applied" ? (e.target.checked ? "applied" : "new") : e.target.value;
  const r = await api(`/api/jobs/${id}/status`, { method: "POST", body: { status } });
  Object.assign(JOBS.find((j) => j.id === id), r);
  if (act === "applied" && e.target.checked) {
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const n = JOBS.filter((j) => j.applied_at && j.applied_at * 1000 >= today.getTime()).length;
    toast(`Marked applied ✓  (${n} today)`);
  }
  renderJobs();
  renderUnis();
});
}
bindRowActions($("#jobs tbody"));
bindRowActions($("#uni-table tbody"));
$$("#jobs th[data-sort]").forEach((th) => (th.onclick = () => {
  SORT = { key: th.dataset.sort, asc: SORT.key === th.dataset.sort ? !SORT.asc : false };
  renderJobs();
}));
$("#more").onclick = () => { SHOWN += 300; renderJobs(); };
$("#q").oninput = (e) => { F.q = e.target.value; SHOWN = 200; renderJobs(); };
$("#f-h1b").onchange = (e) => { F.h1b = e.target.value; renderJobs(); };
$("#f-cap").onchange = (e) => { F.cap = e.target.checked; renderJobs(); };
$("#f-top").onchange = (e) => { F.top = e.target.checked; renderJobs(); };
$("#f-source").onchange = (e) => { F.source = e.target.value; renderJobs(); };
$("#f-status").onchange = (e) => { F.status = e.target.value; renderJobs(); };

async function startRefresh(apify) {
  if (apify && !STATUS.apify) return toast("Add APIFY_TOKEN to .env first (see Settings).", 4000);
  if (apify && !confirm("Run the Apify LinkedIn searches from config/sources.yaml? This uses your Apify credits.")) return;
  await api("/api/refresh", { method: "POST", body: { apify } });
  pollRefresh();
}
async function pollRefresh() {
  const s = await api("/api/refresh");
  $("#refresh-state").innerHTML = s.running ? `<span class="spinner"></span>Fetching…` : lastFetched(s.log);
  $("#btn-refresh").disabled = $("#btn-apify").disabled = s.running;
  if (s.running) return setTimeout(pollRefresh, 2000);
  const errs = s.results.filter((r) => r.error);
  if (s.results.length) toast(errs.length ? `Done, with errors: ${errs.map((e) => e.source).join(", ")}` : `Fetched ${s.results.reduce((a, r) => a + r.count, 0)} jobs`);
  await loadStatus();
  loadJobs();
}
function lastFetched(log) {
  const t = Math.max(0, ...log.map((l) => l.last_run));
  return t ? `Updated ${ageText(Date.now() / 1000 - t)} ago` : "Not fetched yet";
}
$("#btn-refresh").onclick = () => startRefresh(false);

// The server refreshes sources every hour on its own; pick up new data without a page reload.
let LAST_FETCH = 0;
setInterval(async () => {
  try {
    const s = await api("/api/refresh");
    const latest = Math.max(0, ...s.log.map((l) => l.last_run));
    if (!s.running && latest > LAST_FETCH) { await loadStatus(); loadJobs(); }
    else $("#refresh-state").innerHTML = s.running ? `<span class="spinner"></span>Fetching…` : lastFetched(s.log);
  } catch { /* server restarting */ }
}, 120000);
$("#btn-apify").onclick = () => startRefresh(true);

$("#btn-add-job").onclick = () => $("#dlg-job").showModal();
$("#dlg-job").addEventListener("close", async () => {
  if ($("#dlg-job").returnValue !== "ok") return;
  const body = Object.fromEntries(new FormData($("#add-job-form")));
  await api("/api/jobs", { method: "POST", body });
  $("#add-job-form").reset();
  toast("Job added");
  loadJobs();
});

// ------------------------------------------------------------------ ASK ALL
const TEMPLATES = {
  "Cover letter": "Write a concise, specific cover letter (under 250 words) for this job using my resume. No clichés.\n\nJOB DESCRIPTION:\n\n\nMY RESUME:\n",
  "Recruiter message": "Write a 3-sentence LinkedIn connection note to a recruiter at this company about this role, mentioning one specific fit point.\n\nROLE / JD:\n",
  "Interview prep": "Give me the 10 most likely interview questions for this role (technical + behavioral) and a short outline answer for each based on my background.\n\nJD:\n\n\nMY BACKGROUND:\n",
  "Does this sponsor H-1B?": "Based on public info you know, does this company historically sponsor H-1B / hire F-1 OPT candidates for this kind of role? Be clear about uncertainty.\n\nCompany and role:\n",
  "Fit score": "Score my fit for this job 1-10, list gaps, and tell me whether I should apply.\n\nJD:\n\n\nMY RESUME:\n",
};
$("#templates").innerHTML = Object.keys(TEMPLATES).map((k) => `<button class="chip" data-t="${esc(k)}">${esc(k)}</button>`).join("");
$$("#templates .chip").forEach((b) => (b.onclick = () => { $("#ask-prompt").value = TEMPLATES[b.dataset.t]; $("#ask-prompt").focus(); }));

function renderAskProviders() {
  $("#ask-providers").innerHTML = STATUS.llms.map((l) => `<label class="check"><input type="checkbox" value="${l.id}" ${["chatgpt", "claude"].includes(l.id) || l.configured ? "checked" : ""}> ${esc(l.label)} <span class="muted">${l.configured ? esc(l.model) : "(no key)"}</span></label>`).join("");
}
$("#ask-go").onclick = async () => {
  const prompt = $("#ask-prompt").value.trim();
  if (!prompt) return;
  const chosen = $$("#ask-providers input:checked").map((i) => i.value);
  const withKey = chosen.filter((p) => STATUS.llms.find((l) => l.id === p).configured);
  const noKey = chosen.filter((p) => !withKey.includes(p));
  const full = ($("#ask-system").value.trim() ? $("#ask-system").value.trim() + "\n\n" : "") + prompt;
  $("#ask-out").innerHTML = withKey.map((p) => `<div class="card" id="ans-${p}"><h3>${esc(STATUS.llms.find((l) => l.id === p).label)}</h3><span class="spinner"></span>Thinking…</div>`).join("")
    + noKey.map((p) => { const l = STATUS.llms.find((x) => x.id === p); return `<div class="card"><h3>${esc(l.label)}</h3><p class="muted">No API key — use your subscription:</p><div class="row"><button data-copy>Copy prompt</button><a class="btn" href="${esc(l.chat_url)}" target="_blank" rel="noopener">Open ${esc(l.label)} ↗</a></div></div>`; }).join("");
  $$("#ask-out [data-copy]").forEach((b) => (b.onclick = () => { navigator.clipboard.writeText(full); toast("Copied"); }));
  if (!withKey.length) return;
  const res = await api("/api/ask", { method: "POST", body: { prompt, system: $("#ask-system").value, providers: withKey } });
  res.forEach((r) => {
    $(`#ans-${r.provider}`).innerHTML = `<h3>${esc(r.label)} <span class="muted">${esc(r.model || "")}</span></h3>` +
      (r.error ? `<p class="flag">${esc(r.error)}</p>` : `<div class="answer">${esc(r.text)}</div><button data-c>Copy</button>`);
    const c = $(`#ans-${r.provider} [data-c]`);
    if (c) c.onclick = () => { navigator.clipboard.writeText(r.text); toast("Copied"); };
  });
};

// ------------------------------------------------------------------ UNIVERSITIES
let UNIS = [];
const UF = { uni: "", type: "", age: "", q: "" };
let USHOWN = 200;
const UTYPES = [
  ["", "All roles"],
  ["tech", "Tech & Software", /software|developer|programmer|\b(it|ios|sre)\b|information technology|information systems|systems (engineer|admin|analyst)|devops|cloud|\bweb\b|application (developer|engineer|analyst)|database|network (engineer|admin)|cyber|information security|research computing|computer|full.?stack|front.?end|back.?end/i],
  ["data", "Data, AI & Analytics", /\bdata\b|analytic|machine learning|\bai\b|artificial intelligence|statistic|bioinformatic|computational|quantitative/i],
  ["research", "Research", /research|postdoc|scientist|\blab\b|laboratory|fellow/i],
  ["finance", "Finance & Business", /financ|budget|account|investment|grant|fiscal|business|operations analyst|procurement/i],
];
const UAGES = [["", "Any time"], [24, "≤ 24h"], [72, "≤ 3d"], [168, "≤ 7d"], [336, "≤ 14d"], [720, "≤ 30d"]];

async function loadUnis() {
  UNIS = await api("/api/universities");
  renderUnis();
}

function uniMatch(j, skip) {
  if (!j.uni) return false;
  if (skip !== "uni" && UF.uni && j.uni !== UF.uni) return false;
  if (skip !== "type" && UF.type && !UTYPES.find((t) => t[0] === UF.type)[2].test(j.title)) return false;
  if (skip !== "age" && UF.age && ageOf(j) > UF.age * 3600) return false;
  if (j.status === "hidden") return false;
  if (UF.q) {
    const hay = `${j.title} ${j.location} ${j.company}`.toLowerCase();
    if (!UF.q.toLowerCase().split(/\s+/).every((w) => hay.includes(w))) return false;
  }
  return true;
}

function renderUnis() {
  if (!UNIS.length || !JOBS.length) return;
  const forCards = JOBS.filter((j) => uniMatch(j, "uni"));
  $("#uni-cards").innerHTML = UNIS.map((u) => {
    const mine = forCards.filter((j) => j.uni === u.short);
    const fresh = mine.filter((j) => ageOf(j) <= 86400).length;
    const err = u.log && u.log.error;
    return `<div class="uni ${UF.uni === u.short ? "on" : ""}" data-u="${esc(u.short)}" title="${esc(u.name)}${err ? " — fetch error: " + esc(err) : ""}">
      <b>${esc(u.short)}</b>
      <span class="n">${mine.length}</span>
      <span class="meta"><span class="${fresh ? "fresh" : ""}">${fresh ? fresh + " new today" : u.feed ? "direct feed" : "link only"}${err ? " ⚠" : ""}</span>
      <a href="${esc(u.careers_url)}" target="_blank" rel="noopener" data-stop>Site ↗</a></span></div>`;
  }).join("");
  $$("#uni-cards [data-stop]").forEach((a) => a.addEventListener("click", (e) => e.stopPropagation()));
  $$("#uni-cards .uni").forEach((c) => (c.onclick = () => { UF.uni = UF.uni === c.dataset.u ? "" : c.dataset.u; USHOWN = 200; renderUnis(); }));

  const forType = JOBS.filter((j) => uniMatch(j, "type")), forAge = JOBS.filter((j) => uniMatch(j, "age"));
  const uchips = (el, items, key, counter) => {
    el.innerHTML = items.map(([v, label]) => `<button class="chip ${String(UF[key]) === String(v) ? "on" : ""}" data-v="${v}">${esc(label)}<small>${counter(v)}</small></button>`).join("");
    $$("button", el).forEach((b) => (b.onclick = () => { UF[key] = b.dataset.v === "" ? "" : isNaN(b.dataset.v) ? b.dataset.v : Number(b.dataset.v); USHOWN = 200; renderUnis(); }));
  };
  uchips($("#u-type"), UTYPES, "type", (v) => (v ? forType.filter((j) => UTYPES.find((t) => t[0] === v)[2].test(j.title)).length : forType.length));
  uchips($("#u-age"), UAGES, "age", (v) => (v ? forAge.filter((j) => ageOf(j) <= v * 3600).length : forAge.length));

  const rows = JOBS.filter((j) => uniMatch(j)).sort((a, b) => ageOf(a) - ageOf(b));
  $("#uni-count").textContent = `${rows.length.toLocaleString()} jobs${UF.uni ? " at " + UF.uni : ""}`;
  $("#uni-table tbody").innerHTML = rows.slice(0, USHOWN).map((j) => {
    const types = UTYPES.slice(1).filter((t) => t[2].test(j.title)).map((t) => `<span class="tag">${esc(t[1])}</span>`).join("");
    return `<tr class="${rowClass(j)}" data-id="${j.id}">
      ${appliedBox(j)}
      ${postedCell(j)}
      <td class="company">${esc(j.uni)}<br><span class="tag cap">Cap-exempt</span></td>
      <td>${esc(j.title)}</td>
      <td class="loc">${esc(j.location)}</td>
      <td>${types}</td>
      ${sourceCell(j)}
      <td><div class="actions">
        ${j.url ? `<a class="btn" href="${esc(j.url)}" target="_blank" rel="noopener">Apply ↗</a>` : ""}
        ${statusSelect(j)}
      </div></td></tr>`;
  }).join("");
  $("#u-more").classList.toggle("hidden", rows.length <= USHOWN);
}
$("#uq").oninput = (e) => { UF.q = e.target.value; USHOWN = 200; renderUnis(); };
$("#u-more").onclick = () => { USHOWN += 300; renderUnis(); };

// ------------------------------------------------------------------ SETTINGS
function renderSettings() {
  $("#set-llms").innerHTML = `<ul class="list">${STATUS.llms.map((l) => `<li><span><b>${esc(l.label)}</b> <span class="muted">${esc(l.model)}</span></span><span class="tag ${l.configured ? "yes" : "no"}">${l.configured ? "API key set" : "no key → copy & paste mode"}</span></li>`).join("")}</ul>`;
  $("#set-sources").innerHTML = STATUS.sources.map((s) => `<li><span><b>${esc(s.name)}</b> <span class="tag">${esc(LEVEL_LABEL[s.level] || s.level || "")}</span><br><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.url)}</a></span><button data-del="${esc(s.url)}">Remove</button></li>`).join("");
  $$("#set-sources [data-del]").forEach((b) => (b.onclick = async () => { if (!confirm("Remove this source?")) return; await api(`/api/sources/github?url=${encodeURIComponent(b.dataset.del)}`, { method: "DELETE" }); loadStatus(); }));
  $("#set-apify").innerHTML = `<p><span class="tag ${STATUS.apify ? "yes" : "no"}">${STATUS.apify ? "APIFY_TOKEN set" : "APIFY_TOKEN missing"}</span> Searches (edit in <code>config/sources.yaml</code>):</p><ul>${STATUS.apify_searches.map((s) => `<li>${esc(s.keywords)} · ${esc(s.location || "")} · ${esc(s.datePosted || "")}</li>`).join("")}</ul>`;
  renderFirms();
  renderCompanies();
  $("#set-log tbody").innerHTML = STATUS.log.map((l) => `<tr><td>${esc(l.source)}</td><td>${l.count} jobs</td><td class="muted">${ageText(Date.now() / 1000 - l.last_run)} ago</td><td class="flag">${esc(l.error || "")}</td></tr>`).join("");
}
async function renderFirms() {
  const d = await api("/api/finance");
  $("#set-firms tbody").innerHTML = d.firms.map((f) => {
    const log = f.log;
    const feed = !f.feed ? `<a href="${esc(f.careers)}" target="_blank" rel="noopener">link only ↗</a>`
      : !log ? `<span class="muted">not fetched yet</span>`
      : log.error ? `<span class="flag" title="${esc(log.error)}">error ⚠</span>`
      : `<span class="tag yes">${log.count} US jobs</span> <span class="muted">${ageText(Date.now() / 1000 - log.last_run)} ago</span>`;
    return `<tr><td><b>${esc(f.name)}</b></td><td><span class="seg seg-${f.segment}">${esc(f.segment_label)}</span></td>
      <td>${f.h1b_fy23 ? f.h1b_fy23.toLocaleString() : '<span class="muted">none found</span>'}</td><td>${feed}</td></tr>`;
  }).join("");
}

async function renderCompanies() {
  const list = await api("/api/companies");
  $("#set-companies tbody").innerHTML = list.map((c) => {
    const log = c.log;
    const feed = !log ? `<span class="muted">not fetched yet</span>`
      : log.error ? `<span class="flag" title="${esc(log.error)}">error ⚠</span>`
      : `<span class="tag yes">${log.count} jobs</span> <span class="muted">${ageText(Date.now() / 1000 - log.last_run)} ago</span>`;
    return `<tr><td><b>${esc(c.name)}</b></td><td>${esc(c.group)}</td>
      <td>${c.h1b_fy23 ? c.h1b_fy23.toLocaleString() : '<span class="muted">none found</span>'}</td><td>${feed}</td></tr>`;
  }).join("");
}

$("#src-add").onclick = async () => {
  try {
    await api("/api/sources/github", { method: "POST", body: { url: $("#src-url").value, name: $("#src-name").value, level: $("#src-level").value } });
    $("#src-url").value = $("#src-name").value = "";
    await loadStatus();
    toast("Added — fetching it now");
    startRefresh(false);
  } catch (e) { toast(e.message, 4000); }
};

// ------------------------------------------------------------------ ANALYTICS
// Hand-built charts (no library): one accent hue for magnitude, an ordinal blue ramp for the funnel,
// thin marks with rounded data-ends, hover tooltips, and a table view under every chart.
let AN = null, AN_RANGE = 30;
const SECTOR = { swe: "Software Engineering", finance: "Finance & Banks", data: "Data Science & ML", other: "Other" };
const REGION = { us: "🇺🇸 United States", india: "🇮🇳 India", other: "🌍 Other countries" };
const DAY = 86400;

async function loadAnalytics() {
  $("#an").innerHTML = `<div class="card"><span class="spinner"></span>Crunching your numbers…</div>`;
  AN = await api("/api/analytics");
  renderAnalytics();
}

const fmt = (n) => (n >= 10000 ? `${(n / 1000).toFixed(1)}K` : n.toLocaleString());
const pct = (a, b) => (b ? Math.round((100 * a) / b) : 0);
const dayStart = (t) => { const d = new Date(t * 1000); d.setHours(0, 0, 0, 0); return d.getTime() / 1000; };
function countBy(items, keyFn) {
  const m = new Map();
  items.forEach((x) => [].concat(keyFn(x)).filter(Boolean).forEach((k) => m.set(k, (m.get(k) || 0) + 1)));
  return [...m.entries()].map(([label, value]) => ({ label, value })).sort((a, b) => b.value - a.value);
}

// ---- chart pieces
function tableView(rows, cols) {
  return `<details class="tview"><summary>Show as table</summary><table class="small"><thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r) => `<tr>${r.map((v) => `<td>${esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table></details>`;
}
function hbars(items, { total, ramp } = {}) {
  if (!items.length) return `<p class="muted">Nothing yet.</p>`;
  const max = Math.max(...items.map((i) => i.value)) || 1;
  return `<div class="hbars">${items.map((i, k) => {
    const share = total ? ` · ${pct(i.value, total)}%` : "";
    const color = ramp ? `var(--ord-${Math.min(k + 1, 4)})` : "var(--viz-accent)";
    return `<div class="hb" data-tip="${esc(i.label)}: ${i.value.toLocaleString()}${share}">
      <span class="hb-label">${esc(i.label)}</span>
      <span class="hb-track"><span class="hb-bar" style="width:${Math.max(2, (100 * i.value) / max)}%;background:${color}"></span>
      <span class="hb-val">${i.value.toLocaleString()}<span class="muted">${share}</span></span></span></div>`;
  }).join("")}</div>`;
}
function niceMax(v) {
  if (v <= 4) return 4;
  const p = 10 ** Math.floor(Math.log10(v)), n = v / p;
  return (n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}
function columns(items, { width = 760, height = 190, labelEvery = 1 } = {}) {
  const W = width, H = height, padL = 34, padB = 26, padT = 14, n = items.length;
  const max = niceMax(Math.max(1, ...items.map((i) => i.value)));
  const band = (W - padL - 6) / n, bw = Math.min(24, band - 2), y = (v) => padT + (H - padT - padB) * (1 - v / max);
  const ticks = [0, max / 2, max].map((t) => Math.round(t));
  let svg = `<svg viewBox="0 0 ${W} ${H}" class="cols" role="img" aria-label="Column chart" preserveAspectRatio="xMidYMid meet">`;
  ticks.forEach((t) => { svg += `<line x1="${padL}" x2="${W}" y1="${y(t)}" y2="${y(t)}" class="grid"/><text x="${padL - 6}" y="${y(t) + 4}" class="tick" text-anchor="end">${t}</text>`; });
  items.forEach((it, k) => {
    const x = padL + k * band + (band - bw) / 2, top = y(it.value), h = H - padB - top;
    if (it.value > 0) {
      const r = Math.min(4, h);  // rounded data-end, square at the baseline
      svg += `<path class="col" d="M${x},${H - padB} V${top + r} Q${x},${top} ${x + r},${top} H${x + bw - r} Q${x + bw},${top} ${x + bw},${top + r} V${H - padB} Z"/>`;
    }
    svg += `<rect class="hit" x="${padL + k * band}" y="${padT}" width="${band}" height="${H - padT - padB}" data-tip="${esc(it.tip || `${it.label}: ${it.value}`)}"/>`;
    if (k % labelEvery === 0 || k === n - 1) svg += `<text x="${x + bw / 2}" y="${H - 8}" class="tick" text-anchor="middle">${esc(it.label)}</text>`;
  });
  svg += `<line x1="${padL}" x2="${W}" y1="${H - padB}" y2="${H - padB}" class="base"/></svg>`;
  return svg;
}
function card(title, sub, body, table, wide = false) {
  return `<div class="card an-card ${wide ? "wide" : ""}"><h3>${title}</h3>${sub ? `<p class="muted an-sub">${sub}</p>` : ""}${body}${table || ""}</div>`;
}
function tile(label, value, note, cls = "") {
  return `<div class="tile ${cls}"><span class="t-label">${label}</span><span class="t-value">${value}</span>${note ? `<span class="t-note">${note}</span>` : ""}</div>`;
}

function renderAnalytics() {
  const apps = AN.applied.filter((j) => j.applied_at), now = AN.now, today = dayStart(now);
  if (!apps.length) {
    $("#an").innerHTML = `<div class="card empty-state"><h3>No applications tracked yet</h3>
      <p>Tick the <b>Applied</b> box on the left of any job (Jobs, India, Other countries or Universities tabs). The date is saved automatically, and this page fills up with your stats.</p>
      <p class="muted">Later, change a job's stage to <b>interviewing</b>, <b>offer</b> or <b>rejected</b> from its dropdown to see your funnel.</p></div>`;
    return;
  }
  const inDays = (d) => apps.filter((j) => j.applied_at >= today - (d - 1) * DAY);
  const week = inDays(7).length, prevWeek = apps.filter((j) => j.applied_at >= today - 13 * DAY && j.applied_at < today - 6 * DAY).length;
  const last30 = inDays(30).length;
  const days = new Set(apps.map((j) => dayStart(j.applied_at)));
  let streak = 0, d = days.has(today) ? today : today - DAY;
  while (days.has(d)) { streak++; d -= DAY; }
  const interviews = apps.filter((j) => j.status === "interviewing" || j.status === "offer").length;
  const offers = apps.filter((j) => j.status === "offer").length, rejected = apps.filter((j) => j.status === "rejected").length;
  const usApps = apps.filter((j) => (j.regions || ["us"]).includes("us"));
  const sponsor = usApps.filter(hasSponsored).length;
  const delta = week - prevWeek;
  const deltaTxt = prevWeek || week ? `<span class="${delta >= 0 ? "up" : "down"}">${delta >= 0 ? "▲" : "▼"} ${Math.abs(delta)}</span> vs previous 7 days` : "";

  // ---- time series
  const nDays = AN_RANGE;
  const series = [...Array(nDays)].map((_, k) => {
    const start = today - (nDays - 1 - k) * DAY, v = apps.filter((j) => j.applied_at >= start && j.applied_at < start + DAY).length;
    const dt = new Date(start * 1000);
    return { label: dt.toLocaleDateString(undefined, { month: "short", day: "numeric" }), value: v,
             tip: `${dt.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}: ${v} applied` };
  });

  // ---- breakdowns
  const sectors = countBy(apps, (j) => j.categories.split(",").map((c) => SECTOR[c] || c));
  const segs = countBy(apps.filter((j) => j.fin), (j) => j.fin.segment_label);
  const regions = countBy(apps, (j) => (j.regions || ["us"]).map((r) => REGION[r]));
  const levels = countBy(apps, (j) => LEVEL_LABEL[j.level] === "—" ? "Unspecified" : LEVEL_LABEL[j.level] || j.level);
  const companies = countBy(apps, (j) => j.uni || j.company).slice(0, 10);
  const sources = countBy(apps, (j) => STYPE[j.source_type] || j.source_type);
  const wd = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const weekdays = wd.map((w, k) => ({ label: w, value: apps.filter((j) => (new Date(j.applied_at * 1000).getDay() + 6) % 7 === k).length }));
  const buckets = [["< 1 day", 1], ["1–3 days", 3], ["3–7 days", 7], ["1–2 weeks", 14], ["2+ weeks", 1e9]];
  const withPost = apps.filter((j) => j.posted_at && j.applied_at >= j.posted_at);
  const speed = buckets.map(([label, maxD], k) => ({ label, value: withPost.filter((j) => {
    const age = (j.applied_at - j.posted_at) / DAY; return age < maxD && age >= (k ? buckets[k - 1][1] : 0);
  }).length }));
  const fast = withPost.length ? pct(speed[0].value + speed[1].value, withPost.length) : 0;
  const funnel = [{ label: "Applied", value: apps.length }, { label: "Interviewing or beyond", value: interviews }, { label: "Offer", value: offers }];
  const topSector = sectors[0];

  $("#an").innerHTML = `
  <div class="an-head">
    <div><h2>Your application analytics</h2><p class="muted">Based on the jobs you've ticked as applied. Updated live.</p></div>
    <button id="an-refresh">Refresh</button>
  </div>
  <div class="tiles">
    <div class="tile hero"><span class="t-label">Total applications</span><span class="t-value">${fmt(apps.length)}</span>
      <span class="t-note">since ${new Date(Math.min(...apps.map((j) => j.applied_at)) * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</span></div>
    ${tile("Last 7 days", week, deltaTxt)}
    ${tile("Daily average", (last30 / 30).toFixed(1), "last 30 days")}
    ${tile("Current streak", `${streak} day${streak === 1 ? "" : "s"}`, streak ? "keep it going" : "apply today to start one")}
    ${tile("Interview rate", `${pct(interviews, apps.length)}%`, `${interviews - offers} interviewing · ${offers} offer${offers === 1 ? "" : "s"} · ${rejected} rejected`)}
    ${tile("To H-1B sponsors", `${pct(sponsor, usApps.length)}%`, `${sponsor} of ${usApps.length} US applications`)}
  </div>
  ${topSector ? `<div class="insight">You apply most to <b>${esc(topSector.label)}</b> (${pct(topSector.value, apps.length)}% of applications)${segs[0] ? `, and among finance firms mostly to <b>${esc(segs[0].label)}</b>` : ""}. ${withPost.length ? `<b>${fast}%</b> of your applications went in within 3 days of the posting.` : ""}</div>` : ""}

  <div class="an-grid">
    ${card("Applications per day", `<span class="seg-toggle">${[30, 90].map((n) => `<button class="chip ${AN_RANGE === n ? "on" : ""}" data-range="${n}">Last ${n} days</button>`).join("")}</span>`,
      columns(series, { width: 1320, height: 220, labelEvery: nDays > 30 ? 14 : 5 }), tableView(series.map((s) => [s.label, s.value]), ["Day", "Applied"]), true)}
    ${card("By sector", "A job can count in more than one sector", hbars(sectors, { total: apps.length }), tableView(sectors.map((s) => [s.label, s.value]), ["Sector", "Applied"]))}
    ${card("Finance firm categories", `${apps.filter((j) => j.fin).length} applications to finance firms`, hbars(segs, { total: apps.filter((j) => j.fin).length }), tableView(segs.map((s) => [s.label, s.value]), ["Category", "Applied"]))}
    ${card("Pipeline", "Change a job's stage from its dropdown", hbars(funnel, { ramp: true, total: apps.length }) + `<p class="muted an-foot">${rejected} rejected so far</p>`, tableView(funnel.map((s) => [s.label, s.value]), ["Stage", "Jobs"]))}
    ${card("Where", "", hbars(regions, { total: apps.length }), tableView(regions.map((s) => [s.label, s.value]), ["Region", "Applied"]))}
    ${card("Level", "", hbars(levels, { total: apps.length }), tableView(levels.map((s) => [s.label, s.value]), ["Level", "Applied"]))}
    ${card("Top companies", "Your 10 most-applied employers", hbars(companies), tableView(companies.map((s) => [s.label, s.value]), ["Company", "Applied"]))}
    ${card("How fast you apply", "Time from posting to your application", hbars(speed, { total: withPost.length }), tableView(speed.map((s) => [s.label, s.value]), ["After posting", "Applied"]))}
    ${card("By weekday", "When you tend to apply", columns(weekdays, { width: 420, height: 190 }), tableView(weekdays.map((s) => [s.label, s.value]), ["Day", "Applied"]))}
    ${card("Where you found them", "", hbars(sources, { total: apps.length }), tableView(sources.map((s) => [s.label, s.value]), ["Source", "Applied"]))}
    ${card("Recent applications", "", `<div class="table-wrap"><table class="small recent"><thead><tr><th>Applied</th><th>Company</th><th>Role</th><th>Sector</th><th>Stage</th><th></th></tr></thead><tbody>
      ${apps.slice(0, 25).map((j) => `<tr data-id="${j.id}"><td>${new Date(j.applied_at * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</td>
        <td><b>${esc(j.uni || j.company)}</b></td><td>${esc(j.title)}</td><td>${j.categories.split(",").map((c) => `<span class="tag">${esc(CAT_LABEL[c] || c)}</span>`).join("")}</td>
        <td>${statusSelect(j)}</td><td>${j.url ? `<a href="${esc(j.url)}" target="_blank" rel="noopener">Open ↗</a>` : ""}</td></tr>`).join("")}
      </tbody></table></div>`, "", true)}
  </div>`;

  $$("[data-range]").forEach((b) => (b.onclick = () => { AN_RANGE = +b.dataset.range; renderAnalytics(); }));
  $("#an-refresh").onclick = loadAnalytics;
  $$("#an .recent select").forEach((sel) => (sel.onchange = async () => {
    const id = sel.closest("tr").dataset.id;
    const r = await api(`/api/jobs/${id}/status`, { method: "POST", body: { status: sel.value } });
    const j = JOBS.find((x) => x.id === id); if (j) Object.assign(j, r);
    toast(`Stage → ${sel.value}`);
    loadAnalytics();
  }));
}

// One tooltip for every chart mark with data-tip.
document.addEventListener("mousemove", (e) => {
  const t = e.target.closest?.("[data-tip]"), tip = $("#viz-tip");
  if (!t || !t.closest("#an")) { tip.classList.remove("show"); return; }
  tip.textContent = t.dataset.tip;
  tip.classList.add("show");
  const x = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8), y = e.clientY - tip.offsetHeight - 12;
  tip.style.left = `${x}px`; tip.style.top = `${y < 8 ? e.clientY + 18 : y}px`;
});

// ------------------------------------------------------------------ QUICK-COPY BAR
// Slides up from the bottom once you scroll; one click copies a link or saved answer. Everything autosaves.
let PROFILE = { links: [], snippets: [], notes: "" }, QPIN = false;
try { QPIN = localStorage.getItem("qpin") === "1"; } catch {}

async function loadProfile() {
  PROFILE = await api("/api/profile");
  renderQbar();
  $("#q-notes").value = PROFILE.notes || "";
}
let qTimer;
function saveProfile() {
  clearTimeout(qTimer);
  $("#q-saved").textContent = "saving…";
  qTimer = setTimeout(async () => {
    await api("/api/profile", { method: "POST", body: PROFILE });
    $("#q-saved").textContent = "saved";
    renderChips();
  }, 700);
}
function copy(text, what) {
  if (!text) return toast(`Add your ${what} first (Notes & edit ▴)`);
  navigator.clipboard.writeText(text);
  toast(`Copied ${what}`);
}
function renderChips() {
  const links = PROFILE.links.filter((l) => l.value), snips = PROFILE.snippets.filter((x) => x.value);
  $("#q-chips").innerHTML = (links.length || snips.length)
    ? links.map((l, i) => `<button class="qchip" data-l="${PROFILE.links.indexOf(l)}" title="${esc(l.value)}"><b>${esc(l.label)}</b> ${esc(l.value.replace(/^https?:\/\/(www\.)?/, "").slice(0, 34))}</button>`).join("")
      + snips.map((x) => `<button class="qchip snip" data-s="${PROFILE.snippets.indexOf(x)}" title="${esc(x.value.slice(0, 200))}">📝 ${esc(x.label)}</button>`).join("")
    : `<span class="muted">Add your LinkedIn, GitHub and saved answers → click “Notes &amp; edit”</span>`;
  $$("#q-chips [data-l]").forEach((b) => (b.onclick = () => copy(PROFILE.links[b.dataset.l].value, PROFILE.links[b.dataset.l].label)));
  $$("#q-chips [data-s]").forEach((b) => (b.onclick = () => copy(PROFILE.snippets[b.dataset.s].value, `"${PROFILE.snippets[b.dataset.s].label}"`)));
}
function renderQbar() {
  const row = (kind, x, i, big) => `<div class="qrow">
      <input class="ql" value="${esc(x.label)}" data-k="${kind}" data-i="${i}" data-f="label" placeholder="Label">
      ${big ? `<textarea rows="2" data-k="${kind}" data-i="${i}" data-f="value" placeholder="Your answer">${esc(x.value)}</textarea>`
            : `<input value="${esc(x.value)}" data-k="${kind}" data-i="${i}" data-f="value" placeholder="https://…">`}
      <button class="qcopy" data-copy="${kind}:${i}" title="Copy">⧉</button><button class="qdel" data-del="${kind}:${i}" title="Remove">×</button></div>`;
  $("#q-links").innerHTML = PROFILE.links.map((x, i) => row("links", x, i, false)).join("");
  $("#q-snips").innerHTML = PROFILE.snippets.map((x, i) => row("snippets", x, i, true)).join("");
  renderChips();
}
$("#qpanel").addEventListener("input", (e) => {
  const t = e.target;
  if (t.id === "q-notes") PROFILE.notes = t.value;
  else if (t.dataset.k) PROFILE[t.dataset.k][t.dataset.i][t.dataset.f] = t.value;
  else return;
  saveProfile();
});
$("#qpanel").addEventListener("click", (e) => {
  const c = e.target.dataset.copy, d = e.target.dataset.del;
  if (c) { const [k, i] = c.split(":"); copy(PROFILE[k][i].value, PROFILE[k][i].label); }
  if (d) { const [k, i] = d.split(":"); PROFILE[k].splice(+i, 1); renderQbar(); saveProfile(); }
});
$("#q-add-link").onclick = () => { PROFILE.links.push({ label: "", value: "" }); renderQbar(); $$("#q-links .ql").at(-1).focus(); };
$("#q-add-snip").onclick = () => { PROFILE.snippets.push({ label: "", value: "" }); renderQbar(); $$("#q-snips .ql").at(-1).focus(); };

function showQbar(on) { $("#qbar").classList.toggle("up", on); $("#q-fab").classList.toggle("hidden", on); }
function openPanel(on) {
  $("#qpanel").classList.toggle("hidden", !on);
  $("#q-toggle").innerHTML = on ? "Close ▾" : "Notes &amp; edit ▴";
  if (on) showQbar(true);
}
window.addEventListener("scroll", () => {
  if (QPIN || !$("#qpanel").classList.contains("hidden")) return;
  showQbar(window.scrollY > 120);
}, { passive: true });
$("#q-toggle").onclick = () => openPanel($("#qpanel").classList.contains("hidden"));
$("#q-fab").onclick = () => { showQbar(true); };
$("#q-pin").onclick = () => {
  QPIN = !QPIN;
  try { localStorage.setItem("qpin", QPIN ? "1" : "0"); } catch {}
  $("#q-pin").classList.toggle("on", QPIN);
  toast(QPIN ? "Bar pinned: always visible" : "Bar unpinned: shows when you scroll");
  if (!QPIN) showQbar(window.scrollY > 120);
};
$("#q-pin").classList.toggle("on", QPIN);
showQbar(QPIN);

// ------------------------------------------------------------------ boot
(async () => {
  await loadStatus();
  try { FIN_SEGMENTS = Object.entries((await api("/api/finance")).segments); } catch {}
  loadJobs();
  loadUnis();
  pollRefresh();
  loadProfile();
  if (location.hash) showTab(location.hash.slice(1));
})();
