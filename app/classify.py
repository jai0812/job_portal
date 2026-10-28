# Job Portal · built by JAI SHARMA
"""Turn raw job fields into tagged rows: category, level, H-1B, cap-exempt, top company."""
import hashlib
import re
import time
from datetime import datetime
from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .config import load_companies

# HR, recruiting and people-operations roles (the Canada tab's HR section).
HR_TITLE = re.compile(
    r"\bhr\b|\bh\.r\.|human resource|\bhrbp\b|\bhris\b|\brecruit(er|ing|ment)\b|talent acquisition|\bsourcer\b"
    r"|talent (partner|sourcing|coordinator|specialist|advisor|management)|staffing (specialist|coordinator|advis[eo]r)"
    r"|people (operations|ops|partner|business partner|advisor|coordinator|generalist|analyst|experience|team|and culture|& culture)"
    r"|payroll|compensation|total rewards|benefits (specialist|analyst|coordinator|administrator|advis[eo]r)"
    r"|employee (relations|experience|engagement)|labou?r relations|workforce (planning|analyst)|organi[sz]ational development"
    r"|learning (and|&) development|\bl&d\b|onboarding (specialist|coordinator)|diversity|\bdei\b|\bedi\b", re.I)

CATEGORY_PATTERNS = {
    "hr": HR_TITLE.pattern,
    "data": r"data scien|machine learning|\bml\b|\bai\b|artificial intelligence|deep learning|\bnlp\b|computer vision"
            r"|data analy|data engineer|analytics|research scientist|\bllm|applied scientist|statistic|business intelligence",
    "finance": r"\bquant|\btrad(er|ing)\b|investment|banking|financ|risk analy|actuar|portfolio|credit|wealth|asset management"
               r"|treasury|\baudit|accounting|fixed income|equity research|capital markets|underwrit",
    "swe": r"software|developer|\bsde\b|\bswe\b|back.?end|front.?end|full.?stack|devops|\bsre\b|site reliability|platform eng"
           r"|mobile|\bios\b|android|\bweb\b|cloud|infrastructure|systems eng|security eng|programmer|application eng"
           r"|forward deployed|solutions eng|\bqa\b|test automation|embedded software",
}
# Category names used by SimplifyJobs / similar lists.
SOURCE_CATEGORY = {
    "software": "swe", "software engineering": "swe",
    "ai/ml/data": "data", "data science, ai & machine learning": "data",
    "quant": "finance", "quantitative finance": "finance",
    "swe": "swe", "data": "data", "finance": "finance", "hr": "hr",  # per-source hints from config/sources.yaml
}

LEVEL_PATTERNS = [
    ("internship", r"\bintern\b|internship|co-?op\b|\bsummer 20\d\d|apprentice|fellowship"),
    ("experienced", r"senior|\bsr\.?\b|\bstaff\b|principal|\blead\b|manager|director|\bii\b|\biii\b|\biv\b|architect"
                    r"|head of|\bvp\b|\b[3-9]\+? years"),
    ("early_career", r"new grad|graduate|entry|junior|\bjr\.?\b|early career|associate|university|campus|\bi\b|level 1"
                     r"|rotational|analyst program|20(2[5-9]) start|recent grad|college grad"
                     r"|\b(hr|human resources?|recruit\w*|talent acquisition|people|payroll|benefits) (assistant|coordinator|administrator)"),
]

H1B_PATTERNS = [
    ("citizen", r"citizenship is required|must be (a )?u\.?s\.? citizen|security clearance|clearance (is )?required"
                r"|\bts/sci\b|active clearance|us persons? only"),
    ("no", r"does not offer sponsorship|(not|unable to|cannot|can ?not|won'?t) (be able to )?sponsor|no (visa )?sponsorship"
           r"|without (the need for )?(current or future )?(visa )?sponsorship|not eligible for (visa )?sponsorship"),
    ("yes", r"offers sponsorship|(visa|h-?1b) sponsorship (is )?available|\bwill sponsor|sponsorship available"
            r"|we sponsor|open to sponsor"),
]


# Postings that need someone to start right away ("immediate joiner" is the usual Indian phrasing).
IMMEDIATE = re.compile(
    r"immediate(ly)?[ -](start|join|joiner|joining|hire|hiring|opening|need|requirement|availability|available)"
    r"|(start|join|joining|available)\s+(date\s*[:\-]?\s*)?(immediately|asap|right away)|\basap\b"
    r"|urgent(ly)?\s+(hiring|requirement|need|opening|position)"
    r"|notice period[^.]{0,25}?\b(0|immediate|15)\b|\b(0|zero)\s*-\s*(15|30)\s*days?\s*notice|can join (within|in) (15|30) days", re.I)


