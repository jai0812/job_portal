# Job Portal · built by JAI SHARMA
"""Phone, Telegram and email alerts. Both channels are free:
- ntfy (https://ntfy.sh): no account, just its phone app and a private topic name.
- Telegram: your own bot (made in 1 minute with @BotFather) messages you.

Every alert is one short line ("Snapchat 1m", "Google · posting window in 5 min"), and only the admin gets them:
- New job: a matching role at a top company posted in the last 15 minutes (checked every 10 minutes by the fast lane).
- Window: sent about 5 minutes before a company's usual posting window opens.
- Morning digest: one line with last night's count and today's likely windows.

Settings live in data/alerts.json (private, never committed). The ntfy topic name works like a password:
anyone who knows it can read your alerts, so it's long and random.
"""
import json
import secrets
import threading
import time
from datetime import datetime

import httpx

from . import finance, h1b, patterns
from .config import DATA_DIR, load_more_companies, load_sources

SETTINGS = DATA_DIR / "alerts.json"
STATE = DATA_DIR / "alerts_state.json"
_lock = threading.Lock()

DEFAULTS = {
    "enabled": False,
    "use_ntfy": True,
    "use_telegram": False,
    "telegram_token": "",      # from @BotFather; stays in data/alerts.json on this Mac
    "telegram_chat_id": "",    # filled in by "Connect Telegram"
    "server": "https://ntfy.sh",
    "topic": "",
    "email": "",
    "portal_url": "http://localhost:8787/#top",
    "new_jobs": True,          # alert on new roles at top companies
    "max_age_min": 15,         # only jobs posted at most this many minutes ago
    "levels": ["early_career", "internship"],
    "sectors": ["swe", "data", "finance"],
    "regions": ["us"],
    "sponsor_only": True,      # only employers with H-1B history (or postings that say they sponsor)
    "windows": True,           # "usually posts around now" heads-ups
    "watch": [],               # companies for window alerts; empty = the ones with the clearest patterns
    "digest": True,
    "digest_hour": 8,          # local time
    "quiet_start": 23,         # no alerts between these hours (local time)
    "quiet_end": 7,
}


def load() -> dict:
    data = json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {}
    cfg = {**DEFAULTS, **data}
    if not cfg["topic"]:
        cfg["topic"] = "sharmajai-jobs-" + secrets.token_hex(6)
        save(cfg)
    return cfg


def save(cfg: dict) -> dict:
    clean = {k: cfg.get(k, v) for k, v in DEFAULTS.items()}
    SETTINGS.write_text(json.dumps(clean, indent=1))
    SETTINGS.chmod(0o600)
    return clean


def _state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {"sent_ids": [], "history": [], "digest_day": "", "windows": {}}


def _save_state(st: dict) -> None:
    st["sent_ids"] = st["sent_ids"][-5000:]
    st["history"] = st["history"][-40:]
    STATE.write_text(json.dumps(st))


def _quiet(cfg: dict, now: datetime | None = None) -> bool:
    h = (now or datetime.now()).hour
    a, b = int(cfg["quiet_start"]), int(cfg["quiet_end"])
    return (a <= h or h < b) if a > b else (a <= h < b)


def send(title: str, message: str, click: str = "", tags: list[str] | None = None, priority: int = 3,
         cfg: dict | None = None, force: bool = False) -> dict:
    """Publish one notification. force=True ignores the on/off switch and quiet hours (used by the Test button)."""
    cfg = cfg or load()
    if not force and (not cfg["enabled"] or _quiet(cfg)):
        return {"sent": False, "reason": "off" if not cfg["enabled"] else "quiet hours"}
    results, errors = [], []
    if cfg.get("use_ntfy", True) and cfg.get("topic"):
        body = {"topic": cfg["topic"], "title": title[:250], "message": message[:3500], "tags": tags or ["briefcase"],
                "priority": priority}
        if click:
            body["click"] = click
        if cfg.get("email"):
            body["email"] = cfg["email"]
        try:
            r = httpx.post(cfg["server"].rstrip("/"), json=body, timeout=20)
            results.append(r.status_code < 300)
            if r.status_code >= 300:
                errors.append(f"ntfy: {r.text[:150]}")
        except Exception as e:
            results.append(False)
            errors.append(f"ntfy: {e}")
    if cfg.get("use_telegram") and cfg.get("telegram_token") and cfg.get("telegram_chat_id"):
        ok, err = _telegram(cfg, title, message, click)
        results.append(ok)
        if err:
            errors.append(f"Telegram: {err}")
    ok = bool(results) and all(results)
    with _lock:
        st = _state()
        st["history"].append({"at": int(time.time()), "title": title, "ok": ok, "error": "; ".join(errors)[:200]})
        _save_state(st)
    return {"sent": ok, "detail": "; ".join(errors) or ("" if results else "no channel set up")}


