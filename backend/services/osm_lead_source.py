import requests
from urllib.parse import urlparse


# Houston, TX inner-city fallback bbox (south, west, north, east)
_HOUSTON_BBOX = (29.7, -95.5, 30.0, -95.1)


def _resolve_bbox(location: str) -> tuple[float, float, float, float]:
    """Return (south, west, north, east) for location via Nominatim, or Houston fallback."""
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": location, "format": "json", "limit": 1},
            headers={"User-Agent": "LeadForge-AI/1.0 (research)"},
            timeout=5,
        )
        data = resp.json()
        if data:
            bb = data[0]["boundingbox"]  # [south, north, west, east]
            return float(bb[0]), float(bb[2]), float(bb[1]), float(bb[3])
    except Exception as exc:
        print(f"[OSM] Nominatim geocoding failed for '{location}': {exc}; using Houston fallback")
    return _HOUSTON_BBOX


def _build_osm_address(tags: dict) -> str:
    """Assemble a street-level address from OSM addr:* tags."""
    parts = [
        tags.get("addr:housenumber", ""),
        tags.get("addr:street", ""),
        tags.get("addr:city", ""),
        tags.get("addr:state", ""),
        tags.get("addr:postcode", ""),
    ]
    return ", ".join(p for p in parts if p)


def _normalize_domain(url: str) -> str:
    """Return a bare domain from a full URL.

    Strips protocol (http/https), leading www., path, and query params.
    Returns an empty string for empty or unparseable input.

    Examples:
        "https://www.smiledental.com"      → "smiledental.com"
        "http://clinic.org/contact"        → "clinic.org"
        "https://example.com/path?q=1"     → "example.com"
        "www.nodomain.com"                 → "nodomain.com"
        ""                                 → ""
    """
    if not url or not url.strip():
        return ""
    raw = url.strip()
    # urlparse requires a scheme to correctly split netloc from path
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    netloc = urlparse(raw).netloc
    if not netloc:
        return ""
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc.lower()


# Keywords that map directly to a valid OSM amenity= tag.
AMENITY_MAP = {
    # Food & drink
    "restaurant": "restaurant",
    "food":       "restaurant",
    "pizza":      "restaurant",
    "burger":     "restaurant",
    "cafe":       "cafe",
    "coffee":     "cafe",
    "bar":        "bar",
    "pub":        "pub",
    "fast food":  "fast_food",
    "fast_food":  "fast_food",
    # Accommodation
    "hotel":      "hotel",
    # Health & medical
    "dentist":    "dentist",
    "clinic":     "clinic",
    "pharmacy":   "pharmacy",
    "hospital":   "hospital",
    "doctor":     "doctors",
    "doctors":    "doctors",
    "vet":        "veterinary",
    "veterinary": "veterinary",
    # Fitness
    "gym":        "gym",
    # Education
    "school":     "school",
    "university": "university",
    # Finance & services
    "bank":       "bank",
    "atm":        "atm",
    "fuel":       "fuel",
    "gas":        "fuel",
    "gas station": "fuel",
}

# Keywords whose correct OSM tag is shop= or craft=, NOT amenity=.
# The current Overpass query only supports amenity= lookups, so these
# cannot return accurate results yet. They are listed here explicitly
# so the fallback is logged clearly instead of failing silently.
_SHOP_OR_CRAFT_KEYWORDS: dict[str, str] = {
    "plumber":     "craft=plumber",
    "electrician": "craft=electrician",
    "mechanic":    "shop=car_repair",
    "car repair":  "shop=car_repair",
    "salon":       "shop=beauty",
    "hair salon":  "shop=hairdresser",
    "hairdresser": "shop=hairdresser",
    "barber":      "shop=barber",
    "bakery":      "shop=bakery",
    "florist":     "shop=florist",
    "tailor":      "shop=tailor",
    "optician":    "shop=optician",
}


def fetch_osm_leads(keyword: str, location: str) -> list[dict]:
    """
    Fetch businesses from OpenStreetMap via Overpass API
    """

    keyword = keyword.lower()

    if keyword in _SHOP_OR_CRAFT_KEYWORDS:
        osm_tag            = _SHOP_OR_CRAFT_KEYWORDS[keyword]   # e.g. "craft=plumber"
        namespace, value   = osm_tag.split("=", 1)              # "craft", "plumber"
        print(f"[OSM] category: keyword='{keyword}' → {osm_tag}")
    elif keyword in AMENITY_MAP:
        namespace = "amenity"
        value     = AMENITY_MAP[keyword]
        print(f"[OSM] category: keyword='{keyword}' → amenity='{value}'")
    else:
        namespace = "amenity"
        value     = "restaurant"
        print(
            f"[OSM] category: keyword='{keyword}'"
            f" | no mapping found → falling back to amenity='restaurant'"
        )

    south, west, north, east = _resolve_bbox(location)

    url = "https://overpass.kumi.systems/api/interpreter"

    query = f"""
[out:json];
node["{namespace}"="{value}"]({south},{west},{north},{east});
out;
"""

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.post(
        url,
        data={"data": query},
        headers=headers,
        timeout=20
    )

    if response.status_code != 200:
        print("OSM ERROR:", response.status_code, response.text[:200])
        return []

    try:
        data = response.json()
    except Exception as e:
        print("OSM JSON ERROR:", str(e))
        print(response.text[:200])
        return []

    leads = []

    for el in data.get("elements", []):
        tags        = el.get("tags", {})
        raw_website = tags.get("website", "")

        osm_phone   = tags.get("phone") or tags.get("contact:phone") or ""
        osm_address = _build_osm_address(tags)

        leads.append({
            "full_name":      tags.get("name", ""),
            "company":        tags.get("name", ""),
            "title":          "owner",
            "location":       location,
            "email":          "",
            "domain":         _normalize_domain(raw_website),
            "website":        raw_website,
            "email_candidates": [],
            "source":         "osm",
            "phone":          osm_phone,
            "phone_source":   "osm" if osm_phone else "",
            "address":        osm_address,
            "address_source": "osm" if osm_address else "",
        })

    total        = len(leads)
    with_website = sum(1 for l in leads if l.get("website", "").strip())
    with_domain  = sum(1 for l in leads if l.get("domain",  "").strip())
    no_website   = total - with_website
    no_domain    = total - with_domain

    def _pct(n: int) -> str:
        return f"{n / total * 100:.0f}%" if total else "n/a"

    print(
        f"[OSM] leads={total}"
        f" | website: {with_website} ({_pct(with_website)}) present,"
        f" {no_website} ({_pct(no_website)}) missing"
        f" | domain: {with_domain} ({_pct(with_domain)}) present,"
        f" {no_domain} ({_pct(no_domain)}) missing"
    )

    return leads
