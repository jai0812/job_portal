# ===== JAI SHARMA watermark =====
#   ,,,,,,,    ,,,    ,,,,,,         ,,,,,   ,,   ,,    ,,,    ,,,,,,   ,,   ,,    ,,,
#       ,,    ,, ,,     ,,          ,,   ,,  ,,   ,,   ,, ,,   ,,   ,,  ,,, ,,,   ,, ,,
#       ,,   ,,   ,,    ,,          ,,       ,,   ,,  ,,   ,,  ,,   ,,  ,,,,,,,  ,,   ,,
#       ,,   ,,   ,,    ,,           ,,,,,   ,,,,,,,  ,,   ,,  ,,,,,,   ,, , ,,  ,,   ,,
#       ,,   ,,,,,,,    ,,               ,,  ,,   ,,  ,,,,,,,  ,, ,,    ,,   ,,  ,,,,,,,
#   ,,  ,,   ,,   ,,    ,,          ,,   ,,  ,,   ,,  ,,   ,,  ,,  ,,   ,,   ,,  ,,   ,,
#    ,,,,    ,,   ,,  ,,,,,,         ,,,,,   ,,   ,,  ,,   ,,  ,,   ,,  ,,   ,,  ,,   ,,
#
#                                                    J       A
#                       IS                           HA     RM
#                     AJAISH                         ARMAJAISHAR
#                   MAJAISHARM                      AJAI00SHARMAJAI
#                 SHARMAJAISHARM                   AJAISHARMAJAISHARMAJ
#               AISHARMAJAISHARMAJ                AISHARMAJAISHARMAJAISHAR
#             MAJAISHARMAJAISHARMAJA             ISHARMAJAISHARMA  JA  IS H
#           ARMAJAISHARMAJAISHARMAJAIS          HARMAJAISHAR   MA  JA
#         ISHARMAJAISHARMAJAISHARMAJAISH       ARMAJAISHAR
#             MAJAISHARMAJAISHARMAJAISHARM    AJAISHARMA
#    J           AISHARMAJAISHARMAJAISHARMAJAISHARM
#    AJ        AISHARMAJAISHARMAJAISHARMAJAISHARMA
#    JAI     SHARMAJAISHARMAJAISHARMAJAISHARMAJA
#     ISHA  RMAJAISHARMAJAISHARMAJAISHARMAJAISH
#      ARMAJAISHARMAJAISHARMAJAISHARMAJAISHAR
#        MAJAISHARMAJAISHARMAJAISHARMAJAISH
#           ARMAJAISHAR  MAJAISHA   RMAJAISH
#                        ARMAJ      AISHA
#                        RMAJAI     SHARMA
#                       JAI SHAR   MAJ AISH
#
#               ~ built by JAI SHARMA ~
# ==============================
"""Job Portal: jobs dashboard, analytics and multi-LLM chat. Run with ./run.sh"""
import gzip
import json
import re
import threading
import time

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import alerts, auth, classify, db, finance, geo, h1b, llm, patterns, readme, refresh
from .config import DATA_DIR, ROOT, env, load_more_companies, load_sources, load_universities, save_sources

app = FastAPI(title="Job Portal", docs_url=None, redoc_url=None, openapi_url=None)
db.init()

# ---------------------------------------------------------------- security

LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
if env("PORTAL_HOST", "127.0.0.1") not in LOCAL_HOSTS and not auth.enabled():
    raise SystemExit("Refusing to start: PORTAL_HOST makes the portal reachable from other computers, but no password "
                     "is set. Run  .venv/bin/python scripts/set_password.py  first.")
if auth.enabled() and len(env("SESSION_SECRET")) < 32:
    raise SystemExit("A password is set but SESSION_SECRET is missing. Run scripts/set_password.py again.")


def me(request: Request) -> dict:
    return request.state.user

OPEN_PATHS = {"/login", "/login.html", "/login.js", "/style.css", "/logo-mark.svg", "/login-bg.gif", "/api/login", "/favicon.ico"}
HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                               "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
    "Cache-Control": "no-store",
}


