# Job Portal · built by JAI SHARMA
"""Accounts and sign-in for running the portal on the internet.

The admin (you) signs in with a username and password and creates accounts for other people from the
Users tab; nobody can sign up on their own. Off on a local Mac until a password is set (scripts/set_password.py).

- passwords are never stored: only salted scrypt hashes (slow by design, so guessing is expensive)
- lockout after repeated wrong attempts, per visitor, per account and overall
- sessions are signed cookies (HttpOnly, SameSite=Strict, Secure on https) that expire; changing a password
  or disabling an account signs that person out everywhere
- every state-changing request must come from the portal's own page (CSRF protection)
"""
import base64
import hashlib
import hmac
import json
import secrets
import threading
import time

from . import db
from .config import env

SESSION_HOURS = 12
COOKIE = "portal_session"
MAX_FAILS, WINDOW, LOCK = 5, 15 * 60, 15 * 60       # 5 wrong tries in 15 min → locked for 15 min
GLOBAL_MAX_FAILS = 30                               # across all visitors: slows down distributed guessing
SCRYPT = dict(n=2 ** 15, r=8, p=1, dklen=32, maxmem=64 * 1024 * 1024)
_DUMMY = None  # a hash to check unknown usernames against, so they take as long as real ones


def enabled() -> bool:
    """Sign-in is required as soon as any account has a password."""
    return any(u["pw_hash"] for u in db.all_users().values())


# ---------------------------------------------------------------- password hashing

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify(pw_hash: str, password: str) -> bool:
    try:
        _, salt, digest = pw_hash.split("$")
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), **SCRYPT)
        return hmac.compare_digest(actual, base64.b64decode(digest))
    except Exception:
        return False


def check_login(username: str, password: str) -> dict | None:
    global _DUMMY
    user = db.user_by_name(username)
    if not (user and user["active"] and user["pw_hash"]):
        _DUMMY = _DUMMY or hash_password(secrets.token_hex(8))
        verify(_DUMMY, password)  # same cost as a real check
        return None
    return user if verify(user["pw_hash"], password) else None


def password_problem(pw: str) -> str:
    """Why a new password isn't good enough ("" when it's fine)."""
    if len(pw) < 8:
        return "Use at least 8 characters."
    if len(set(pw)) < 5:
        return "Too simple: use more different characters."
    return ""


# ---------------------------------------------------------------- lockout after wrong attempts

_lock = threading.Lock()
_fails: dict[str, list[float]] = {}
_locked_until: dict[str, float] = {}


def _recent(key: str, now: float) -> list[float]:
    _fails[key] = [t for t in _fails.get(key, []) if now - t < WINDOW]
    return _fails[key]


def locked_for(ip: str) -> int:
    """Seconds this visitor (or everyone) still has to wait, 0 if they may try."""
    now = time.time()
    with _lock:
        return int(max(_locked_until.get(ip, 0) - now, _locked_until.get("*", 0) - now, 0))


def record_failure(*keys: str) -> None:
    """keys: the visitor's IP and the account they tried ("user:name"); the overall counter is added once."""
    now = time.time()
    with _lock:
        for key, limit in [(k, MAX_FAILS) for k in keys] + [("*", GLOBAL_MAX_FAILS)]:
            fails = _recent(key, now)
            fails.append(now)
            if len(fails) >= limit:
                _locked_until[key] = now + LOCK
                _fails[key] = []


def record_success(*keys: str) -> None:
    with _lock:
        for key in keys:
            _fails.pop(key, None)
            _locked_until.pop(key, None)


# ---------------------------------------------------------------- signed session cookies

def _sign(payload: bytes) -> str:
    return hmac.new(env("SESSION_SECRET").encode(), payload, hashlib.sha256).hexdigest()


def new_session(user: dict) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(
        {"u": user["id"], "v": user["sv"], "exp": int(time.time()) + SESSION_HOURS * 3600, "n": secrets.token_hex(8)}).encode())
    return payload.decode() + "." + _sign(payload)


def session_user(token: str) -> dict | None:
    """The signed-in user for this cookie, or None (expired, tampered with, account disabled or password changed)."""
    if not token or "." not in token or len(env("SESSION_SECRET")) < 32:
        return None
    payload, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(_sign(payload.encode()), sig):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return None
    user = db.all_users().get(data.get("u"))
    if not user or not user["active"] or data.get("v") != user["sv"] or data.get("exp", 0) <= time.time():
        return None
    return user
