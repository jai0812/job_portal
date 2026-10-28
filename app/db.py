# Job Portal · built by JAI SHARMA
"""SQLite storage: jobs (shared by everyone), user accounts, and each user's own marks (status, notes)."""
import json
import sqlite3
import threading
import time
from contextlib import contextmanager

from .config import DB_PATH, env

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
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT NOT NULL UNIQUE COLLATE NOCASE,
    pw_hash     TEXT NOT NULL DEFAULT '',
    role        TEXT NOT NULL DEFAULT 'user',   -- admin | user
    active      INTEGER NOT NULL DEFAULT 1,
    sv          INTEGER NOT NULL DEFAULT 1,      -- session version: bumped to sign this user out everywhere
    created_at  INTEGER,
    last_login  INTEGER,
    profile     TEXT,                            -- quick-copy bar (links, snippets), JSON
    email       TEXT                             -- optional: can sign in with this instead of the username
);
-- Each user's own status / notes per job (the jobs table's status columns are from before accounts existed).
CREATE TABLE IF NOT EXISTS marks (
    user_id     INTEGER NOT NULL,
    job_id      TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'new',
    notes       TEXT NOT NULL DEFAULT '',
    applied_at  INTEGER,
    updated_at  INTEGER,
    PRIMARY KEY (user_id, job_id)
);
CREATE INDEX IF NOT EXISTS idx_marks_job ON marks(job_id);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
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
        if "email" not in {r["name"] for r in c.execute("PRAGMA table_info(users)")}:
            c.execute("ALTER TABLE users ADD COLUMN email TEXT")
        done = {r[0] for r in c.execute("SELECT key FROM meta")}
        # Accounts: the first admin comes from the single password the portal had before accounts existed.
        if not c.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
            c.execute("INSERT INTO users (username, pw_hash, role, created_at) VALUES (?,?,'admin',?)",
                      (env("PORTAL_ADMIN_USER", "jai"), env("PORTAL_PASSWORD_HASH"), int(time.time())))
        admin = c.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()[0]
        if "marks_from_jobs" not in done:  # your applied / waiting / declined jobs and notes become the admin's
            c.execute("INSERT OR IGNORE INTO marks SELECT ?, id, status, COALESCE(notes,''), applied_at, ? FROM jobs "
                      "WHERE status != 'new' OR COALESCE(notes,'') != ''", (admin, int(time.time())))
            c.execute("INSERT INTO meta VALUES ('marks_from_jobs', '1')")
        if "hr_tag_v1" not in done:  # tag existing HR / recruiting titles with the new "hr" category
            from .classify import HR_TITLE
            rows = c.execute("SELECT id, title, categories FROM jobs WHERE categories NOT LIKE '%hr%'").fetchall()
            tagged = [(",".join(sorted((set(r[2].split(",")) - {"other"}) | {"hr"})), r[0])
                      for r in rows if HR_TITLE.search(r[1] or "")]
            c.executemany("UPDATE jobs SET categories=? WHERE id=?", tagged)
            c.execute("INSERT INTO meta VALUES ('hr_tag_v1', '1')")
    _users_changed()


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
    """Recent jobs, plus every job anyone has saved or applied to, however old."""
    cutoff = int(time.time()) - max_age_days * 86400
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM jobs WHERE COALESCE(posted_at, first_seen) >= ? "
            "OR id IN (SELECT job_id FROM marks WHERE status NOT IN ('new', 'hidden')) "
            "ORDER BY COALESCE(posted_at, first_seen) DESC", (cutoff,))
        return [dict(r) for r in rows]


# ---------------------------------------------------------------- each user's marks (status, notes)

def marks(user_id: int) -> dict:
    """{job id: [status, notes, applied_at]} for every job this user has touched."""
    with conn() as c:
        return {r[0]: [r[1], r[2], r[3]] for r in c.execute(
            "SELECT job_id, status, notes, applied_at FROM marks WHERE user_id=?", (user_id,))}


def decision_counts(user_id: int) -> dict:
    with conn() as c:
        return {r[0]: r[1] for r in c.execute(
            "SELECT status, COUNT(*) FROM marks WHERE user_id=? AND status IN ('waiting','declined') GROUP BY status", (user_id,))}


