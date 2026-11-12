# Job Portal · built by JAI SHARMA
"""Job Bank (jobbank.gc.ca), the Government of Canada's job board: public search pages, no key.

The portal runs many narrow searches (occupation codes plus keywords) for HR, recruiting, payroll, software and
data jobs. Every hour it reads the newest page of each search; every sixth hour it pages through the whole of
each one, so every active posting is found, not only the newest.

The search results have no details, so each new posting's own page is read once for the things people filter on:
the start date ("Starts as soon as possible" = immediate start), permanent / temporary, hours a week, experience.
Job Bank's robots.txt asks for 5 seconds between requests; this keeps to that."""
import html
import re
import time
from datetime import datetime

import httpx

from .. import classify, db

SITE = "https://www.jobbank.gc.ca/"
SEARCH = SITE + "jobsearch/jobsearch"
POSTING = SITE + "jobsearch/jobposting/"
PROVINCES = {"AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"}
DELAY = 5            # seconds between requests (robots.txt: Crawl-delay: 5)
DETAILS_PER_RUN = 45  # posting pages read per run, HR first; the rest are picked up by the next hourly run
DEEP_EVERY_HOURS = 6  # how often every page of every search is read (other runs read the newest page only)
MAX_PAGES = {"hr": 14, "swe": 4, "data": 3}  # per occupation code, 25 postings a page
KEYWORD_PAGES = 6     # keyword searches match loosely, so most of what matters is in the first pages

# NOC 2021 occupation codes (fn21) and keyword searches.
DEFAULT_SEARCHES = [  # cat: the category occupation-code results get (the code already says what the job is)
    {"fn21": "10011", "cat": "hr"},   # human resources managers
    {"fn21": "11200", "cat": "hr"},   # human resources professionals (advisers, business partners, labour relations)
    {"fn21": "12101", "cat": "hr"},   # human resources and recruitment officers
    {"fn21": "13102", "cat": "hr"},   # payroll administrators
    {"fn21": "14102", "cat": "hr"},   # personnel clerks (HR assistants, HR clerks, staffing clerks)
    {"searchstring": "human resources", "cat": "hr"},
    {"searchstring": "HR", "cat": "hr"},
    {"searchstring": "recruitment", "cat": "hr"},
    {"searchstring": "recruiter", "cat": "hr"},
    {"searchstring": "payroll", "cat": "hr"},
    {"searchstring": "talent acquisition", "cat": "hr"},
    {"searchstring": "people and culture", "cat": "hr"},
    {"searchstring": "labour relations", "cat": "hr"},
    {"searchstring": "staffing", "cat": "hr"},
    {"searchstring": "compensation benefits", "cat": "hr"},
    {"fn21": "21231", "cat": "swe"},  # software engineers and designers
    {"fn21": "21232", "cat": "swe"},  # software developers and programmers
    {"fn21": "21234", "cat": "swe"},  # web developers and programmers
    {"fn21": "21220", "cat": "swe"},  # cybersecurity specialists
    {"fn21": "21222", "cat": "swe"},  # information systems specialists
    {"fn21": "21211", "cat": "data"},  # data scientists
    {"fn21": "21223", "cat": "data"},  # database analysts and data administrators
    {"searchstring": "data analyst", "cat": "data"},
]


def _text(fragment: str) -> str:
    """Plain text; some postings carry HTML that was escaped once more, so tags are stripped before and after unescaping."""
    plain = html.unescape(re.sub(r"<[^>]+>", " ", fragment or ""))
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", plain)).strip()


