-- Job Portal launcher: starts the local server if it isn't running, then opens the portal.
-- The server keeps running in the background (and refreshes jobs every hour) after you close the browser tab.
set portalDir to "__PORTAL_DIR__"
set portalURL to "http://localhost:8787"

on isUp()
	try
		set code to do shell script "curl -s -m 2 -o /dev/null -w '%{http_code}' http://127.0.0.1:8787/login.html || true"
		return code is "200"
	on error
		return false
	end try
end isUp

if not isUp() then
	do shell script "cd " & quoted form of portalDir & " || exit 1; mkdir -p data; nohup ./run.sh > data/server.log 2>&1 < /dev/null &"
	repeat 60 times
		delay 0.5
		if isUp() then exit repeat
	end repeat
	if not isUp() then
		display dialog "Job Portal didn't start. See " & portalDir & "/data/server.log" buttons {"OK"} default button 1 with icon caution
		return
	end if
end if
open location portalURL
