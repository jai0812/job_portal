# Job Portal · built by JAI SHARMA
"""Startup radar: who is starting up, raising money and launching, rebuilt from public sources every day.

Sources (free, no keys, no sign-ins):
  - Y Combinator's company directory (the yc-oss mirror): every active YC company with tags, stage and hiring status.
    Each company's YC page names its founders and their LinkedIn; that's read when someone opens the company
    (and ahead of time for the newest batches), never for all 4,000+ at once.
  - SEC Form D filings: a US company raising private money files one within 15 days. It gives the amount, the year the
    company was formed, its industry and its executives' names. Funds, real estate and companies older than five
    years are skipped.
  - Funding & startup news (TechCrunch, Crunchbase News, Sifted, EU-Startups, BetaKit, Inc42) and Launch HN posts.

Stages: early (pre-seed / seed / angel), second (Series A-B), advanced (Series C and later, growth).
When only the amount is known (SEC filings), the stage is estimated from it.

Nothing here guesses or collects people's personal emails: the contacts shown are the company's own public addresses
(role addresses like hello@ / founders@ on its website), the company phone in its SEC filing, and LinkedIn profiles
the founders list publicly on their YC page (or a LinkedIn search link).
"""
import gc
import gzip
import hashlib
import html
import json
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx

from . import db

UA = {"User-Agent": "SharmaJai-Job-Portal/1.0 (+https://jobs.sharmajai.com; startup radar)"}
YC_ALL = "https://yc-oss.github.io/api/companies/all.json"
SEC_INDEX = "https://www.sec.gov/Archives/edgar/daily-index/{y}/QTR{q}/form.{d}.idx"
SEC_DOC = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/primary_doc.xml"
HN = "https://hn.algolia.com/api/v1/search_by_date"
NEWS_FEEDS = {
    "TechCrunch": "https://techcrunch.com/category/startups/feed/",
    "TechCrunch Venture": "https://techcrunch.com/category/venture/feed/",
    "Crunchbase News": "https://news.crunchbase.com/feed/",
    "Sifted": "https://sifted.eu/feed",
    "EU-Startups": "https://www.eu-startups.com/feed/",
    "BetaKit": "https://betakit.com/feed/",
    "Inc42": "https://inc42.com/feed/",
}
# Worth following yourself: shown on the Startups tab.
RECOMMENDED = [
    ("Y Combinator companies", "https://www.ycombinator.com/companies", "Every YC startup, by batch and industry"),
    ("Work at a Startup", "https://www.workatastartup.com/", "YC's own job board"),
    ("Crunchbase News", "https://news.crunchbase.com/", "Funding rounds and the weekly biggest-rounds list"),
    ("TechCrunch Venture", "https://techcrunch.com/category/venture/", "Funding and VC news"),
    ("Launch HN", "https://news.ycombinator.com/launches", "YC companies launching, with founders in the comments"),
    ("Product Hunt", "https://www.producthunt.com/", "New products every day"),
    ("Wellfound", "https://wellfound.com/jobs", "Startup jobs with salary and equity"),
    ("Sifted", "https://sifted.eu/", "European startups"),
    ("BetaKit", "https://betakit.com/", "Canadian startups"),
    ("Inc42", "https://inc42.com/", "Indian startups"),
    ("SEC Form D search", "https://efts.sec.gov/LATEST/search-index?forms=D", "Raw private-funding filings"),
    ("a16z portfolio", "https://a16z.com/portfolio/", "Who a top VC has backed"),
]