def _client_ip(request: Request) -> str:
    if env("TRUST_PROXY") == "1":  # behind Caddy / Cloudflare / a hosting platform's proxy
        forwarded = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else "?"


def _is_https(request: Request) -> bool:
    return request.url.scheme == "https" or (env("TRUST_PROXY") == "1" and request.headers.get("x-forwarded-proto") == "https")


# Only the admin may use these (everyone else gets the job tabs and their own Analytics). Checked on the server,
# not just hidden in the page.
ADMIN_PATHS = ("/api/alerts", "/api/sources", "/api/ask", "/api/apify", "/api/users", "/api/handshake")
ADMIN_WRITES = {"/api/refresh", "/api/jobs"}


def _admin_only(method: str, path: str) -> bool:
    return path.startswith(ADMIN_PATHS) or (method == "POST" and path in ADMIN_WRITES)


@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path
    if auth.enabled():
        user = auth.session_user(request.cookies.get(auth.COOKIE, ""))
        request.state.user = user
        if path not in OPEN_PATHS and not user:
            response = (JSONResponse({"detail": "Please sign in"}, status_code=401) if path.startswith("/api/")
                        else RedirectResponse("/login", status_code=303))
        elif user and user["role"] != "admin" and _admin_only(request.method, path):
            response = JSONResponse({"detail": "Only the admin can do that."}, status_code=403)
        elif request.method not in ("GET", "HEAD", "OPTIONS") and not _same_site(request):
            response = JSONResponse({"detail": "Request blocked (cross-site)"}, status_code=403)
        else:
            response = await call_next(request)
    else:  # local use on your own Mac, no password set: you're the admin
        request.state.user = db.admin_user()
        response = await call_next(request)
    if path == "/login-bg.gif" and response.status_code == 200:  # 2.5 MB picture: download it once, not every visit
        response.headers["Cache-Control"] = "public, max-age=604800"
    for k, v in HEADERS.items():
        response.headers.setdefault(k, v)
    if _is_https(request):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def _same_site(request: Request) -> bool:
    """State-changing requests must come from the portal's own pages: a custom header browsers won't add
    cross-site, plus a matching Origin when the browser sends one."""
    if request.headers.get("x-portal") != "1":
        return False
    origin = request.headers.get("origin")
    return not origin or origin.split("://", 1)[-1] == request.headers.get("host", "")


@app.get("/login")
def login_page():
    return RedirectResponse("/login.html" if auth.enabled() else "/", status_code=303)


@app.post("/api/login")
def login(request: Request, body: dict = Body(...)):
    if not auth.enabled():
        return {"ok": True}
    ip = _client_ip(request)
    wait = auth.locked_for(ip)
    if wait:
        raise HTTPException(429, f"Too many wrong attempts. Try again in {wait // 60 + 1} minutes.")
    username = str(body.get("username", "")).strip()[:64]
    account = "user:" + username.lower()
    wait = max(wait, auth.locked_for(account))
    if wait:
        raise HTTPException(429, f"Too many wrong attempts. Try again in {wait // 60 + 1} minutes.")
    time.sleep(0.4)  # every attempt costs time, right or wrong
    user = auth.check_login(username, str(body.get("password", ""))[:256])
    if not user:
        auth.record_failure(ip, account)
        raise HTTPException(401, "Wrong username or password.")
    auth.record_success(ip, account)
    db.update_user(user["id"], last_login=int(time.time()))
    response = JSONResponse({"ok": True})
    response.set_cookie(auth.COOKIE, auth.new_session(db.all_users()[user["id"]]), max_age=auth.SESSION_HOURS * 3600,
                        httponly=True, samesite="strict", secure=_is_https(request), path="/")
    return response


# ---------------------------------------------------------------- accounts (admin creates them; nobody signs up)

def _user_row(u: dict, stats: dict) -> dict:
    s = stats.get(u["id"], {})
    return {"id": u["id"], "username": u["username"], "email": u.get("email") or "", "role": u["role"], "active": bool(u["active"]),
            "created_at": u["created_at"], "last_login": u["last_login"], "applied": s.get("applied") or 0,
            "last_active": s.get("last_active")}


