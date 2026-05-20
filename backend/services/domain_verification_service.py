"""
domain_verification_service.py

Lightweight verification of domain reachability and email-delivery signals.
No SMTP probing, no paid APIs, no headless browsers.

Signals produced:
  domain_verified          — domain resolves to at least one A/AAAA address (stdlib socket)
  mx_present               — at least one MX record exists (dnspython; None when unavailable)
  phone_verified           — phone string contains 7–15 digits (plausibility, not SMTP)
  verification_checked_at  — ISO-8601 UTC timestamp of this check
"""
import socket
from datetime import datetime, timezone

try:
    import dns.resolver as _dns_resolver
    _DNS_AVAILABLE = True
except ImportError:
    _DNS_AVAILABLE = False

_MX_TIMEOUT = 3  # seconds per MX query


def _resolve_domain(domain: str) -> bool:
    """Return True if domain resolves to at least one address (A or AAAA)."""
    try:
        socket.getaddrinfo(domain, None)
        return True
    except (socket.gaierror, OSError):
        return False


def _has_mx(domain: str) -> bool | None:
    """
    Return True when at least one MX record is found, False when query
    succeeds but returns none, None when dnspython is not installed.
    """
    if not _DNS_AVAILABLE:
        return None
    try:
        answers = _dns_resolver.resolve(domain, "MX", lifetime=_MX_TIMEOUT)
        return len(answers) > 0
    except Exception:
        return False


def _phone_plausible(phone: str | None) -> bool:
    """
    Return True when phone is non-null and contains 7–15 digits.

    Phones in our pipeline are already normalized by _normalize_phone in
    website_email_extractor, so any non-null scraped phone passed digit-count
    and garbage filtering. This re-confirms plausibility for phones sourced
    from OSM or other pre-normalization paths.
    """
    if not phone:
        return False
    digits = "".join(c for c in phone if c.isdigit())
    return 7 <= len(digits) <= 15


def verify_domain_signals(domain: str, phone: str | None = None) -> dict:
    """
    Run all verification checks for a single domain.

    Returns a dict with:
      domain_verified          — bool
      mx_present               — bool | None (None = dnspython not installed)
      phone_verified           — bool
      verification_checked_at  — ISO-8601 UTC string
    """
    import time as _time
    _t0 = _time.monotonic()

    dom_verified = _resolve_domain(domain)
    _a_ms = round((_time.monotonic() - _t0) * 1000)

    mx = _has_mx(domain)
    _mx_ms = round((_time.monotonic() - _t0) * 1000)

    phone_ok = _phone_plausible(phone)

    print(
        f"[VERIFY] domain={domain}"
        f" | A-record={dom_verified} ({_a_ms}ms)"
        f" | MX={mx} (cumulative {_mx_ms}ms)"
        f" | phone_plausible={phone_ok}"
        f" | dns_lib={'dnspython' if _DNS_AVAILABLE else 'unavailable'}"
    )

    return {
        "domain_verified":         dom_verified,
        "mx_present":              mx,
        "phone_verified":          phone_ok,
        "verification_checked_at": datetime.now(timezone.utc).isoformat(),
    }
