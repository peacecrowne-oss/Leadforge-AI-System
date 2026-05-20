"""
osm_lead_source.py

Fetch businesses from OpenStreetMap via Overpass API.

CATEGORY_CATALOG groups all supported keyword → OSM-tag mappings by namespace.
_KEYWORD_MAP is a flat lookup dict built from CATEGORY_CATALOG at module load
for O(1) routing in fetch_osm_leads.

Supported OSM namespaces:
  amenity=    public/commercial spaces (cafes, clinics, banks, laundromats …)
  shop=       retail establishments (bakery, auto repair, nail salon …)
  craft=      skilled trades (plumber, electrician, roofer, brewer …)
  office=     professional services (lawyer, accountant, real estate …)
  leisure=    recreational / wellness facilities (gym, spa, dance studio …)
  tourism=    accommodation (hotel, motel, hostel …)
  healthcare= allied health professionals (chiropractor, physiotherapist …)

Coverage limitation: the Overpass query targets node elements only.
Many offices and large venues are mapped as way/relation in OSM — those will
not appear in results.  Namespaces most affected: office=, healthcare=.
"""
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


def _osm_confidence(name: str, domain: str, phone: str, el_type: str) -> str:
    """Compute provider-level confidence from OSM data completeness.

    Signals counted: domain present (+1), phone present (+1).
    Way and relation elements implicitly carry one extra signal because they
    require intentional area/multipolygon mapping — a more complete entry.

    high   — 2+ signals  (name + domain + phone, or named way/relation with one signal)
    medium — 1 signal    (name + domain or phone)
    low    — 0 signals   (name only, or anonymous)
    """
    if not name:
        return "low"
    signals = sum(bool(x) for x in (domain, phone))
    if el_type in ("way", "relation"):
        signals += 1
    if signals >= 2:
        return "high"
    if signals == 1:
        return "medium"
    return "low"


# ── Category catalog ──────────────────────────────────────────────────────────
# CATEGORY_CATALOG: {namespace: {keyword: osm_value}}
#
# To add a new category: append a keyword → value pair in the correct namespace
# section below.  The keyword should be lowercase.  Use the OSM wiki to confirm
# the tag value is in active use before adding it.
#
# To add a new namespace: add a new top-level key and update _SPARSE_NAMESPACES
# if node coverage is known to be thin for that namespace.

