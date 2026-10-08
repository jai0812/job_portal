# Job Portal · built by JAI SHARMA
"""Fetch jobs from the command line (handy for cron/launchd).

    .venv/bin/python scripts/fetch_jobs.py            # GitHub sources
    .venv/bin/python scripts/fetch_jobs.py --apify    # + LinkedIn via Apify (paid)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import db, refresh  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--apify", action="store_true", help="also run the Apify searches from config/sources.yaml")
args = p.parse_args()
db.init()
for r in refresh.run(include_apify=args.apify):
    print(f"{r['source']:<40} {r['count']:>6} jobs  {('ERROR: ' + r['error']) if r['error'] else ''}")
