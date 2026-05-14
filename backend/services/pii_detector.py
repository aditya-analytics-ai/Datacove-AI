"""
pii_detector.py - PII detection and masking service.

Detects and masks personally identifiable information without external deps.
Supported PII types:
  email, phone, ssn, credit_card, ip_address, name (heuristic), postcode

Masking strategies:
  redact   - replace with [REDACTED] or ***
  hash     - first 6 chars of SHA256 hex digest
  fake     - deterministic plausible replacement (no Faker needed)
"""

from __future__ import annotations

import hashlib
import re
import string
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd
from pandas import Series

# ── Regex patterns ────────────────────────────────────────────────────────────

_PATTERNS: Dict[str, re.Pattern] = {
    "email": re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"),
    "phone": re.compile(r"\b(\+?\d[\d\s\-().]{6,14}\d)\b"),
    "ssn": re.compile(r"\b\d{3}[-\s]\d{2}[-\s]\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ \-]?){13,16}\b"),
    "ip_address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "postcode_uk": re.compile(
        r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}\b", re.IGNORECASE
    ),
    "postcode_us": re.compile(r"\b\d{5}(?:-\d{4})?\b"),
}

# Column name keywords that strongly suggest PII content
_NAME_KEYWORDS = ("name", "first", "last", "surname", "fname", "lname", "fullname")
_EMAIL_KEYWORDS = ("email", "e-mail", "mail")
_PHONE_KEYWORDS = ("phone", "mobile", "tel", "cell", "contact")
_ADDRESS_KEYWORDS = ("address", "street", "addr", "postcode", "zipcode", "zip")
_SSN_KEYWORDS = ("ssn", "national_id", "tax_id", "passport", "nino")
_DOB_KEYWORDS = ("dob", "birth", "birthdate", "date_of_birth")


# ── Public API ────────────────────────────────────────────────────────────────


