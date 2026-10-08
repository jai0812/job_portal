# Job Portal · built by JAI SHARMA
"""Password protection for running the portal on the internet.

Off by default (local use on your own Mac). It turns on as soon as PORTAL_PASSWORD_HASH is set in .env,
which scripts/set_password.py does for you. What it provides:

- the password is never stored: only a salted scrypt hash (slow by design, so guessing is expensive)
- optional second step: 6-digit codes from an authenticator app (TOTP)
- lockout after repeated wrong attempts, per visitor and overall
- sessions are signed cookies (HttpOnly, SameSite=Strict, Secure on https) that expire
- every state-changing request must come from the portal's own page (CSRF protection)
- strict security headers on every response
"""
import base64
import hashlib
import hmac
import json
import secrets
import struct
import threading
import time

from .config import env

SESSION_HOURS = 12
COOKIE = "portal_session"
MAX_FAILS, WINDOW, LOCK = 5, 15 * 60, 15 * 60       # 5 wrong tries in 15 min → locked for 15 min
GLOBAL_MAX_FAILS = 30                               # across all visitors: slows down distributed guessing
SCRYPT = dict(n=2 ** 15, r=8, p=1, dklen=32, maxmem=64 * 1024 * 1024)


def enabled() -> bool:
    return bool(env("PORTAL_PASSWORD_HASH"))


# ---------------------------------------------------------------- password hashing

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def check_password(password: str) -> bool:
    try:
        _, salt, digest = env("PORTAL_PASSWORD_HASH").split("$")
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), **SCRYPT)
    except Exception:
        return False
    return hmac.compare_digest(actual, expected)


# ---------------------------------------------------------------- authenticator-app codes (TOTP, RFC 6238)

_used_codes: set[tuple[int, str]] = set()


def totp_enabled() -> bool:
    return bool(env("PORTAL_TOTP_SECRET"))


def _totp(secret_b32: str, counter: int) -> str:
    key = base64.b32decode(secret_b32.upper() + "=" * (-len(secret_b32) % 8))
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    return f"{(struct.unpack('>I', mac[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


def check_totp(code: str) -> bool:
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(code) != 6:
        return False
    now = int(time.time()) // 30
    for counter in (now - 1, now, now + 1):  # allow one step of clock drift
        if hmac.compare_digest(_totp(env("PORTAL_TOTP_SECRET"), counter), code):
            if (counter, code) in _used_codes:  # each code works once
                return False
            _used_codes.add((counter, code))
            for old in [c for c in _used_codes if c[0] < now - 4]:
                _used_codes.discard(old)
            return True
    return False


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


def record_failure(ip: str) -> None:
    now = time.time()
    with _lock:
        for key, limit in ((ip, MAX_FAILS), ("*", GLOBAL_MAX_FAILS)):
            fails = _recent(key, now)
            fails.append(now)
            if len(fails) >= limit:
                _locked_until[key] = now + LOCK
                _fails[key] = []


def record_success(ip: str) -> None:
    with _lock:
        _fails.pop(ip, None)
        _locked_until.pop(ip, None)


# ---------------------------------------------------------------- signed session cookies

def _sign(payload: bytes) -> str:
    return hmac.new(env("SESSION_SECRET").encode(), payload, hashlib.sha256).hexdigest()


def new_session() -> str:
    payload = base64.urlsafe_b64encode(json.dumps(
        {"exp": int(time.time()) + SESSION_HOURS * 3600, "n": secrets.token_hex(8)}).encode())
    return payload.decode() + "." + _sign(payload)


def valid_session(token: str) -> bool:
    if not token or "." not in token or len(env("SESSION_SECRET")) < 32:
        return False
    payload, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(_sign(payload.encode()), sig):
        return False
    try:
        return json.loads(base64.urlsafe_b64decode(payload))["exp"] > time.time()
    except Exception:
        return False