def _telegram(cfg: dict, title: str, message: str, click: str = "") -> tuple[bool, str]:
    """One line: the bold headline, the detail after it, and a link."""
    from html import escape
    text = f"<b>{escape(title)}</b>" + (f" · {escape(message)}" if message else "")
    if click:
        text += f' <a href="{escape(click, quote=True)}">↗</a>'
    try:
        r = httpx.post(f"https://api.telegram.org/bot{cfg['telegram_token']}/sendMessage", timeout=20,
                       json={"chat_id": cfg["telegram_chat_id"], "text": text[:4000], "parse_mode": "HTML",
                             "disable_web_page_preview": True})
        return r.status_code == 200, "" if r.status_code == 200 else r.json().get("description", r.text[:150])
    except Exception as e:
        return False, str(e)[:150]


def telegram_connect() -> dict:
    """Find the chat where you sent /start to your bot, remember it, and say hello there."""
    cfg = load()
    token = cfg.get("telegram_token", "").strip()
    if not token:
        raise ValueError("Paste your bot token first.")
    r = httpx.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20).json()
    if not r.get("ok"):
        raise ValueError(f"Telegram didn't accept that token ({r.get('description', 'unknown error')}).")
    chats = [u["message"]["chat"] for u in r.get("result", []) if "message" in u]
    if not chats:
        raise ValueError("No message found yet. Open your bot in Telegram, tap Start (or send /start), then try again.")
    chat = chats[-1]
    cfg["telegram_chat_id"] = str(chat["id"])
    cfg["use_telegram"] = True
    save(cfg)
    ok, err = _telegram(cfg, "✅ SharmaJai Job Portal connected", "Job alerts and your morning summary will arrive here.")
    if not ok:
        raise ValueError(f"Connected, but sending failed: {err}")
    return {"chat": chat.get("first_name") or chat.get("title") or "you"}


# ---------------------------------------------------------------- new-job alerts

def _approvals(company: str) -> int:
    firm = finance.firm_for(company)
    if firm:
        return firm["h1b_fy23"]
    for c in load_more_companies():
        if c["name"].lower() == (company or "").lower() and c.get("uscis"):
            return h1b.approvals_for_names(c["uscis"])
    return h1b.approvals_for_company(company or "")


def _is_top(job: dict, fast: set[str]) -> bool:
    return bool(job.get("top_company")) or (job.get("company") or "").lower() in fast


