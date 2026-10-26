#!/bin/bash
# Job Portal · built by JAI SHARMA
# Prepares an Ubuntu server (e.g. Oracle Cloud Always Free) to run the portal 24/7.
# Run on the server:  sudo bash server_setup.sh      (safe to run again; it updates in place)
set -euo pipefail
REPO=${REPO:-https://github.com/jai0812/job_portal.git}
APP=/opt/jobportal
echo "▸ System packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y -q
apt-get install -y -q python3 python3-venv python3-pip git sqlite3 curl cron unattended-upgrades >/dev/null
timedatectl set-timezone America/New_York || true          # alerts' quiet hours and morning summary use local time
if [ ! -f /swapfile ] && [ "$(awk '/MemTotal/{print $2}' /proc/meminfo)" -lt 4000000 ]; then
  echo "▸ Adding 2 GB swap (small machine)"
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
echo "▸ Cloudflare tunnel tool"
if ! command -v cloudflared >/dev/null; then
  curl -fsSL -o /tmp/cloudflared.deb "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-$(dpkg --print-architecture).deb"
  dpkg -i /tmp/cloudflared.deb >/dev/null
fi
echo "▸ App user and code"
id jobportal >/dev/null 2>&1 || useradd --system --create-home --home-dir $APP --shell /usr/sbin/nologin jobportal
if [ -d $APP/app/.git ]; then sudo -u jobportal git -C $APP/app pull -q --rebase; else sudo -u jobportal git clone -q $REPO $APP/app; fi
[ -d $APP/venv ] || sudo -u jobportal python3 -m venv $APP/venv
sudo -u jobportal $APP/venv/bin/pip install -q --upgrade pip
sudo -u jobportal $APP/venv/bin/pip install -q -r $APP/app/requirements.txt
sudo -u jobportal mkdir -p $APP/app/data $APP/backups
mkdir -p /etc/cloudflared
echo "▸ Services (start on boot, restart if they stop)"
cat > /etc/systemd/system/jobportal.service <<UNIT
[Unit]
Description=SharmaJai Job Portal
After=network-online.target
Wants=network-online.target
[Service]
User=jobportal
WorkingDirectory=$APP/app
Environment=PORTAL_HOST=127.0.0.1
Environment=TRUST_PROXY=1
# the server doesn't push README updates to GitHub (that needs a GitHub token on the server)
Environment=PORTAL_README=0
ExecStart=$APP/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8787 --proxy-headers --forwarded-allow-ips 127.0.0.1
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/systemd/system/jobportal-tunnel.service <<UNIT
[Unit]
Description=Cloudflare tunnel for the Job Portal
After=network-online.target jobportal.service
Wants=network-online.target
[Service]
ExecStart=/usr/bin/cloudflared --no-autoupdate --config /etc/cloudflared/config.yml tunnel run
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
UNIT
echo "▸ Daily database backup at 3:15 AM, kept 14 days"
cat > /etc/cron.d/jobportal-backup <<CRON
15 3 * * * jobportal sqlite3 $APP/app/data/jobs.db ".backup '$APP/backups/jobs-\$(date +\%F).db'" && find $APP/backups -name 'jobs-*.db' -mtime +14 -delete
CRON
systemctl daemon-reload
systemctl enable jobportal >/dev/null
echo "✓ Server ready. (The portal and tunnel start once your data and tunnel keys are copied over.)"