@app.get("/api/users")
def list_users():
    stats = db.user_stats()
    return sorted((_user_row(u, stats) for u in db.all_users().values()), key=lambda u: (u["role"] != "admin", u["id"]))


@app.post("/api/users")
def create_user(body: dict = Body(...)):
    username, password = str(body.get("username", "")).strip(), str(body.get("password", ""))
    email = str(body.get("email", "")).strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,32}", username):
        raise HTTPException(400, "Username: 3–32 letters, numbers, dots, dashes or underscores.")
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(400, "That email doesn't look right.")
    if db.user_by_name(username) or (email and db.user_by_name(email)):
        raise HTTPException(400, "That username or email is taken.")
    if problem := auth.password_problem(password):
        raise HTTPException(400, problem)
    db.create_user(username, auth.hash_password(password), email=email)
    return list_users()


@app.post("/api/users/{user_id}")
def change_user(user_id: int, request: Request, body: dict = Body(...)):
    """Reset a password and/or turn an account on or off (both sign that person out everywhere)."""
    u = db.all_users().get(user_id)
    if not u:
        raise HTTPException(404, "No such user.")
    fields = {}
    if body.get("password"):
        if problem := auth.password_problem(str(body["password"])):
            raise HTTPException(400, problem)
        fields["pw_hash"] = auth.hash_password(str(body["password"]))
    if "active" in body:
        if u["id"] == me(request)["id"] and not body["active"]:
            raise HTTPException(400, "You can't turn off your own account.")
        fields["active"] = int(bool(body["active"]))
    db.update_user(user_id, **fields)
    return list_users()


@app.delete("/api/users/{user_id}")
def remove_user(user_id: int, request: Request):
    u = db.all_users().get(user_id)
    if not u or u["role"] == "admin":
        raise HTTPException(400, "The admin account can't be deleted.")
    db.delete_user(user_id)
    return list_users()


@app.post("/api/me/password")
def change_my_password(request: Request, body: dict = Body(...)):
    """Anyone can change their own password (they need the current one)."""
    user = me(request)
    if not auth.verify(user["pw_hash"], str(body.get("current", ""))):
        raise HTTPException(400, "Your current password is wrong.")
    if problem := auth.password_problem(str(body.get("new", ""))):
        raise HTTPException(400, problem)
    db.update_user(user["id"], pw_hash=auth.hash_password(str(body["new"])))
    response = JSONResponse({"ok": True})  # the old session is now invalid: hand out a fresh one
    response.set_cookie(auth.COOKIE, auth.new_session(db.all_users()[user["id"]]), max_age=auth.SESSION_HOURS * 3600,
                        httponly=True, samesite="strict", secure=_is_https(request), path="/")
    return response


@app.post("/api/logout")
def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(auth.COOKIE, path="/")
    return response

# ---------------------------------------------------------------- refresh

_refresh = {"running": False, "started": None, "results": []}


def _do_refresh(include_apify: bool):
    _refresh.update(running=True, started=int(time.time()), results=[])
    try:
        # a job new to this refresh wasn't there when the fast lane last checked the top companies
        _refresh["results"] = refresh.run(include_apify=include_apify,
                                          on_new=lambda jobs: alerts.on_new(jobs, since=_fast.get("started")))
        rebuild_jobs()
        try:  # keep the README's live snapshot current (and push it to GitHub when that's set up)
            readme.update()
            _refresh["readme"] = readme.push_if_due()
        except Exception as e:
            _refresh["readme"] = f"error: {e}"[:200]
    finally:
        _refresh["running"] = False


def _auto_refresh_loop():
    while env("PORTAL_NO_REFRESH") != "1":
        minutes = int(load_sources().get("auto_refresh_minutes") or 0)
        newest = max((l["last_run"] or 0 for l in db.fetch_log()), default=0)
        due = time.time() - newest >= minutes * 60 - 120  # skip when a refresh finished recently (e.g. after a restart)
        if minutes > 0 and due and not _refresh["running"]:
            _do_refresh(False)
        time.sleep(max(min(minutes, 10), 5) * 60)


