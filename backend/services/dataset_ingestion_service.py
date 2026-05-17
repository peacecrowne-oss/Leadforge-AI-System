import csv
import requests
import os

DATASET_URLS = [
    "https://raw.githubusercontent.com/npboston/restaurant-inspections/master/data/restaurants.csv"
]

DATA_PATH = "data/leads.csv"


def refresh_datasets():
    """
    Download and merge datasets into leads.csv
    """

    all_rows = []

    for url in DATASET_URLS:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0"
            }

            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code != 200:
                continue

            lines = response.text.splitlines()
            reader = csv.DictReader(lines)

            for row in reader:
                all_rows.append({
                    "full_name": row.get("business_name", ""),
                    "company": row.get("business_name", ""),
                    "title": "owner",
                    "location": row.get("city", ""),
                    "email": "",
                    "domain": "",
                    "website": "",
                    "email_candidates": [],
                    "source": "dataset",
                })

        except Exception:
            continue

    os.makedirs("data", exist_ok=True)

    with open(DATA_PATH, "w", newline="", encoding="utf-8") as f:
        if all_rows:
            fieldnames = all_rows[0].keys()
        else:
            fieldnames = [
                "full_name",
                "company",
                "title",
                "location",
                "email",
                "domain",
                "website",
                "email_candidates",
                "source",
            ]

        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        if all_rows:
            writer.writerows(all_rows)