def detect_pii_columns(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Scan a DataFrame and return a list of columns that likely contain PII,
    with the detected PII type and confidence score.
    """
    results: List[Dict[str, Any]] = []
    for col in df.columns:
        pii_type, confidence, match_count = _detect_column_pii(df[col], col)
        if pii_type:
            results.append(
                {
                    "column": col,
                    "pii_type": pii_type,
                    "confidence": confidence,
                    "match_count": match_count,
                    "suggestion": f"Mask or redact '{col}' - contains {pii_type} data.",
                }
            )
    return results


def mask_pii_column(
    series: pd.Series,
    pii_type: str,
    strategy: str = "redact",
) -> pd.Series:
    """
    Apply a masking strategy to a Series.
    strategy: "redact" | "hash" | "fake"
    """
    masker: Callable[..., str] = _MASKERS.get(strategy, _mask_redact)
    return series.apply(lambda v: _apply_mask(v, pii_type, masker))


# ── Detection logic ───────────────────────────────────────────────────────────


def _detect_column_pii(
    series: pd.Series,
    col: str,
) -> Tuple[Optional[str], float, int]:
    col_lower: str = col.lower()

    # 1) Column-name keyword heuristics (high confidence)
    if any(k in col_lower for k in _EMAIL_KEYWORDS):
        return "email", 0.95, int(series.notna().sum())
    if any(k in col_lower for k in _PHONE_KEYWORDS):
        return "phone", 0.95, int(series.notna().sum())
    if any(k in col_lower for k in _SSN_KEYWORDS):
        return "ssn", 0.98, int(series.notna().sum())
    if any(k in col_lower for k in _NAME_KEYWORDS):
        return "name", 0.85, int(series.notna().sum())
    if any(k in col_lower for k in _DOB_KEYWORDS):
        return "date_of_birth", 0.90, int(series.notna().sum())
    if any(k in col_lower for k in _ADDRESS_KEYWORDS):
        return "address", 0.80, int(series.notna().sum())

    # 2) Content-based regex scan on sample
    non_null: Series[str] = series.dropna().astype(str).head(200)
    if len(non_null) == 0:
        return None, 0.0, 0

    for pii_type, pattern in _PATTERNS.items():
        matches = non_null.apply(lambda v: bool(pattern.search(v))).sum()
        ratio = matches / len(non_null)
        if ratio >= 0.50:
            return pii_type, round(float(ratio), 2), int(matches)

    return None, 0.0, 0


# ── Masking strategies ───────────────────────────────────────────────────────


def _apply_mask(val: Any, pii_type: str, masker) -> Any:
    if pd.isna(val) or str(val).strip() == "":
        return val
    return masker(str(val), pii_type)


def _mask_redact(val: str, pii_type: str) -> str:
    """Replace with a [TYPE_REDACTED] token."""
    labels: Dict[str, str] = {
        "email": "[EMAIL_REDACTED]",
        "phone": "[PHONE_REDACTED]",
        "ssn": "[SSN_REDACTED]",
        "credit_card": "[CARD_REDACTED]",
        "ip_address": "[IP_REDACTED]",
        "name": "[NAME_REDACTED]",
        "date_of_birth": "[DOB_REDACTED]",
        "address": "[ADDRESS_REDACTED]",
        "postcode_uk": "[POSTCODE_REDACTED]",
        "postcode_us": "[POSTCODE_REDACTED]",
    }
    return labels.get(pii_type, "[REDACTED]")


def _mask_hash(val: str, pii_type: str) -> str:
    """Replace with first 8 chars of SHA-256 digest (consistent, irreversible)."""
    digest: str = hashlib.sha256(val.encode()).hexdigest()[:8]
    return f"HASH_{digest}"


def _mask_fake(val: str, pii_type: str) -> str:
    """
    Generate a deterministic plausible-looking fake value based on val hash.
    No external library needed.
    """
    seed = int(hashlib.md5(val.encode()).hexdigest(), 16)

    if pii_type == "email":
        users: List[str] = [
            "alice",
            "bob",
            "carol",
            "dave",
            "eve",
            "frank",
            "grace",
            "henry",
        ]
        domains: List[str] = ["example.com", "test.org", "demo.net", "sample.io"]
        return f"{users[seed % len(users)]}{seed % 999}@{domains[(seed // 100) % len(domains)]}"

    if pii_type == "phone":
        n: int = seed % 10_000_000_000
        return f"+1-{n:010d}"[:14]

    if pii_type == "ssn":
        a, b, c = (seed % 899) + 100, (seed % 89) + 10, (seed % 8999) + 1000
        return f"{a:03d}-{b:02d}-{c:04d}"

    if pii_type == "credit_card":
        n: int = (seed % 9_000_000_000_000_000) + 1_000_000_000_000_000
        s = str(n)
        return f"{s[:4]}-{s[4:8]}-{s[8:12]}-{s[12:16]}"

    if pii_type == "ip_address":
        return f"10.{seed % 254 + 1}.{(seed // 254) % 254 + 1}.{(seed // 254 // 254) % 254 + 1}"

    if pii_type == "name":
        firsts: List[str] = [
            "Alex",
            "Jordan",
            "Morgan",
            "Taylor",
            "Casey",
            "Riley",
            "Quinn",
            "Cameron",
        ]
        lasts: List[str] = [
            "Smith",
            "Jones",
            "Williams",
            "Brown",
            "Davis",
            "Miller",
            "Wilson",
            "Moore",
        ]
        return f"{firsts[seed % len(firsts)]} {lasts[(seed // 10) % len(lasts)]}"

    if pii_type == "date_of_birth":
        y: int = 1950 + (seed % 55)
        m: int = (seed % 12) + 1
        d: int = (seed % 28) + 1
        return f"{y:04d}-{m:02d}-{d:02d}"

    # fallback
    return _mask_hash(val, pii_type)


_MASKERS: Dict[str, Callable[..., str]] = {
    "redact": _mask_redact,
    "hash": _mask_hash,
    "fake": _mask_fake,
}