def _self_check_loop():
    """If macOS takes away this process's access to its own files (it happened once after the process ran for
    days), pages come out empty. Exit instead, so the Desktop app or the watchdog starts a healthy copy."""
    import os
    probe = ROOT / "static" / "login.html"
    while True:
        time.sleep(300)
        try:
            ok = len(probe.read_bytes()) > 100
        except Exception:
            ok = False
        if not ok:
            print("SELF-CHECK FAILED: can't read the portal's own files any more; exiting so it can be restarted.", flush=True)
            os._exit(3)


_fast = {"last": 0, "started": None, "results": []}


def _fast_lane_loop():
    """Every few minutes, re-check the top companies' own career sites so new postings (and alerts) arrive fast."""
    time.sleep(90)
    while env("PORTAL_NO_REFRESH") != "1":
        cfg = load_sources()
        minutes = int(cfg.get("fast_lane_minutes") or 0)
        names = cfg.get("fast_lane") or []
        started = time.time()
        if minutes > 0 and names and not _refresh["running"]:
            try:
                prev = _fast.get("started")  # what this run finds wasn't there when the previous run looked
                _fast["results"] = refresh.run_fast(names, on_new=lambda jobs: alerts.on_new(jobs, since=prev))
                _fast["started"], _fast["last"] = started, int(time.time())
                if any(r["new"] for r in _fast["results"]):
                    rebuild_jobs()
            except Exception as e:
                _fast["results"] = [{"source": "fast lane", "error": str(e)[:200]}]
        time.sleep(max(max(minutes, 5) * 60 - (time.time() - started), 60))  # every N minutes from start to start


def _alerts_loop():
    while True:
        try:
            alerts.tick()
        except Exception:
            pass
        time.sleep(240)


@app.on_event("startup")
def _startup():
    try:
        gz = {r: (DATA_DIR / f"jobs_cache_{r}.json.gz").read_bytes() for r in REGIONS}
        _jobs.update(gz=gz, built=int((DATA_DIR / "jobs_cache_us.json.gz").stat().st_mtime))
    except OSError:
        pass
    rebuild_jobs()
    threading.Thread(target=_auto_refresh_loop, daemon=True).start()
    threading.Thread(target=_self_check_loop, daemon=True).start()
    threading.Thread(target=_fast_lane_loop, daemon=True).start()
    threading.Thread(target=_alerts_loop, daemon=True).start()


@app.post("/api/refresh")
def start_refresh(body: dict = Body(default={})):
    if _refresh["running"]:
        return {"started": False, "reason": "already running"}
    threading.Thread(target=_do_refresh, args=(bool(body.get("apify")),), daemon=True).start()
    return {"started": True}


@app.get("/api/refresh")
def refresh_status():
    return {**_refresh, "log": db.fetch_log(), "fast_lane": _fast, "jobs_built": _jobs["built"]}


@app.get("/api/apify")
def apify_usage():
    from .fetchers import apify
    try:
        return apify.usage()
    except Exception as e:
        return {"configured": True, "error": str(e)[:200]}


@app.get("/api/patterns")
def posting_patterns():
    return {"timezone": "ET", "patterns": patterns.all_patterns()}


@app.get("/api/alerts")
def get_alerts():
    cfg = alerts.load()
    src = load_sources()
    shown = {**cfg, "telegram_token": ("•••• saved" if cfg.get("telegram_token") else "")}  # never send the token back
    return {"settings": shown, "history": alerts.history(), "fast_lane": src.get("fast_lane") or [],
            "fast_lane_minutes": src.get("fast_lane_minutes", 0), "fast_last": _fast["last"],
            "watch_default": [p["company"] for p in alerts._watchlist({**cfg, "watch": []})]}


@app.post("/api/alerts")
def save_alerts(body: dict = Body(...)):
    current = alerts.load()
    cfg = {**current, **{k: v for k, v in body.items() if k in alerts.DEFAULTS}}
    if cfg.get("telegram_token", "").startswith("••••"):  # unchanged placeholder from the page
        cfg["telegram_token"] = current.get("telegram_token", "")
    if cfg["telegram_token"] != current.get("telegram_token"):
        cfg["telegram_chat_id"] = ""  # new bot: connect again
    if not str(cfg["topic"]).strip() or len(str(cfg["topic"])) < 12:
        raise HTTPException(400, "Use a topic name of at least 12 characters (it works like a password).")
    saved = alerts.save(cfg)
    return {**saved, "telegram_token": "•••• saved" if saved.get("telegram_token") else ""}


