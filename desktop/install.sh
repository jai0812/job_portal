#!/bin/zsh
# Job Portal · built by JAI SHARMA
# Builds "Job Portal.app" on your Desktop for this folder's location, with the portal icon.
cd "$(dirname "$0")"
PORTAL_DIR="$(cd .. && pwd -P)"
APP="$HOME/Desktop/Job Portal.app"
TMP="$(mktemp -t launcher).applescript"
if [ "$1" = "--cloud" ]; then
  # the portal runs on a server: the icon just opens the website
  echo 'open location "https://jobs.sharmajai.com"' > "$TMP"
else
  sed "s#__PORTAL_DIR__#${PORTAL_DIR}#" launcher.applescript > "$TMP"
fi
rm -rf "$APP"
osacompile -o "$APP" "$TMP"
rm -f "$TMP"
cp Portal.icns "$APP/Contents/Resources/applet.icns"
touch "$APP"
echo "Created $APP (portal folder: $PORTAL_DIR)"

# Optional: ./desktop/install.sh --watchdog  → a background helper that checks every 5 minutes and restarts
# the portal if it isn't answering properly. Remove it with: ./desktop/install.sh --no-watchdog
AGENT="$HOME/Library/LaunchAgents/com.sharmajai.jobportal.watchdog.plist"
WATCH="$HOME/Applications/Job Portal Watchdog.app"
if [ "$1" = "--watchdog" ]; then
  mkdir -p "$HOME/Applications"
  sed "s#__PORTAL_DIR__#${PORTAL_DIR}#" watchdog.applescript > "$TMP"
  rm -rf "$WATCH"; osacompile -o "$WATCH" "$TMP"; rm -f "$TMP"
  /usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$WATCH/Contents/Info.plist" 2>/dev/null
  cp Portal.icns "$WATCH/Contents/Resources/applet.icns"
  cat > "$AGENT" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.sharmajai.jobportal.watchdog</string>
  <key>ProgramArguments</key><array><string>/usr/bin/open</string><string>-g</string><string>-j</string><string>$WATCH</string></array>
  <key>StartInterval</key><integer>300</integer>
  <key>RunAtLoad</key><true/>
</dict></plist>
PLIST
  launchctl unload "$AGENT" 2>/dev/null; launchctl load "$AGENT"
  echo "Watchdog installed: checks every 5 minutes. (macOS may ask once to let it access Documents: click Allow.)"
elif [ "$1" = "--no-watchdog" ]; then
  launchctl unload "$AGENT" 2>/dev/null; rm -f "$AGENT"; rm -rf "$WATCH"
  echo "Watchdog removed."
fi
