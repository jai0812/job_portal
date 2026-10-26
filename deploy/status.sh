#!/bin/zsh
# Quick health check of the portal on the server:  ./deploy/status.sh ubuntu@SERVER_IP
TARGET="${1:?Usage: ./deploy/status.sh ubuntu@SERVER_IP}"
ssh -i ~/.ssh/jobportal_server "$TARGET" '
  echo "portal: $(systemctl is-active jobportal) · tunnel: $(systemctl is-active jobportal-tunnel) · uptime: $(uptime -p)"
  echo "page: $(curl -s -m 5 http://127.0.0.1:8787/login.html | wc -c) bytes · disk free: $(df -h /opt | awk "NR==2{print \$4}") · memory free: $(free -m | awk "/Mem/{print \$7}") MB"
  sudo -u jobportal sqlite3 /opt/jobportal/app/data/jobs.db "select \"last refresh: \"||datetime(max(last_run),\"unixepoch\",\"localtime\")||\" · sources with errors: \"||sum(error!=\"\") from fetch_log;"
  echo "backups: $(ls /opt/jobportal/backups 2>/dev/null | wc -l)"; sudo journalctl -u jobportal -n 5 --no-pager -o cat'
echo "online: $(curl -s -m 15 https://jobs.sharmajai.com/login.html | wc -c | tr -d ' ') bytes"