@app.post("/api/alerts/telegram")
def connect_telegram():
    try:
        return alerts.telegram_connect()
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/alerts/test")
def test_alert():
    r = alerts.send("✅ SharmaJai Job Portal alerts work", "This is a test. New-job alerts, posting-window heads-ups and "
                    "your morning summary will arrive here.", click=alerts.load()["portal_url"], tags=["white_check_mark"], force=True)
    if not r.get("sent"):
        raise HTTPException(502, f"Couldn't send: {r.get('detail')}")
    return r


# ---------------------------------------------------------------- status & sources

@app.get("/api/status")
def status(request: Request):
    cfg = load_sources()
    user = me(request)
    return {
        "auth": auth.enabled(),
        "me": {"username": user["username"], "role": user["role"]},
        "llms": llm.status(),
        "apify": bool(env("APIFY_TOKEN")),
        "sources": cfg.get("github") or [],
        "apify_searches": (cfg.get("apify") or {}).get("searches") or [],
        "max_age_days": cfg.get("max_age_days", 45),
        "jobright_url": cfg.get("jobright_url", "https://jobright.ai/jobs"),
        "log": db.fetch_log(),
    }


@app.post("/api/sources/github")
def add_source(body: dict = Body(...)):
    from .fetchers.github import parse_repo
    url = body.get("url", "").strip()
    owner, repo, _ = parse_repo(url)  # validates
    cfg = load_sources()
    cfg.setdefault("github", [])
    if any(s["url"].rstrip("/") == url.rstrip("/") for s in cfg["github"]):
        raise HTTPException(400, "Source already added")
    cfg["github"].append({"name": body.get("name") or f"{owner}/{repo}", "url": url,
                          "level": body.get("level") or "early_career"})
    save_sources(cfg)
    return cfg["github"]


@app.delete("/api/sources/github")
def remove_source(url: str):
    cfg = load_sources()
    cfg["github"] = [s for s in cfg.get("github") or [] if s["url"] != url]
    save_sources(cfg)
    return cfg["github"]


# ---------------------------------------------------------------- jobs

def _university_matchers() -> list[tuple[str, re.Pattern]]:
    return [(u["short"], re.compile(r"\b(" + "|".join(re.escape(m) for m in u.get("match") or [u["name"]]) + r")\b"))
            for u in load_universities()]


def _uscis_counts() -> dict[str, int]:
    """FY2023 approvals for companies in more_companies.yaml whose legal name differs from their everyday name."""
    return {c["name"].lower(): h1b.approvals_for_names(c["uscis"]) for c in load_more_companies() if c.get("uscis")}


def _enrich(rows: list[dict]) -> list[dict]:
    unis = _university_matchers()
    legal = _uscis_counts()
    by_company, by_location = {}, {}  # ~130k jobs but only a few thousand companies and places: work each out once

    def company_info(company: str):
        if company not in by_company:
            firm = finance.firm_for(company)
            by_company[company] = (
                next((short for short, rx in unis if rx.search(company)), None),
                firm and {k: firm[k] for k in ("name", "segment", "segment_label")},
                # USCIS FY2023 H-1B approvals: exact entity list for known finance firms, name match for everyone else
                firm["h1b_fy23"] if firm else legal[company.lower()] if company.lower() in legal
                else h1b.approvals_for_company(company))
        return by_company[company]

    def place_info(location: str):
        if location not in by_location:
            by_location[location] = (list(geo.regions(location)), list(geo.countries(location)))
        return by_location[location]

    for r in rows:
        desc = r.pop("description", "") or ""
        r["has_description"] = bool(desc)
        r["immediate"] = classify.immediate(r.get("title", ""), desc)
        uni, r["fin"], r["h1b_fy23"] = company_info(r["company"] or "")
        r["uni"] = r["source_name"] if r["source_type"] == "university" else uni
        if r["source_type"] == "university":
            r["regions"], r["countries"] = ["us"], [geo.US]
        else:
            r["regions"], r["countries"] = place_info(r["location"])
    return rows


