import requests
from bs4 import BeautifulSoup


BLOCKED_DOMAINS = [
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "linkedin.com",
    "youtube.com",
    "google.com",
    "yelp.com",
    "tripadvisor.com",
    "apps.apple.com",
]


def scrape_business_domains(url: str) -> list[str]:
    """
    Extract business domains from a listing page
    """

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(url, headers=headers, timeout=5)

    soup = BeautifulSoup(response.text, "html.parser")

    domains = []

    for card in soup.select("div.restaurant-card"):
        a = card.select_one("a")

        if not a:
            continue

        href = a.get("href")

        if not href:
            continue

        # Convert relative → absolute
        if href.startswith("/"):
            href = "https://www.restaurantji.com" + href

        if not href.startswith("http"):
            continue

        domain = href.split("//")[-1].split("/")[0].lower()

        # Skip directory domain itself
        if "restaurantji.com" in domain:
            continue

        # Apply existing blocked filters
        if any(block in domain for block in BLOCKED_DOMAINS):
            continue

        domains.append(domain)

    return list(set(domains))
