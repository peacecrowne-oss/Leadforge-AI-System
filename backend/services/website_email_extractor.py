"""
website_email_extractor.py

Scrape email addresses and lightweight business details (phone, address,
contact name) from a domain's public web pages.

Extraction sources in descending trust order:
  json_ld              — schema.org JSON-LD structured data
  scraped_html         — tel: hyperlinks or regex on the homepage
  scraped_contact_page — tel: hyperlinks or regex on /contact[/-us]
"""
import json
import re
import requests

try:
    from bs4 import BeautifulSoup
    _BS4 = True
except ImportError:
    _BS4 = False

EMAIL_REGEX = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"

# Strict: requires at least one separator between digit groups so bare numeric
# strings (dates, IDs, prices) in general body text are not matched.
PHONE_REGEX = r"\+?1?[-.\s]?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}"

# Loose: optional separators; used only in high-signal contexts (tel: link
# values, footer/header elements, contact pages) where context guarantees phones.
PHONE_REGEX_LOOSE = r"\+?1?[\s.\-]?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}"

# Digit strings that are never real phone numbers.
_GARBAGE_DIGITS = {
    "0000000", "1234567", "7654321",
    "0000000000", "1234567890", "0987654321",
    "1111111111", "2222222222", "3333333333", "4444444444", "5555555555",
    "6666666666", "7777777777", "8888888888", "9999999999",
}

_HEADERS = {"User-Agent": "LeadForge-Research/1.0 (research)"}


# ── Phone normalization & validation ──────────────────────────────────────────

def _normalize_phone(raw: str) -> str | None:
    """
    Validate and normalize a raw phone string.

    - Strips tel: scheme prefix.
    - Validates digit count: 7 (min local) to 15 (ITU max).
    - Rejects all-same-digit and known-garbage sequences.
    - US/CA numbers (10 digits, or 11 starting with 1): formatted as (XXX) XXX-XXXX.
    - Other valid strings: returned as cleaned digits (international).
    Returns None when the input is not a credible phone number.
    """
    if not raw:
        return None
    s = raw.strip()
    if s.lower().startswith("tel:"):
        s = s[4:].strip()
    has_plus = s.startswith("+")
    digits = re.sub(r"\D", "", s)
    n = len(digits)
    if n < 7 or n > 15:
        return None
    if digits in _GARBAGE_DIGITS:
        return None
    if len(set(digits)) == 1:
        return None
    # US/CA: strip leading country code 1 when 11 digits
    if n == 11 and digits[0] == "1":
        digits = digits[1:]
        n = 10
    if n == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return f"+{digits}" if has_plus else digits


# ── Existing email extraction (unchanged) ─────────────────────────────────────

def extract_emails_from_domain(domain: str) -> list[str]:
    """Fetch homepage and several sub-paths; return all unique emails found."""
    base_urls = [f"https://{domain}", f"http://{domain}"]
    paths = ["", "/contact", "/contact-us", "/about", "/about-us"]
    urls_to_try = [base + path for base in base_urls for path in paths]

    all_emails = []
    for url in urls_to_try:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code != 200:
                continue
            all_emails.extend(re.findall(EMAIL_REGEX, response.text))
        except requests.exceptions.RequestException:
            continue
    return list(set(all_emails))


# ── Business-detail extraction helpers ────────────────────────────────────────

def _fetch(url: str, timeout: int = 5) -> str | None:
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout)
        if resp.status_code == 200:
            return resp.text
    except requests.exceptions.RequestException:
        pass
    return None


def _parse_json_ld(html: str) -> list[dict]:
    if not _BS4:
        return []
    soup = BeautifulSoup(html, "html.parser")
    blocks: list[dict] = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
            if isinstance(data, list):
                blocks.extend(data)
            elif isinstance(data, dict):
                blocks.append(data)
        except (json.JSONDecodeError, ValueError):
            pass
    return blocks


def _ld_telephone(blocks: list[dict]) -> str | None:
    for b in blocks:
        if not isinstance(b, dict):
            continue
        for key in ("telephone", "phone"):
            val = b.get(key)
            if val:
                return str(val).strip()
    return None


