// Job Portal · built by JAI SHARMA
// Home page: the split-flap board of newest jobs, live totals, the laptop tour, gentle reveals.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
const fmt = (n) => Number(n || 0).toLocaleString("en-US");

// ------------------------------------------------------------------ the board
const ROWS = 8;
const CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
// Column widths in characters, by board width (desktop / tablet / phone).
const LAYOUTS = [
  { min: 940, cols: [["Found", "found", 6], ["Employer", "company", 14], ["Role", "title", 24], ["City", "city", 12], ["Remarks", "remark", 9]] },
  { min: 620, cols: [["Found", "found", 6], ["Employer", "company", 12], ["Role", "title", 18], ["Remarks", "remark", 9]] },
  { min: 0, compact: true, cols: [["Found", "found", 4], ["Employer", "company", 10], ["Role", "title", 13]] },
];
let JOBS = [], PAGE = 0, LAYOUT = null, TIMER = null, VISIBLE = true;

const plain = (s) => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase().replace(/[^A-Z0-9 &.,'/+\-:#]/g, " ").replace(/\s+/g, " ").trim();
function city(loc) {
  const parts = (loc || "").split(/[,;·|]/).map((p) => p.trim()).filter(Boolean);
  const good = parts.find((p) => /[A-Za-z]{3}/.test(p) && !/^(R|REQ|JR)?[-\s]?\d/i.test(p) && !/^(united states|usa|us)( of america)?$/i.test(p) && !/^\d/.test(p));
  if (good) return good.replace(/\b(hybrid|on-?site)\b/ig, "").trim();
  return parts.some((p) => /united states|usa/i.test(p)) ? "USA" : (parts[0] || "");
}
function found(ts, compact = false) {  // compact (phones): 16M · 3H · 2D
  const m = Math.max(1, Math.round((Date.now() / 1000 - ts) / 60)), h = Math.round(m / 60);
  if (m < 60) return compact ? `${m}M` : `${m} MIN`;
  return h < 48 ? (compact ? `${h}H` : `${h} HR`) : (compact ? `${Math.round(h / 24)}D` : `${Math.round(h / 24)} DAY`);
}
function remark(j) {
  if (j.immediate) return ["START NOW", "r-sign"];
  if (j.sponsor) return ["H-1B", "r-go"];
  return [{ internship: "INTERN", early_career: "ENTRY", experienced: "3+ YRS" }[j.level] || "", ""];
}
const fit = (s, n) => (s.length > n ? s.slice(0, n) : s.padEnd(n, " "));

function pickLayout() {
  const w = $("#board").clientWidth;
  return LAYOUTS.find((l) => w >= l.min);
}
function size() {
  const board = $("#board"), lay = pickLayout();
  const chars = lay.cols.reduce((a, c) => a + c[2], 0), gaps = lay.cols.length - 1;
  const inner = board.clientWidth - parseFloat(getComputedStyle(board).paddingLeft) * 2 - 4;
  // each character is a tile plus 2px, each column gap is one tile wide
  const tile = Math.max(8, Math.min(22, (inner - chars * 2) / (chars + gaps)));
  board.style.setProperty("--tile", tile.toFixed(2) + "px");
  if (lay !== LAYOUT) { LAYOUT = lay; build(); }
}
function build() {
  $("#board-cols").innerHTML = LAYOUT.cols.map(([label, , n]) => `<span style="width:calc(${n} * (var(--tile) + 2px) - 2px)">${label}</span>`).join("");
  $("#board-rows").innerHTML = Array.from({ length: ROWS }, () =>
    `<a class="board-row" href="/jobs">${LAYOUT.cols.map(([, , n]) => `<span class="cell">${"<span class=\"tile\"> </span>".repeat(n)}</span>`).join("")}</a>`).join("");
  show(false);
}
function rowText(j) {
  const [r, cls] = remark(j);
  const v = { found: found(j.found, LAYOUT.compact), company: plain(j.company), title: plain(j.title), city: plain(city(j.location)), remark: r };
  return LAYOUT.cols.map(([, key, n]) => ({ text: fit(v[key] || "", n), cls: key === "remark" ? cls : "" }));
}
// Flip one tile through a few random letters, then land on its character.
function flipTo(tile, ch, delay) {
  if (calm || tile.textContent === ch) { tile.textContent = ch; return; }
  const spins = 2 + Math.floor(Math.random() * 4);
  for (let i = 0; i <= spins; i++) {
    setTimeout(() => {
      tile.textContent = i === spins ? ch : CHARS[Math.floor(Math.random() * CHARS.length)];
      tile.classList.remove("flip"); void tile.offsetWidth; tile.classList.add("flip");
    }, delay + i * 70);
  }
}
function show(animate = true) {
  if (!JOBS.length || !LAYOUT) return;
  const pages = Math.max(1, Math.ceil(JOBS.length / ROWS));
  const slice = JOBS.slice(PAGE * ROWS, PAGE * ROWS + ROWS);
  $("#board-page").textContent = `${PAGE + 1}/${pages}`;
  $$("#board-rows .board-row").forEach((row, r) => {
    const j = slice[r];
    const cells = j ? rowText(j) : LAYOUT.cols.map(([, , n]) => ({ text: " ".repeat(n), cls: "" }));
    $$(".cell", row).forEach((cell, c) => {
      cell.className = `cell ${cells[c].cls}`;
      $$(".tile", cell).forEach((t, i) => flipTo(t, cells[c].text[i] || " ", animate ? r * 110 + c * 40 + i * 12 : 0));
    });
  });
  $("#board-list").innerHTML = slice.map((j) => `<li>${esc(j.company)}: ${esc(j.title)}, ${esc(city(j.location))}, found ${found(j.found).toLowerCase()} ago</li>`).join("");
}
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function tick() {
  const now = new Date();
  $("#board-clock").textContent = now.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "America/New_York" }) + " ET";
}
function cycle() {
  clearInterval(TIMER);
  if (calm) return;
  TIMER = setInterval(() => {
    if (!VISIBLE || document.hidden) return;
    PAGE = (PAGE + 1) % Math.max(1, Math.ceil(JOBS.length / ROWS));
    show(true);
  }, 9000);
}