def details(page: str) -> tuple[str, str]:
    """(description, job type label) from a posting page. The description starts with the facts people filter on:
    "Start date: as soon as possible. Permanent employment, Full time. 30 hours per week." then the posting's own text."""
    def grab(pattern):
        m = re.search(pattern, page, re.S)
        return _text(m.group(1)) if m else ""
    start = grab(r'fa-calendar[^>]*></span>\s*<span>(.*?)</span>')          # "Starts as soon as possible" / "Starts 2026-12-01"
    terms = grab(r'property="employmentType"[^>]*>(.*?)</span>\s*</span>')   # "Permanent employment Full time"
    hours = grab(r"property=.workHours.[^>]*>(.*?)</span>")                  # "30 hours per week"
    body = grab(r'<span class="hidden" property="description">(.*?)</span>')
    start = re.sub(r"^starts?\s*", "", start, flags=re.I)
    facts = [f"Start date: {start}" if start else "", terms, hours]
    return (". ".join(f for f in facts if f) + ". " + body).strip(". ")[:5000], terms


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


def _results(page: str) -> list[dict]:
    """The postings on one search-results page."""
    out = []
    for m in re.finditer(r'<article id="article-(\d+)"(.*?)</article>', page, re.S):
        block = m.group(2)

        def field(cls, tag="li"):
            f = re.search(rf'<{tag} class="{cls}">(.*?)</{tag}>', block, re.S)
            return _text(f.group(1)) if f else ""
        try:  # Job Bank gives the posting date only
            posted = classify.day_start(datetime.strptime(field("date"), "%B %d, %Y").replace(hour=12).timestamp())
        except ValueError:
            posted = None
        out.append({"url": POSTING + m.group(1), "title": _title(field("noctitle", "span")), "company": field("business"),
                    "location": _location(re.sub(r"^Location\s*", "", field("location"))),
                    "salary": re.sub(r"^Salary\s*", "", field("salary")), "posted_at": posted})
    return out


def fetch(cfg: dict, max_age_days: int) -> list[dict]:
    cutoff = time.time() - max_age_days * 86400
    deep = bool(cfg.get("deep")) or int(time.time() // 3600) % DEEP_EVERY_HOURS == 0
    found, seen = [], set()
    with httpx.Client(headers={"User-Agent": "Mozilla/5.0 (job-portal)"}, timeout=30, follow_redirects=True) as c:
        for search in cfg.get("searches") or DEFAULT_SEARCHES:
            cat, by_code = search.get("cat", ""), "fn21" in search
            params = {k: v for k, v in search.items() if k != "cat"}
            pages = (MAX_PAGES.get(cat, 2) if by_code else KEYWORD_PAGES) if deep else 1
            for page in range(1, pages + 1):
                try:
                    r = c.get(SEARCH, params={**params, "sort": "D", "page": page})
                except httpx.HTTPError:
                    break
                time.sleep(DELAY)
                rows = _results(r.text) if r.status_code == 200 else []
                recent = 0  # sorted newest first: once a whole page is older than the cutoff, the rest is too
                for f in rows:
                    if f["posted_at"] and f["posted_at"] < cutoff:
                        continue
                    recent += 1
                    if f["url"] in seen:
                        continue
                    hr_title = bool(classify.HR_TITLE.search(f["title"]))
                    # occupation-code searches are exact; keyword searches also match unrelated ads, so an HR
                    # keyword search keeps only HR titles, and the others are classified by title like everything else
                    if cat == "hr" and not by_code and not hr_title:
                        continue
                    seen.add(f["url"])
                    found.append({**f, "source_category": cat if by_code else "", "hr": cat == "hr"})
                if len(rows) < 25 or not recent:  # the last page, or everything from here on is too old
                    break
        # Read the page of each posting that has no details yet: HR first (people look for immediate-start HR jobs).
        have = db.described_urls(SITE)
        todo = sorted((f for f in found if f["url"] not in have), key=lambda f: not f["hr"])[:int(cfg.get("details_per_run", DETAILS_PER_RUN))]
        for f in todo:
            try:
                r = c.get(f["url"])
                if r.status_code == 200:
                    f["description"], f["job_type"] = details(r.text)
            except httpx.HTTPError:
                pass
            time.sleep(DELAY)
    return [classify.build(source_type="jobbank", source_name="Job Bank Canada", posted_precision="day",
                           **{k: v for k, v in f.items() if k != "hr"}) for f in found]