CATEGORY_CATALOG: dict[str, dict[str, str]] = {

    # ── amenity= ──────────────────────────────────────────────────────────────
    # Public and commercial spaces, healthcare facilities, civic services.
    # Best node density of all namespaces — most reliable for lead counts.
    "amenity": {
        # Food & drink
        "restaurant":           "restaurant",
        "food":                 "restaurant",
        "pizza":                "restaurant",
        "burger":               "restaurant",
        "cafe":                 "cafe",
        "coffee":               "cafe",
        "coffee shop":          "cafe",
        "bar":                  "bar",
        "pub":                  "pub",
        "fast food":            "fast_food",
        "fast_food":            "fast_food",
        # Healthcare — facility level
        "dentist":              "dentist",
        "clinic":               "clinic",
        "urgent care":          "clinic",
        "urgent_care":          "clinic",
        "pharmacy":             "pharmacy",
        "hospital":             "hospital",
        "doctor":               "doctors",
        "doctors":              "doctors",
        "vet":                  "veterinary",
        "veterinary":           "veterinary",
        "animal hospital":      "veterinary",
        "pet hospital":         "veterinary",
        # Finance
        "bank":                 "bank",
        "atm":                  "atm",
        # Transport / fuel
        "fuel":                 "fuel",
        "gas":                  "fuel",
        "gas station":          "fuel",
        # Education
        "school":               "school",
        "university":           "university",
        "college":              "university",
        # Community / social
        "church":               "place_of_worship",
        "place of worship":     "place_of_worship",
        "mosque":               "place_of_worship",
        "synagogue":            "place_of_worship",
        "nonprofit":            "social_facility",
        # Services
        "laundromat":           "laundry",
        "laundry":              "laundry",
        "daycare":              "childcare",
        "child care":           "childcare",
        "childcare":            "childcare",
        "coworking":            "coworking",
    },

    # ── shop= ─────────────────────────────────────────────────────────────────
    # Retail establishments and consumer-facing service shops.
    "shop": {
        # Food retail
        "bakery":               "bakery",
        "grocery":              "supermarket",
        "supermarket":          "supermarket",
        "convenience store":    "convenience",
        "convenience":          "convenience",
        "liquor store":         "alcohol",
        "liquor":               "alcohol",
        # Beauty & personal care
        "nail salon":           "beauty",
        "nail":                 "beauty",
        "beauty":               "beauty",
        "hair salon":           "hairdresser",
        "hairdresser":          "hairdresser",
        "barber":               "barber",
        "barber shop":          "barber",
        "optician":             "optician",
        # Home & garden
        "florist":              "florist",
        "tailor":               "tailor",
        # Automotive (both retail and repair use shop= in OSM)
        "car dealer":           "car",
        "auto dealer":          "car",
        "dealership":           "car",
        "auto repair":          "car_repair",
        "car repair":           "car_repair",
        "mechanic":             "car_repair",
        "auto mechanic":        "car_repair",
        # Pets
        "pet grooming":         "pet",
        "pet shop":             "pet",
        # Other services
        "storage":              "storage_rental",
        "printing":             "copyshop",
        "print":                "copyshop",
        "copy shop":            "copyshop",
        # No standard OSM tag for moving companies — coverage will be sparse
        "moving company":       "moving",
        "moving":               "moving",
    },

    # ── craft= ───────────────────────────────────────────────────────────────
    # Skilled-trade businesses: tradespeople, artisans, contractors.
    # Node coverage is moderate — many trades operate from a home address.
    "craft": {
        "plumber":              "plumber",
        "plumbing":             "plumber",
        "electrician":          "electrician",
        "electrical":           "electrician",
        "carpenter":            "carpenter",
        "carpentry":            "carpenter",
        "roofing":              "roofer",
        "roofer":               "roofer",
        "hvac":                 "hvac",
        "air conditioning":     "hvac",
        "contractor":           "builder",
        "general contractor":   "builder",
        "builder":              "builder",
        "cleaning service":     "cleaning",
        "cleaning":             "cleaning",
        "maid service":         "cleaning",
        "janitorial":           "cleaning",
        "photography":          "photographer",
        "photographer":         "photographer",
        "brewery":              "brewery",
        "microbrewery":         "brewery",
        "painter":              "painter",
        "painting":             "painter",
        "landscaping":          "gardener",
        "landscaper":           "gardener",
        "lawn care":            "gardener",
        "window cleaning":      "window_cleaning",
        "pest control":         "pest_control",
    },

    # ── office= ──────────────────────────────────────────────────────────────
    # Professional service offices.
    # SPARSE: office entities are frequently mapped as way/relation, not node.
    # Expect lower lead counts than amenity= or shop= searches.
    "office": {
        "lawyer":               "lawyer",
        "attorney":             "lawyer",
        "law firm":             "lawyer",
        "legal":                "lawyer",
        "accountant":           "accountant",
        "accounting":           "accountant",
        "cpa":                  "accountant",
        "bookkeeping":          "accountant",
        "insurance":            "insurance",
        "insurance agency":     "insurance",
        "real estate":          "estate_agent",
        "realtor":              "estate_agent",
        "estate agent":         "estate_agent",
        "realty":               "estate_agent",
        "marketing agency":     "advertising_agency",
        "marketing":            "advertising_agency",
        "advertising":          "advertising_agency",
        "consulting":           "consulting",
        "consultant":           "consulting",
        "management consulting":"consulting",
        "travel agency":        "travel_agent",
        "travel agent":         "travel_agent",
        "financial advisor":    "financial",
        "financial":            "financial",
        "wealth management":    "financial",
        "tax advisor":          "tax_advisor",
        "tax":                  "tax_advisor",
        "tax preparation":      "tax_advisor",
    },

    # ── leisure= ─────────────────────────────────────────────────────────────
    # Recreational and wellness facilities.
    "leisure": {
        "gym":                  "fitness_centre",
        "fitness":              "fitness_centre",
        "fitness studio":       "fitness_centre",
        "yoga":                 "fitness_centre",
        "yoga studio":          "fitness_centre",
        "pilates":              "fitness_centre",
        "crossfit":             "fitness_centre",
        "martial arts":         "fitness_centre",
        "boxing":               "fitness_centre",
        "spa":                  "spa",
        "day spa":              "spa",
        "swimming pool":        "swimming_pool",
        "pool":                 "swimming_pool",
        "dance studio":         "dance",
        "dance":                "dance",
        "golf":                 "golf_course",
        "golf course":          "golf_course",
        "sports":               "sports_centre",
        "sports complex":       "sports_centre",
    },

    # ── tourism= ─────────────────────────────────────────────────────────────
    # Accommodation and visitor services.
    "tourism": {
        "hotel":                "hotel",
        "motel":                "motel",
        "hostel":               "hostel",
        "bed and breakfast":    "guest_house",
        "b&b":                  "guest_house",
        "inn":                  "guest_house",
        "vacation rental":      "apartment",
        "campground":           "camp_site",
        "camping":              "camp_site",
    },

    # ── healthcare= ──────────────────────────────────────────────────────────
    # Allied health professionals distinct from amenity=clinic / amenity=doctors.
    # SPARSE: healthcare= is a newer OSM key; node density varies widely by region.
    "healthcare": {
        "chiropractor":         "chiropractor",
        "chiropractic":         "chiropractor",
        "physical therapy":     "physiotherapist",
        "physiotherapy":        "physiotherapist",
        "physical therapist":   "physiotherapist",
        "optometrist":          "optometrist",
        "eye doctor":           "optometrist",
        "eye care":             "optometrist",
        "psychologist":         "psychologist",
        "therapist":            "psychologist",
        "mental health":        "psychologist",
        "counselor":            "psychologist",
        "counseling":           "psychologist",
        "dietitian":            "dietitian",
        "nutritionist":         "dietitian",
        "massage":              "alternative",
        "massage therapy":      "alternative",
        "acupuncture":          "alternative",
        "naturopath":           "alternative",
    },
}