def _ld_address(blocks: list[dict]) -> str | None:
    for b in blocks:
        if not isinstance(b, dict):
            continue
        addr = b.get("address")
        if isinstance(addr, dict):
            parts = [
                addr.get("streetAddress"),
                addr.get("addressLocality"),
                addr.get("addressRegion"),
                addr.get("postalCode"),
            ]
            combined = ", ".join(p for p in parts if p)
            if combined:
                return combined
        elif isinstance(addr, str) and addr.strip():
            return addr.strip()
    return None


def _ld_contact_name(blocks: list[dict]) -> str | None:
    for b in blocks:
        if not isinstance(b, dict):
            continue
        for key in ("employee", "founder", "owner"):
            val = b.get(key)
            if isinstance(val, dict) and val.get("name"):
                return val["name"]
            if isinstance(val, list) and val:
                first = val[0]
                if isinstance(first, dict) and first.get("name"):
                    return first["name"]
    return None


def _html_telephone(html: str, *, contact_page: bool = False) -> str | None:
    """
    Extract and return the first valid, normalized phone number from HTML.

    Strategy (in confidence order):
      1. tel: href links anywhere on the page — explicit, lowest noise.
      2. Regex over <footer> and <header> elements — loose pattern, medium noise.
      3. Regex over full page text — strict pattern (contact_page=True uses loose).
    All candidates are validated and normalized through _normalize_phone.
    """
    candidates: list[str] = []

    if _BS4:
        soup = BeautifulSoup(html, "html.parser")

        # 1. tel: links — explicit, highest confidence
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.lower().startswith("tel:"):
                candidates.append(href[4:].strip())

        # 2. Footer and header elements — semi-structured, use loose pattern
        for section_tag in ("footer", "header"):
            section = soup.find(section_tag)
            if section:
                candidates.extend(re.findall(PHONE_REGEX_LOOSE, section.get_text(" ")))

        # 3. Full page text — strict by default; loose only on contact/about pages
        if not candidates:
            pattern = PHONE_REGEX_LOOSE if contact_page else PHONE_REGEX
            candidates.extend(re.findall(pattern, soup.get_text(" ")))
    else:
        pattern = PHONE_REGEX_LOOSE if contact_page else PHONE_REGEX
        candidates.extend(re.findall(pattern, html))

    for raw in candidates:
        phone = _normalize_phone(raw)
        if phone:
            return phone
    return None


# ── Public entry point ────────────────────────────────────────────────────────

def extract_business_details(domain: str) -> dict:
    """
    Fetch the homepage (HTTPS then HTTP) and optionally contact/about pages to
    extract phone, address, and contact_name.

    Returns a dict containing only fields that were found.  Each field is
    paired with a *_source key indicating extraction confidence:
      "json_ld"              — structured data, machine-readable  (high trust)
      "scraped_html"         — tel: link or regex on homepage      (medium trust)
      "scraped_contact_page" — tel: link or regex on /contact      (medium trust)
    All extracted phone numbers are normalized via _normalize_phone.
    """
    result: dict = {}

    homepage = _fetch(f"https://{domain}") or _fetch(f"http://{domain}")
    if not homepage:
        return result

    blocks = _parse_json_ld(homepage)

    # ── Phone ────────────────────────────────────────────────────────────────
    phone = _normalize_phone(_ld_telephone(blocks) or "")
    if phone:
        result["phone"] = phone
        result["phone_source"] = "json_ld"
    else:
        phone = _html_telephone(homepage)
        if phone:
            result["phone"] = phone
            result["phone_source"] = "scraped_html"

    # ── Address ──────────────────────────────────────────────────────────────
    address = _ld_address(blocks)
    if address:
        result["address"] = address
        result["address_source"] = "json_ld"

    # ── Contact name ─────────────────────────────────────────────────────────
    name = _ld_contact_name(blocks)
    if name:
        result["contact_name"] = name
        result["contact_name_source"] = "json_ld"

    # ── Contact/about page fallback (phone only, up to 4 extra requests) ─────
    if "phone" not in result:
        contact_paths = ["/contact", "/contact-us", "/about", "/about-us"]
        for path in contact_paths:
            contact_html = _fetch(f"https://{domain}{path}")
            if not contact_html:
                continue
            contact_blocks = _parse_json_ld(contact_html)
            raw_ld = _ld_telephone(contact_blocks)
            phone = _normalize_phone(raw_ld or "") or _html_telephone(contact_html, contact_page=True)
            if phone:
                result["phone"] = phone
                result["phone_source"] = "scraped_contact_page"
                break

    return result
