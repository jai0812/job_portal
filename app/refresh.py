# Job Portal · built by JAI SHARMA
"""Run all job sources and store the results."""
import time
from concurrent.futures import ThreadPoolExecutor

from . import db, finance
from .config import load_more_companies, load_sources, load_universities
from .fetchers import apify, careers, github


def _employers() -> list[dict]:
    finance.reload()
    return [f for f in finance.public_list() if f.get("feeds")] + [c for c in load_more_companies() if c.get("feeds")]


def _due(name: str, every_hours: float | None) -> bool:
    """Employers with every_hours (e.g. the mid-size sponsors) are only re-checked that often, to keep refreshes quick."""
    if not every_hours:
        return True
    last = {l["source"]: l["last_run"] for l in db.fetch_log()}.get(name) or 0
    return time.time() - last >= every_hours * 3600 - 300


def run_fast(names: list[str], on_new=None) -> list[dict]:
    """Fast lane: re-check just these companies' own career sites for postings from the last few days."""
    cfg = load_sources()
    regions = cfg.get("company_regions") or ["us", "india", "other"]
    wanted = {n.lower() for n in names}
    tasks = [(f"Company: {e['name']}",
              lambda e=e: careers.fetch(e["feeds"], {"source_type": "company", "source_name": e["name"], "company": e["name"]},
                                        3, [r for r in regions if r in (e.get("regions") or regions)],
                                        tech_only=bool(e.get("tech_only"))))
             for e in _employers() if e["name"].lower() in wanted]
    return _execute(tasks, on_new, log=False)


def run(include_apify: bool = False, only: str | None = None, on_new=None) -> list[dict]:
    """Fetch every configured source. Returns one status dict per source; on_new(jobs) gets brand-new jobs."""
    cfg = load_sources()
    max_age = int(cfg.get("max_age_days", 45))
    firm_age = int(cfg.get("company_max_age_days", 30))
    tasks = [(s.get("name") or s["url"], lambda s=s: github.fetch(s, max_age)) for s in cfg.get("github") or []]
    tasks += [(f"University: {u['short']}",
               lambda u=u: careers.fetch([u["feed"]], {"source_type": "university", "source_name": u["short"],
                                                       "company": u["name"]}, max_age))
              for u in load_universities() if u.get("feed")]
    if cfg.get("company_feeds", True):
        regions = cfg.get("company_regions") or ["us", "india", "other"]
        employers = _employers()
        tasks += [(f"Company: {e['name']}",
                   lambda e=e: careers.fetch(e["feeds"], {"source_type": "company", "source_name": e["name"], "company": e["name"]},
                                             firm_age, [r for r in regions if r in (e.get("regions") or regions)],
                                             tech_only=bool(e.get("tech_only"))))
                  for e in employers if only or _due(f"Company: {e['name']}", e.get("every_hours"))]
    ap = cfg.get("apify") or {}
    if include_apify and ap.get("enabled", True):
        def linkedin():
            started = time.time()
            jobs = apify.fetch(ap, max_age)
            try:  # what did that cost, and how much is left? → alert
                from . import alerts
                spent = apify.record_fetch(started, len(jobs))
                u = apify.usage()
                alerts.send("💸 LinkedIn fetch done",
                            f"{len(jobs)} jobs · cost ${spent['cost']:.2f}\n${u['left']:.2f} of ${u['limit']:.0f} left this month "
                            f"≈ {u['clicks_left']} more fetches (resets {u['resets']})", tags=["moneybag"])
            except Exception:
                pass
            return jobs
        tasks.append(("LinkedIn (Apify)", linkedin))
    tasks = [t for t in tasks if not only or t[0] == only]
    return _execute(tasks, on_new)


def _execute(tasks, on_new=None, log=True) -> list[dict]:
    def one(task):
        name, fn = task
        try:
            jobs = fn()
            new = db.upsert_jobs(jobs)
            if log:  # the fast lane only looks at a few days, so it doesn't overwrite the hourly counts
                db.log_fetch(name, len(jobs))
            if new and on_new:
                try:
                    on_new(new)
                except Exception:
                    pass
            return {"source": name, "count": len(jobs), "new": len(new), "error": ""}
        except Exception as e:  # one broken source shouldn't stop the others
            if log:
                db.log_fetch(name, 0, str(e)[:300])
            return {"source": name, "count": 0, "new": 0, "error": str(e)[:300]}

    # GitHub lists are fast, so fetch them in parallel. Employer career sites (Workday especially) throttle
    # bursts, so universities and companies each get a small pool.
    groups = {"University:": 2, "Company:": 6}  # each company is a different site, so they can run side by side
    slow = {p: [t for t in tasks if t[0].startswith(p)] for p in groups}
    fast = [t for t in tasks if not any(t[0].startswith(p) for p in groups)]
    pools = [ThreadPoolExecutor(max_workers=6)] + [ThreadPoolExecutor(max_workers=n) for n in groups.values()]
    try:
        futures = [pools[0].map(one, fast)] + [pool.map(one, slow[p]) for pool, p in zip(pools[1:], groups)]
        return [r for f in futures for r in f]
    finally:
        for p in pools:
            p.shutdown()
