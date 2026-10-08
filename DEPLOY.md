# Putting the Job Portal online (on your own domain, behind a password)

The portal is a small Python server with a database file. That decides where it can run:

| Place | Can it run the portal? |
|---|---|
| **GitHub** | No. GitHub stores code; GitHub Pages only serves fixed pages, not a Python server. Use it as a **private** backup of the code. |
| **Basic website hosting** (the kind bundled with a domain) | Usually no. It needs a server that can run Python all the time. |
| **Your Mac + Cloudflare Tunnel** | Yes. Free. Works while the Mac is on. |
| **A small cloud server (VPS)** | Yes. About $5–6 a month. Runs 24/7. |

Either way your domain points at it, e.g. `jobs.yourdomain.com`.

## Step 0 (always): turn on the password

```bash
cd ~/Documents/MY_PORTAL
.venv/bin/python scripts/set_password.py --2fa
```

- You type the password yourself (14+ characters). Only a hash of it is saved in `.env`.
- `--2fa` adds a 6-digit code from an authenticator app (Google Authenticator, Authy, 1Password).
- Restart the portal. It now shows a sign-in page; nothing else is reachable without signing in.
- The portal **refuses to start** on a public address if no password is set.

What the protection includes: scrypt password hashing, lockout after 5 wrong tries (15 minutes), sessions that expire after
12 hours, cookies that scripts and other sites can't read or reuse, blocking of requests coming from other websites, and
strict browser security headers. Running `set_password.py` again changes the password and signs out every device.

## Option A: your Mac + Cloudflare Tunnel (free, recommended to start)

Your Mac keeps doing the work; Cloudflare gives it a secure address on your domain with HTTPS, without opening your home network.

1. Create a free Cloudflare account and add your domain (Cloudflare shows two nameservers; set them at the company where you bought the domain).
2. Install the tunnel tool: `brew install cloudflared`, then `cloudflared tunnel login`.
3. Create and route a tunnel:
   ```bash
   cloudflared tunnel create job-portal
   cloudflared tunnel route dns job-portal jobs.yourdomain.com
   ```
4. Add `TRUST_PROXY=1` to `.env` and restart the portal.
5. Steps 3–5 in one go: `./scripts/go_online.sh jobs.yourdomain.com` creates the tunnel, the DNS record and the config, restarts the portal,
   and installs the tunnel as a service that starts whenever you log in.
6. **Second lock (strongly recommended):** in Cloudflare → Zero Trust → Access → Applications, add `jobs.yourdomain.com` and allow only
   your email address. Visitors must pass Cloudflare's email check *before* they even reach the portal's own sign-in page.

## Option B: a small cloud server (24/7)

1. Rent the smallest Ubuntu server at DigitalOcean, Hetzner or similar (1 GB RAM is enough).
2. At your domain company, add a DNS **A record**: `jobs` → the server's IP address.
3. On the server, install Docker, copy this folder to it (without `.env` and `data/`), then:
   ```bash
   docker build -t job-portal .
   docker run -d --name job-portal --restart unless-stopped \
     -v portal-data:/app/data --env-file .env -p 127.0.0.1:8787:8787 job-portal
   ```
   Create the server's `.env` there with your API keys, plus the `PORTAL_PASSWORD_HASH`, `SESSION_SECRET` and `PORTAL_TOTP_SECRET`
   lines copied from your Mac's `.env` (made in Step 0). Copy the file over a secure connection (`scp`), never by email or chat.
4. Put Caddy in front for automatic HTTPS. `/etc/caddy/Caddyfile`:
   ```
   jobs.yourdomain.com {
       reverse_proxy 127.0.0.1:8787
   }
   ```
5. Optional but recommended: put the domain behind Cloudflare too and add the Access rule from Option A, step 6.

Notes for a cloud server: copy `data/jobs.db` from your Mac if you want to keep your applied history; some career sites
block cloud servers more than home connections, so a few feeds may fail there (Settings shows which).

## GitHub (code backup only)

```bash
cd ~/Documents/MY_PORTAL
git init && git add . && git commit -m "Job Portal"
```
Then create a **private** repository on github.com and push to it. `.gitignore` already keeps `.env` (your keys and password hash)
and `data/` (your jobs, applications and notes) out of it. Never make the repository public with those files in it.

## Never do these

- Don't expose the portal to the internet without the password set.
- Don't share `.env` or put it in GitHub, a zip, or a chat.
- Don't use plain `http://` on the internet: always go through Cloudflare or Caddy so it's `https://`.
