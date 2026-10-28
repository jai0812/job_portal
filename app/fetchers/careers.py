# Job Portal · built by JAI SHARMA
"""Pull job postings straight from employers' own career sites.

Supported systems: Workday, Oracle HCM, SmartRecruiters, Greenhouse, Lever, Ashby and Phenom.
Used for the Universities page and for the finance firms in config/finance_firms.yaml.
"""
import json
import re
import time
from datetime import datetime

import httpx

from .. import classify, geo

MAX_PER_FEED = 1000
# For employers that aren't tech companies (Nike, Verizon, Pfizer…): keep only IT / software / data / ML roles.
TECH_ROLES = re.compile(
    r"software|developer|programmer|full.?stack|front.?end|back.?end|devops|\bsre\b|site reliability|cloud|cyber|infosec"
    r"|information security|security (engineer|analyst|architect)|data (scien|engineer|analy|architect|platform|govern|manage)"
    r"|machine learning|\bml\b|\bai\b|artificial intelligence|deep learning|\bnlp\b|\bllm|generative|computer vision"
    r"|analytics|business intelligence|\bbi\b|statistic|biostatistic|quantitative|bioinformatic|computational"
    r"|(research|applied|decision) scientist|platform engineer|systems? (engineer|analyst|architect|admin)|solutions? architect"
    r"|\bit\b|information technology|information systems|database|\bdba\b|network (engineer|architect|admin)"
    r"|technical program|technical product|product manager.*(data|ai|ml|platform|tech)|\bqa\b|test automation|\bsdet\b"
    r"|salesforce|\bsap\b|\berp\b|workday (analyst|developer)|servicenow|automation engineer|firmware|embedded"
    r"|mobile (engineer|developer)|\bios\b|android|web (engineer|developer)|\bapi\b|engineering manager|\bux\b", re.I)
# Most jobs to keep per employer and region, so huge global banks don't drown everything else.
REGION_CAPS = {"us": 1000, "india": 600, "canada": 600, "other": 400}
HEADERS = {"User-Agent": "Mozilla/5.0 (job-portal)"}
TIMEOUT = httpx.Timeout(60, connect=20)


def _client() -> httpx.Client:
    return httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True,
                        transport=httpx.HTTPTransport(retries=2))


# ---------------------------------------------------------------- helpers

def _iso(s) -> int | None:
    if not s:
        return None
    try:
        return int(datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def _workday_age(text: str) -> int:
    """Workday only says "Posted Today" / "Posted Yesterday" / "Posted 3 Days Ago" / "Posted 30+ Days Ago"."""
    t = (text or "").lower()
    if "yesterday" in t:
        return classify.days_ago(1)
    m = re.search(r"(\d+)\+?\s*day", t)
    return classify.days_ago(int(m.group(1)) if m else 0)


class Sink:
    """Collects jobs for one employer: applies the date cutoff, keeps only the wanted regions, caps each region."""

    def __init__(self, owner: dict, cutoff: float, regions=("us",), only: re.Pattern | None = None):
        self.owner, self.cutoff, self.regions, self.jobs = owner, cutoff, set(regions), []
        self.only = only  # when set, keep only titles matching it (HR titles are kept too when the job is in Canada)
        self.counts = dict.fromkeys(REGION_CAPS, 0)
        self.seen: set[str] = set()

    def full(self, region: str) -> bool:
        return region not in self.regions or self.counts[region] >= REGION_CAPS[region]

    def add(self, title, location, url, posted, precision="exact", description="", region=None, known_only=False) -> bool:
        """region forces the tab (from a country filter on the career site); known_only skips unclear locations.
        Returns False when the posting is older than the cutoff."""
        if posted and posted < self.cutoff:
            return False
        if known_only and not geo.detected(location):
            return True
        if region and geo.countries(location) == (geo.US,) and region != "us":
            label = {"india": geo.INDIA, "canada": geo.CANADA}.get(region, "Outside US")
            location = f"{location} · {label}".strip(" ·")
        places = geo.regions(location)
        if self.only and not self.only.search(title or "") and not ("canada" in places and classify.HR_TITLE.search(title or "")):
            return True
        wanted = [r for r in places if not self.full(r)]
        if not wanted or url in self.seen:
            return True
        self.seen.add(url)
        for r in wanted:
            self.counts[r] += 1
        self.jobs.append(classify.build(
            source_type=self.owner["source_type"], source_name=self.owner["source_name"], company=self.owner["company"],
            title=title, location=location, url=url, posted_at=posted or None,  # None = the site gives no date
            posted_precision=precision if posted else "exact", description=description))
        return True


# ---------------------------------------------------------------- one function per career-site system

def workday(f: dict, sink: Sink) -> None:
    base = f"https://{f['tenant']}.{f['wd']}.myworkdayjobs.com"
    api = f"{base}/wday/cxs/{f['tenant']}/{f['site']}/jobs"
    with _client() as c:
        first = c.post(api, json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}).json()
        # Most Workday sites have a country filter, so fetch the US, India and Canada separately; then one unfiltered
        # pass picks up everything else (that pass only keeps jobs in the remaining regions).
        passes = []
        for region, names in (("us", ("United States of America", "United States", "USA")), ("india", ("India",)),
                              ("canada", ("Canada",))):
            if region in sink.regions:
                facet = _workday_facet(first.get("facets") or [], names)
                if facet:
                    passes.append((region, facet))
        done = {r for r, _ in passes}
        if (sink.regions - done):
            passes.append((None, {}))
        for region, facet in passes:
            # In the unfiltered pass, skip places we can't place ("2 Locations"): the country passes covered those.
            _workday_pass(c, base, api, f["site"], facet, region, sink, known_only=region is None and bool(done),
                          cap=f.get("max"))


