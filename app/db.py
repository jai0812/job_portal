# Job Portal · built by JAI SHARMA
"""SQLite storage for jobs and your application status."""
import sqlite3
import time
from contextlib import contextmanager

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id           TEXT PRIMARY KEY,
    source_type  TEXT,           -- github | apify | university | manual
    source_name  TEXT,           -- the list the posted date came from
    sources      TEXT,           -- every list this job appeared on, "|"-separated
    company      TEXT,
    title        TEXT,
    location     TEXT,
    url          TEXT,
    posted_at    INTEGER,        -- unix seconds
    posted_precision TEXT DEFAULT 'exact',  -- exact | hour | day (some lists only say "today" / "3d")
    first_seen   INTEGER,
    categories   TEXT,           -- comma list: swe,finance,data
    level        TEXT,           -- internship | early_career | experienced | unspecified
    h1b          TEXT,           -- yes | likely | no | citizen | unknown
    cap_exempt   INTEGER DEFAULT 0,
    top_company  INTEGER DEFAULT 0,
    salary       TEXT,
    description  TEXT,
    status       TEXT DEFAULT 'new',   -- new | saved | waiting | declined | applied | interviewing | offer | rejected | hidden
    applied_at   INTEGER,              -- when you marked it applied (for analytics)
    notes        TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_jobs_posted ON jobs(posted_at);
CREATE TABLE IF NOT EXISTS fetch_log (
    source TEXT PRIMARY KEY, last_run INTEGER, count INTEGER, error TEXT
);
"""

# Fields a re-fetch may overwrite; status and notes are yours and are never overwritten.
UPDATABLE = ["source_type", "source_name", "company", "title", "location", "url", "posted_at", "posted_precision",
             "categories", "level", "h1b", "cap_exempt", "top_company", "salary", "description"]
NEW_COLUMNS = {"posted_precision": "TEXT DEFAULT 'exact'", "sources": "TEXT", "applied_at": "INTEGER"}
STATUSES = ("new", "saved", "waiting", "declined", "applied", "interviewing", "offer", "rejected", "hidden")
APPLIED_STAGES = ("applied", "interviewing", "offer", "rejected")


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH, timeout=30)  # refresh, fast lane and page loads overlap: wait instead of "database is locked"
    c.execute("PRAGMA journal_mode=WAL")
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init() -> None:
    with conn() as c:
        c.executescript(SCHEMA)
        have = {r["name"] for r in c.execute("PRAGMA table_info(jobs)")}
        for col, decl in NEW_COLUMNS.items():  # upgrade databases created by older versions
            if col not in have:
                c.execute(f"ALTER TABLE jobs ADD COLUMN {col} {decl}")
        c.execute("UPDATE jobs SET sources = source_name WHERE sources IS NULL")
        c.execute("UPDATE jobs SET applied_at = first_seen WHERE applied_at IS NULL AND status IN ('applied','interviewing','offer','rejected')")


# When the same job is on several lists, the date (and the source credited with it) comes from the list
# with the most precise timestamp; among equally precise ones, the earliest date wins.
_RANK = "(CASE {t}.posted_precision WHEN 'exact' THEN 0 WHEN 'hour' THEN 1 ELSE 2 END)"
_TAKE_NEW = (f"(jobs.posted_at IS NULL OR (excluded.posted_at IS NOT NULL AND ({_RANK.format(t='excluded')} < {_RANK.format(t='jobs')}"
             f" OR ({_RANK.format(t='excluded')} = {_RANK.format(t='jobs')} AND excluded.posted_at < jobs.posted_at))))")


def upsert_jobs(jobs: list[dict]) -> list[dict]:
    """Insert or update jobs. Returns the jobs that weren't in the database before (used for alerts)."""
    now = int(time.time())
    if not jobs:
        return []
    cols = ["id", "first_seen", "sources"] + UPDATABLE
    placeholders = ",".join("?" for _ in cols)

    def rule(f):
        if f in ("description", "salary"):  # keep a real value if a later source doesn't have one
            return f"{f}=COALESCE(NULLIF(excluded.{f}, ''), jobs.{f})"
        if f in ("posted_at", "posted_precision", "source_type", "source_name"):
            return f"{f}=CASE WHEN {_TAKE_NEW} THEN excluded.{f} ELSE jobs.{f} END"
        if f == "h1b":  # a known answer beats "unknown"/"likely" from a source with less info
            return f"{f}=CASE WHEN excluded.{f} IN ('unknown','likely') AND jobs.{f} IN ('yes','no','citizen') THEN jobs.{f} ELSE excluded.{f} END"
        return f"{f}=excluded.{f}"
    updates = ",".join(rule(f) for f in UPDATABLE) + (
        ",sources=CASE WHEN instr('|' || COALESCE(jobs.sources, '') || '|', '|' || excluded.source_name || '|') > 0"
        " THEN jobs.sources ELSE COALESCE(jobs.sources || '|', '') || excluded.source_name END")
    sql = f"INSERT INTO jobs ({','.join(cols)}) VALUES ({placeholders}) ON CONFLICT(id) DO UPDATE SET {updates}"
    with conn() as c:
        ids = list({j["id"] for j in jobs})
        existing = set()
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            existing |= {r[0] for r in c.execute(f"SELECT id FROM jobs WHERE id IN ({','.join('?' * len(chunk))})", chunk)}
        c.executemany(sql, [[j["id"], now, j["source_name"]] + [j.get(f) for f in UPDATABLE] for j in jobs])
    seen, new = set(), []
    for j in jobs:
        if j["id"] not in existing and j["id"] not in seen:
            seen.add(j["id"])
            new.append(j)
    return new