# Building the job list (~130k rows, H-1B / finance / region lookups) takes minutes on a small cloud server, so it is
# built in the background after each refresh and kept gzipped; page loads get that copy instantly. Your own marks
# (status, notes) change all the time, so they come separately from /api/jobs/mine and the page merges them in.
# One prebuilt list per tab (US, India, Canada, other countries), so each tab only downloads its own jobs.
# Handshake jobs are the admin's own (imported from their Handshake account): only in the admin's Handshake list.
REGIONS = ("us", "india", "canada", "other", "handshake")
_jobs = {"gz": None, "built": 0, "building": False, "again": False}  # gz: {region: gzipped JSON}
_jobs_lock = threading.Lock()


def _build_jobs():
    rows = _enrich(db.list_jobs(int(load_sources().get("max_age_days", 45))))
    now = int(time.time())
    by_region = {r: [] for r in REGIONS}
    for row in rows:
        for k in ("status", "notes", "applied_at"):  # pre-accounts columns: each user's marks come from /api/jobs/mine
            row.pop(k, None)
        if row["source_type"] == "handshake":
            by_region["handshake"].append(row)
            continue
        for r in row["regions"]:
            by_region[r].append(row)
    gz = {r: gzip.compress(json.dumps({"now": now, "region": r, "jobs": js}, separators=(",", ":")).encode(), 5)
          for r, js in by_region.items()}
    _jobs.update(gz=gz, built=now)
    for r, data in gz.items():
        try:
            tmp = DATA_DIR / f"jobs_cache_{r}.tmp"
            tmp.write_bytes(data)
            tmp.replace(DATA_DIR / f"jobs_cache_{r}.json.gz")
        except OSError:
            pass


def rebuild_jobs():
    """Rebuild the job list in the background (coalesces calls that arrive while a build is running)."""
    with _jobs_lock:
        if _jobs["building"]:
            _jobs["again"] = True
            return
        _jobs["building"] = True

    def work():
        while True:
            try:
                _build_jobs()
            except Exception as e:
                print(f"job list build failed: {e}", flush=True)
            with _jobs_lock:
                if not _jobs["again"]:
                    _jobs["building"] = False
                    return
                _jobs["again"] = False
    threading.Thread(target=work, daemon=True).start()


@app.get("/api/jobs")
def jobs(request: Request, region: str = "us"):
    if region not in REGIONS:
        raise HTTPException(400, "Unknown region.")
    if region == "handshake" and me(request)["role"] != "admin":
        raise HTTPException(403, "Only the admin can do that.")
    for _ in range(600):  # very first start, nothing cached yet: wait for the background build
        if _jobs["gz"] is not None or not _jobs["building"]:
            break
        time.sleep(1)
    if _jobs["gz"] is None:
        _build_jobs()
    data = _jobs["gz"][region]
    if "gzip" in request.headers.get("accept-encoding", ""):
        return Response(data, media_type="application/json",
                        headers={"Content-Encoding": "gzip", "Cache-Control": "no-store", "Vary": "Accept-Encoding"})
    return Response(gzip.decompress(data), media_type="application/json", headers={"Cache-Control": "no-store"})


@app.get("/api/jobs/mine")
def my_marks(request: Request):
    """Your status / notes / applied date for every job you've touched (everything else is 'new')."""
    return {"now": int(time.time()), "built": _jobs["built"], "marks": db.marks(me(request)["id"])}


@app.get("/api/analytics")
def analytics(request: Request):
    """Everything you've applied to (any age), enriched like the job list."""
    uid = me(request)["id"]
    return {"now": int(time.time()), "applied": _enrich(db.applied_jobs(uid)), "decisions": db.decision_counts(uid)}


@app.get("/api/companies")
def more_companies():
    """Tech and other employers from config/more_companies.yaml, with H-1B history and feed status."""
    log = {l["source"]: l for l in db.fetch_log()}
    legal = _uscis_counts()
    return [{"name": c["name"], "group": c.get("group", ""), "regions": c.get("regions") or ["us", "india", "other"],
             "h1b_fy23": legal.get(c["name"].lower(), h1b.approvals_for_company(c["name"])),
             "log": log.get(f"Company: {c['name']}")} for c in load_more_companies()]