def _workday_pass(c, base, api, site, facets, region, sink, known_only=False, cap=None) -> None:
    offset, total, old_pages = 0, MAX_PER_FEED, 0
    limit = cap or MAX_PER_FEED * (2 if sink.only else 1)  # look further when most rows will be filtered out
    while offset < min(total, limit):
        if region and sink.full(region):
            break
        if not region and all(sink.full(r) for r in sink.regions):
            break
        r = c.post(api, json={"appliedFacets": facets, "limit": 20, "offset": offset, "searchText": ""})
        r.raise_for_status()
        data = r.json()
        if offset == 0:  # Workday only reports the total on the first page
            total = data.get("total") or 0
        posts = data.get("jobPostings") or []
        if not posts:
            break
        fresh = [sink.add(p.get("title", ""), p.get("locationsText", ""), f"{base}/en-US/{site}{p.get('externalPath', '')}",
                          _workday_age(p.get("postedOn", "")), "day", region=region, known_only=known_only) for p in posts]
        # Results are roughly newest-first; stop after three pages with nothing new enough.
        old_pages = 0 if any(fresh) else old_pages + 1
        if old_pages >= 3:
            break
        offset += 20
        time.sleep(0.3)  # Workday throttles rapid paging


def _workday_facet(facets: list, names) -> dict:
    """Find the country filter value (e.g. "India") in a Workday site's facet list."""
    for f in facets:
        for v in f.get("values") or []:
            if "facetParameter" in v:  # nested facet group
                found = _workday_facet([v], names)
                if found:
                    return found
            elif (v.get("descriptor") or "").strip() in names and "ountry" in f.get("facetParameter", "") + f.get("descriptor", ""):
                return {f["facetParameter"]: [v["id"]]}
    return {}


def oracle(f: dict, sink: Sink) -> None:
    api = f"https://{f['host']}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
    site = f.get("site") or f.get("site_number", "CX_1")
    with _client() as c:
        offset = 0
        while offset < MAX_PER_FEED * 3:  # global lists are long; the US filter drops most of them
            finder = f"findReqs;siteNumber={f.get('site_number', 'CX_1')},limit=25,offset={offset},sortBy=POSTING_DATES_DESC"
            d = c.get(api, params={"onlyData": "true", "expand": "requisitionList", "finder": finder}).json()
            item = (d.get("items") or [{}])[0]
            reqs = item.get("requisitionList") or []
            stop = False
            for p in reqs:
                loc = p.get("PrimaryLocation", "")
                if not sink.add(p.get("Title", ""), loc,
                                f"https://{f['host']}/hcmUI/CandidateExperience/en/sites/{site}/job/{p.get('Id')}",
                                _iso(p.get("PostedDate")), "day", p.get("ShortDescriptionStr", "")):
                    stop = True  # sorted newest first
                    break
            offset += 25
            if stop or not reqs or offset >= item.get("TotalJobsCount", 0) or all(sink.full(r) for r in sink.regions):
                break


def smartrecruiters(f: dict, sink: Sink) -> None:
    cid, offset = f["company"], 0
    with _client() as c:
        while offset < MAX_PER_FEED:
            d = c.get(f"https://api.smartrecruiters.com/v1/companies/{cid}/postings",
                      params={"limit": 100, "offset": offset}).json()
            items = d.get("content") or []
            for p in items:
                loc = p.get("location") or {}
                where = ", ".join(x for x in (loc.get("city"), loc.get("region"), loc.get("country", "").upper()) if x) \
                    or ("Remote" if loc.get("remote") else "")
                sink.add(p.get("name", ""), where, f"https://jobs.smartrecruiters.com/{cid}/{p.get('id')}", _iso(p.get("releasedDate")))
            offset += 100
            if offset >= d.get("totalFound", 0) or not items:
                break


