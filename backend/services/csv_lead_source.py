import csv
import os


def load_leads_from_csv(file_path: str) -> list[dict]:
    if not os.path.exists(file_path):
        return []

    leads = []

    try:
        with open(file_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                leads.append({
                    "full_name": row.get("full_name", "") or row.get("company", ""),
                    "company": row.get("company", ""),
                    "title": row.get("title", "owner"),
                    "location": row.get("location", ""),
                    "email": row.get("email", ""),
                    "domain": row.get("domain", ""),
                    "website": row.get("website", ""),
                    "email_candidates": [row.get("email")] if row.get("email") else [],
                    "source": row.get("source", "csv"),
                    "provider": "csv",
                })
    except Exception:
        return []

    return leads