STAGES = {"early": "Early stage", "second": "Second round (Series A-B)", "advanced": "Advanced (Series C+)"}
CATEGORIES = [  # (id, label, words): a startup gets up to three, by how many of the words its text uses
    ("ai", "🤖 AI & ML", r"\bai\b|artificial intelligence|machine learning|\bml\b|\bllms?\b|generative|\bagents?\b|agentic"
                        r"|computer vision|\bnlp\b|deep learning|foundation model|\bgpt"),
    ("devtools", "🛠️ Developer tools", r"developer|devtools|\bapis?\b|open[- ]source|\bsdk|devops|database|observability"
                                       r"|\btesting\b|infrastructure|\bcloud\b|kubernetes|compute"),
    ("fintech", "💳 Fintech", r"fintech|payments?|banking|\blending|insurtech|\binsurance|\bcredit\b|accounting|invoic"
                             r"|payroll|wealth|trading|stablecoin|financ"),
    ("health", "🧬 Health & bio", r"health|medical|clinic|patient|biotech|therapeut|\bdrugs?\b|pharma|genom|diagnos|hospital"
                                  r"|healthcare|\bbio\b|biolog|oncolog|cancer"),
    ("robotics", "🦾 Robotics & hardware", r"robot|hardware|drones?|manufactur|semiconductor|\bchips?\b|sensors?|industrial"
                                          r"|autonomous|physical ai|3d print"),
    ("climate", "🌱 Climate & energy", r"climate|energy|solar|batter(y|ies)|carbon|\bgrid\b|sustainab|\bev\b|electrif|nuclear"
                                      r"|fusion|geotherm|hydrogen"),
    ("security", "🔐 Security", r"security|cyber|fraud|identity|compliance|privacy|threat"),
    ("data", "📊 Data & analytics", r"\bdata\b|analytics|business intelligence|\betl\b|warehouse|dashboards?"),
    ("saas", "🏢 B2B & SaaS", r"\bb2b\b|saas|enterprise|workflow|\bsales\b|\bcrm\b|marketing|recruit|productivity|\blegal\b"
                             r"|operations|back[- ]office|customer support|procurement"),
    ("consumer", "🛍️ Consumer", r"consumer|\bb2c\b|social|e-?commerce|retail|\bfood\b|travel|gaming|\bgames?\b|media"
                               r"|creators?|fashion|dating|fitness|music|\bpets?\b"),
    ("crypto", "🪙 Crypto & web3", r"crypto|blockchain|web3|defi\b|bitcoin|ethereum|\btokens?\b|solana"),
    ("edu", "🎓 Education", r"education|edtech|learning|tutor|students?|school"),
    ("defense", "🚀 Defense & space", r"defen[cs]e|military|\bspace\b|satellite|aerospace|rockets?|national security"),
    ("mobility", "🚚 Mobility & logistics", r"logistic|supply chain|freight|shipping|mobility|transport|delivery|fleet|trucking"),
    ("proptech", "🏠 Real estate & construction", r"real estate|propert|proptech|construction|housing|mortgage|home ?buy"),
]
_CAT_RX = [(cid, re.compile(words, re.I)) for cid, _, words in CATEGORIES]

SCHEMA = """
CREATE TABLE IF NOT EXISTS startups (
    id          TEXT PRIMARY KEY,   -- normalised name
    name        TEXT, website TEXT, one_liner TEXT, description TEXT,
    categories  TEXT,               -- comma list of CATEGORIES ids
    tags        TEXT,               -- the source's own tags, comma list
    stage       TEXT,               -- early | second | advanced | ''
    round       TEXT,               -- "Seed", "Series A"... when a source says it
    amount      REAL,               -- latest raise, US dollars
    raised_at   INTEGER,            -- when that raise was announced / filed
    location    TEXT, batch TEXT, team_size INTEGER, hiring INTEGER DEFAULT 0, founded INTEGER,
    yc_url      TEXT, linkedin TEXT, -- the company's YC page and LinkedIn page
    people      TEXT,               -- JSON [{name, title, linkedin}] founders / executives
    people_at   INTEGER,            -- when people was last read from YC
    phone       TEXT, email TEXT, email_checked INTEGER DEFAULT 0,
    sources     TEXT,               -- comma list: yc, sec, news, hn
    added       INTEGER,            -- when it appeared (YC listing date, filing date, first news item)
    first_seen  INTEGER, updated_at INTEGER
);
CREATE TABLE IF NOT EXISTS startup_news (
    id TEXT PRIMARY KEY, startup_id TEXT, title TEXT, url TEXT, source TEXT, published INTEGER,
    amount REAL, round TEXT, funding INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_snews_pub ON startup_news(published);
"""
_status = {"running": False, "last": 0, "last_news": 0, "log": [], "built": 0}
_payload = {"gz": None}
_lock = threading.Lock()


# ---------------------------------------------------------------- helpers

