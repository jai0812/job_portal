# Job Portal · built by JAI SHARMA
"""Set (or reset) the admin account's password. Needed once before putting the portal online.

    .venv/bin/python scripts/set_password.py              # set or change the admin password
    .venv/bin/python scripts/set_password.py --user NAME  # also rename the admin account
    .venv/bin/python scripts/set_password.py --off        # remove all passwords (local use only)

Other people's accounts are made from the portal's 👤 Users tab. Your password is typed here, in your own
Terminal; only a scrypt hash is stored (in the portal's database). Running this signs the admin out everywhere.
"""
import argparse
import getpass
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import auth, db  # noqa: E402

ENV = ROOT / ".env"
KEYS = ("PORTAL_PASSWORD_HASH", "SESSION_SECRET", "PORTAL_TOTP_SECRET")  # the last two are from before accounts


def write_env(values: dict) -> None:
    """Set these keys in .env (a value of None removes the key), leaving everything else untouched."""
    lines = ENV.read_text().splitlines() if ENV.exists() else []
    lines = [l for l in lines if not any(l.startswith(k + "=") for k in values)]
    lines += [f"{k}={v}" for k, v in values.items() if v is not None]
    ENV.write_text("\n".join(lines) + "\n")
    ENV.chmod(0o600)  # readable only by you


p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--user", help="new username for the admin account")
p.add_argument("--off", action="store_true", help="remove password protection")
args = p.parse_args()
db.init()
admin = db.admin_user()

if args.off:
    for u in db.all_users().values():
        db.update_user(u["id"], pw_hash="")
    write_env({"PORTAL_PASSWORD_HASH": None, "PORTAL_TOTP_SECRET": None})
    print("Password protection removed (all accounts). Restart the portal.")
    sys.exit()

print(f"Choose a password for the admin account '{args.user or admin['username']}': at least 14 characters.")
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

if args.user:
    with db.conn() as c:
        c.execute("UPDATE users SET username=? WHERE id=?", (args.user.strip(), admin["id"]))
    db._users_changed()
db.update_user(admin["id"], pw_hash=auth.hash_password(pw))
env = ENV.read_text() if ENV.exists() else ""
write_env({"PORTAL_PASSWORD_HASH": None, "PORTAL_TOTP_SECRET": None,
           **({} if re.search(r"^SESSION_SECRET=.{32,}", env, re.M) else {"SESSION_SECRET": secrets.token_hex(32)})})
print(f"\n✓ Admin password saved (as a hash). Sign in as '{db.admin_user()['username']}'. Restart the portal if it isn't running yet.")