def log_fetch(source: str, count: int, error: str = "") -> None:
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO fetch_log VALUES (?,?,?,?)", (source, int(time.time()), count, error))


def fetch_log() -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM fetch_log ORDER BY source")]


def list_jobs(max_age_days: int) -> list[dict]:
    """Recent jobs, plus every job you've saved or applied to, however old."""
    cutoff = int(time.time()) - max_age_days * 86400
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM jobs WHERE COALESCE(posted_at, first_seen) >= ? OR status NOT IN ('new', 'hidden') "
            "ORDER BY COALESCE(posted_at, first_seen) DESC", (cutoff,))
        return [dict(r) for r in rows]


def marks() -> dict:
    """{job id: [status, notes, applied_at]} for every job that isn't plain 'new' with no notes."""
    with conn() as c:
        return {r[0]: [r[1], r[2] or "", r[3]] for r in c.execute(
            "SELECT id, status, notes, applied_at FROM jobs WHERE status != 'new' OR COALESCE(notes, '') != ''")}


def decision_counts() -> dict:
    with conn() as c:
        return {r[0]: r[1] for r in c.execute("SELECT status, COUNT(*) FROM jobs WHERE status IN ('waiting','declined') GROUP BY status")}


def applied_jobs() -> list[dict]:
    with conn() as c:
        rows = c.execute(f"SELECT * FROM jobs WHERE status IN {APPLIED_STAGES} ORDER BY applied_at DESC")
        return [dict(r) for r in rows]


def get_job(job_id: str) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(r) if r else None


def set_status(job_id: str, status: str, notes: str | None = None) -> dict | None:
    """Moving into any applied stage stamps applied_at once; moving back to new/saved clears it."""
    with conn() as c:
        if status in APPLIED_STAGES:
            c.execute("UPDATE jobs SET status=?, applied_at=COALESCE(applied_at, ?) WHERE id=?", (status, int(time.time()), job_id))
        else:
            c.execute("UPDATE jobs SET status=?, applied_at=NULL WHERE id=?", (status, job_id))
        if notes is not None:
            c.execute("UPDATE jobs SET notes=? WHERE id=?", (notes, job_id))
        r = c.execute("SELECT status, applied_at FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(r) if r else None
