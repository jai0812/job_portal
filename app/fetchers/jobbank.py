# Job Portal · built by JAI SHARMA
"""Job Bank (jobbank.gc.ca), the Government of Canada's job board: free Atom feeds of search results, no key.

Each feed only shows the newest ~30 postings for a search, so the portal asks for many narrow searches
(occupation codes plus keywords) every couple of hours and keeps what it has seen: over a few days that adds
up to most of Job Bank's HR, recruiting, software and data postings."""
import html
import re
import time
from datetime import datetime
from xml.etree import ElementTree as ET

import httpx

from .. import classify

FEED = "https://www.jobbank.gc.ca/jobsearch/feed/jobSearchRSSfeed"
ATOM = "{http://www.w3.org/2005/Atom}"
PROVINCES = {"AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"}

# NOC 2021 occupation codes (fn21) and keyword searches. Job Bank feeds return ~30 newest results each.
DEFAULT_SEARCHES = [  # cat: the category occupation-code results get (the code already says what the job is)
    {"fn21": "10011", "cat": "hr"},   # human resources managers
    {"fn21": "11200", "cat": "hr"},   # human resources professionals (advisers, business partners, labour relations)
    {"fn21": "12101", "cat": "hr"},   # human resources and recruitment officers
    {"searchstring": "human resources", "cat": "hr"},
    {"searchstring": "payroll", "cat": "hr"},
    {"searchstring": "talent acquisition", "cat": "hr"},
    {"fn21": "21231", "cat": "swe"},  # software engineers and designers
    {"fn21": "21232", "cat": "swe"},  # software developers and programmers
    {"fn21": "21234", "cat": "swe"},  # web developers and programmers
    {"fn21": "21220", "cat": "swe"},  # cybersecurity specialists
    {"fn21": "21222", "cat": "swe"},  # information systems specialists
    {"fn21": "21211", "cat": "data"},  # data scientists
    {"fn21": "21223", "cat": "data"},  # database analysts and data administrators
    {"searchstring": "data analyst", "cat": "data"},
]


def _location(text: str) -> str:
    """"Laval (QC)" -> "Laval, QC, Canada"."""
    m = re.match(r"\s*(.*?)\s*\(([A-Z]{2})\)\s*$", text or "")
    if m and m.group(2) in PROVINCES:
        return f"{m.group(1)}, {m.group(2)}, Canada"
    return f"{(text or '').strip()}, Canada".strip(", ")


def _title(t: str) -> str:
    """Job Bank titles are all lower case: "human resources advisor" -> "Human Resources Advisor"."""
    small = {"and", "or", "of", "the", "in", "to", "for", "a", "an", "on", "at", "with"}
    words = (t or "").split()
    return " ".join(w if any(c.isupper() for c in w) else (w if i and w in small else w[:1].upper() + w[1:])
                    for i, w in enumerate(words))


def _summary(raw: str) -> dict:
    """Fields from the entry summary: Location, Employer, Salary."""
    text = html.unescape(re.sub(r"<br\s*/?>", "\n", raw or ""))
    out = {}
    for m in re.finditer(r"<strong>\s*([^<:]+?)\s*:\s*</strong>\s*([^\n]*)", text):
        out[m.group(1).strip().lower()] = re.sub(r"<[^>]+>", "", m.group(2)).strip()
    return out


def fetch(cfg: dict, max_age_days: int) -> list[dict]:
    cutoff = time.time() - max_age_days * 86400
    jobs, seen = [], set()
    with httpx.Client(headers={"User-Agent": "Mozilla/5.0 (job-portal)"}, timeout=30, follow_redirects=True) as c:
        for search in cfg.get("searches") or DEFAULT_SEARCHES:
            params = {k: v for k, v in search.items() if k != "cat"}
            r = c.get(FEED, params={**params, "sort": "D"})
            if r.status_code != 200:
                continue
            try:
                root = ET.fromstring(r.content)
            except ET.ParseError:
                continue
            for e in root.iter(f"{ATOM}entry"):
                link = (e.find(f"{ATOM}link").attrib.get("href", "") if e.find(f"{ATOM}link") is not None else "")
                if not link or link in seen:
                    continue
                seen.add(link)
                info = _summary(e.findtext(f"{ATOM}summary") or "")
                try:  # Job Bank gives the posting date only (time is always 07:00 / 10:00 UTC)
                    posted = classify.day_start(datetime.fromisoformat(e.findtext(f"{ATOM}updated").replace("Z", "+00:00")).timestamp())
                except (AttributeError, ValueError):
                    posted = None
                if posted and posted < cutoff:
                    continue
                jobs.append(classify.build(
                    source_type="jobbank", source_name="Job Bank Canada", company=info.get("employer", ""),
                    title=_title(e.findtext(f"{ATOM}title") or ""), location=_location(info.get("location", "")),
                    url=link, posted_at=posted, posted_precision="day", salary=info.get("salary", ""),
                    # occupation-code searches are exact; keyword searches also match unrelated ads, so those
                    # are classified by their title like everything else
                    source_category=search.get("cat", "") if "fn21" in search else ""))
            time.sleep(1)  # be polite to a government site
    return jobs