def _age_min(job: dict, now: float, since: float | None, limit: int) -> tuple[int, bool] | None:
    """How many minutes ago the job was posted, and whether that's an upper bound; None when it's older than
    `limit` (or we can't tell). Exact timestamps are used as they are. Sites that only give the day ("Posted Today",
    most Workday sites) count only when this check found a job that wasn't there on the previous check `since`,
    a few minutes ago: then it was posted at most that long ago."""
    ts = job.get("posted_at")
    if ts and job.get("posted_precision", "exact") == "exact":
        age = max(0, int((now - ts) // 60))
        return (age, False) if age <= limit else None
    if since and now - since <= (limit + 5) * 60 and ts and datetime.fromtimestamp(ts).date() == datetime.fromtimestamp(now).date():
        return max(1, int((now - since) // 60)), True
    return None


def on_new(jobs: list[dict], since: float | None = None) -> None:
    """since: when the previous check of these sources started (fast lane only); None for the full refresh."""
    cfg = load()
    if not (cfg["enabled"] and cfg["new_jobs"]):
        return
    from . import geo
    fast = {n.lower() for n in load_sources().get("fast_lane") or []}
    now = time.time()
    picks = []
    for j in jobs:
        cats = set((j.get("categories") or "").split(","))
        if not (_is_top(j, fast) and j.get("level") in cfg["levels"] and cats & set(cfg["sectors"])):
            continue
        # "posted today" can only be narrowed down for sources the 10-minute check looks at
        checked = j.get("source_type") == "github" or (j.get("company") or "").lower() in fast
        age = _age_min(j, now, since if checked else None, int(cfg.get("max_age_min") or 15))
        if age is None:
            continue
        j = {**j, "_age": age}
        if not set(geo.regions(j.get("location") or "")) & set(cfg["regions"]):
            continue
        if j.get("h1b") in ("no", "citizen"):
            continue
        n = _approvals(j["company"])
        if cfg["sponsor_only"] and not (n or j.get("h1b") == "yes"):
            continue
        picks.append((j, n))
    if not picks:
        return
    with _lock:
        st = _state()
        sent = set(st["sent_ids"])
        unique = []
        for j, n in picks:  # never twice for the same job, within this batch or across days
            if j["id"] not in sent:
                sent.add(j["id"])
                unique.append((j, n))
        picks = unique
        st["sent_ids"] += [j["id"] for j, _ in picks]
        _save_state(st)
    if not picks:
        return

    def ago(j):
        mins, upper = j["_age"]
        return f"{'≤' if upper else ''}{mins}m"

    picks.sort(key=lambda p: p[0]["_age"][0])
    if len(picks) == 1:
        j, _ = picks[0]
        send(f"{j['company']} {ago(j)}", j["title"][:90], click=j.get("url") or cfg["portal_url"], tags=["briefcase"],
             priority=4, cfg=cfg)
    else:  # one line for the whole batch: "Snapchat 1m · Stripe 5m · Google ≤10m"
        head = " · ".join(f"{j['company']} {ago(j)}" for j, _ in picks[:6]) + (f" +{len(picks) - 6}" if len(picks) > 6 else "")
        send(head[:200], " · ".join(j["title"][:40] for j, _ in picks[:3]), click=cfg["portal_url"], tags=["briefcase"],
             priority=4, cfg=cfg)


# ---------------------------------------------------------------- posting-window heads-ups and the morning digest

def _watchlist(cfg: dict) -> list[dict]:
    """Companies to send window heads-ups for: your picks, or else the fast-lane (top) companies whose
    posting times are actually predictable."""
    if cfg["watch"]:
        names = {w.lower() for w in cfg["watch"]}
        return [p for p in patterns.all_patterns() if p["company"].lower() in names]
    fast = {n.lower() for n in load_sources().get("fast_lane") or []}
    return [p for p in patterns.all_patterns() if p["company"].lower() in fast and p["strength"] != "spread out"][:8]


def tick() -> None:
    """Called every few minutes: sends the morning digest and window heads-ups when they're due."""
    cfg = load()
    if not cfg["enabled"]:
        return
    _apify_check(cfg)
    now_et = datetime.now(patterns.TZ)
    today = now_et.strftime("%Y-%m-%d")
    st = _state()
    watch = _watchlist(cfg)

    if cfg["digest"] and st.get("digest_day") != today and datetime.now().hour >= int(cfg["digest_hour"]):
        todays = [p for p in watch if now_et.weekday() in p["top_day_idx"]]
        overnight = _matching_since(cfg, time.time() - 24 * 3600)
        send(f"☀️ {len(overnight)} new top-company roles since yesterday",
             " · ".join(f"{p['company']} {p['window']}" for p in todays[:4]), click=cfg["portal_url"], tags=["sunny"], cfg=cfg)
        st = _state()
        st["digest_day"] = today
        _save_state(st)

    if cfg["windows"]:
        for p in watch:
            if now_et.weekday() not in p["top_day_idx"]:
                continue
            minutes_to = (p["window_start"] * 60) - (now_et.hour * 60 + now_et.minute)
            key = f"{p['company']}|{today}"
            if 0 <= minutes_to <= 6 and key not in st.get("windows", {}):  # checked every 4 minutes
                send(f"{p['company']} · posting window in {max(minutes_to, 1)} min", p["window"],
                     click=cfg["portal_url"], tags=["alarm_clock"], cfg=cfg)
                st = _state()
                st.setdefault("windows", {})[key] = int(time.time())
                st["windows"] = {k: v for k, v in st["windows"].items() if k.endswith(today)}
                _save_state(st)


_apify_checked = {"at": 0}


def _apify_check(cfg: dict) -> None:
    """At most every 3 hours: warn when LinkedIn (Apify) spending passes 50 / 80 / 95 % of the monthly allowance."""
    if time.time() - _apify_checked["at"] < 3 * 3600:
        return
    _apify_checked["at"] = time.time()
    from .fetchers import apify
    try:
        u = apify.usage()
        crossed = apify.thresholds_to_alert(u)
    except Exception:
        return
    if crossed:
        t = max(crossed)
        send(f"Apify {t}% used · ${u['left']:.2f} left", f"≈ {u['clicks_left']} LinkedIn fetches · resets {u['resets']}",
             tags=["moneybag"], priority=4 if t >= 80 else 3, cfg=cfg)


def _matching_since(cfg: dict, since: float) -> list[dict]:
    """Top-company roles first seen since `since` that match your alert filters (for the morning summary)."""
    from . import db, geo
    fast = {n.lower() for n in load_sources().get("fast_lane") or []}
    with db.conn() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM jobs WHERE first_seen >= ? "
                                           "ORDER BY COALESCE(posted_at, first_seen) DESC", (int(since),))]
    out = []
    for j in rows:
        if j.get("posted_at") and j["posted_at"] < since - 12 * 3600:  # old posting from a newly added list
            continue
        cats = set((j.get("categories") or "").split(","))
        if not (_is_top(j, fast) and j.get("level") in cfg["levels"] and cats & set(cfg["sectors"])):
            continue
        if not set(geo.regions(j.get("location") or "")) & set(cfg["regions"]) or j.get("h1b") in ("no", "citizen"):
            continue
        if cfg["sponsor_only"] and not (j.get("h1b") == "yes" or _approvals(j["company"])):
            continue
        out.append(j)
    return out


def history() -> list[dict]:
    return list(reversed(_state()["history"]))
