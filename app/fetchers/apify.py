# Job Portal · built by JAI SHARMA
"""Fetch LinkedIn (or other) jobs through an Apify actor."""
import time
from datetime import datetime

import httpx

from .. import classify
from ..config import env

RUN_URL = "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"


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


def fetch(cfg: dict, max_age_days: int) -> list[dict]:
    token = env("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN is not set in .env")
    actor = cfg.get("actor", "curious_coder/linkedin-jobs-scraper").replace("/", "~")
    cutoff = time.time() - max_age_days * 86400
    jobs = []
    with httpx.Client(timeout=600) as client:
        for search in cfg.get("searches") or []:
            r = client.post(RUN_URL.format(actor=actor), params={"token": token}, json=search)
            r.raise_for_status()
            for it in r.json():
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
                    posted_at=posted or int(time.time()), posted_precision=precision if posted else "exact",
                    description=desc if isinstance(desc, str) else "",
                    salary=str(_first(it, "salary", "salaryInfo", "salaryRange")),
                    seniority=_first(it, "seniorityLevel", "experienceLevel"),
                ))
    return jobs
