#!/bin/zsh
# Job Portal · built by JAI SHARMA
# Switches on "Sign in with Google" on the server:  ./deploy/set_google_login.sh ubuntu@SERVER_IP
#
# First make the keys (once, about 5 minutes) at https://console.cloud.google.com :
#   1. Create a project (any name), then APIs & Services → OAuth consent screen → External → app name
#      "SharmaJai Job Portal", your support email, authorized domain sharmajai.com → Save. Publish the app.
#   2. APIs & Services → Credentials → Create credentials → OAuth client ID → Web application.
#      Authorized redirect URI:  https://jobs.sharmajai.com/auth/google/callback
#   3. Copy the Client ID and Client secret, then run this script and paste them when asked.
# The secret is typed here, sent over SSH and written to the server's .env (readable only by the portal);
# it never goes into git. Run it again to change the keys; run it with --off to remove them.
set -e
TARGET="${1:?Usage: ./deploy/set_google_login.sh ubuntu@SERVER_IP [--off]}"
KEY=~/.ssh/jobportal_server
if [[ "$2" == "--off" ]]; then
  ID=""; SECRET=""
else
  print -n "Google Client ID: "; read -r ID
  print -n "Google Client secret (not shown): "; read -rs SECRET; print
  [[ "$ID" == *.apps.googleusercontent.com ]] || { print "That Client ID doesn't end in .apps.googleusercontent.com"; exit 1; }
  [[ -n "$SECRET" ]] || { print "The Client secret is empty"; exit 1; }
fi
# The values travel on stdin, so they never appear in a command line on either machine.
printf '%s\n%s\n' "$ID" "$SECRET" | ssh -i $KEY "$TARGET" 'sudo -u jobportal python3 -c "
import sys, pathlib
cid, secret = sys.stdin.readline().strip(), sys.stdin.readline().strip()
p = pathlib.Path(\"/opt/jobportal/app/.env\")
lines = [l for l in p.read_text().splitlines() if not l.startswith((\"GOOGLE_CLIENT_ID=\", \"GOOGLE_CLIENT_SECRET=\"))]
if cid:
    lines += [\"GOOGLE_CLIENT_ID=\" + cid, \"GOOGLE_CLIENT_SECRET=\" + secret]
p.write_text(\"\n\".join(lines) + \"\n\")
print(\"Google sign-in\", \"switched on\" if cid else \"switched off\")
" && sudo systemctl restart jobportal && sleep 4 && echo "portal: $(systemctl is-active jobportal)"'
print "Check: https://jobs.sharmajai.com/signup should now show \"Sign up with Google\"."
