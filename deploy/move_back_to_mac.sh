#!/bin/zsh
# Undo: bring the portal (with the server's latest data) back to this Mac.  ./deploy/move_back_to_mac.sh ubuntu@SERVER_IP
set -e
cd "$(dirname "$0")/.."
TARGET="${1:?Usage: ./deploy/move_back_to_mac.sh ubuntu@SERVER_IP}"
KEY=~/.ssh/jobportal_server
ssh -i $KEY "$TARGET" 'sudo systemctl disable --now jobportal-tunnel; sudo systemctl stop jobportal
  sudo -u jobportal sqlite3 /opt/jobportal/app/data/jobs.db ".backup /tmp/jobs-latest.db"; sudo chmod 644 /tmp/jobs-latest.db'
cp data/jobs.db "data/jobs-before-moving-back-$(date +%F).db"
scp -q -i $KEY "$TARGET":/tmp/jobs-latest.db data/jobs.db
ssh -i $KEY "$TARGET" 'rm -f /tmp/jobs-latest.db'
launchctl enable gui/$(id -u)/com.cloudflare.cloudflared; launchctl load -w ~/Library/LaunchAgents/com.cloudflare.cloudflared.plist
./desktop/install.sh >/dev/null 2>&1; open "$HOME/Desktop/Job Portal.app"
echo "✓ Back on this Mac."
