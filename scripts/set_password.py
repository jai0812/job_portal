# Job Portal · built by JAI SHARMA
"""Turn on password protection (needed before putting the portal online).

    .venv/bin/python scripts/set_password.py          # set or change the password
    .venv/bin/python scripts/set_password.py --2fa    # also require a code from an authenticator app
    .venv/bin/python scripts/set_password.py --off    # remove protection (local use only)

Your password is typed here, in your own Terminal. Only a scrypt hash of it is saved in .env; the password
itself is never stored anywhere. Running this again signs out every device.
"""
import argparse
import base64
import getpass
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import auth  # noqa: E402

ENV = ROOT / ".env"
KEYS = ("PORTAL_PASSWORD_HASH", "SESSION_SECRET", "PORTAL_TOTP_SECRET")


def write_env(values: dict) -> None:
    """Set these keys in .env (a value of None removes the key), leaving everything else untouched."""
    lines = ENV.read_text().splitlines() if ENV.exists() else []
    lines = [l for l in lines if not any(l.startswith(k + "=") for k in values)]
    lines += [f"{k}={v}" for k, v in values.items() if v is not None]
    ENV.write_text("\n".join(lines) + "\n")
    ENV.chmod(0o600)  # readable only by you


p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--2fa", dest="twofa", action="store_true", help="also require authenticator-app codes")
p.add_argument("--off", action="store_true", help="remove password protection")
args = p.parse_args()

if args.off:
    write_env(dict.fromkeys(KEYS))
    print("Password protection removed. Restart the portal.")
    sys.exit()

print("Choose a password for the portal: at least 14 characters. A few random words works well.")
while True:
    pw = getpass.getpass("New password: ")
    problems = []
    if len(pw) < 14:
        problems.append("use at least 14 characters")
    if len(set(pw)) < 6 or re.fullmatch(r"(.)\1*|\d+", pw):
        problems.append("too simple")
    if problems:
        print("  → " + ", ".join(problems))
        continue
    if getpass.getpass("Type it again: ") != pw:
        print("  → they didn't match")
        continue
    break

values = {"PORTAL_PASSWORD_HASH": auth.hash_password(pw), "SESSION_SECRET": secrets.token_hex(32)}
if args.twofa:
    secret = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
    values["PORTAL_TOTP_SECRET"] = secret
write_env(values)
print("\n✓ Password saved (as a hash) in .env. Restart the portal to turn protection on.")
if args.twofa:
    print("\n2-step sign-in: open Google Authenticator / Authy / 1Password → add account → enter this key by hand:")
    print(f"\n    {' '.join(secret[i:i + 4] for i in range(0, len(secret), 4))}\n")
    print("  Account name: Job Portal    Type: time-based")
    print("  Keep this key private; it's shown only this once. To turn 2-step off, run this script again without --2fa.")
else:
    print("Tip: add --2fa to also require a code from an authenticator app.")
