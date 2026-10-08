# Job Portal · built by JAI SHARMA
"""Run all job sources and store the results."""
from concurrent.futures import ThreadPoolExecutor

from . import db, finance
from .config import load_more_companies, load_sources, load_universities
from .fetchers import apify, careers, github


def run(include_apify: bool = False, only: str | None = None) -> list[dict]:
    """Fetch every configured source. Returns one status dict per source."""
    cfg = load_sources()
    max_age = int(cfg.get("max_age_days", 45))
    firm_age = int(cfg.get("company_max_age_days", 30))
    tasks = [(s.get("name") or s["url"], lambda s=s: github.fetch(s, max_age)) for s in cfg.get("github") or []]
    tasks += [(f"University: {u['short']}",
               lambda u=u: careers.fetch([u["feed"]], {"source_type": "university", "source_name": u["short"],
                                                       "company": u["name"]}, max_age))
              for u in load_universities() if u.get("feed")]
    if cfg.get("company_feeds", True):
        finance.reload()
        regions = cfg.get("company_regions") or ["us", "india", "other"]
        employers = [f for f in finance.public_list() if f.get("feeds")] + \
                    [c for c in load_more_companies() if c.get("feeds")]
        tasks += [(f"Company: {e['name']}",
                   lambda e=e: careers.fetch(e["feeds"], {"source_type": "company", "source_name": e["name"], "company": e["name"]},
                                             firm_age, [r for r in regions if r in (e.get("regions") or regions)],
                                             tech_only=bool(e.get("tech_only"))))
                  for e in employers]
    ap = cfg.get("apify") or {}
    if include_apify and ap.get("enabled", True):
        tasks.append(("LinkedIn (Apify)", lambda: apify.fetch(ap, max_age)))
    tasks = [t for t in tasks if not only or t[0] == only]

    def one(task):
        name, fn = task
        try:
            jobs = fn()
            db.upsert_jobs(jobs)
            db.log_fetch(name, len(jobs))
            return {"source": name, "count": len(jobs), "error": ""}
        except Exception as e:  # one broken source shouldn't stop the others
            db.log_fetch(name, 0, str(e)[:300])
            return {"source": name, "count": 0, "error": str(e)[:300]}

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