def _plain(html_text: str, limit: int = 5000) -> str:
    """Job description HTML → plain text (Greenhouse sends it HTML-escaped)."""
    import html as _h
    text = re.sub(r"<[^>]+>", " ", _h.unescape(_h.unescape(html_text or "")))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def greenhouse(f: dict, sink: Sink) -> None:
    with _client() as c:
        # content=true includes each job's description in the same request: used to spot
        # "no visa sponsorship" / "US citizens only" and "immediate start" wording
        d = c.get(f"https://boards-api.greenhouse.io/v1/boards/{f['board']}/jobs", params={"content": "true"})
        d.raise_for_status()
        for p in d.json().get("jobs") or []:
            sink.add(p.get("title", ""), (p.get("location") or {}).get("name", ""), p.get("absolute_url", ""),
                     _iso(p.get("first_published") or p.get("updated_at")), description=_plain(p.get("content", "")))


def lever(f: dict, sink: Sink) -> None:
    with _client() as c:
        d = c.get(f"https://api.lever.co/v0/postings/{f['company']}", params={"mode": "json"})
        d.raise_for_status()
        for p in d.json():
            cat = p.get("categories") or {}
            where = "; ".join(cat.get("allLocations") or [cat.get("location") or ""])
            created = p.get("createdAt")
            sink.add(p.get("text", ""), where, p.get("hostedUrl", ""), int(created / 1000) if created else None,
                     description=p.get("descriptionPlain", ""))


def ashby(f: dict, sink: Sink) -> None:
    with _client() as c:
        d = c.get(f"https://api.ashbyhq.com/posting-api/job-board/{f['board']}")
        d.raise_for_status()
        for p in d.json().get("jobs") or []:
            if p.get("isListed") is False:
                continue
            country = ((p.get("address") or {}).get("postalAddress") or {}).get("addressCountry", "")
            where = ", ".join(x for x in (p.get("location", ""), country) if x)
            sink.add(p.get("title", "").strip(), where, p.get("jobUrl", ""), _iso(p.get("publishedAt")),
                     description=p.get("descriptionPlain", ""))


def phenom(f: dict, sink: Sink) -> None:
    """Phenom career sites embed the search results as JSON in the page (10 per page)."""
    with _client() as c:
        offset, total = 0, MAX_PER_FEED
        while offset < min(total, MAX_PER_FEED):
            html = c.get(f"https://{f['host']}/{f.get('locale', 'us/en')}/search-results", params={"from": offset, "s": 1}).text
            m = re.search(r"phApp\.ddo\s*=\s*(\{.*?\});\s*phApp", html, re.S)
            data = (json.loads(m.group(1)) if m else {}).get("eagerLoadRefineSearch") or {}
            total = data.get("totalHits") or 0
            posts = (data.get("data") or {}).get("jobs") or []
            if not posts:
                break
            for p in posts:
                where = p.get("cityStateCountry") or p.get("location") or ""
                url = p.get("applyUrl") or f"https://{f['host']}/{f.get('locale', 'us/en')}/job/{p.get('jobSeqNo', '')}"
                sink.add(p.get("title", ""), where, url, _iso(p.get("postedDate")), "day")
            offset += len(posts)
            time.sleep(0.3)


def amazon(f: dict, sink: Sink) -> None:
    """amazon.jobs public search, one country at a time (country: ISO-3 code like IND or USA).
    categories (optional) limits it to job families such as software-development, so warehouse roles stay out."""
    with _client() as c:
        for category in f.get("categories") or [None]:
            offset = 0
            while offset < MAX_PER_FEED:
                params = {"normalized_country_code[]": f.get("country", "IND"), "result_limit": 100, "offset": offset,
                          "sort": "recent", "base_query": f.get("query", "")}
                if category:
                    params["category[]"] = category
                d = c.get("https://www.amazon.jobs/en/search.json", params=params).json()
                jobs = d.get("jobs") or []
                stop = False
                for p in jobs:
                    try:
                        posted = int(datetime.strptime(p.get("posted_date", ""), "%B %d, %Y").timestamp())
                    except ValueError:
                        posted = None
                    if not sink.add(p.get("title", ""), p.get("location", ""), "https://www.amazon.jobs" + p.get("job_path", ""),
                                    posted, "day", p.get("description_short", "")):
                        stop = True
                        break
                offset += 100
                if stop or not jobs or offset >= (d.get("hits") or 0):
                    break


