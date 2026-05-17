import itertools
import requests


def generate_domains(keyword: str, location: str) -> list[str]:
    """
    Generate possible business domains from keyword + location
    """

    keyword = keyword.replace(" ", "")
    location = location.replace(" ", "")

    patterns = [
        f"{keyword}{location}.com",
        f"{location}{keyword}.com",
        f"get{keyword}{location}.com",
        f"{keyword}hub{location}.com",
        f"{keyword}{location}tx.com",
    ]

    return list(set(patterns))


def validate_domains(domains: list[str]) -> list[str]:
    """
    Keep only domains that respond to HTTP request
    """

    valid = []

    for domain in domains:
        try:
            url = f"http://{domain}"
            response = requests.get(url, timeout=3)

            if response.status_code == 200 and len(response.text) > 500:
                content = response.text.lower()

                if any(x in content for x in ["domain for sale", "buy this domain", "parked free", "godaddy"]):
                    continue

                valid.append(domain)

        except Exception:
            continue

    return valid
