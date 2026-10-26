#!/bin/zsh
# After pushing code changes to GitHub, update the server:  ./deploy/update_server.sh ubuntu@SERVER_IP
TARGET="${1:?Usage: ./deploy/update_server.sh ubuntu@SERVER_IP}"
ssh -i ~/.ssh/jobportal_server "$TARGET" 'set -e
  sudo -u jobportal git -C /opt/jobportal/app pull -q --rebase
  sudo -u jobportal /opt/jobportal/venv/bin/pip install -q -r /opt/jobportal/app/requirements.txt
  sudo systemctl restart jobportal && sleep 3 && echo "updated: $(systemctl is-active jobportal)"'
