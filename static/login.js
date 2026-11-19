// Job Portal · built by JAI SHARMA
// Sign in and Create account: one page, two modes (the address says which: /login or /signup).
// Google sign-in appears when the server has it switched on.
const $ = (id) => document.getElementById(id);
const MODES = {
  signin: {
    path: "/login", doc: "Sign in", title: "Welcome back",
    lede: "Sign in to see apply links, H-1B data and your applications.",
    google: "Continue with Google", or: "or with your email", email: "Email or username", go: "Sign in",
    switchText: "New here? ", switchLink: "Create a free account", switchHref: "/signup",
    side: "Jobs from the source, minutes after they're posted.", kicker: "New postings",
  },
  signup: {
    path: "/signup", doc: "Create account", title: "Create your free account",
    lede: "One click with Google, or an email and a password. No card, no ads.",
    google: "Sign up with Google", or: "or sign up with your email", email: "Email", go: "Create free account",
    switchText: "Already have an account? ", switchLink: "Sign in", switchHref: "/login",
    side: "Everything a guest sees, plus the parts that get you hired.", kicker: "Free account",
  },
};
const ERRORS = {
  google_off: "Google sign-in isn't switched on yet. Use your email for now.",
  cancelled: "Google sign-in was cancelled.",
  expired: "That sign-in took too long or started in another tab. Try again.",
  google_down: "Couldn't reach Google. Try again in a minute.",
  google_refused: "Google didn't confirm the sign-in. Try again.",
  unverified: "That Google account's email address isn't verified with Google.",
  off: "This account is turned off. Ask the site owner.",
  closed: "New accounts are closed right now. Sign in if you already have one.",
  too_many: "Too many new accounts from here in the last hour. Try again later.",
};
let mode = location.pathname.startsWith("/signup") || location.hash === "#signup" ? "signup" : "signin";
let OPTIONS = { google: false, signup: true };

function render() {
  const m = MODES[mode], up = mode === "signup";
  document.title = `${m.doc} · SharmaJai Job Portal`;
  $("tab-in").setAttribute("aria-selected", String(!up));
  $("tab-up").setAttribute("aria-selected", String(up));
  $("title").textContent = m.title;
  $("lede").textContent = m.lede;
  $("google").href = `/auth/google?mode=${mode}`;
  $("google-label").textContent = m.google;
  $("or-label").textContent = m.or;
  $("email-label").textContent = m.email;
  const email = $("email"), pass = $("password");
  email.type = up ? "email" : "text";
  email.autocomplete = up ? "email" : "username";
  pass.autocomplete = up ? "new-password" : "current-password";
  $("pw-hint").hidden = !up;
  $("go-label").textContent = m.go;
  $("switch").firstChild.textContent = m.switchText;
  $("switch-link").textContent = m.switchLink;
  $("switch-link").href = m.switchHref;
  $("forgot").hidden = up;
  $("side-title").textContent = m.side;
  $("side-fresh").textContent = m.kicker;
  $("perks").hidden = !up;
  $("feed").hidden = up;
  const closed = up && !OPTIONS.signup;
  $("form").hidden = closed;
  $("google-wrap").hidden = !OPTIONS.google || closed;
  if (closed) say(ERRORS.closed);
}
function go(next, push = true) {
  if (next === mode) return;
  mode = next;
  say("");
  if (push) history.pushState(null, "", MODES[mode].path);
  render();
  $("email").focus();
}
function say(text) { $("msg").textContent = text; $("msg").classList.toggle("on", !!text); }

$("tab-in").addEventListener("click", (e) => { e.preventDefault(); go("signin"); });
$("tab-up").addEventListener("click", (e) => { e.preventDefault(); go("signup"); });
$("switch-link").addEventListener("click", (e) => { e.preventDefault(); go(mode === "signup" ? "signin" : "signup"); });
addEventListener("popstate", () => go(location.pathname.startsWith("/signup") ? "signup" : "signin", false));
$("pw-show").addEventListener("click", () => {
  const p = $("password"), show = p.type === "password";
  p.type = show ? "text" : "password";
  $("pw-show").textContent = show ? "Hide" : "Show";
  $("pw-show").setAttribute("aria-pressed", String(show));
  p.focus();
});

const looksLikeEmail = (v) => /^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/.test(v);
$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const up = mode === "signup", email = $("email").value.trim(), password = $("password").value;
  if (!email) { say(up ? "Type your email." : "Type your email or username."); return $("email").focus(); }
  if (up && !looksLikeEmail(email)) { say("That email doesn't look right."); return $("email").focus(); }
  if (!password) { say(up ? "Choose a password." : "Type your password."); return $("password").focus(); }
  if (up && password.length < 8) { say("Use at least 8 characters for the password."); return $("password").focus(); }
  say("");
  $("go").disabled = true;
  try {
    const r = await fetch(up ? "/api/signup" : "/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Portal": "1" },
      body: JSON.stringify(up ? { email, password, website: $("website").value } : { username: email, password }),
    });
    if (r.ok) { location.href = "/"; return; }
    $("password").value = "";
    say((await r.json().catch(() => ({}))).detail || (up ? "Couldn't create the account." : "Sign-in failed."));
  } catch { say("Can't reach the portal. Check your connection."); }
  $("go").disabled = false;
});

// Google on or off, sign-ups open or closed; an error sent back from the Google step
fetch("/api/auth/options").then((r) => r.json()).then((o) => { OPTIONS = o; render(); }).catch(() => {});
const err = new URLSearchParams(location.search).get("error");
render();
if (err) { say(ERRORS[err] || "Sign-in didn't work. Try again."); history.replaceState(null, "", MODES[mode].path); }

// the side panel: the newest jobs, from the same feed as the home page's board
fetch("/api/public/board").then((r) => r.json()).then(({ jobs = [], stats = {} }) => {
  const ago = (ts) => { const m = Math.max(1, Math.round((Date.now() / 1000 - ts) / 60)); return m < 60 ? `${m}m` : m < 2880 ? `${Math.round(m / 60)}h` : `${Math.round(m / 1440)}d`; };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  $("feed").innerHTML = jobs.slice(0, 6).map((j) => `<li><span class="t">${ago(j.found)}</span><span class="c">${esc(j.company)}</span>
    <span class="r">${esc(j.title)}</span>${j.sponsor ? '<span class="h">H-1B</span>' : j.immediate ? '<span class="s">Start now</span>' : ""}</li>`).join("");
  if (stats.career_sites) document.querySelectorAll("[data-stat=career_sites]").forEach((e) => (e.textContent = stats.career_sites.toLocaleString("en-US")));
  if (stats.github_lists) document.querySelectorAll("[data-stat=github_lists]").forEach((e) => (e.textContent = stats.github_lists));
}).catch(() => {});