def applied_jobs(user_id: int) -> list[dict]:
    with conn() as c:
        rows = c.execute(f"SELECT j.*, m.status AS m_status, m.notes AS m_notes, m.applied_at AS m_applied FROM marks m "
                         f"JOIN jobs j ON j.id = m.job_id WHERE m.user_id=? AND m.status IN {APPLIED_STAGES} "
                         f"ORDER BY m.applied_at DESC", (user_id,))
        out = []
        for r in rows:
            d = dict(r)
            d["status"], d["notes"], d["applied_at"] = d.pop("m_status"), d.pop("m_notes"), d.pop("m_applied")
            out.append(d)
        return out


def get_job(job_id: str) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(r) if r else None


def set_status(user_id: int, job_id: str, status: str, notes: str | None = None) -> dict | None:
    """Moving into any applied stage stamps applied_at once; moving back to new/saved clears it."""
    now = int(time.time())
    with conn() as c:
        if not c.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone():
            return None
        old = c.execute("SELECT notes, applied_at FROM marks WHERE user_id=? AND job_id=?", (user_id, job_id)).fetchone()
        note = notes if notes is not None else (old[0] if old else "")
        applied = ((old[1] if old else None) or now) if status in APPLIED_STAGES else None
        if status == "new" and not note:
            c.execute("DELETE FROM marks WHERE user_id=? AND job_id=?", (user_id, job_id))
        else:
            c.execute("INSERT OR REPLACE INTO marks VALUES (?,?,?,?,?,?)", (user_id, job_id, status, note, applied, now))
        return {"status": status, "applied_at": applied, "notes": note}


# ---------------------------------------------------------------- user accounts

_users: dict | None = None  # id -> user, cached: read on every request, changed rarely
_users_lock = threading.Lock()


def _users_changed() -> None:
    global _users
    with _users_lock:
        _users = None


def all_users() -> dict[int, dict]:
    global _users
    with _users_lock:
        if _users is None:
            with conn() as c:
                _users = {r["id"]: dict(r) for r in c.execute("SELECT * FROM users")}
        return _users


def user_by_name(username: str) -> dict | None:
    """By username or email, ignoring case."""
    name = (username or "").strip().lower()
    return next((u for u in all_users().values() if name in (u["username"].lower(), (u.get("email") or "").lower())), None)


def admin_user() -> dict:
    return min((u for u in all_users().values() if u["role"] == "admin"), key=lambda u: u["id"])


def create_user(username: str, pw_hash: str, role: str = "user", email: str = "") -> int:
    with conn() as c:
        cur = c.execute("INSERT INTO users (username, pw_hash, role, created_at, email) VALUES (?,?,?,?,?)",
                        (username.strip(), pw_hash, role, int(time.time()), email.strip().lower() or None))
    _users_changed()
    return cur.lastrowid


def update_user(user_id: int, **fields) -> None:
    """pw_hash / active changes also sign the user out everywhere (sv + 1)."""
    allowed = {k: v for k, v in fields.items() if k in ("pw_hash", "active", "last_login", "profile")}
    if not allowed:
        return
    bump = ", sv = sv + 1" if {"pw_hash", "active"} & allowed.keys() else ""
    with conn() as c:
        c.execute(f"UPDATE users SET {', '.join(f'{k}=?' for k in allowed)}{bump} WHERE id=?", [*allowed.values(), user_id])
    _users_changed()


def delete_user(user_id: int) -> None:
    with conn() as c:
        c.execute("DELETE FROM marks WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM users WHERE id=? AND role != 'admin'", (user_id,))
    _users_changed()


def user_stats() -> dict[int, dict]:
    """Applied count and last activity per user, for the admin's Users page."""
    with conn() as c:
        return {r[0]: {"applied": r[1], "last_active": r[2]} for r in c.execute(
            f"SELECT user_id, SUM(status IN {APPLIED_STAGES}), MAX(updated_at) FROM marks GROUP BY user_id")}


def get_profile(user_id: int) -> dict | None:
    raw = (all_users().get(user_id) or {}).get("profile")
    return json.loads(raw) if raw else None
