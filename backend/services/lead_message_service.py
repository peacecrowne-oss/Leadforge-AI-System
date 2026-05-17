"""
lead_message_service.py

Simulated message sending and status tracking.
Does NOT send real emails — marks leads with sent/no_email status.
"""
import os

TEST_MODE  = os.getenv("EMAIL_TEST_MODE", "false").lower() == "true"
TEST_EMAIL = "peacecrowne@gmail.com"
TEST_PHONE = "+18322777883"


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

        # Gate: fabricated emails must never reach a send path.
        # Checked before TEST_MODE substitution so the guessed address
        # is never overwritten with a real test target either.
        if lead.get("fabricated_email"):
            lead["message_status"] = "skipped_fabricated_email"
            updated.append(lead)
            continue

        if TEST_MODE:
            # Preserve originals before overriding with test targets
            lead["original_email"] = lead.get("email")
            lead["original_phone"] = lead.get("phone")

            if lead.get("email"):
                lead["email"] = TEST_EMAIL

            if lead.get("phone"):
                lead["phone"] = TEST_PHONE

        if lead.get("email"):
            lead["message_status"] = "sent"
            lead["message"]        = message
        else:
            lead["message_status"] = "no_email"

        updated.append(lead)

    sent     = sum(1 for l in updated if l.get("message_status") == "sent")
    skipped  = sum(1 for l in updated if l.get("message_status") == "skipped_fabricated_email")
    no_email = sum(1 for l in updated if l.get("message_status") == "no_email")
    print(
        f"[SEND GATE] total={len(updated)}"
        f" | sent={sent}"
        f" | skipped_fabricated={skipped}"
        f" | no_email={no_email}"
    )

    return updated