@app.get("/api/finance")
def finance_firms():
    log = {l["source"]: l for l in db.fetch_log()}
    cfg = finance.config()
    return {"segments": cfg["segments"],
            "firms": [{"name": f["name"], "segment": f["segment"], "segment_label": f["segment_label"],
                       "h1b_fy23": f["h1b_fy23"], "careers": f.get("careers", ""), "feed": bool(f.get("feeds")),
                       "log": log.get(f"Company: {f['name']}")} for f in cfg["firms"]]}


@app.get("/api/universities")
def universities():
    log = {l["source"]: l for l in db.fetch_log()}
    return [{"name": u["name"], "short": u["short"], "careers_url": u.get("careers_url", ""),
             "feed": (u.get("feed") or {}).get("type"), "log": log.get(f"University: {u['short']}")}
            for u in load_universities()]


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    j = db.get_job(job_id)
    if not j:
        raise HTTPException(404)
    return j


@app.post("/api/jobs/{job_id}/status")
def job_status(job_id: str, request: Request, body: dict = Body(...)):
    if body.get("status") not in db.STATUSES:
        raise HTTPException(400, "bad status")
    return db.set_status(me(request)["id"], job_id, body["status"], body.get("notes")) or {}


@app.post("/api/jobs")
def add_job(body: dict = Body(...)):
    """Add a job by hand (e.g. something you found on LinkedIn or JobRight)."""
    j = classify.build(source_type="manual", source_name=body.get("source") or "Manual",
                       company=body.get("company", ""), title=body.get("title", ""),
                       location=body.get("location", ""), url=body.get("url", ""),
                       posted_at=int(time.time()), description=body.get("description", ""))
    db.upsert_jobs([j])
    rebuild_jobs()
    return j


@app.post("/api/handshake/import")
def handshake_import(body: dict = Body(...)):
    """Jobs copied from Handshake with the bookmark (or pasted Handshake job links)."""
    from .fetchers import handshake
    jobs = handshake.parse(str(body.get("text", ""))[:2_000_000])
    if not jobs:
        raise HTTPException(400, "No Handshake jobs found in what you pasted. Use the bookmark on a Handshake job-search page.")
    new = db.upsert_jobs(jobs)
    db.log_fetch("Handshake (imported)", len(jobs))
    rebuild_jobs()
    return {"found": len(jobs), "new": len(new)}


# ---------------------------------------------------------------- quick-copy bar (links, snippets, notes)

PROFILE_JSON = DATA_DIR / "profile.json"
DEFAULT_PROFILE = {
    "links": [{"label": "LinkedIn", "value": ""}, {"label": "GitHub", "value": ""},
              {"label": "Portfolio", "value": ""}, {"label": "Email", "value": ""}, {"label": "Phone", "value": ""}],
    "snippets": [{"label": "Work authorization", "value": ""}, {"label": "Why this company", "value": ""}],
    "notes": "",
}


@app.get("/api/profile")
def get_profile(request: Request):
    """Each person's own quick-copy bar. The admin's starts from the profile.json saved before accounts existed."""
    user = me(request)
    saved = db.get_profile(user["id"])
    if saved is None and user["role"] == "admin" and PROFILE_JSON.exists():
        saved = json.loads(PROFILE_JSON.read_text())
    return saved or DEFAULT_PROFILE


@app.post("/api/profile")
def save_profile(request: Request, body: dict = Body(...)):
    profile = {k: body.get(k, DEFAULT_PROFILE[k]) for k in DEFAULT_PROFILE}
    db.update_user(me(request)["id"], profile=json.dumps(profile))
    return profile


# ---------------------------------------------------------------- ask all LLMs

@app.post("/api/ask")
def ask(body: dict = Body(...)):
    providers = [p for p in body.get("providers") or [] if p in llm.PROVIDERS]
    return llm.ask_all(providers, body.get("system") or "You are a helpful career assistant.", body.get("prompt", ""))


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