def immediate(title: str, description: str = "") -> bool:
    return bool(IMMEDIATE.search(title or "") or IMMEDIATE.search(description or ""))


RETAIL_BANKING = re.compile(
    r"\bteller|\bbranch\b|\bbanker\b|client service (associate|representative)|customer service|call center|contact center"
    r"|lending officer|loan officer|financial (solutions )?advisor|wealth advisor|private client advisor|\bhome lending\b"
    r"|\bpart[- ]time\b|\b(20|30) hours?\b", re.I)


def _names_regex(names: list[str]) -> re.Pattern | None:
    names = [n for n in names or [] if n]
    if not names:
        return None
    return re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b", re.I)


@lru_cache(maxsize=1)
def _company_rules():
    c = load_companies()
    return {
        "top": _names_regex(c.get("top_companies")),
        "finance": _names_regex(c.get("finance_companies")),
        "h1b": _names_regex(c.get("h1b_sponsors")),
        "cap_list": _names_regex(c.get("cap_exempt_companies")),
        "cap_kw": re.compile("|".join(re.escape(k) for k in c.get("cap_exempt_keywords") or ["university"]), re.I),
    }


def reload_rules() -> None:
    _company_rules.cache_clear()


def day_start(ts: float) -> int:
    """Local midnight of the day containing ts: used when a source only gives the date, not the time."""
    d = datetime.fromtimestamp(ts)
    return int(d.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


def days_ago(n: int) -> int:
    return day_start(time.time() - n * 86400)


def normalize_url(url: str) -> str:
    if not url:
        return ""
    p = urlsplit(url.strip())
    q = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith("utm_") and k.lower() not in ("ref", "source", "src")]
    return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip("/"), urlencode(q), ""))


def job_id(url: str, company: str, title: str, location: str) -> str:
    key = normalize_url(url) or f"{company}|{title}|{location}".lower()
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def categories(title: str, company: str, source_category: str = "") -> list[str]:
    t = title.lower()
    cats = {k for k, pat in CATEGORY_PATTERNS.items() if re.search(pat, t)}
    if source_category and source_category.lower() in SOURCE_CATEGORY:
        cats.add(SOURCE_CATEGORY[source_category.lower()])
    rules = _company_rules()
    # Working at a bank counts as Finance, except branch / retail jobs (tellers, bankers, advisors, call centre)
    if rules["finance"] and rules["finance"].search(company or "") and not RETAIL_BANKING.search(t):
        cats.add("finance")
    return sorted(cats) or ["other"]


def level(title: str, hint: str = "", seniority: str = "") -> str:
    t = title.lower()
    for name, pat in LEVEL_PATTERNS:
        if re.search(pat, t):
            return name
    s = (seniority or "").lower()
    if "intern" in s:
        return "internship"
    if "entry" in s or "associate" in s:
        return "early_career"
    if any(w in s for w in ("mid", "senior", "director", "executive")):
        return "experienced"
    return hint or "unspecified"


def h1b(company: str, text: str) -> str:
    text = (text or "").lower()
    for label, pat in H1B_PATTERNS:
        if re.search(pat, text):
            return label
    rules = _company_rules()
    if rules["h1b"] and rules["h1b"].search(company or ""):
        return "likely"
    return "unknown"


def cap_exempt(company: str) -> bool:
    rules = _company_rules()
    return bool(rules["cap_kw"].search(company or "") or (rules["cap_list"] and rules["cap_list"].search(company or "")))


def top_company(company: str) -> bool:
    rules = _company_rules()
    return bool(rules["top"] and rules["top"].search(company or ""))


def build(*, source_type: str, source_name: str, company: str, title: str, location: str = "", url: str = "",
          posted_at: int | None = None, posted_precision: str = "exact", description: str = "", salary: str = "", level_hint: str = "",
          seniority: str = "", source_category: str = "", sponsorship_text: str = "") -> dict:
    company, title = (company or "").strip(), (title or "").strip()
    return {
        "id": job_id(url, company, title, location),
        "source_type": source_type,
        "source_name": source_name,
        "company": company,
        "title": title,
        "location": (location or "").strip(),
        "url": url,
        "posted_at": posted_at,
        "posted_precision": posted_precision,
        "categories": ",".join(categories(title, company, source_category)),
        "level": level(title, level_hint, seniority),
        "h1b": h1b(company, f"{sponsorship_text}\n{description}"),
        "cap_exempt": int(cap_exempt(company)),
        "top_company": int(top_company(company)),
        "salary": salary or "",
        "description": description or "",
    }