_LEGAL = re.compile(r"[,.]?\s+(inc|incorporated|llc|l\.l\.c|corp|corporation|co|ltd|limited|plc|pbc|gmbh|s\.?a\.?s?|b\.?v)\.?$", re.I)


def key(name: str) -> str:
    n = html.unescape(name or "").strip()
    while _LEGAL.search(n):
        n = _LEGAL.sub("", n).strip()
    return re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")


def clean_name(name: str) -> str:
    n = html.unescape(name or "").strip()
    while _LEGAL.search(n):
        n = _LEGAL.sub("", n).strip()
    return n.title() if n.isupper() and len(n) > 4 else n  # SEC names are often ALL CAPS


def categorize(*texts) -> list[str]:
    text = " ".join(t for t in texts if t)
    scores = sorted(((len(rx.findall(text)), cid) for cid, rx in _CAT_RX), reverse=True)
    return [cid for n, cid in scores if n][:3] or ["other"]


_ROUND = re.compile(r"pre-?seed|seed|angel|pre-series [a-c]|series [a-h]\b|growth|late[- ]stage|bridge", re.I)


def stage_of(round_name: str = "", amount: float | None = None) -> str:
    r = (round_name or "").lower()
    if re.search(r"pre-?seed|\bseed|angel|pre-series a", r):
        return "early"
    if re.search(r"series [ab]\b|pre-series [bc]", r):
        return "second"
    if re.search(r"series [c-h]\b|growth|late", r):
        return "advanced"
    if amount:  # only the size is known: a rough guess
        return "early" if amount < 5e6 else "second" if amount < 40e6 else "advanced"
    return ""


_AMOUNT = re.compile(r"(US\$|CA\$|C\$|A\$|\$|€|£|₹|Rs\.?\s?|INR\s?|EUR\s?|USD\s?)\s?(\d+(?:[.,]\d+)?)\s?"
                     r"(billion|bn|b\b|million|mn|mln|m\b|crore|cr\b|lakh|k\b)?", re.I)
_FX = {"€": 1.08, "eur": 1.08, "£": 1.27, "ca$": 0.73, "c$": 0.73, "a$": 0.66, "₹": 0.012, "rs": 0.012, "inr": 0.012}


def amount_usd(text: str) -> float | None:
    m = _AMOUNT.search(text or "")
    if not m:
        return None
    cur, num, unit = m.group(1).strip().lower().rstrip("."), float(m.group(2).replace(",", "")), (m.group(3) or "").lower()
    mult = {"billion": 1e9, "bn": 1e9, "b": 1e9, "million": 1e6, "mn": 1e6, "mln": 1e6, "m": 1e6, "crore": 1e7, "cr": 1e7,
            "lakh": 1e5, "k": 1e3}.get(unit, 1)
    usd = num * mult * _FX.get(cur, 1)
    return usd if usd >= 50_000 else None


# "Fintech startup Ramp raises $500M Series E" → Ramp, $500M, Series E
_RAISES = re.compile(r"^(?:exclusive:\s*)?(?P<co>.{2,70}?)\s+(?:raises|lands|secures|closes|bags|nabs|snags|scores|picks up"
                     r"|pulls in|banks|grabs|collects|gets|announces|completes|emerges from stealth with)\s+(?P<rest>.+)$", re.I)
_DESCRIPTOR = re.compile(r"^.*\b(startup|start-up|company|platform|maker|firm|provider|developer|unicorn|upstart|outfit|"
                         r"specialist|scaleup|scale-up|spinout|spin-out)\s+", re.I)
_NOT_STARTUP = re.compile(r"\b(ventures|capital|partners|fund|vc|investors?|accelerator|government|ministry)\b", re.I)


def parse_funding(title: str) -> dict | None:
    t = html.unescape(title or "").strip()
    m = _RAISES.match(t)
    if not m:
        return None
    co, rest = m.group("co").strip(" ,:–-"), m.group("rest")
    co = _DESCRIPTOR.sub("", co).strip(" ,:–-'’\"")
    co = re.sub(r"^.*\b[\w.]+-based\s+", "", co)  # "Bengaluru-based Zepto" → Zepto
    if not co or len(co.split()) > 4 or _NOT_STARTUP.search(co) or re.search(r"\bfunds?\b", rest[:40], re.I):
        return None
    amt = amount_usd(rest)
    rnd = _ROUND.search(rest)
    if not amt and not rnd:
        return None
    rnd = rnd.group(0).title().replace("Pre-Seed", "Pre-seed") if rnd else ""
    return {"name": co, "amount": amt, "round": rnd}


