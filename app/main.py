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
import json
import re
import threading
import time

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
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
    raise SystemExit("PORTAL_PASSWORD_HASH is set but SESSION_SECRET is missing. Run scripts/set_password.py again.")

OPEN_PATHS = {"/login", "/login.html", "/login.js", "/style.css", "/logo-mark.svg", "/api/login", "/favicon.ico"}
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


@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path
    if auth.enabled():
        if path not in OPEN_PATHS and not auth.valid_session(request.cookies.get(auth.COOKIE, "")):
            response = (JSONResponse({"detail": "Please sign in"}, status_code=401) if path.startswith("/api/")
                        else RedirectResponse("/login", status_code=303))
        elif request.method not in ("GET", "HEAD", "OPTIONS") and not _same_site(request):
            response = JSONResponse({"detail": "Request blocked (cross-site)"}, status_code=403)
        else:
            response = await call_next(request)
    else:
        response = await call_next(request)
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
    time.sleep(0.4)  # every attempt costs time, right or wrong
    ok = auth.check_password(str(body.get("password", ""))[:256])
    if ok and auth.totp_enabled():
        ok = auth.check_totp(str(body.get("code", "")))
    if not ok:
        auth.record_failure(ip)
        raise HTTPException(401, "Wrong password or code.")
    auth.record_success(ip)
    response = JSONResponse({"ok": True})
    response.set_cookie(auth.COOKIE, auth.new_session(), max_age=auth.SESSION_HOURS * 3600, httponly=True,
                        samesite="strict", secure=_is_https(request), path="/")
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
        _refresh["results"] = refresh.run(include_apify=include_apify, on_new=alerts.on_new)
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


_fast = {"last": 0, "results": []}


def _fast_lane_loop():
    """Every few minutes, re-check the top companies' own career sites so new postings (and alerts) arrive fast."""
    time.sleep(90)
    while env("PORTAL_NO_REFRESH") != "1":
        cfg = load_sources()
        minutes = int(cfg.get("fast_lane_minutes") or 0)
        names = cfg.get("fast_lane") or []
        if minutes > 0 and names and not _refresh["running"]:
            try:
                _fast["results"] = refresh.run_fast(names, on_new=alerts.on_new)
                _fast["last"] = int(time.time())
            except Exception as e:
                _fast["results"] = [{"source": "fast lane", "error": str(e)[:200]}]
        time.sleep(max(minutes, 5) * 60)


def _alerts_loop():
    while True:
        try:
            alerts.tick()
        except Exception:
            pass
        time.sleep(240)


@app.on_event("startup")
def _startup():
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
    return {**_refresh, "log": db.fetch_log(), "fast_lane": _fast}


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
def status():
    cfg = load_sources()
    return {
        "auth": auth.enabled(),
        "two_step": auth.enabled() and auth.totp_enabled(),
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
    for r in rows:
        r["has_description"] = bool(r.pop("description", ""))
        r["uni"] = r["source_name"] if r["source_type"] == "university" else next(
            (short for short, rx in unis if rx.search(r["company"] or "")), None)
        if r["source_type"] == "university":
            r["regions"], r["countries"] = ["us"], [geo.US]
        else:
            r["regions"], r["countries"] = list(geo.regions(r["location"])), list(geo.countries(r["location"]))
        firm = finance.firm_for(r["company"])
        r["fin"] = firm and {k: firm[k] for k in ("name", "segment", "segment_label")}
        # USCIS FY2023 H-1B approvals: exact entity list for known finance firms, name match for everyone else
        company = r["company"] or ""
        r["h1b_fy23"] = (firm["h1b_fy23"] if firm
                         else legal[company.lower()] if company.lower() in legal
                         else h1b.approvals_for_company(company))
    return rows


@app.get("/api/jobs")
def jobs():
    return {"now": int(time.time()), "jobs": _enrich(db.list_jobs(int(load_sources().get("max_age_days", 45))))}


@app.get("/api/analytics")
def analytics():
    """Everything you've applied to (any age), enriched like the job list."""
    return {"now": int(time.time()), "applied": _enrich(db.applied_jobs()), "decisions": db.decision_counts()}


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
def job_status(job_id: str, body: dict = Body(...)):
    if body.get("status") not in db.STATUSES:
        raise HTTPException(400, "bad status")
    return db.set_status(job_id, body["status"], body.get("notes")) or {}


@app.post("/api/jobs")
def add_job(body: dict = Body(...)):
    """Add a job by hand (e.g. something you found on LinkedIn or JobRight)."""
    j = classify.build(source_type="manual", source_name=body.get("source") or "Manual",
                       company=body.get("company", ""), title=body.get("title", ""),
                       location=body.get("location", ""), url=body.get("url", ""),
                       posted_at=int(time.time()), description=body.get("description", ""))
    db.upsert_jobs([j])
    return j


# ---------------------------------------------------------------- quick-copy bar (links, snippets, notes)

PROFILE_JSON = DATA_DIR / "profile.json"
DEFAULT_PROFILE = {
    "links": [{"label": "LinkedIn", "value": ""}, {"label": "GitHub", "value": ""},
              {"label": "Portfolio", "value": ""}, {"label": "Email", "value": ""}, {"label": "Phone", "value": ""}],
    "snippets": [{"label": "Work authorization", "value": ""}, {"label": "Why this company", "value": ""}],
    "notes": "",
}


@app.get("/api/profile")
def get_profile():
    return json.loads(PROFILE_JSON.read_text()) if PROFILE_JSON.exists() else DEFAULT_PROFILE


@app.post("/api/profile")
def save_profile(body: dict = Body(...)):
    profile = {k: body.get(k, DEFAULT_PROFILE[k]) for k in DEFAULT_PROFILE}
    PROFILE_JSON.write_text(json.dumps(profile, indent=1))
    return profile


# ---------------------------------------------------------------- ask all LLMs

@app.post("/api/ask")
def ask(body: dict = Body(...)):
    providers = [p for p in body.get("providers") or [] if p in llm.PROVIDERS]
    return llm.ask_all(providers, body.get("system") or "You are a helpful career assistant.", body.get("prompt", ""))


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
