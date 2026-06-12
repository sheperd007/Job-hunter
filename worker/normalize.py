"""Pure normalization helpers: canonical URLs (dedupe key) + region detection."""
from urllib.parse import urlsplit, urlunsplit

# Region keyword buckets. UK is checked before EU (distinct sponsor regime).
_UK = ["united kingdom", "uk", "england", "scotland", "wales", "london",
       "manchester", "edinburgh", "cambridge", "oxford", "britain"]
_EU = ["netherlands", "amsterdam", "germany", "berlin", "munich", "france",
       "paris", "spain", "madrid", "barcelona", "italy", "rome", "ireland",
       "dublin", "belgium", "brussels", "sweden", "stockholm", "denmark",
       "copenhagen", "finland", "helsinki", "norway", "oslo", "austria",
       "vienna", "switzerland", "zurich", "portugal", "lisbon", "poland",
       "czech", "prague", "luxembourg", "europe", "eu"]
_CANADA = ["canada", "toronto", "vancouver", "montreal", "ottawa", "ontario",
           "quebec", "calgary", "alberta", "british columbia"]
_AUNZ = ["australia", "sydney", "melbourne", "brisbane", "canberra", "perth",
         "new zealand", "auckland", "wellington"]
_US = ["united states", "usa", "u.s.", "new york", "california", "boston",
       "san francisco", "seattle", "texas", "chicago"]


def canonical_url(url: str) -> str:
    """Strip query/fragment, lowercase host, drop trailing slash -> stable key."""
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, "", ""))


def _has(text: str, words: list[str]) -> bool:
    return any(w in text for w in words)


def detect_region(text: str) -> str:
    """Best-effort region bucket from a location string. Order matters."""
    t = (text or "").lower()
    if "remote" in t:
        return "Remote"
    if _has(t, _UK):
        return "UK"
    if _has(t, _CANADA):
        return "Canada"
    if _has(t, _AUNZ):
        return "AU-NZ"
    if _has(t, _EU):
        return "EU"
    if _has(t, _US):
        return "US"
    return "Other"


TARGET_REGIONS = {"UK", "EU", "Canada", "AU-NZ", "Remote"}


def in_target_region(region: str) -> bool:
    """Owner targets EU+UK, Canada, AU/NZ (and Remote that may relocate)."""
    return region in TARGET_REGIONS
