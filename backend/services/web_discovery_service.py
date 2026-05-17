import base64
import re
import urllib.parse
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse


def extract_real_url(bing_url: str) -> str:
    """
    Extract real URL from Bing redirect link
    """
    try:
        parsed = urllib.parse.urlparse(bing_url)
        query = urllib.parse.parse_qs(parsed.query)

        if "u" in query:
            encoded = query["u"][0]

            # Bing uses base64-like encoding starting with 'a1'
            if encoded.startswith("a1"):
                encoded = encoded[2:]

            decoded = base64.b64decode(encoded).decode("utf-8")
            return decoded

        return bing_url
    except Exception:
        return bing_url


def extract_domain(url: str) -> str:
    """
    Extract clean domain from a URL
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Remove common prefixes
        if domain.startswith("www."):
            domain = domain[4:]

        return domain
    except Exception:
        return ""


def is_valid_business_domain(domain: str) -> bool:
    """
    Allow most domains except obvious junk
    """
    if not domain:
        return False

    blocked = [
        "bing.com"
    ]

    return not any(b in domain for b in blocked)


def generate_email_patterns(domain: str, full_name: str) -> list[str]:
    """
    Generate possible email addresses from domain + name
    """
    if not domain:
        return []

    name_parts = full_name.lower().split()
    first = name_parts[0] if len(name_parts) > 0 else ""
    last  = name_parts[-1] if len(name_parts) > 1 else ""

    emails = []

    if first:
        emails.append(f"{first}@{domain}")

    if first and last:
        emails.append(f"{first}.{last}@{domain}")
        emails.append(f"{first[0]}{last}@{domain}")

    # Generic business emails
    emails.extend([
        f"info@{domain}",
        f"contact@{domain}",
        f"sales@{domain}"
    ])

    return list(set(emails))


def infer_roles(query: str) -> list[str]:
    """
    Infer likely decision-maker roles based on search query
    """

    q = query.lower()

    if "restaurant" in q or "cafe" in q:
        return ["owner", "manager"]

    if "agency" in q or "marketing" in q:
        return ["marketing director", "account manager"]

    if "saas" in q or "software" in q or "tech" in q:
        return ["ceo", "founder", "head of growth"]

    if "real estate" in q:
        return ["broker", "agent"]

    if "lawyer" in q or "law firm" in q:
        return ["partner", "attorney"]

    # default fallback
    return ["owner"]


def validate_email_candidates(emails: list[str], domain: str) -> list[str]:
    """
    Validate and rank email candidates
    """

    if not emails:
        return []

    valid = []

    for email in emails:
        # Basic format check
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            continue

        # Domain consistency check
        if domain and not email.endswith(domain):
            continue

        valid.append(email)

    # Rank emails (priority order)
    priority = ["owner@", "ceo@", "founder@", "info@", "contact@", "sales@"]

    def score(e):
        for i, p in enumerate(priority):
            if e.startswith(p):
                return i
        return len(priority)

    valid.sort(key=score)

    return valid


def search_bing(query: str, location: str = "") -> list[dict]:
    """
    TEMP: Mock data to validate pipeline
    """

    return [
        {
            "full_name": "Houston Pizza Co",
            "company": "Houston Pizza Co",
            "title": "owner",
            "roles": ["owner"],
            "location": "Houston",
            "website": "https://houstonpizza.com",
            "domain": "houstonpizza.com",
            "email": "info@houstonpizza.com",
            "email_candidates": ["info@houstonpizza.com"],
            "source": "mock",
        },
        {
            "full_name": "Bayou Burgers",
            "company": "Bayou Burgers",
            "title": "owner",
            "roles": ["owner"],
            "location": "Houston",
            "website": "https://bayouburgers.com",
            "domain": "bayouburgers.com",
            "email": "contact@bayouburgers.com",
            "email_candidates": ["contact@bayouburgers.com"],
            "source": "mock",
        }
    ]
