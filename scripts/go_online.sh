#!/bin/zsh
# Job Portal · built by JAI SHARMA
# Connects this Mac's portal to your own domain through a Cloudflare Tunnel (free, no ports opened at home).
#
#   ./scripts/go_online.sh jobs.sharmajai.com
#
# Before running it: (1) set the portal password, (2) add your domain to Cloudflare, (3) brew install cloudflared,
# (4) cloudflared tunnel login.  DEPLOY.md has the full walkthrough.
set -e
cd "$(dirname "$0")/.."
HOSTNAME_="${1:?Usage: ./scripts/go_online.sh jobs.yourdomain.com}"
TUNNEL=job-portal
PORT=$(grep -E '^PORT=' .env | cut -d= -f2); PORT=${PORT:-8787}

say() { print -P "%F{cyan}▸%f $1"; }
stop() { print -P "%F{red}✗ $1%f"; exit 1; }

grep -q '^PORTAL_PASSWORD_HASH=.' .env || stop "Set the portal password first:  .venv/bin/python scripts/set_password.py --2fa"
command -v cloudflared >/dev/null || stop "Install the tunnel tool first:  brew install cloudflared"
[ -f ~/.cloudflared/cert.pem ] || stop "Sign in to Cloudflare first:  cloudflared tunnel login   (pick your domain in the browser)"

say "Telling the portal it sits behind Cloudflare (TRUST_PROXY=1)"
grep -q '^TRUST_PROXY=' .env || echo "TRUST_PROXY=1" >> .env

if ! cloudflared tunnel list --output json | grep -q "\"name\": *\"$TUNNEL\""; then
  say "Creating the tunnel \"$TUNNEL\""
  cloudflared tunnel create "$TUNNEL"
fi
ID=$(cloudflared tunnel list --output json | .venv/bin/python -c "import json,sys; print(next(t['id'] for t in json.load(sys.stdin) if t['name']=='$TUNNEL'))")
[ -n "$ID" ] || stop "Couldn't find the tunnel id."

say "Pointing $HOSTNAME_ at the tunnel"
cloudflared tunnel route dns --overwrite-dns "$TUNNEL" "$HOSTNAME_"

CONFIG=~/.cloudflared/config.yml
[ -f "$CONFIG" ] && cp "$CONFIG" "$CONFIG.backup-$(date +%Y%m%d-%H%M%S)"
cat > "$CONFIG" <<YAML
tunnel: $ID
credentials-file: $HOME/.cloudflared/$ID.json
ingress:
  - hostname: $HOSTNAME_
    service: http://localhost:$PORT
  - service: http_status:404
YAML
say "Wrote $CONFIG"

say "Restarting the portal so the password and proxy settings take effect"
pkill -f "uvicorn app.main:app" 2>/dev/null || true
sleep 1
mkdir -p data
nohup ./run.sh > data/server.log 2>&1 < /dev/null &
for i in {1..30}; do curl -s -o /dev/null "http://127.0.0.1:$PORT/login.html" && break; sleep 1; done

say "Starting the tunnel now and at every login"
PLIST=~/Library/LaunchAgents/com.cloudflare.cloudflared.plist
[ -f "$PLIST" ] || cloudflared service install >/dev/null 2>&1 || true
if [ -f "$PLIST" ]; then
  launchctl unload "$PLIST" 2>/dev/null || true
  # the service Cloudflare installs runs plain "cloudflared"; it has to be "cloudflared tunnel run"
  if ! /usr/libexec/PlistBuddy -c "Print :ProgramArguments" "$PLIST" | grep -q "run"; then
    /usr/libexec/PlistBuddy -c "Add :ProgramArguments:1 string tunnel" -c "Add :ProgramArguments:2 string run" "$PLIST"
  fi
  /usr/libexec/PlistBuddy -c "Add :KeepAlive bool true" "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
fi

print ""
print -P "%F{green}✓ Ready.%f Open https://$HOSTNAME_  — you should see the portal's sign-in page."
print "  (A brand-new address can take a few minutes to work on this Mac; try your phone on mobile data first.)"
print "  Then add the Cloudflare Access email check (DEPLOY.md, \"Second lock\")."
