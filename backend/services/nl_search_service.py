"""Natural-language query parser for LeadForge lead search.

Rule-based only — no external APIs, fully deterministic.

Public API:
    parse_query(query: str) -> dict
"""
import re

# ── Compiled patterns ─────────────────────────────────────────────────────────

# "top 5" or "top 20" anywhere in the query
_LIMIT_RE = re.compile(r'\btop\s+(\d+)\b', re.I)

# "in San Francisco" — stops before "at", "from", "with", or end of string
_LOCATION_RE = re.compile(
    r'\bin\s+([A-Za-z][A-Za-z ,]+?)(?=\s+at\b|\s+from\b|\s+with\b|$)',
    re.I,
)

# "at OpenAI" — stops before "in", "from", "with", or end of string
_COMPANY_RE = re.compile(
    r'\bat\s+([A-Za-z][A-Za-z &.,]+?)(?=\s+in\b|\s+from\b|\s+with\b|$)',
    re.I,
)

# ── Vocabulary ────────────────────────────────────────────────────────────────

_SENIORITY_TERMS = frozenset({
    'senior', 'junior', 'principal', 'staff', 'lead', 'director', 'manager',
    'vp', 'head', 'chief', 'ceo', 'cto', 'cfo', 'intern', 'associate', 'executive',
})

_STOP_WORDS = frozenset({
    'find', 'me', 'a', 'an', 'the', 'some', 'and', 'or', 'of', 'for', 'with',
    'who', 'that', 'are', 'is', 'i', 'want', 'need', 'looking', 'top', 'please',
    'help', 'show', 'get', 'search', 'list', 'give',
})

_DEFAULT_LIMIT = 10
_MAX_LIMIT     = 200


# ── Public API ────────────────────────────────────────────────────────────────

def parse_query(query: str) -> dict:
    """Parse a natural-language query into LeadSearchRequest field values.

    Extraction order:
      1. limit    — "top N" anywhere in the query
      2. location — "in <City>" (stops before "at …")
      3. company  — "at <Company>" (stops before "in …")
      4. remaining tokens:
            seniority words  → title
            all other words  → keywords

    Args:
        query: Raw user query string.

    Returns:
        dict with keys: keywords, title, location, company, limit.
        String values are stripped; limit is always a positive int.

    Examples:
        >>> parse_query("Find senior engineers in San Francisco at OpenAI")
        {'keywords': 'engineers', 'title': 'senior',
         'location': 'San Francisco', 'company': 'OpenAI', 'limit': 10}

        >>> parse_query("top 5 marketing directors at Google")
        {'keywords': 'marketing', 'title': 'directors',
         'location': None, 'company': 'Google', 'limit': 5}
    """
    text = query.strip()

    # ── 1. Limit ("top N") ────────────────────────────────────────────────────
    limit = _DEFAULT_LIMIT
    m = _LIMIT_RE.search(text)
    if m:
        limit = max(1, min(_MAX_LIMIT, int(m.group(1))))
        text = text[:m.start()] + text[m.end():]

    # ── 2. Location ("in <City>") ─────────────────────────────────────────────
    location = None
    m = _LOCATION_RE.search(text)
    if m:
        location = m.group(1).strip().rstrip(',')
        text = text[:m.start()] + text[m.end():]

    # ── 3. Company ("at <Company>") ───────────────────────────────────────────
    company = None
    m = _COMPANY_RE.search(text)
    if m:
        company = m.group(1).strip().rstrip(',. ')
        text = text[:m.start()] + text[m.end():]

    # ── 4. Remaining tokens → title and keywords ──────────────────────────────
    tokens = [t.lower() for t in re.split(r'\s+', text.strip()) if t]
    seniority_tokens: list[str] = []
    keyword_tokens:   list[str] = []

    for tok in tokens:
        if tok in _STOP_WORDS:
            continue
        if tok in _SENIORITY_TERMS:
            seniority_tokens.append(tok)
        else:
            keyword_tokens.append(tok)

    title    = ' '.join(seniority_tokens) or None
    keywords = ' '.join(keyword_tokens) or None

    return {
        "keywords": keywords,
        "title":    title,
        "location": location,
        "company":  company,
        "limit":    limit,
    }
