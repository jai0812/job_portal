# Job Portal · built by JAI SHARMA
"""Keeps the "Live snapshot" section of README.md up to date after every refresh, and (optionally) pushes
that one file to GitHub. Only public job-market numbers go in: never your applications, notes or keys."""
import re
import subprocess
import time
from collections import Counter
from datetime import datetime

from . import db, finance, geo, h1b
from .config import ROOT, load_more_companies, load_sources, load_universities

README = ROOT / "README.md"
START, END = "<!-- LIVE:START (auto-generated, do not edit by hand) -->", "<!-- LIVE:END -->"
SECTOR = {"swe": "Software Engineering", "data": "Data Science & ML", "finance": "Finance & Banks"}


def _cell(text: str, limit: int = 60) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).replace("|", "/").strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _ago(seconds: float) -> str:
    m = int(seconds // 60)
    return "just now" if m < 1 else f"{m} min ago" if m < 60 else f"{m // 60}h ago" if m < 1440 else f"{m // 1440}d ago"


def snapshot() -> str:
    cfg = load_sources()
    now = time.time()
    jobs = db.list_jobs(int(cfg.get("max_age_days", 45)))
    board = [j for j in jobs if j["source_type"] != "university"]
    legal = {c["name"].lower(): h1b.approvals_for_names(c["uscis"]) for c in load_more_companies() if c.get("uscis")}

    def approvals(company: str) -> int:
        firm = finance.firm_for(company)
        if firm:
            return firm["h1b_fy23"]
        return legal.get((company or "").lower(), h1b.approvals_for_company(company or ""))

    regions = Counter(r for j in board for r in geo.regions(j["location"]))
    day = [j for j in board if now - (j["posted_at"] or j["first_seen"]) < 86400]
    us = [j for j in board if "us" in geo.regions(j["location"])]
    sponsors = sum(1 for j in us if j["h1b"] not in ("no", "citizen") and (j["h1b"] == "yes" or approvals(j["company"]) > 0))
    sectors = Counter(c for j in board for c in (j["categories"] or "").split(",") if c in SECTOR)
    firms = finance.public_list()
    feeds = sum(1 for f in firms if f.get("feeds")) + sum(1 for c in load_more_companies() if c.get("feeds"))
    unis = sum(1 for u in load_universities() if u.get("feed"))

    rows = [
        ("🇺🇸 United States", f"{regions['us']:,}"),
        ("🇮🇳 India", f"{regions['india']:,}"),
        ("🌍 Other countries", f"{regions['other']:,}"),
        ("🎓 University jobs", f"{len(jobs) - len(board):,}"),
        ("🆕 Posted in the last 24 hours", f"{len(day):,}"),
        ("✅ US jobs at employers with H-1B history", f"{sponsors:,} ({round(100 * sponsors / max(len(us), 1))}%)"),
    ] + [(f"{'💻' if k == 'swe' else '📊' if k == 'data' else '🏦'} {SECTOR[k]}", f"{sectors[k]:,}") for k in ("swe", "data", "finance")] + [
        ("🔌 Sources", f"{len(cfg.get('github') or [])} GitHub lists · {feeds} company career sites · {unis} universities · LinkedIn (Apify)"),
    ]

    # Freshest early-career / intern tech & data roles at employers with H-1B history: one per company.
    picks, seen = [], set()
    fresh = sorted((j for j in us if j["posted_at"] and j["posted_precision"] != "day" and j["url"]),
                   key=lambda j: -j["posted_at"])
    for j in fresh:
        cats = set((j["categories"] or "").split(","))
        if j["company"] in seen or j["level"] not in ("early_career", "internship") or not cats & {"swe", "data"}:
            continue
        if j["h1b"] in ("no", "citizen"):
            continue
        n = approvals(j["company"])
        if not n and j["h1b"] != "yes":
            continue
        seen.add(j["company"])
        picks.append((j, n))
        if len(picks) == 15:
            break

    stamp = datetime.now().astimezone().strftime("%b %-d, %Y at %-I:%M %p %Z")
    out = [START, "", f"**Last updated: {stamp}** · refreshed automatically every hour", "",
           "| Right now in the portal | |", "|---|---|"] + [f"| {a} | **{b}** |" for a, b in rows]
    out += ["", "**Freshest early-career tech & data roles at employers with H-1B history**", "",
            "| Company | Role | Location | Posted | H-1B approvals (FY23) | |", "|---|---|---|---|---|---|"]
    for j, n in picks:
        out.append(f"| **{_cell(j['company'], 28)}** | {_cell(j['title'], 58)} | {_cell(j['location'], 28)} | "
                   f"{_ago(now - j['posted_at'])} | {f'{n:,}' if n else 'says it sponsors'} | [Apply ↗]({j['url']}) |")
    if not picks:
        out.append("| | *No fresh matches right now: check back after the next refresh.* | | | | |")
    out += ["", END]
    return "\n".join(out)


def update() -> bool:
    """Rewrite the live section in README.md. Returns True if the file changed."""
    if not README.exists():
        return False
    text = README.read_text()
    if START not in text or END not in text:
        return False
    new = text[:text.index(START)] + snapshot() + text[text.index(END) + len(END):]
    if new == text:
        return False
    README.write_text(new)
    return True


def push_if_due() -> str:
    """Commit and push README.md (only that file) when this folder is a git repo with a GitHub remote.
    Controlled by readme_auto_push / readme_push_hours in config/sources.yaml."""
    cfg = load_sources()
    if not cfg.get("readme_auto_push", True) or not (ROOT / ".git").exists():
        return "skipped"

    def git(*args):
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=60)

    if not git("remote", "get-url", "origin").stdout.strip():
        return "no remote"
    last = git("log", "-1", "--format=%ct", "--grep=^Update live job snapshot").stdout.strip()
    if last and time.time() - int(last) < float(cfg.get("readme_push_hours", 6)) * 3600:
        return "not due"
    if not git("status", "--porcelain", "README.md").stdout.strip():
        return "unchanged"
    git("add", "README.md")
    if git("commit", "-m", "Update live job snapshot", "--", "README.md").returncode != 0:
        return "commit failed"
    return "pushed" if git("push", "origin", "HEAD").returncode == 0 else "push failed"
