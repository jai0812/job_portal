# Job Portal · built by JAI SHARMA
"""Handshake (joinhandshake.com) jobs, imported by hand: Handshake needs your own sign-in, so the portal never logs in.

On a Handshake job-search page, the "Copy jobs from Handshake" bookmark (Handshake tab) copies the jobs on screen as
JSON: {"handshake": [{"id", "url", "title", "lines": [the card's text lines]}]}. Pasting that into the Handshake tab
lands here. Each card's lines are sorted into company / location / posted / job type by what they look like."""
import json
import re
import time

from .. import classify, geo
from .github import parse_age

POSTED = re.compile(r"\b(just now|today|yesterday|(\d+|an?|one)\s*(minute|min|hour|hr|day|week|month)s?\s+ago)\b", re.I)
JOB_TYPE = re.compile(r"^(full[- ]time|part[- ]time|internship|intern|on[- ]campus|fellowship|co-?op|temporary|contract)\b", re.I)
WORK_MODE = re.compile(r"^(remote|onsite|on-site|hybrid)\b", re.I)
NOISE = re.compile(r"^(apply|save|saved|applied|new|promoted|featured|easy apply|quick apply|•|·|\$.*|\d+ applicants?|actively hiring"
                   r"|.*\bper (hour|year|month)\b.*|.*/(hr|yr)\b.*)$", re.I)


def _posted(text: str) -> tuple[int | None, str]:
    t = text.lower()
    now = time.time()
    if "just now" in t:
        return int(now), "exact"
    if "today" in t:
        return classify.day_start(now), "day"
    if "yesterday" in t:
        return classify.day_start(now - 86400), "day"
    m = re.search(r"(\d+|an?|one)\s*(minute|min|hour|hr|day|week|month)s?\s+ago", t)
    if not m:
        return None, "exact"
    n = 1 if m.group(1) in ("a", "an", "one") else int(m.group(1))
    unit = {"minute": "min", "min": "min", "hour": "h", "hr": "h", "day": "d", "week": "w", "month": "mo"}[m.group(2)]
    return parse_age(f"{n}{unit}", now)


def parse(text: str) -> list[dict]:
    """Bookmark JSON (or a plain list of Handshake job links) → job rows ready for db.upsert_jobs."""
    try:
        items = json.loads(text).get("handshake") or []
    except (ValueError, AttributeError):  # plain links, one per line
        items = [{"id": m.group(1), "url": f"https://app.joinhandshake.com/jobs/{m.group(1)}", "title": "", "lines": []}
                 for m in re.finditer(r"joinhandshake\.com/\S*?jobs/(\d+)", text or "")]
    jobs, seen = [], set()
    for it in items:
        jid = str(it.get("id") or "")
        if not jid or jid in seen:
            continue
        seen.add(jid)
        lines = [re.sub(r"\s+", " ", str(l)).strip() for l in it.get("lines") or [] if str(l).strip()]
        title = (it.get("title") or (lines[0] if lines else "") or f"Handshake job {jid}").strip()[:200]
        company = location = kind = ""
        posted, precision = None, "exact"
        for line in lines:
            if line == title or NOISE.match(line):
                continue
            if not posted and POSTED.search(line):
                posted, precision = _posted(line)
                continue
            if not kind and JOB_TYPE.match(line):
                kind = line
                continue
            if not location and (WORK_MODE.match(line) or geo.detected(line) or re.search(r", [A-Z]{2}\b", line)):
                location = line
                continue
            if not company and len(line) <= 80:
                company = line
        jobs.append(classify.build(
            source_type="handshake", source_name="Handshake", company=company or "Handshake employer", title=title,
            location=location, url=it.get("url") or f"https://app.joinhandshake.com/jobs/{jid}", posted_at=posted,
            posted_precision=precision,
            level_hint="internship" if re.search(r"intern|co-?op", kind, re.I) else "early_career"))
    return jobs