# Flat routing map: keyword (lowercase) → (namespace, osm_value).
# Built once at module load from CATEGORY_CATALOG — O(1) lookup per search.
# When a keyword appears in multiple namespace sections, the last entry wins.
_KEYWORD_MAP: dict[str, tuple[str, str]] = {
    keyword: (namespace, value)
    for namespace, entries in CATEGORY_CATALOG.items()
    for keyword, value in entries.items()
}

# Namespaces where overall OSM data density is thin regardless of element type.
# office= and healthcare= simply have fewer total entries than amenity= or shop=.
# nwr queries fetch all element types, so this is a data-coverage note, not a
# query-mode limitation.
_SPARSE_NAMESPACES = frozenset({"office", "healthcare"})


def fetch_osm_leads(keyword: str, location: str) -> list[dict]:
    """
    Fetch businesses from OpenStreetMap via Overpass API.

    Routes keyword to the correct OSM namespace and tag value via _KEYWORD_MAP
    (built from CATEGORY_CATALOG).  Unknown keywords fall back to
    amenity=restaurant with a warning log.
    """
    keyword_lower = keyword.lower().strip()

    if keyword_lower in _KEYWORD_MAP:
        namespace, value = _KEYWORD_MAP[keyword_lower]
        _coverage = (
            " | NOTE: sparse OSM data density — fewer total entries for this namespace"
            if namespace in _SPARSE_NAMESPACES
            else ""
        )
        print(
            f"[OSM] keyword='{keyword_lower}'"
            f" → namespace='{namespace}' tag='{namespace}={value}'"
            + _coverage
        )
    else:
        namespace = "amenity"
        value     = "restaurant"
        print(
            f"[OSM] keyword='{keyword_lower}'"
            f" → UNSUPPORTED: no mapping in CATEGORY_CATALOG"
            f" | fallback=amenity=restaurant"
            f" | fix: add '{keyword_lower}' to CATEGORY_CATALOG in osm_lead_source.py"
        )

    south, west, north, east = _resolve_bbox(location)

    url = "https://overpass.kumi.systems/api/interpreter"

    query = f"""
[out:json];
nwr["{namespace}"="{value}"]({south},{west},{north},{east});
out center;
"""

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    import time as _time
    _http_t0 = _time.perf_counter()
    response = requests.post(
        url,
        data={"data": query},
        headers=headers,
        timeout=20
    )
    _http_ms = round((_time.perf_counter() - _http_t0) * 1000)
    print(f"[OSM_TIMING] overpass_http_ms={_http_ms} status={response.status_code}")

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
    nodes = ways = relations = skipped_osm_dup = 0
    # OSM-level dedup: same (name, domain) pair across element types = same
    # physical business mapped as both a node and a way/relation.  Only fires
    # when both name AND domain are non-empty — avoids collapsing distinct
    # chain locations that share a website but are physically separate.
    seen_nwr: set[tuple[str, str]] = set()

    for el in data.get("elements", []):
        el_type = el.get("type", "")
        if el_type == "node":
            nodes += 1
        elif el_type == "way":
            ways += 1
        elif el_type == "relation":
            relations += 1

        tags        = el.get("tags", {})
        name        = tags.get("name", "")
        raw_website = tags.get("website", "")
        domain      = _normalize_domain(raw_website)

        # Dedup: skip if this (name, domain) was already seen from another
        # element type in this result set.
        if name and domain:
            dedup_key = (name.lower(), domain)
            if dedup_key in seen_nwr:
                skipped_osm_dup += 1
                continue
            seen_nwr.add(dedup_key)

        osm_phone   = tags.get("phone") or tags.get("contact:phone") or ""
        osm_address = _build_osm_address(tags)

        leads.append({
            "full_name":              name,
            "company":                name,
            "title":                  "owner",
            "location":               location,
            "email":                  "",
            "domain":                 domain,
            "website":                raw_website,
            "email_candidates":       [],
            "source":                 "osm",
            "phone":                  osm_phone,
            "phone_source":           "osm" if osm_phone else "",
            "address":                osm_address,
            "address_source":         "osm" if osm_address else "",
            "provider":               "osm",
            "provider_entity_type":   el_type or "node",
            "provider_confidence":    _osm_confidence(name, domain, osm_phone, el_type),
        })

    total        = len(leads)
    with_website = sum(1 for l in leads if l.get("website", "").strip())
    with_domain  = sum(1 for l in leads if l.get("domain",  "").strip())
    no_website   = total - with_website
    no_domain    = total - with_domain

    def _pct(n: int) -> str:
        return f"{n / total * 100:.0f}%" if total else "n/a"

    _pc: dict[str, int] = {}
    for _l in leads:
        _k = _l.get("provider_confidence", "low")
        _pc[_k] = _pc.get(_k, 0) + 1

    print(
        f"[OSM] leads={total} (after osm_dup_skip={skipped_osm_dup})"
        f" | node={nodes} way={ways} relation={relations}"
        f" | provider_confidence={_pc}"
        f" | website: {with_website} ({_pct(with_website)}) present,"
        f" {no_website} ({_pct(no_website)}) missing"
        f" | domain: {with_domain} ({_pct(with_domain)}) present,"
        f" {no_domain} ({_pct(no_domain)}) missing"
    )

    return leads
