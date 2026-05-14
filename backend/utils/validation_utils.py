"""
Validation utilities - regex patterns and helpers.
"""
import re

EMAIL_RE   = re.compile(r'^[\w\.-]+@[\w\.-]+\.\w{2,}$')
PHONE_RE   = re.compile(r'^\+?[\d\s\-\(\)]{7,15}$')
URL_RE     = re.compile(r'^https?://')
DATE_FMTS  = [
    "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y",
    "%d-%m-%Y", "%Y/%m/%d", "%B %d, %Y",
]

def is_valid_email(val: str) -> bool:
    return bool(EMAIL_RE.match(str(val).strip()))

def is_valid_phone(val: str) -> bool:
    return bool(PHONE_RE.match(str(val).strip()))

def looks_like_date(series_sample: list[str]) -> bool:
    from datetime import datetime
    hits = 0
    for v in series_sample[:50]:
        for fmt in DATE_FMTS:
            try:
                datetime.strptime(str(v).strip(), fmt)
                hits += 1
                break
            except ValueError:
                pass
    return hits / max(len(series_sample[:50]), 1) > 0.6
