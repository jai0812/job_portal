-- Job Portal watchdog: run every few minutes in the background. Restarts the portal if it isn't answering properly.
-- The server keeps running in the background (and refreshes jobs every hour) after you close the browser tab.
set portalDir to "__PORTAL_DIR__"
set portalURL to "http://localhost:8787"

on isUp()
	try
		-- "up" means the sign-in page actually has content (a broken process can answer 200 with an empty page)
		set n to do shell script "curl -s -m 3 http://127.0.0.1:8787/login.html | wc -c | tr -d ' ' || true"
		return (n as integer) > 100
	on error
		return false
	end try
end isUp

if not isUp() then
	do shell script "pkill -f 'uvicorn app.main:app' || true"
	delay 1
	do shell script "cd " & quoted form of portalDir & " || exit 1; mkdir -p data; nohup ./run.sh > data/server.log 2>&1 < /dev/null &"
	repeat 60 times
		delay 0.5
		if isUp() then exit repeat
	end repeat
	if not isUp() then
		return
	end if
end if
