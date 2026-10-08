# Job Portal · built by JAI SHARMA
"""Fetch jobs from GitHub job-list repos (SimplifyJobs-style JSON, or README tables)."""
import html
import json
import re
import time
from datetime import datetime

import httpx

from .. import classify

RAW = "https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
BRANCHES = ("dev", "main", "master")
HEADERS = {"User-Agent": "job-portal/1.0"}


def parse_repo(url: str) -> tuple[str, str, str | None]:
    m = re.search(r"github\.com/([^/\s]+)/([^/\s#?]+)(?:/(?:tree|blob)/([^/\s#?]+))?", url)
    if not m:
        raise ValueError(f"Not a GitHub repo URL: {url}")
    return m.group(1), m.group(2).removesuffix(".git"), m.group(3)


def _get(client: httpx.Client, owner: str, repo: str, branches, path: str) -> str | None:
    for b in branches:
        r = client.get(RAW.format(owner=owner, repo=repo, branch=b, path=path))
        if r.status_code == 200:
            return r.text
    return None


def fetch(source: dict, max_age_days: int) -> list[dict]:
    owner, repo, branch = parse_repo(source["url"])
    branches = [branch] if branch else BRANCHES
    name = source.get("name") or f"{owner}/{repo}"
    hint = source.get("level", "")
    cutoff = time.time() - max_age_days * 86400
    with httpx.Client(headers=HEADERS, timeout=60, follow_redirects=True) as client:
        raw = _get(client, owner, repo, branches, ".github/scripts/listings.json")
        if raw:
            return _from_listings(json.loads(raw), name, hint, cutoff)
        readme = _get(client, owner, repo, branches, "README.md")
        if readme is None:
            raise RuntimeError("Found neither listings.json nor README.md")
        category = source.get("category", "")  # optional hint: swe | data | finance
        if re.search(r"^\|\s*Role\s*\|\s*Links\s*\|", readme, re.M | re.I):
            return _from_role_sections(readme, name, hint, category)
        return _from_readme(readme, name, hint, cutoff, category)


def _from_listings(items: list[dict], name: str, hint: str, cutoff: float) -> list[dict]:
    jobs = []
    for it in items:
        if not it.get("active", True) or not it.get("is_visible", True):
            continue
        posted = int(it.get("date_posted") or it.get("date_updated") or 0) or None
        if posted and posted < cutoff:
            continue
        locs = it.get("locations") or []
        sponsorship = it.get("sponsorship") or ""
        jobs.append(classify.build(
            source_type="github", source_name=name,
            company=it.get("company_name", ""), title=it.get("title", ""),
            location=" · ".join(locs[:3]) + (f" +{len(locs) - 3}" if len(locs) > 3 else ""),
            url=it.get("url", ""), posted_at=posted, level_hint=hint,
            source_category=it.get("category", ""),
            sponsorship_text="" if sponsorship == "Other" else sponsorship,
        ))
    return jobs


# ---------- README tables (Markdown pipes or HTML) ----------

COLS = {
    "company": r"company|employer|organization",
    "title": r"role|position|title|job",
    "location": r"location",
    "link": r"appl|link|posting|url",
    "age": r"age|date|posted",
    "salary": r"salary|pay|comp",
}


def _rows(text: str) -> list[list[str]]:
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S | re.I):
        rows.append(re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S | re.I))
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|") and not re.fullmatch(r"\|[\s:\-|]+\|?", s):
            rows.append([c.strip() for c in s.strip("|").split("|")])
    return rows


def _text(cell: str) -> str:
    cell = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", cell)
    cell = re.sub(r"<[^>]+>", " ", cell)
    cell = cell.replace("**", "").replace("__", "")
    return re.sub(r"\s+", " ", html.unescape(cell)).strip()


def _link(cell: str) -> str:
    m = re.search(r'href="([^"]+)"', cell) or re.search(r"\]\((https?://[^)\s]+)\)", cell) or re.search(r"(https?://\S+)", cell)
    return html.unescape(m.group(1)) if m else ""


