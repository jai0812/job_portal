#!/bin/zsh
# Job Portal · built by JAI SHARMA
# Moves the portal from this Mac to your server, so it runs 24/7 even when the Mac is off.
#   ./deploy/move_to_server.sh ubuntu@SERVER_IP
# What it does: sets the server up, stops the portal on this Mac, copies your data, settings and tunnel keys,
# starts everything on the server and switches jobs.sharmajai.com over to it. Nothing is deleted from this Mac.
set -e
cd "$(dirname "$0")/.."
TARGET="${1:?Usage: ./deploy/move_to_server.sh ubuntu@SERVER_IP}"
KEY=~/.ssh/jobportal_server
SSH=(ssh -i $KEY -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 "$TARGET")
say() { print -P "%F{cyan}▸%f $1"; }
TUNNEL_ID=$(awk '/^tunnel:/{print $2}' ~/.cloudflared/config.yml)
[ -n "$TUNNEL_ID" ] && [ -f ~/.cloudflared/$TUNNEL_ID.json ] || { echo "Tunnel files not found in ~/.cloudflared"; exit 1; }

say "Checking the connection to $TARGET"
"${SSH[@]}" "echo connected: \$(uname -m), \$(lsb_release -ds 2>/dev/null)"

say "Setting the server up (a few minutes the first time)"
scp -q -i $KEY deploy/server_setup.sh "$TARGET":/tmp/server_setup.sh
"${SSH[@]}" "sudo bash /tmp/server_setup.sh"

say "Stopping the portal on this Mac so no changes are lost while copying"
launchctl unload ~/Library/LaunchAgents/com.sharmajai.jobportal.watchdog.plist 2>/dev/null || true
PID=$(lsof -tiTCP:8787 -sTCP:LISTEN || true); [ -n "$PID" ] && kill $PID; sleep 2

say "Copying your data, settings and keys (over the encrypted SSH connection)"
STAGE=$(mktemp -d)
sqlite3 data/jobs.db ".backup '$STAGE/jobs.db'"        # a consistent copy of the database
cp .env "$STAGE/.env"
for f in data/*.json(N); do cp "$f" "$STAGE/"; done
cp ~/.cloudflared/$TUNNEL_ID.json "$STAGE/tunnel.json"
cat > "$STAGE/config.yml" <<YAML
tunnel: $TUNNEL_ID
credentials-file: /etc/cloudflared/$TUNNEL_ID.json
ingress:
  - hostname: $(awk '/hostname:/{print $3}' ~/.cloudflared/config.yml)
    service: http://localhost:8787
  - service: http_status:404
YAML
"${SSH[@]}" "rm -rf /tmp/portal-move && mkdir -p /tmp/portal-move && chmod 700 /tmp/portal-move"
scp -q -i $KEY "$STAGE"/* "$STAGE"/.env "$TARGET":/tmp/portal-move/
rm -rf "$STAGE"
"${SSH[@]}" "set -e; cd /tmp/portal-move
  sudo install -o jobportal -g jobportal -m 600 .env /opt/jobportal/app/.env
  sudo install -o jobportal -g jobportal -m 600 jobs.db /opt/jobportal/app/data/jobs.db
  for f in *.json; do [ \"\$f\" = tunnel.json ] || sudo install -o jobportal -g jobportal -m 600 \"\$f\" /opt/jobportal/app/data/\$f; done
  sudo install -m 600 tunnel.json /etc/cloudflared/$TUNNEL_ID.json
  sudo install -m 644 config.yml /etc/cloudflared/config.yml
  rm -rf /tmp/portal-move
  sudo systemctl restart jobportal
  for i in \$(seq 1 30); do curl -s -m 3 http://127.0.0.1:8787/login.html | grep -qi portal && break; sleep 1; done
  curl -s -m 3 http://127.0.0.1:8787/login.html | grep -qi portal && echo 'portal running on the server'"

say "Switching jobs.sharmajai.com from this Mac to the server"
launchctl unload ~/Library/LaunchAgents/com.cloudflare.cloudflared.plist 2>/dev/null || true
"${SSH[@]}" "sudo systemctl enable --now jobportal-tunnel >/dev/null && sleep 6 && systemctl is-active jobportal-tunnel"

say "Desktop icon now just opens the website"
./desktop/install.sh --cloud >/dev/null 2>&1 || true

for i in {1..12}; do
  n=$(curl -s -m 15 https://jobs.sharmajai.com/login.html | wc -c | tr -d ' ')
  [ "${n:-0}" -gt 100 ] && break; sleep 5
done
[ "${n:-0}" -gt 100 ] && print -P "%F{green}✓ Done. jobs.sharmajai.com now runs on the server: your Mac can be off.%f" \
  || print -P "%F{yellow}The server is set up but the website didn't answer yet. Run: ./deploy/status.sh $TARGET%f"