async function loadBoard() {
  try {
    const r = await fetch("/api/public/board");
    const d = await r.json();
    JOBS = d.jobs || [];
    stats(d.stats || {});
    size();
    show(true);
    cycle();
  } catch { /* the page still works without the board */ }
}
function stats(s) {
  const set = (k, v) => $$(`[data-stat="${k}"]`).forEach((el) => (el.textContent = v));
  if (s.total) set("total", fmt(s.total));
  if (s.companies) set("companies", fmt(s.companies));
  if (s.career_sites) set("career_sites", fmt(s.career_sites));
  if (s.github_lists) set("github_lists", fmt(s.github_lists));
  for (const [reg, n] of Object.entries(s.jobs || {})) $$(`[data-region="${reg}"]`).forEach((el) => (el.textContent = fmt(n)));
  if (s.last_fetch) {
    const m = Math.max(1, Math.round((Date.now() / 1000 - s.last_fetch) / 60));
    $("#fresh").textContent = m < 90 ? `Last checked ${m} minute${m === 1 ? "" : "s"} ago` : "Checked every 10 minutes";
  }
}

new IntersectionObserver(([e]) => (VISIBLE = e.isIntersecting), { threshold: 0.1 }).observe($("#board"));
let RZ = null;
addEventListener("resize", () => { clearTimeout(RZ); RZ = setTimeout(size, 120); });
tick();
setInterval(tick, 20000);
size();
loadBoard();

// ------------------------------------------------------------------ reveal sections as they scroll in
const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }), { threshold: 0.12 });
$$(".reveal").forEach((el) => io.observe(el));
