# Job Portal · built by JAI SHARMA
"""Fetch LinkedIn (or other) jobs through an Apify actor."""
import time
from datetime import datetime

import httpx

from .. import classify
from ..config import env



def _first(item: dict, *keys, default=""):
    for k in keys:
        v = item.get(k)
        if isinstance(v, dict):
            v = v.get("name") or v.get("text") or ""
        if v not in (None, "", []):
            return v
    return default


def _ts(value) -> tuple[int | None, str]:
    """Returns (unix time, precision). LinkedIn often gives only a date like "2026-09-24"."""
    if value in (None, ""):
        return None, "exact"
    if isinstance(value, (int, float)):
        return int(value / 1000 if value > 1e11 else value), "exact"
    s = str(value).replace("Z", "+00:00")
    try:
        return int(datetime.fromisoformat(s).timestamp()), ("exact" if "T" in s or ":" in s else "day")
    except ValueError:
        pass
    try:
        return int(datetime.strptime(s[:10], "%Y-%m-%d").timestamp()), "day"
    except ValueError:
        return None, "exact"


API = "https://api.apify.com/v2"


def _run(client: httpx.Client, actor: str, token: str, search: dict, wait_minutes: int = 12) -> list[dict]:
    """Start one actor run, wait for it to finish (polling, so no single request has to stay open for minutes),
    then download its results."""
    run = client.post(f"{API}/acts/{actor}/runs", params={"token": token}, json=search).json()["data"]
    deadline = time.time() + wait_minutes * 60
    while run["status"] in ("READY", "RUNNING") and time.time() < deadline:
        time.sleep(10)
        run = client.get(f"{API}/actor-runs/{run['id']}", params={"token": token}).json()["data"]
    if run["status"] not in ("SUCCEEDED", "RUNNING"):  # RUNNING past the deadline: take what it has so far
        raise RuntimeError(f"run {run['status'].lower()}")
    return client.get(f"{API}/datasets/{run['defaultDatasetId']}/items", params={"token": token, "clean": "true"}).json()


def fetch(cfg: dict, max_age_days: int) -> list[dict]:
    token = env("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN is not set in .env")
    actor = cfg.get("actor", "curious_coder/linkedin-jobs-scraper").replace("/", "~")
    cutoff = time.time() - max_age_days * 86400
    jobs, failures = [], []
    with httpx.Client(timeout=60, transport=httpx.HTTPTransport(retries=2)) as client:
        for search in cfg.get("searches") or []:
            # skip the per-job company lookups: slower, costs extra, and the portal doesn't need them
            params = {"scrapeCompany": False, **search}
            try:
                items = _run(client, actor, token, params)
            except Exception as e:
                failures.append(f"{search.get('keywords', '?')[:30]}: {e}")
                continue
            for it in items:
                posted, precision = _ts(_first(it, "postedAt", "postedDate", "publishedAt", "datePosted", "listedAt", "postedTime"))
                if posted and posted < cutoff:
                    continue
                desc = _first(it, "descriptionText", "description", "jobDescription")
                jobs.append(classify.build(
                    source_type="apify", source_name="LinkedIn (Apify)",
                    company=_first(it, "companyName", "company", "company_name"),
                    title=_first(it, "title", "jobTitle", "position"),
                    location=_first(it, "location", "jobLocation", "place"),
                    url=_first(it, "applyUrl", "link", "jobUrl", "url"),
                    posted_at=posted or None, posted_precision=precision if posted else "exact",
                    description=desc if isinstance(desc, str) else "",
                    salary=str(_first(it, "salary", "salaryInfo", "salaryRange")),
                    seniority=_first(it, "seniorityLevel", "experienceLevel"),
                ))
    if failures and not jobs:
        raise RuntimeError("; ".join(failures))
    return jobs


# ---------------------------------------------------------------- spending: how much is left this month

PRICE_PER_RESULT = 0.002  # this actor's free-plan price per job; a run's start fee is tiny on top
STATE_FILE = None  # set lazily (data/apify_state.json)


def _state_path():
    from ..config import DATA_DIR
    return DATA_DIR / "apify_state.json"


def _read_state() -> dict:
    import json
    p = _state_path()
    return json.loads(p.read_text()) if p.exists() else {"fetches": [], "thresholds_sent": {}}


def _write_state(st: dict) -> None:
    import json
    st["fetches"] = st["fetches"][-30:]
    _state_path().write_text(json.dumps(st))


def usage() -> dict:
    """This billing cycle's spend, the plan limit, and roughly how many more LinkedIn fetches that allows."""
    from datetime import datetime
    from ..config import load_sources
    token = env("APIFY_TOKEN")
    if not token:
        return {"configured": False}
    d = httpx.get(f"{API}/users/me/limits", params={"token": token}, timeout=30).json()["data"]
    used = float((d.get("current") or {}).get("monthlyUsageUsd") or 0)
    limit = float((d.get("limits") or {}).get("maxMonthlyUsageUsd") or 0)
    end = ((d.get("monthlyUsageCycle") or {}).get("endAt") or "")[:10]
    st = _read_state()
    searches = (load_sources().get("apify") or {}).get("searches") or []
    planned = sum(int(s.get("limitPerSource") or 100) for s in searches) * PRICE_PER_RESULT + 0.01 * len(searches)
    recent = [f["cost"] for f in st["fetches"][-3:] if f.get("cost")]
    per_click = max(sum(recent) / len(recent), 0.01) if recent else planned  # learn from real fetches once there are some
    left = max(limit - used, 0)
    return {"configured": True, "used": round(used, 2), "limit": limit, "left": round(left, 2),
            "per_click": round(per_click, 2), "clicks_left": int(left // per_click) if per_click else 0,
            "resets": datetime.fromisoformat(end).strftime("%b %-d") if end else "", "searches": len(searches),
            "last_fetch": st["fetches"][-1] if st["fetches"] else None}


def record_fetch(started: float, jobs: int) -> dict:
    """After a LinkedIn fetch: add up what its runs actually cost and remember it."""
    token = env("APIFY_TOKEN")
    runs = httpx.get(f"{API}/actor-runs", params={"token": token, "desc": 1, "limit": 20}, timeout=30).json()["data"]["items"]
    from datetime import datetime
    cost = sum(float(r.get("usageTotalUsd") or 0) for r in runs
               if datetime.fromisoformat(r["startedAt"].replace("Z", "+00:00")).timestamp() >= started - 5)
    st = _read_state()
    entry = {"at": int(time.time()), "cost": round(cost, 3), "jobs": jobs}
    st["fetches"].append(entry)
    _write_state(st)
    return entry


def thresholds_to_alert(u: dict) -> list[int]:
    """Spending thresholds (50 / 80 / 95 % of the monthly allowance) crossed and not yet reported this cycle."""
    if not u.get("configured") or not u.get("limit"):
        return []
    st = _read_state()
    cycle = u.get("resets", "")
    sent = set(st.get("thresholds_sent", {}).get(cycle, []))
    pct = 100 * u["used"] / u["limit"]
    new = [t for t in (50, 80, 95) if pct >= t and t not in sent]
    if new:
        st.setdefault("thresholds_sent", {})[cycle] = sorted(sent | set(new))
        _write_state(st)
    return new
