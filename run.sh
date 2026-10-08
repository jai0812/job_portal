#!/bin/zsh
# Job Portal · built by JAI SHARMA
# Start the Job Portal at http://localhost:8787
cd "$(dirname "$0")"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
[ -f .env ] || cp .env.example .env
PORT=${PORT:-$(grep -E '^PORT=' .env | cut -d= -f2)}; PORT=${PORT:-8787}
# PORTAL_HOST stays 127.0.0.1 (this computer only) unless .env or the environment says otherwise, e.g. 0.0.0.0 on a server.
PORTAL_HOST=${PORTAL_HOST:-$(grep -E '^PORTAL_HOST=' .env | cut -d= -f2)}; PORTAL_HOST=${PORTAL_HOST:-127.0.0.1}
export PORTAL_HOST
exec .venv/bin/uvicorn app.main:app --host "$PORTAL_HOST" --port "$PORT" --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
