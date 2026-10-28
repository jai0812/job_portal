# Job Portal · built by JAI SHARMA
"""Paths, environment and YAML config loading."""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
load_dotenv(ROOT / ".env")
DATA_DIR = Path(os.getenv("PORTAL_DATA_DIR") or ROOT / "data")  # PORTAL_DATA_DIR: run a test copy on other data
DB_PATH = DATA_DIR / "jobs.db"
SOURCES_FILE = CONFIG_DIR / "sources.yaml"
COMPANIES_FILE = CONFIG_DIR / "companies.yaml"

DATA_DIR.mkdir(exist_ok=True)


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def load_sources() -> dict:
    return yaml.safe_load(SOURCES_FILE.read_text()) or {}


def save_sources(cfg: dict) -> None:
    SOURCES_FILE.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))


def load_companies() -> dict:
    return yaml.safe_load(COMPANIES_FILE.read_text()) or {}


UNIVERSITIES_FILE = CONFIG_DIR / "universities.yaml"


def load_universities() -> list[dict]:
    return (yaml.safe_load(UNIVERSITIES_FILE.read_text()) or {}).get("universities") or []


MORE_COMPANIES_FILE = CONFIG_DIR / "more_companies.yaml"


SPONSORS_FILE = CONFIG_DIR / "sponsor_companies.yaml"
CANADA_FILE = CONFIG_DIR / "canada_companies.yaml"


def load_more_companies() -> list[dict]:
    """config/more_companies.yaml (FAANG, big tech, India…) + sponsor_companies.yaml (mid-size H-1B sponsors)
    + canada_companies.yaml (Canadian employers: tech, banks, insurers, telecoms, retail)."""
    out = []
    for f in (MORE_COMPANIES_FILE, SPONSORS_FILE, CANADA_FILE):
        if f.exists():
            out += (yaml.safe_load(f.read_text()) or {}).get("companies") or []
    return out