def _get_json(c: httpx.Client, url: str, tries: int = 4, **kw):
    """GET that waits and retries when the site says "slow down" (HTTP 429) or sends a non-JSON page."""
    for attempt in range(tries):
        r = c.get(url, **kw)
        if r.status_code == 200:
            try:
                return r.json()
            except ValueError:
                pass
        time.sleep(6 * (attempt + 1))
    raise RuntimeError(f"{url.split('/')[2]} kept refusing requests (HTTP {r.status_code})")


def microsoft(f: dict, sink: Sink) -> None:
    """Microsoft careers search: 10 per page, newest first, strict rate limit (so go slowly)."""
    with _client() as c:
        for location in f.get("locations") or ["United States"]:
            start = 0
            while start < MAX_PER_FEED:
                d = _get_json(c, "https://apply.careers.microsoft.com/api/pcsx/search", params={
                    "domain": "microsoft.com", "query": "", "location": location, "start": start, "sort_by": "timestamp"})["data"]
                posts = d.get("positions") or []
                stop = False
                for p in posts:
                    where = "; ".join(", ".join(reversed(x.split(", "))) for x in (p.get("locations") or [])[:3])
                    if not sink.add(p.get("name", ""), where, "https://apply.careers.microsoft.com" + p.get("positionUrl", ""),
                                    p.get("postedTs")):
                        stop = True  # sorted newest first
                        break
                start += 10
                if stop or not posts or start >= (d.get("count") or 0):
                    break
                time.sleep(1.5)


def eightfold(f: dict, sink: Sink) -> None:
    """Eightfold-powered career sites (e.g. Netflix): {host, domain}."""
    with _client() as c:
        start = 0
        while start < MAX_PER_FEED:
            d = _get_json(c, f"https://{f['host']}/api/apply/v2/jobs",
                          params={"domain": f["domain"], "start": start, "num": 10, "sort_by": "new"})
            posts = d.get("positions") or []
            stop = False
            for p in posts:
                where = "; ".join(x.replace(",", ", ") for x in (p.get("locations") or [p.get("location", "")])[:3])
                # t_create is midnight UTC of the posting day, so it's a date, not a time
                if not sink.add(p.get("name", ""), where, p.get("canonicalPositionUrl", ""), p.get("t_create"), "day"):
                    stop = True
                    break
            start += len(posts)
            if stop or not posts or start >= (d.get("count") or 0):
                break
            time.sleep(0.4)


def tiktok(f: dict, sink: Sink) -> None:
    """TikTok / ByteDance careers. The site doesn't publish posting dates, so jobs are dated when first seen."""
    with _client() as c:
        offset = 0
        while offset < 3000 and not all(sink.full(r) for r in sink.regions):
            r = c.post("https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts",
                       json={"recruitment_id_list": [], "job_category_id_list": [], "subject_id_list": [],
                             "location_code_list": [], "keyword": "", "limit": 100, "offset": offset},
                       headers={"website-path": "tiktok", "accept-language": "en-US"})
            r.raise_for_status()
            posts = (r.json().get("data") or {}).get("job_post_list") or []
            if not posts:
                break
            for p in posts:
                parts, node = [], p.get("city_info")
                while node:
                    if node.get("en_name") and node["en_name"] not in parts:
                        parts.append(node["en_name"])
                    node = node.get("parent")
                sink.add(p.get("title", ""), ", ".join(parts), f"https://lifeattiktok.com/search/{p.get('id')}", None,
                         description=(p.get("requirement") or "")[:4000], known_only=True)
            offset += 100
            time.sleep(0.3)


FETCHERS = {"amazon": amazon, "microsoft": microsoft, "eightfold": eightfold, "tiktok": tiktok, "workday": workday, "oracle": oracle, "smartrecruiters": smartrecruiters, "greenhouse": greenhouse,
            "lever": lever, "ashby": ashby, "phenom": phenom}


def fetch(feeds: list[dict], owner: dict, max_age_days: int, regions=("us", "india", "other"), tech_only=False) -> list[dict]:
    """owner = {source_type, source_name, company}. Fetches every feed; one retry on timeouts."""
    sink = Sink(owner, time.time() - max_age_days * 86400, regions, TECH_ROLES if tech_only else None)
    for feed in feeds:
        fn = FETCHERS[feed["type"]]
        try:
            fn(feed, sink)
        except (httpx.TimeoutException, ValueError):  # slow, or a throttled/empty reply: wait and try once more
            time.sleep(10)
            fn(feed, sink)
    return sink.jobs
