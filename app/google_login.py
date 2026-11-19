# Job Portal · built by JAI SHARMA
"""Sign in with Google (OpenID Connect, authorization-code flow with PKCE).

Switched on by two lines in .env, from a Google Cloud "OAuth client ID" of type Web application:
    GOOGLE_CLIENT_ID=....apps.googleusercontent.com
    GOOGLE_CLIENT_SECRET=...
with the redirect URI https://<your domain>/auth/google/callback registered on that client
(or set GOOGLE_REDIRECT_URI to the exact one you registered).

The flow:
  1. /auth/google           a random state, nonce and PKCE verifier go into a short-lived signed cookie;
                            the browser is sent to Google.
  2. Google -> /auth/google/callback?code&state
                            the state must match the cookie; the code is exchanged (with the client secret
                            and the PKCE verifier) for an ID token directly from Google's token endpoint over
                            TLS, which is what makes its contents trustworthy (OpenID Connect Core 3.1.3.7);
                            issuer, audience, expiry, nonce and a verified email are still checked.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlencode

import httpx

from .config import env

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")
COOKIE = "g_oauth"
MAX_AGE = 600  # seconds the person has to finish at Google


def enabled() -> bool:
    return bool(env("GOOGLE_CLIENT_ID") and env("GOOGLE_CLIENT_SECRET"))


def redirect_uri(scheme: str, host: str) -> str:
    return env("GOOGLE_REDIRECT_URI") or f"{scheme}://{host}/auth/google/callback"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _sign(payload: str) -> str:
    return hmac.new(env("SESSION_SECRET").encode(), payload.encode(), hashlib.sha256).hexdigest()


def start(callback: str, mode: str) -> tuple[str, str]:
    """(URL to send the browser to, value for the signed state cookie)."""
    state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    url = AUTH_URL + "?" + urlencode({
        "client_id": env("GOOGLE_CLIENT_ID"), "redirect_uri": callback, "response_type": "code",
        "scope": "openid email profile", "state": state, "nonce": nonce,
        "code_challenge": challenge, "code_challenge_method": "S256", "prompt": "select_account"})
    payload = _b64(json.dumps({"s": state, "n": nonce, "v": verifier, "t": int(time.time()),
                               "m": "signup" if mode == "signup" else "signin"}).encode())
    return url, payload + "." + _sign(payload)


class LoginError(Exception):
    """code: a short name the sign-in page turns into a sentence."""
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _read_cookie(value: str) -> dict:
    if not value or "." not in value:
        raise LoginError("expired")
    payload, sig = value.rsplit(".", 1)
    if not hmac.compare_digest(_sign(payload), sig):
        raise LoginError("expired")
    data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    if time.time() - data.get("t", 0) > MAX_AGE:
        raise LoginError("expired")
    return data


def mode_of(cookie: str) -> str:
    """"signup" or "signin": which tab to send the person back to if something goes wrong."""
    try:
        return _read_cookie(cookie).get("m", "signin")
    except (LoginError, ValueError):
        return "signin"


def finish(callback: str, cookie: str, code: str, state: str) -> dict:
    """The verified Google account: {sub, email, name}. Raises LoginError."""
    saved = _read_cookie(cookie)
    if not state or not hmac.compare_digest(saved["s"], state):
        raise LoginError("expired")
    if not code:
        raise LoginError("cancelled")
    try:
        r = httpx.post(TOKEN_URL, timeout=20, data={
            "code": code, "client_id": env("GOOGLE_CLIENT_ID"), "client_secret": env("GOOGLE_CLIENT_SECRET"),
            "redirect_uri": callback, "grant_type": "authorization_code", "code_verifier": saved["v"]})
    except httpx.HTTPError:
        raise LoginError("google_down")
    if r.status_code != 200:
        raise LoginError("google_refused")
    token = (r.json() or {}).get("id_token", "")
    try:
        part = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    except (IndexError, ValueError):
        raise LoginError("google_refused")
    if (claims.get("iss") not in ISSUERS or claims.get("aud") != env("GOOGLE_CLIENT_ID")
            or claims.get("exp", 0) < time.time() or claims.get("nonce") != saved["n"]):
        raise LoginError("google_refused")
    if not claims.get("email") or claims.get("email_verified") not in (True, "true"):
        raise LoginError("unverified")
    return {"sub": str(claims["sub"]), "email": claims["email"].strip().lower(), "name": claims.get("name", ""),
            "mode": saved.get("m", "signin")}