def _get(c: httpx.Client, url: str, **kw):
    for i in range(3):
        try:
            r = c.get(url, **kw)
            if r.status_code in (429, 503):
                time.sleep(5 * (i + 1))
                continue
            return r
        except httpx.HTTPError:
            time.sleep(3)
    return None


# ---------------------------------------------------------------- storage

def init() -> None:
    with db.WRITE_LOCK, db.conn() as c:
        c.executescript(SCHEMA)


# Which source is trusted for what: YC describes the company best; news and SEC filings know the latest round.
# These fields only fill a blank when they come from that source.
FILL_ONLY = {"yc": set(), "sec": {"name", "one_liner", "categories", "tags", "location", "people"},
             "news": {"name", "one_liner", "categories", "website", "batch", "location"}}
_FIELDS = ("name", "website", "one_liner", "description", "categories", "tags", "stage", "round", "amount", "raised_at",
           "location", "batch", "team_size", "hiring", "founded", "yc_url", "linkedin", "people", "phone", "added")


def save(rows: list[dict], source: str) -> int:
    """Merge startups into the table: new facts fill in or update, nothing known is blanked. Returns how many were new."""
    if not rows:
        return 0
    now = int(time.time())
    with db.conn() as c:
        have = {r["id"]: dict(r) for r in c.execute(
            f"SELECT * FROM startups WHERE id IN ({','.join('?' * len(rows))})", [r["id"] for r in rows])} \
            if len(rows) < 900 else {r["id"]: dict(r) for r in c.execute("SELECT * FROM startups")}
    out, new = [], 0
    for r in rows:
        old = have.get(r["id"])
        if not old:
            new += 1
            old = {"id": r["id"], "first_seen": now, "sources": "", "email": None, "email_checked": 0, "people_at": None}
        row = dict(old)
        for f in _FIELDS:
            v = r.get(f)
            if v is None or v == "" or (v == 0 and f != "hiring") or (f in FILL_ONLY.get(source, ()) and old.get(f)):
                continue
            if f == "stage" and source == "yc" and (old.get("round") or old.get("amount")):
                continue  # a real funding round beats YC's early / growth label
            if f in ("amount", "raised_at", "round", "stage") and old.get("raised_at") and r.get("raised_at") \
                    and r["raised_at"] < old["raised_at"]:
                continue  # an older round doesn't replace the latest one
            if f == "added" and old.get("added"):
                v = min(old["added"], v)
            row[f] = v
        row["sources"] = ",".join(sorted(set(filter(None, (old.get("sources") or "").split(","))) | {source}))
        row["categories"] = row.get("categories") or "other"
        row["updated_at"] = now
        out.append(row)
    cols = ["id", "first_seen", "updated_at", "sources", "email", "email_checked", "people_at"] + list(_FIELDS)
    sql = f"INSERT OR REPLACE INTO startups ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})"
    for i in range(0, len(out), 300):  # short write transactions, like the job writes
        with db.WRITE_LOCK, db.conn() as c:
            c.executemany(sql, [[r.get(k) for k in cols] for r in out[i:i + 300]])
    return new


