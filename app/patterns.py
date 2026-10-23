# Job Portal · built by JAI SHARMA
"""When does each company post? Measured from the portal's own data, not guessed.

Only timestamps that come straight from a company's own career system with minute precision are used
(Microsoft, Greenhouse, Lever, Ashby, SmartRecruiters…). GitHub lists are left out because they record when
*they* noticed a job, often hours later, and sites that only give a date are left out too.
"""
import time
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from . import db

TZ = ZoneInfo("America/New_York")
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MIN_SAMPLES = 30
WINDOW = 3  # hours


def _hour_label(h: int) -> str:
    return f"{h % 12 or 12} {'AM' if h % 24 < 12 else 'PM'}"


@lru_cache(maxsize=1)
def _compute(bucket: int) -> list[dict]:
    with db.conn() as c:
        rows = c.execute(
            "SELECT company, posted_at FROM jobs WHERE source_type='company' AND posted_precision='exact' "
            "AND posted_at IS NOT NULL AND posted_at > ?", (int(time.time()) - 60 * 86400,)).fetchall()
    by: dict[str, list[datetime]] = {}
    for company, ts in rows:
        by.setdefault(company, []).append(datetime.fromtimestamp(ts, TZ))
    out = []
    for company, stamps in by.items():
        n = len(stamps)
        if n < MIN_SAMPLES:
            continue
        hours = [0] * 24
        days = [0] * 7
        for d in stamps:
            hours[d.hour] += 1
            days[d.weekday()] += 1
        # busiest 3-hour window (wrapping past midnight)
        start = max(range(24), key=lambda h: sum(hours[(h + i) % 24] for i in range(WINDOW)))
        share = sum(hours[(start + i) % 24] for i in range(WINDOW)) / n
        top_days = [i for i in sorted(range(7), key=lambda i: -days[i]) if days[i] / n >= 0.15][:3] or [max(range(7), key=days.__getitem__)]
        out.append({
            "company": company, "samples": n, "hours": hours, "days": days,
            "window_start": start, "window_end": (start + WINDOW) % 24, "window_share": round(share, 2),
            "window": f"{_hour_label(start)}–{_hour_label(start + WINDOW)} ET",
            "top_days": [DAYS[i] for i in sorted(top_days)], "top_day_idx": sorted(top_days),
            # a pattern is "strong" when its 3-hour window holds a big share of all postings
            "strength": "strong" if share >= 0.35 else "moderate" if share >= 0.22 else "spread out",
        })
    return sorted(out, key=lambda p: (-p["window_share"], -p["samples"]))


def all_patterns() -> list[dict]:
    return _compute(int(time.time() // 1800))  # recompute at most every 30 minutes


def for_company(name: str) -> dict | None:
    return next((p for p in all_patterns() if p["company"].lower() == (name or "").lower()), None)
