# Job Portal · built by JAI SHARMA
"""Which country (or countries) a job's location text refers to, and which tab it belongs on (US / India / other)."""
import re
from functools import lru_cache

US = "United States"
INDIA = "India"

_US_STATES = ("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND "
              "OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY").split()
_US_STATE_NAMES = ("Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois"
                   "|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri"
                   "|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|North Carolina|North Dakota|Ohio|Oklahoma|Oregon"
                   "|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington"
                   "|West Virginia|Wisconsin|Wyoming|District of Columbia")
_US_RE = re.compile(r"United States|\bUSA\b|\bU\.S\.A?\.?|\bUS\b|\b(" + "|".join(_US_STATES) + r")\b(\s*\d{3,5})?\s*($|[,;|)\-/])"
                    r"|\b(" + _US_STATE_NAMES + r")\b|New York|NYC|San Francisco|Bay Area|Silicon Valley|Chicago|Seattle|Boston")

_INDIA_RE = re.compile(r"\bIndia\b|Bengaluru|Bangalore|Hyderabad|Mumbai|Pune|Chennai|Gurgaon|Gurugram|Noida|Delhi|Kolkata|Ahmedabad"
                       r"|Jaipur|Kochi|Cochin|Coimbatore|Thiruvananthapuram|Trivandrum|Mysore|Mysuru|Chandigarh|Indore|Nagpur"
                       r"|Vadodara|Bhubaneswar|Visakhapatnam|Mangalore|Telang[aā]na|Karnataka|Maharashtra|Tamil Nadu|Haryana"
                       r"|Uttar Pradesh|Kerala|Gujarat|West Bengal", re.I)
_INDIA_CODE = re.compile(r"^IN, [A-Z]{2}, ")  # amazon.jobs style: "IN, KA, Bengaluru"

# Other countries: country names plus the cities that show up most in job listings.
_OTHER = [(c, re.compile(p, re.I)) for c, p in [
    ("Canada", r"Canada|, (ON|BC|QC|AB|NS|MB)\b|Toronto|Vancouver|Montr[eé]al|Ontario|Qu[eé]bec|Alberta|Calgary|Ottawa|British Columbia|Waterloo, ON|Mississauga"),
    ("United Kingdom", r"United Kingdom|\bUK\b|England|Scotland|Wales|London|Glasgow|Edinburgh|Belfast|Manchester|Leeds|Bristol"),
    ("Ireland", r"Ireland|Dublin|Cork|Galway"),
    ("Germany", r"Germany|Deutschland|Frankfurt|Berlin|Munich|München|Hamburg|Cologne|Stuttgart|Düsseldorf"),
    ("France", r"France|Paris|Lyon"),
    ("Netherlands", r"Netherlands|Amsterdam|Rotterdam|Utrecht|The Hague"),
    ("Switzerland", r"Switzerland|Z[uü]rich|Geneva|Gen[eè]ve|Basel|Lugano"),
    ("Luxembourg", r"Luxembourg"),
    ("Belgium", r"Belgium|Brussels"),
    ("Spain", r"Spain|Madrid|Barcelona"),
    ("Portugal", r"Portugal|Lisbon|Porto"),
    ("Italy", r"Italy|Milan|Milano|Rome"),
    ("Poland", r"Poland|Warsaw|Krak[oó]w|Wroc[lł]aw|Gda[nń]sk"),
    ("Czech Republic", r"Czech|Prague"),
    ("Hungary", r"Hungary|Budapest"),
    ("Romania", r"Romania|Bucharest|Cluj"),
    ("Sweden", r"Sweden|Stockholm"),
    ("Denmark", r"Denmark|Copenhagen"),
    ("Norway", r"Norway|Oslo"),
    ("Finland", r"Finland|Helsinki"),
    ("Austria", r"Austria|Vienna"),
    ("Israel", r"Israel|Tel Aviv|Herzliya"),
    ("United Arab Emirates", r"United Arab Emirates|\bUAE\b|Dubai|Abu Dhabi"),
    ("Saudi Arabia", r"Saudi|Riyadh"),
    ("Singapore", r"Singapore"),
    ("Hong Kong", r"Hong Kong"),
    ("China", r"China|Shanghai|Beijing|Shenzhen|Guangzhou|Dalian"),
    ("Japan", r"Japan|Tokyo|Osaka"),
    ("South Korea", r"Korea|Seoul"),
    ("Taiwan", r"Taiwan|Taipei"),
    ("Philippines", r"Philippines|Manila|Taguig|Makati|Cebu"),
    ("Malaysia", r"Malaysia|Kuala Lumpur"),
    ("Vietnam", r"Vietnam|Ho Chi Minh|Hanoi"),
    ("Indonesia", r"Indonesia|Jakarta"),
    ("Thailand", r"Thailand|Bangkok"),
    ("Australia", r"Australia|Sydney|Melbourne|Brisbane|Perth"),
    ("New Zealand", r"New Zealand|Auckland|Wellington"),
    ("Mexico", r"Mexico|M[eé]xico|Guadalajara|Monterrey|Guanajuato|Quer[eé]taro"),
    ("Brazil", r"Brazil|Brasil|S[aã]o Paulo|Rio de Janeiro"),
    ("Argentina", r"Argentina|Buenos Aires"),
    ("Colombia", r"Colombia|Bogot[aá]|Medell[ií]n"),
    ("Chile", r"Chile|Santiago"),
    ("Costa Rica", r"Costa Rica|San Jos[eé], Costa"),
    ("South Africa", r"South Africa|Johannesburg|Cape Town"),
    ("Egypt", r"Egypt|Cairo"),
    ("Nigeria", r"Nigeria|Lagos"),
    ("Kenya", r"Kenya|Nairobi"),
    ("Sri Lanka", r"Sri Lanka|Colombo"),
    ("Pakistan", r"Pakistan|Karachi|Lahore"),
]]


def countries(location: str) -> tuple[str, ...]:
    """Countries mentioned in a location string. Unclear text ("3 Locations", "Remote") counts as the US."""
    return detected(location) or (US,)


@lru_cache(maxsize=50000)
def detected(location: str) -> tuple[str, ...]:
    """Countries we can actually recognise in the text (empty when unclear)."""
    found: list[str] = []
    for part in re.split(r"[;|·]| / |\n", location or ""):
        part = part.strip()
        if not part:
            continue
        if _INDIA_RE.search(part) or _INDIA_CODE.search(part):
            c = INDIA
        elif _US_RE.search(part):  # before other countries, so "London, KY" or "Paris, TX" stay American
            c = US
        else:
            c = next((name for name, rx in _OTHER if rx.search(part)), None)
        if c and c not in found:
            found.append(c)
    return tuple(found)


def regions(location: str) -> tuple[str, ...]:
    """Which tabs a job shows on: "us", "india", "other" (a multi-country job can be on several)."""
    cs = countries(location)
    out = []
    if US in cs:
        out.append("us")
    if INDIA in cs:
        out.append("india")
    if any(c not in (US, INDIA) for c in cs):
        out.append("other")
    return tuple(out)
