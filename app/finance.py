# Job Portal · built by JAI SHARMA
"""Recognise finance firms (config/finance_firms.yaml) in job listings and attach their H-1B history."""
import re
from functools import lru_cache

import yaml

from . import h1b
from .config import CONFIG_DIR

FIRMS_FILE = CONFIG_DIR / "finance_firms.yaml"


def _alias_regex(alias: str) -> re.Pattern:
    if alias.startswith("="):  # generic words (Ramp, Block, Visa…) must be the whole company name
        return re.compile(r"^\s*" + re.escape(alias[1:]) + r"(,?\s+(inc|llc|corp|corporation|co)\.?)?\s*$", re.I)
    # Short all-caps names (ICE, SIG, UBS, PNC…) only match in capitals, so "ice cream" isn't the NYSE owner.
    flags = 0 if alias.isupper() and len(alias) <= 5 else re.I
    return re.compile(r"(?<![\w&])" + re.escape(alias) + r"(?![\w&])", flags)


@lru_cache(maxsize=1)
def config() -> dict:
    cfg = yaml.safe_load(FIRMS_FILE.read_text()) if FIRMS_FILE.exists() else {}
    segments = cfg.get("segments") or {}
    firms = []
    for f in cfg.get("firms") or []:
        firms.append({**f, "segment_label": segments.get(f["segment"], f["segment"]),
                      "h1b_fy23": h1b.approvals_for_names(f.get("uscis") or []),
                      "_match": [_alias_regex(a) for a in f.get("match") or [f["name"]]],
                      "_exclude": [re.compile(re.escape(x), re.I) for x in f.get("exclude") or []]})
    # Try longer aliases first so "Citadel Securities" wins over "Citadel".
    order = sorted(((max(len(a.lstrip("=")) for a in f.get("match") or [f["name"]]), i) for i, f in enumerate(firms)), reverse=True)
    return {"segments": segments, "firms": firms, "order": [i for _, i in order]}


def reload() -> None:
    config.cache_clear()
    firm_for.cache_clear()


@lru_cache(maxsize=20000)
def firm_for(company: str) -> dict | None:
    """The finance firm a company name belongs to, or None."""
    if not company:
        return None
    cfg = config()
    for i in cfg["order"]:
        f = cfg["firms"][i]
        if any(x.search(company) for x in f["_exclude"]):
            continue
        if any(m.search(company) for m in f["_match"]):
            return {"name": f["name"], "segment": f["segment"], "segment_label": f["segment_label"],
                    "h1b_fy23": f["h1b_fy23"], "careers": f.get("careers", "")}
    return None


def public_list() -> list[dict]:
    """Firms for the UI/settings, without the compiled regexes."""
    return [{k: v for k, v in f.items() if not k.startswith("_")} for f in config()["firms"]]