def save_news(items: list[dict]) -> None:
    if not items:
        return
    cols = ["id", "startup_id", "title", "url", "source", "published", "amount", "round", "funding"]
    with db.WRITE_LOCK, db.conn() as c:
        c.executemany(f"INSERT OR IGNORE INTO startup_news ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                      [[n.get(k) for k in cols] for n in items])


# ---------------------------------------------------------------- sources

def from_yc(c: httpx.Client) -> int:
    r = _get(c, YC_ALL, timeout=120)
    data = r.json() if r is not None and r.status_code == 200 else []
    rows = []
    for x in data:
        if x.get("status") != "Active" or x.get("nonprofit"):
            continue
        tags = x.get("tags") or []
        text = " ".join([x.get("one_liner") or "", x.get("long_description") or "", " ".join(tags), x.get("industry") or "",
                         x.get("subindustry") or ""])
        rows.append({
            "id": key(x["name"]), "name": x["name"].strip(), "website": x.get("website") or "",
            "one_liner": (x.get("one_liner") or "")[:200], "description": (x.get("long_description") or "")[:350],
            "categories": ",".join(categorize(text)), "tags": ",".join(tags[:8]),
            "stage": _yc_stage(x),
            "location": x.get("all_locations") or ", ".join((x.get("regions") or [])[:2]), "batch": x.get("batch") or "",
            "team_size": x.get("team_size") or None, "hiring": int(bool(x.get("isHiring"))), "yc_url": x.get("url") or "",
            "added": x.get("launched_at") or None,
        })
    del data
    gc.collect()
    return save(rows, "yc")


def _yc_stage(x: dict) -> str:
    """YC only says Early or Growth. Early companies with a real team, or a few years past their batch, have
    usually raised a Series A (an estimate)."""
    if x.get("stage") == "Growth":
        return "advanced"
    year = int((re.search(r"(20\d\d)", x.get("batch") or "") or [0, 0])[1] or 0)
    team = x.get("team_size") or 0
    if team >= 25 or (year and datetime.now().year - year >= 3 and team >= 10):
        return "second"
    return "early"


_SEC_SKIP = re.compile(r"\b(funds?|l\.?\s?p\.?|partners|capital|ventures|investors?|holdings|trust|reit|realty|propert(y|ies)"
                       r"|apartments|real estate|equity|portfolio|feeder|offshore|master|spv|co-?invest|opportunit(y|ies)|income"
                       r"|credit|lending|mortgage|bancorp|bank|insurance|royalt|oil|gas|associates|investments?|acquisition"
                       r"|a series of|series [a-z0-9]+ of|dst)\b", re.I)
_SEC_INDUSTRIES = {"Other Technology", "Computers", "Telecommunications", "Biotechnology", "Pharmaceuticals",
                   "Other Health Care", "Health Insurance", "Energy Conservation", "Environmental Services", "Other Energy",
                   "Business Services", "Manufacturing", "Other Banking and Financial Services"}


def from_sec(c: httpx.Client, days: int) -> int:
    """Form D filings from the last `days` days by young (≤5 years) tech / health / energy companies."""
    rows, today = [], datetime.now(timezone.utc).date()
    for back in range(days, -1, -1):
        d = today - timedelta(days=back)
        if d.weekday() >= 5:
            continue
        r = _get(c, SEC_INDEX.format(y=d.year, q=(d.month - 1) // 3 + 1, d=d.strftime("%Y%m%d")), timeout=60)
        if r is None or r.status_code != 200:
            continue
        for line in r.text.splitlines():
            if not re.match(r"^D\s{2,}", line) or _SEC_SKIP.search(line[17:79]):
                continue
            path = line.split()[-1]
            cik, acc = path.split("/")[2], path.split("/")[-1][:-4].replace("-", "")
            x = _get(c, SEC_DOC.format(cik=cik, acc=acc), timeout=30)
            time.sleep(0.15)  # SEC asks for at most 10 requests a second
            if x is None or x.status_code != 200:
                continue
            try:
                row = _form_d(ET.fromstring(x.content), d)
            except ET.ParseError:
                row = None
            if row:
                rows.append(row)
    return save(rows, "sec")


def _form_d(t, filed) -> dict | None:
    text = lambda p: (t.findtext(p) or "").strip()  # noqa: E731
    industry = text(".//industryGroupType")
    if text(".//yearOfInc/withinFiveYears") != "true" or industry not in _SEC_INDUSTRIES:
        return None
    sold = float(text(".//totalAmountSold") or 0) or None
    if not sold or sold < 100_000:
        return None
    name = clean_name(text(".//primaryIssuer/entityName"))
    people = []
    for p in t.findall(".//relatedPersonInfo"):
        who = " ".join(x for x in (p.findtext(".//firstName"), p.findtext(".//lastName")) if x and x.strip() not in ("N/A", "-"))
        roles = [r.text for r in p.findall(".//relationship") if r.text]
        if who and "Promoter" not in roles:
            people.append({"name": who.strip().title() if who.isupper() else who.strip(),
                           "title": " / ".join("Executive" if r == "Executive Officer" else r for r in roles)})
    city, state = text(".//issuerAddress/city"), text(".//issuerAddress/stateOrCountry")
    ts = int(datetime(filed.year, filed.month, filed.day, tzinfo=timezone.utc).timestamp())
    return {
        "id": key(name), "name": name, "one_liner": f"{industry} · raised ${sold / 1e6:.1f}M (SEC Form D)",
        "categories": ",".join(categorize(name, industry.replace("Other ", ""))), "tags": industry,
        "stage": stage_of(amount=sold), "amount": sold, "raised_at": ts,
        "location": ", ".join(x.title() if x.isupper() and len(x) > 2 else x for x in (city, state) if x),
        "founded": int(text(".//yearOfInc/value") or 0) or None, "people": json.dumps(people[:5]) if people else "",
        "phone": text(".//issuerPhoneNumber"), "added": ts,
    }


def _rss(c: httpx.Client, url: str) -> list[dict]:
    r = _get(c, url, timeout=30)
    if r is None or r.status_code != 200:
        return []
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError:
        return []
    items = []
    for it in root.iter("item"):
        title, link = (it.findtext("title") or "").strip(), (it.findtext("link") or "").strip()
        try:
            pub = int(parsedate_to_datetime(it.findtext("pubDate") or "").timestamp())
        except (TypeError, ValueError):
            pub = int(time.time())
        if title and link:
            items.append({"title": html.unescape(title), "url": link, "published": pub})
    return items


def from_news(c: httpx.Client) -> int:
    news, rows = [], []
    for source, url in NEWS_FEEDS.items():
        for it in _rss(c, url):
            f = parse_funding(it["title"])
            sid = key(f["name"]) if f else None
            news.append({**it, "id": hashlib.sha1(it["url"].encode()).hexdigest()[:16], "source": source,
                         "startup_id": sid, "amount": f and f["amount"], "round": f and f["round"], "funding": int(bool(f))})
            if f:
                rows.append({"id": sid, "name": f["name"], "round": f["round"], "amount": f["amount"],
                             "stage": stage_of(f["round"], f["amount"]), "raised_at": it["published"], "added": it["published"],
                             "categories": ",".join(categorize(it["title"])), "one_liner": it["title"][:200]})
    # Launch HN: YC companies launching, usually "Launch HN: Name (YC W24) – what it does"
    r = _get(c, HN, params={"tags": "story", "query": "Launch HN", "hitsPerPage": 100,
                            "numericFilters": f"created_at_i>{int(time.time()) - 30 * 86400}"}, timeout=30)
    for h in (r.json().get("hits") if r is not None and r.status_code == 200 else []):
        m = re.match(r"Launch HN:\s*(.+?)\s*\((?:YC\s*)?([A-Z]\d{2})\)\s*[–—:-]\s*(.+)", h.get("title") or "")
        if not m:
            continue
        name, batch, what = m.groups()
        url = h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}"
        news.append({"id": "hn" + h["objectID"], "title": h["title"], "url": f"https://news.ycombinator.com/item?id={h['objectID']}",
                     "source": "Launch HN", "published": h.get("created_at_i"), "startup_id": key(name), "funding": 0})
        rows.append({"id": key(name), "name": name, "one_liner": what[:200], "batch": batch, "website": url if h.get("url") else "",
                     "categories": ",".join(categorize(what)), "added": h.get("created_at_i"), "stage": "early"})
    save_news(news)
    # one row per startup: several news items can name the same one
    merged = {}
    for r_ in rows:
        merged.setdefault(r_["id"], {}).update({k: v for k, v in r_.items() if v})
    return save(list(merged.values()), "news")


# ---------------------------------------------------------------- founders & contacts

def _yc_page(c: httpx.Client, url: str) -> dict | None:
    r = _get(c, url, timeout=30)
    m = r is not None and r.status_code == 200 and re.search(r'data-page="([^"]+)"', r.text)
    if not m:
        return None
    co = (json.loads(html.unescape(m.group(1))).get("props") or {}).get("company") or {}
    people = [{"name": f.get("full_name", ""), "title": f.get("title") or "Founder", "linkedin": f.get("linkedin_url") or "",
               "twitter": f.get("twitter_url") or ""} for f in co.get("founders") or [] if f.get("full_name")]
    return {"people": people, "linkedin": co.get("linkedin_url") or "", "founded": co.get("year_founded")}


def people(sid: str) -> dict:
    """Founders for one startup: from its YC page (cached two weeks), else the SEC filing's executives."""
    with db.conn() as c:
        row = c.execute("SELECT * FROM startups WHERE id=?", (sid,)).fetchone()
    if not row:
        return {"people": [], "linkedin": ""}
    row = dict(row)
    if row.get("yc_url") and (not row.get("people_at") or time.time() - row["people_at"] > 14 * 86400):
        with httpx.Client(headers=UA, follow_redirects=True) as c:
            got = _yc_page(c, row["yc_url"])
        if got:
            row.update(people=json.dumps(got["people"]), linkedin=got["linkedin"] or row.get("linkedin"),
                       founded=got["founded"] or row.get("founded"))
        with db.WRITE_LOCK, db.conn() as c:
            c.execute("UPDATE startups SET people=?, linkedin=?, founded=?, people_at=? WHERE id=?",
                      (row.get("people"), row.get("linkedin"), row.get("founded"), int(time.time()), sid))
    return {"people": json.loads(row.get("people") or "[]"), "linkedin": row.get("linkedin") or "",
            "founded": row.get("founded"), "email": row.get("email") or "", "phone": row.get("phone") or ""}


_ROLE_EMAIL = re.compile(r"^(hello|hi|hey|contact|info|team|founders?|careers|jobs|hiring|press|partnerships?|sales|support"
                         r"|inquiries|enquiries|business|general|media|work)$", re.I)


def _site_email(c: httpx.Client, website: str) -> str:
    """The company's own role address (hello@ / founders@ / careers@...) from its home page, if it shows one."""
    host = re.sub(r"^www\.", "", httpx.URL(website).host or "")
    r = _get(c, website, timeout=15)
    if r is None or r.status_code != 200 or not host:
        return ""
    for e in re.findall(r"mailto:([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", r.text):
        local, dom = e.lower().split("@", 1)
        if (dom == host or dom.endswith("." + host)) and _ROLE_EMAIL.match(local):
            return e.lower()
    return ""


def enrich(c: httpx.Client, budget_s: int = 240) -> None:
    """A few minutes a day: founders for the newest YC companies and the public contact address for recent startups."""
    stop = time.time() + budget_s
    with db.conn() as d:
        yc = [dict(r) for r in d.execute("SELECT id, yc_url FROM startups WHERE yc_url != '' AND people_at IS NULL "
                                         "ORDER BY COALESCE(added, 0) DESC LIMIT 60")]
        sites = [dict(r) for r in d.execute("SELECT id, website FROM startups WHERE website LIKE 'http%' AND email_checked = 0 "
                                            "ORDER BY COALESCE(raised_at, added, 0) DESC LIMIT 120")]
    for r in yc:
        if time.time() > stop:
            break
        got = _yc_page(c, r["yc_url"])
        with db.WRITE_LOCK, db.conn() as d:
            d.execute("UPDATE startups SET people=COALESCE(?, people), linkedin=COALESCE(NULLIF(?, ''), linkedin), "
                      "founded=COALESCE(?, founded), people_at=? WHERE id=?",
                      (got and json.dumps(got["people"]), got and got["linkedin"], got and got["founded"], int(time.time()), r["id"]))
        time.sleep(1)
    for r in sites:
        if time.time() > stop:
            break
        try:
            email = _site_email(c, r["website"])
        except Exception:
            email = ""
        with db.WRITE_LOCK, db.conn() as d:
            d.execute("UPDATE startups SET email=COALESCE(NULLIF(?, ''), email), email_checked=1 WHERE id=?", (email, r["id"]))


# ---------------------------------------------------------------- the daily run and the page's copy

def run(full: bool = True, sec_days: int = 3) -> None:
    """full: YC directory + SEC filings + news + founders (daily). Otherwise news and Launch HN only (every few hours)."""
    if _status["running"]:
        return
    _status["running"] = True
    log = []
    try:
        with httpx.Client(headers=UA, follow_redirects=True, timeout=30) as c:
            steps = [("news", lambda: from_news(c))]
            if full:
                steps = [("yc", lambda: from_yc(c)), ("sec", lambda: from_sec(c, sec_days))] + steps + \
                        [("enrich", lambda: enrich(c) or 0)]
            for name, fn in steps:
                t = time.time()
                try:
                    log.append(f"{name}: {fn()} new in {time.time() - t:.0f}s")
                except Exception as e:  # one broken source shouldn't stop the others
                    log.append(f"{name}: failed ({str(e)[:120]})")
        _status["last_news"] = int(time.time())
        if full:
            _status["last"] = int(time.time())
            with db.WRITE_LOCK, db.conn() as d:
                d.execute("INSERT OR REPLACE INTO meta VALUES ('startups_last_full', ?)", (str(_status["last"]),))
        build()
    finally:
        _status.update(running=False, log=log)
        print("startup radar: " + "; ".join(log), flush=True)


def build() -> None:
    """The Startups tab's data, gzipped once: every startup, the latest news and the job counts."""
    with db.conn() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM startups")]
        news = [dict(r) for r in c.execute("SELECT * FROM startup_news ORDER BY published DESC LIMIT 400")]
        jobs = {r[0]: r[1] for r in c.execute(
            "SELECT lower(company), count(*) FROM jobs WHERE COALESCE(posted_at, first_seen) > ? GROUP BY 1",
            (int(time.time()) - 45 * 86400,))}
        newsn = {r[0]: r[1] for r in c.execute("SELECT startup_id, count(*) FROM startup_news WHERE startup_id IS NOT NULL GROUP BY 1")}
    out = []
    for r in rows:
        out.append({k: v for k, v in {
            "id": r["id"], "name": r["name"], "website": r["website"], "one_liner": r["one_liner"],
            "description": r["description"], "cats": (r["categories"] or "other").split(","), "tags": r["tags"],
            "stage": r["stage"], "round": r["round"], "amount": r["amount"], "raised_at": r["raised_at"],
            "location": r["location"], "batch": r["batch"], "team_size": r["team_size"], "hiring": r["hiring"],
            "founded": r["founded"], "yc_url": r["yc_url"], "linkedin": r["linkedin"],
            "people": json.loads(r["people"]) if r["people"] else None, "phone": r["phone"], "email": r["email"],
            "src": (r["sources"] or "").split(","), "added": r["added"] or r["first_seen"],
            "jobs": jobs.get((r["name"] or "").lower()), "news": newsn.get(r["id"]),
        }.items() if v not in (None, "", [], 0)})
    body = {"now": int(time.time()), "last_full": _status["last"], "startups": out, "news": news,
            "categories": [[cid, label] for cid, label, _ in CATEGORIES], "stages": STAGES,
            "recommended": [{"name": n, "url": u, "about": a} for n, u, a in RECOMMENDED]}
    _payload["gz"] = gzip.compress(json.dumps(body, separators=(",", ":")).encode(), 5)
    _status["built"] = body["now"]
    try:
        (db.DB_PATH.parent / "startups_cache.json.gz").write_bytes(_payload["gz"])
    except OSError:
        pass


def payload() -> bytes | None:
    if _payload["gz"] is None:
        try:
            _payload["gz"] = (db.DB_PATH.parent / "startups_cache.json.gz").read_bytes()
        except OSError:
            build()
    return _payload["gz"]


def loop(busy=lambda: False) -> None:
    """News every 3 hours; the full scan once a day, early morning US time. busy(): a job refresh is running, so wait."""
    init()
    with db.conn() as c:
        row = c.execute("SELECT value FROM meta WHERE key='startups_last_full'").fetchone()
    _status["last"] = int(row[0]) if row else 0
    time.sleep(240)  # let the portal finish starting up first
    while True:
        try:
            if not busy():
                hour = datetime.now(timezone.utc).hour
                if not _status["last"]:
                    run(full=True, sec_days=30)  # first run: a month of SEC filings
                elif time.time() - _status["last"] > 20 * 3600 and 8 <= hour <= 12:  # ~4-8 AM US Eastern
                    run(full=True)
                elif time.time() - _status["last_news"] > 3 * 3600:
                    run(full=False)
        except Exception as e:
            print(f"startup radar failed, will retry: {e}", flush=True)
        time.sleep(600)