def parse_age(s: str, now: float | None = None) -> tuple[int | None, str]:
    """"5h" / "3d" / "Sep 20" → (unix time, precision). Day-level ages map to the start of that day."""
    now = now or time.time()
    s = (s or "").strip().lower()
    m = re.fullmatch(r"(\d+)\s*(min|mo|m|h|d|w|y)\w*", s)
    if m:
        n, u = int(m.group(1)), m.group(2)
        if u == "min":
            return int(now - n * 60), "exact"
        if u == "h":
            return int(now - n * 3600), "hour"
        days = {"d": 1, "w": 7, "mo": 30, "m": 30, "y": 365}[u] * n
        return classify.day_start(now - days * 86400), "day"
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%b %d", "%B %d", "%d %b"):
        try:
            d = datetime.strptime(s.title() if "%b" in fmt or "%B" in fmt else s, fmt)
        except ValueError:
            continue
        if "%Y" not in fmt:
            d = d.replace(year=datetime.fromtimestamp(now).year)
            if d.timestamp() > now + 86400:
                d = d.replace(year=d.year - 1)
        return int(d.timestamp()), "day"
    return None, "exact"


ROLE_NAMES = {"QD": "Quantitative Developer", "QR": "Quantitative Researcher", "QT": "Quantitative Trader",
              "SWE": "Software Engineer", "HW": "Hardware Engineer", "FPGA": "FPGA Engineer", "ML": "Machine Learning Engineer"}


def _from_role_sections(text: str, name: str, hint: str, category: str) -> list[dict]:
    """Lists laid out as one "## Company" section each, with a |Role|Links| table (e.g. NU Fintech quant internships).
    Only links marked ✅ (open) are kept. These lists carry no posting dates."""
    jobs, company, location = [], "", ""
    suffix = " Intern" if hint == "internship" else ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("## "):
            company, location = line[3:].strip(), ""
        elif line.lower().startswith("**locations**"):
            location = _text(line.split(":", 1)[-1])
        elif line.startswith("|") and company and not re.fullmatch(r"\|[\s:\-|]+\|?", line):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 2 or cells[0].lower() == "role":
                continue
            role = ROLE_NAMES.get(cells[0], cells[0])
            for label, url in re.findall(r"\[([^\]]*)\]\((https?://[^)\s]+)\)", cells[1]):
                if "✅" not in label:
                    continue
                label = label.replace("✅", "").strip()
                jobs.append(classify.build(
                    source_type="github", source_name=name, company=company,
                    title=f"{role}{suffix}" + (f" ({label})" if label else ""), location=location, url=url,
                    posted_at=None, level_hint=hint, source_category=category or "finance"))
    return jobs


def _from_readme(text: str, name: str, hint: str, cutoff: float, category: str = "") -> list[dict]:
    jobs, colmap, last_company, width = [], None, "", 0
    for cells in _rows(text):
        plain = [_text(c) for c in cells]
        if any(re.fullmatch(r"company|employer", p, re.I) for p in plain):  # header row
            width = len(cells)
            colmap = {}
            for key, pat in COLS.items():
                for i, p in enumerate(plain):
                    if i not in colmap.values() and re.search(pat, p, re.I):
                        colmap[key] = i
                        break
            continue
        if not colmap or "company" not in colmap or "title" not in colmap:
            continue
        if len(cells) != width:  # a stray "|" inside a cell shifted the columns: skip rather than misread it
            continue

        def cell(key, raw=False):
            i = colmap.get(key)
            if i is None or i >= len(cells):
                return ""
            return cells[i] if raw else plain[i]

        company = cell("company")
        if company.startswith("↳") or not company:
            company = last_company
        else:
            last_company = company
        title, flags = cell("title"), cell("company", True) + cell("title", True)
        link_cell = cell("link", True) if "link" in colmap else cell("title", True)
        if "🔒" in link_cell or "🔒" in flags:
            continue  # closed
        posted, precision = parse_age(cell("age")) if "age" in colmap else (None, "exact")
        if posted and posted < cutoff:
            continue
        sponsorship = ("U.S. Citizenship is Required" if "🇺🇸" in flags
                       else "Does Not Offer Sponsorship" if "🛂" in flags else "")
        jobs.append(classify.build(
            source_type="github", source_name=name,
            company=re.sub(r"[🔥🛂🇺🇸🎓🔒⭐️]", "", company).strip(),
            title=re.sub(r"[🔥🛂🇺🇸🎓🔒⭐️]", "", title).strip(),
            location=cell("location"), url=_link(link_cell), posted_at=posted, posted_precision=precision,
            salary=cell("salary"), level_hint=hint, sponsorship_text=sponsorship, source_category=category,
        ))
    return [j for j in jobs if j["title"] and j["company"]]
