"""
lead_message_service.py

Simulated message sending and status tracking.
Does NOT send real emails — marks leads with sent/no_email status.
"""


def send_message_to_leads(leads: list[dict], message: str) -> list[dict]:
    """
    Simulate sending a message to each lead and track delivery status.

    Leads with an email address are marked "sent".
    Leads without an email are marked "no_email".
    Returns a new list; originals are not mutated.
    """
    updated = []

    for lead in leads:
        lead = dict(lead)  # shallow copy — do not mutate original

        if lead.get("email"):
            lead["message_status"] = "sent"
            lead["message"]        = message
        else:
            lead["message_status"] = "no_email"

        updated.append(lead)

    return updated
