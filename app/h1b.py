# Job Portal · built by JAI SHARMA
"""H-1B sponsorship history from the official USCIS H-1B Employer Data Hub (FY2023 approvals)."""
import json
import re
from functools import lru_cache

from .config import CONFIG_DIR

DATA_FILE = CONFIG_DIR / "h1b_fy2023.json"
_SUFFIX = re.compile(r"\b(INCORPORATED|INC|LLC|L L C|LLP|LP|L P|LTD|LIMITED|CORPORATION|CORP|CO|COMPANY|NA|N A|PLC|AG|SA|SE|NV"
                     r"|GROUP|HOLDINGS?|THE|USA|US|U S)\b")


def norm(name: str) -> str:
    """Company name → comparable key: "Stripe, Inc." and "STRIPE INC" both become "STRIPE"."""
    n = (name or "").upper().replace("&", " AND ")
    n = re.sub(r"[^A-Z0-9 ]", " ", n)
    return re.sub(r"\s+", " ", _SUFFIX.sub(" ", n)).strip()


@lru_cache(maxsize=1)
def _data() -> tuple[dict, dict, dict]:
    if not DATA_FILE.exists():
        return {}, {}, {}
    raw = json.loads(DATA_FILE.read_text())["approvals"]
    by_norm: dict[str, int] = {}
    for employer, n in raw.items():
        k = norm(employer)
        if k:
            by_norm[k] = by_norm.get(k, 0) + n
    by_first: dict[str, list[str]] = {}  # first word → names, so prefix lookups stay fast
    for k in by_norm:
        by_first.setdefault(k.split(" ", 1)[0], []).append(k)
    return raw, by_norm, by_first


def approvals_for_names(prefixes: list[str]) -> int:
    """Sum approvals for every USCIS employer name starting with one of these (for firms with several legal entities)."""
    raw = _data()[0]
    ps = [p.upper() for p in prefixes or []]
    return sum(n for employer, n in raw.items() if any(employer.startswith(p) for p in ps))


@lru_cache(maxsize=20000)
def approvals_for_company(company: str) -> int:
    """Best-effort match of a job's company name to a USCIS employer (exact match after normalising the name)."""
    _, by_norm, by_first = _data()
    key = norm(company)
    if not key:
        return 0
    if key in by_norm:
        return by_norm[key]
    # "Amazon" files as "Amazon.com Services", "Meta" as "Meta Platforms": also count names that start with it.
    if len(key) < 4:
        return 0
    return sum(by_norm[k] for k in by_first.get(key.split(" ", 1)[0], []) if k.startswith(key + " "))
