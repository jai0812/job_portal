# Job Portal · built by JAI SHARMA
"""The "US citizen jobs" tab (a per-user extra): which employers are government / defense, Big 4, Big 3 consulting
or recruit at Boston University (config/citizen.yaml), and which postings say citizenship or a clearance is required."""
import re
from functools import lru_cache

import yaml

from .config import CONFIG_DIR
from .finance import _alias_regex

FILE = CONFIG_DIR / "citizen.yaml"
BANK_SEGMENTS = ("broad_banks", "global_banks", "ib_markets")  # the tab's "Banks" filter (same list in app.js)
GROUPS = {"gov_defense": "gov", "big4": "big4", "mbb": "mbb", "bu_recruiters": "bu"}  # yaml section -> tag on a job

# Wording that means "US citizens only" (or US persons, for export-controlled work). The title counts too: career
# sites that give no description still say "Software Engineer I - Top Secret" or "(Secret clearance required)".
CITIZEN_TEXT = re.compile(
    r"u\.?s\.? citizenship|citizenship (is )?required|must be (a |an )?(u\.?s\.?|united states|american) citizen"
    r"|(u\.?s\.?|united states) citizens? only|only (u\.?s\.?|united states) citizens|\bu\.?s\.? persons?\b|\bitar\b"
    r"|security clearance|(secret|dod|government|federal|active|interim) clearance|clearance (is )?required"
    r"|(obtain|maintain|hold|possess)( and maintain)? an? [^.]{0,40}clearance|\btop secret\b|\bts[/ ]sci\b|public trust"
    r"|polygraph", re.I)
CITIZEN_TITLE = re.compile(
    r"\btop secret\b|\bts[/ ]sci\b|\bclearance\b|\bcleared\b|\bsecret\b(?! (shopper|santa|sauce))|polygraph|\b(ci|fs|full scope) poly\b"
    r"|public trust|u\.?s\.? citizen", re.I)


def citizen_only(title: str, description: str = "") -> bool:
    return bool(CITIZEN_TITLE.search(title or "") or CITIZEN_TEXT.search(description or ""))


@lru_cache(maxsize=1)
def config() -> dict:
    cfg = (yaml.safe_load(FILE.read_text()) if FILE.exists() else None) or {}
    for section in GROUPS:
        for e in cfg.get(section) or []:
            e["_match"] = [_alias_regex(a) for a in e.get("match") or [e["name"]]]
    return cfg


@lru_cache(maxsize=20000)
def tags(company: str) -> str:
    """'gov,bu' etc. for this employer ('' for most)."""
    if not company:
        return ""
    cfg = config()
    return ",".join(tag for section, tag in GROUPS.items()
                    if any(m.search(company) for e in cfg.get(section) or [] for m in e["_match"]))


def reload() -> None:
    config.cache_clear()
    tags.cache_clear()


def public() -> dict:
    """Links for the tab: career sites per group, job boards, BU fairs."""
    cfg = config()
    out = {s: [{k: v for k, v in e.items() if not k.startswith("_") and k != "match"} for e in cfg.get(s) or []] for s in GROUPS}
    from . import finance  # banks come from the finance-firm list, so there is one place to add a bank
    banks = [{"name": f["name"], "url": f["careers"]} for f in finance.public_list()
             if f["segment"] in BANK_SEGMENTS and f.get("careers")]
    return {**out, "banks": banks, "boards": cfg.get("boards") or [], "fairs": cfg.get("fairs") or {}}
