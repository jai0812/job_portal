#!/bin/zsh
# Job Portal · built by JAI SHARMA
# Builds "Job Portal.app" on your Desktop for this folder's location, with the portal icon.
cd "$(dirname "$0")"
PORTAL_DIR="$(cd .. && pwd -P)"
APP="$HOME/Desktop/Job Portal.app"
TMP="$(mktemp -t launcher).applescript"
sed "s#__PORTAL_DIR__#${PORTAL_DIR}#" launcher.applescript > "$TMP"
rm -rf "$APP"
osacompile -o "$APP" "$TMP"
rm -f "$TMP"
cp Portal.icns "$APP/Contents/Resources/applet.icns"
touch "$APP"
echo "Created $APP (portal folder: $PORTAL_DIR)"
