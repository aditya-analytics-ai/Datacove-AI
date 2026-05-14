"""
pattern_library.py - 50+ named regex patterns for validation and extraction.

Categories: Financial, Identity, Network, Dates, Vehicle, Retail, Geographic,
            Healthcare, Telecom, Codes.

Public API
──────────
  list_patterns()                          -> [{name, category, description, example}]
  validate_column(df, col, pattern_name)   -> {matches, total, pct, sample_matches, sample_fails}
  extract_column(df, col, pattern_name, new_col_name) -> pd.DataFrame
  test_value(value, pattern_name)          -> {matched, groups}
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

# ── Pattern registry ──────────────────────────────────────────────────────────
# (name, category, description, example, regex_string)
_REGISTRY: List[Tuple[str, str, str, str, str]] = [
    # Financial
    ("iban",           "Financial",   "International Bank Account Number",      "GB82WEST12345698765432",   r"\b[A-Z]{2}\d{2}[A-Z0-9]{4,30}\b"),
    ("bic_swift",      "Financial",   "BIC/SWIFT bank code",                    "DEUTDEDB",                  r"\b[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?\b"),
    ("credit_card",    "Financial",   "Credit/debit card number (Luhn)",        "4532015112830366",          r"\b(?:\d[ \-]?){13,16}\b"),
    ("visa",           "Financial",   "Visa card number",                       "4532015112830366",          r"\b4\d{3}[ \-]?\d{4}[ \-]?\d{4}[ \-]?\d{4}\b"),
    ("mastercard",     "Financial",   "Mastercard number",                      "5425233430109903",          r"\b5[1-5]\d{2}[ \-]?\d{4}[ \-]?\d{4}[ \-]?\d{4}\b"),
    ("amex",           "Financial",   "American Express card",                  "371449635398431",           r"\b3[47]\d{2}[ \-]?\d{6}[ \-]?\d{5}\b"),
    ("currency_usd",   "Financial",   "USD amount",                             "$1,234.56",                 r"\$\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?"),
    ("currency_eur",   "Financial",   "EUR amount",                             "€1.234,56",                 r"€\s?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?"),
    ("routing_number", "Financial",   "US bank routing number (ABA)",           "021000021",                 r"\b\d{9}\b"),

    # Identity
    ("ssn_us",         "Identity",    "US Social Security Number",              "123-45-6789",               r"\b\d{3}[-\s]\d{2}[-\s]\d{4}\b"),
    ("nino_uk",        "Identity",    "UK National Insurance Number",           "AB123456C",                 r"\b[A-Z]{2}\d{6}[A-D]\b"),
    ("passport_us",    "Identity",    "US Passport number",                     "A12345678",                 r"\b[A-Z]\d{8}\b"),
    ("passport_uk",    "Identity",    "UK Passport number",                     "123456789",                 r"\b\d{9}\b"),
    ("drivers_license","Identity",    "Generic drivers license (alphanumeric)", "D1234567",                  r"\b[A-Z]{1,2}\d{5,9}\b"),
    ("dob",            "Identity",    "Date of birth (various formats)",        "1990-01-15",                r"\b(?:\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{4})\b"),

    # Network
    ("ipv4",           "Network",     "IPv4 address",                           "192.168.1.1",               r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    ("ipv6",           "Network",     "IPv6 address",                           "2001:0db8::1",              r"\b([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b"),
    ("mac_address",    "Network",     "MAC address",                            "AA:BB:CC:DD:EE:FF",         r"\b([0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}\b"),
    ("url",            "Network",     "URL (http/https/ftp)",                   "https://example.com/path",  r"https?://[^\s/$.?#].[^\s]*"),
    ("email",          "Network",     "Email address",                          "user@example.com",          r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"),
    ("domain",         "Network",     "Domain name",                            "example.com",               r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b"),

    # Phone
    ("phone_us",       "Telecom",     "US/Canada phone number",                 "+1-555-123-4567",           r"\b(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"),
    ("phone_uk",       "Telecom",     "UK phone number",                        "+44 7911 123456",           r"\b(?:\+44|0)\s?7\d{3}\s?\d{6}\b"),
    ("phone_intl",     "Telecom",     "International phone (E.164)",            "+12025551234",              r"\+\d{1,3}[\s\-]?\d{4,14}"),

    # Vehicle
    ("vin",            "Vehicle",     "Vehicle Identification Number",          "1HGBH41JXMN109186",         r"\b[A-HJ-NPR-Z0-9]{17}\b"),
    ("license_plate_us","Vehicle",    "US license plate (generic)",             "ABC-1234",                  r"\b[A-Z]{1,3}[-\s]?\d{1,4}[-\s]?[A-Z]{0,3}\b"),
    ("license_plate_uk","Vehicle",    "UK license plate",                       "AB12 CDE",                  r"\b[A-Z]{2}\d{2}[\s]?[A-Z]{3}\b"),

    # Books / Product
    ("isbn_10",        "Retail",      "ISBN-10 book identifier",                "0-306-40615-2",             r"\b(?:ISBN[-\s]?)?(?:\d[-\s]?){9}[\dX]\b"),
    ("isbn_13",        "Retail",      "ISBN-13 book identifier",                "978-3-16-148410-0",         r"\b(?:ISBN[-\s]?)?97[89][-\s]?\d[-\s]?\d{2}[-\s]?\d{6}[-\s]?\d\b"),
    ("upc_a",          "Retail",      "UPC-A barcode",                          "012345678905",              r"\b\d{12}\b"),
    ("ean_13",         "Retail",      "EAN-13 barcode",                         "5901234123457",             r"\b\d{13}\b"),
    ("asin",           "Retail",      "Amazon ASIN",                            "B07CSKGLMM",                r"\bB[0-9A-Z]{9}\b"),

    # Geographic
    ("postcode_uk",    "Geographic",  "UK postcode",                            "SW1A 1AA",                  r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}\b"),
    ("zipcode_us",     "Geographic",  "US ZIP code",                            "10001-1234",                r"\b\d{5}(?:-\d{4})?\b"),
    ("postcode_ca",    "Geographic",  "Canadian postal code",                   "K1A 0B1",                   r"\b[ABCEGHJ-NPRSTVXY]\d[A-Z]\s?\d[A-Z]\d\b"),
    ("postcode_au",    "Geographic",  "Australian postcode",                    "2000",                      r"\b\d{4}\b"),
    ("geo_coordinates","Geographic",  "Lat/Long decimal degrees",               "51.5074, -0.1278",          r"-?\d{1,3}\.\d+,\s*-?\d{1,3}\.\d+"),
    ("country_code_2", "Geographic",  "ISO 3166-1 alpha-2 country code",       "US",                        r"\b[A-Z]{2}\b"),
    ("country_code_3", "Geographic",  "ISO 3166-1 alpha-3 country code",       "USA",                       r"\b[A-Z]{3}\b"),

    # Dates & Times
    ("date_iso",       "Dates",       "ISO 8601 date (YYYY-MM-DD)",             "2024-01-15",                r"\b\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])\b"),
    ("date_us",        "Dates",       "US date (MM/DD/YYYY)",                   "01/15/2024",                r"\b(?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12]\d|3[01])/\d{4}\b"),
    ("date_eu",        "Dates",       "European date (DD.MM.YYYY)",             "15.01.2024",                r"\b(?:0?[1-9]|[12]\d|3[01])\.(?:0?[1-9]|1[0-2])\.\d{4}\b"),
    ("time_24h",       "Dates",       "24-hour time (HH:MM:SS)",                "14:30:00",                  r"\b(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?\b"),
    ("datetime_iso",   "Dates",       "ISO 8601 datetime",                      "2024-01-15T14:30:00Z",      r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})?"),

    # Healthcare
    ("npi_us",         "Healthcare",  "US National Provider Identifier",        "1234567893",                r"\b\d{10}\b"),
    ("icd10",          "Healthcare",  "ICD-10 diagnosis code",                  "A00.1",                     r"\b[A-Z]\d{2}(?:\.\d{1,4})?\b"),
    ("ndc",            "Healthcare",  "National Drug Code",                     "0069-3060-30",              r"\b\d{4,5}-\d{3,4}-\d{1,2}\b"),

    # Codes & Identifiers
    ("uuid",           "Codes",       "UUID / GUID",                            "550e8400-e29b-41d4-a716-446655440000", r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"),
    ("hex_color",      "Codes",       "Hex color code",                         "#FF5733",                   r"#[0-9A-Fa-f]{6}\b"),
    ("base64",         "Codes",       "Base64-encoded string",                  "SGVsbG8gV29ybGQ=",          r"\b[A-Za-z0-9+/]{20,}={0,2}\b"),
    ("jwt",            "Codes",       "JSON Web Token",                         "eyJ...",                    r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b"),
    ("semver",         "Codes",       "Semantic version number",                "1.2.3-alpha",               r"\bv?\d+\.\d+\.\d+(?:-[a-zA-Z0-9.]+)?\b"),
    ("hex_sha256",     "Codes",       "SHA-256 hash",                           "a665a45920422f...",         r"\b[0-9a-fA-F]{64}\b"),
    ("aws_arn",        "Codes",       "AWS ARN",                                "arn:aws:s3:::my-bucket",    r"\barn:aws:[a-z0-9\-]+:[a-z0-9\-]*:\d*:[a-zA-Z0-9\-_/:.]+\b"),
]

# Build compiled lookup
_COMPILED: Dict[str, re.Pattern] = {
    name: re.compile(pattern) for name, _, _, _, pattern in _REGISTRY
}
_META: Dict[str, Dict] = {
    name: {"name": name, "category": cat, "description": desc, "example": ex, "pattern": pat}
    for name, cat, desc, ex, pat in _REGISTRY
}


# ── Public API ────────────────────────────────────────────────────────────────

def list_patterns() -> List[Dict[str, str]]:
    """Return all patterns grouped by category."""
    return [{"name": m["name"], "category": m["category"],
             "description": m["description"], "example": m["example"],
             "pattern": m["pattern"]}
            for m in _META.values()]


def validate_column(
    df: pd.DataFrame,
    col: str,
    pattern_name: str,
    sample_size: int = 10,
) -> Dict[str, Any]:
    """
    Check how many cells in a column match the named pattern.

    Returns
    -------
    { matches, total, match_pct, sample_matches, sample_fails, pattern_name }
    """
    if col not in df.columns:
        raise ValueError(f"Column '{col}' not found.")
    rx = _get_pattern(pattern_name)
    series  = df[col].dropna().astype(str)
    matched = series.apply(lambda v: bool(rx.search(v)))

    hits    = series[matched]
    misses  = series[~matched]

    return {
        "pattern_name":   pattern_name,
        "column":         col,
        "matches":        int(matched.sum()),
        "total":          len(series),
        "match_pct":      round(matched.mean() * 100, 2),
        "sample_matches": hits.head(sample_size).tolist(),
        "sample_fails":   misses.head(sample_size).tolist(),
    }


def extract_column(
    df: pd.DataFrame,
    col: str,
    pattern_name: str,
    new_col: Optional[str] = None,
) -> pd.DataFrame:
    """
    Extract first regex match from each cell and add as a new column.
    Non-matching cells become NaN.
    """
    if col not in df.columns:
        raise ValueError(f"Column '{col}' not found.")
    rx       = _get_pattern(pattern_name)
    new_col  = new_col or f"{col}_{pattern_name}"
    df       = df.copy()
    df[new_col] = df[col].astype(str).apply(
        lambda v: m.group(0) if (m := rx.search(v)) else None
    )
    return df


def test_value(value: str, pattern_name: str) -> Dict[str, Any]:
    """Test a single value against a named pattern."""
    rx      = _get_pattern(pattern_name)
    match   = rx.search(str(value))
    return {
        "matched": bool(match),
        "match_text": match.group(0) if match else None,
        "groups": list(match.groups()) if match else [],
    }


def _get_pattern(name: str) -> re.Pattern:
    if name not in _COMPILED:
        raise ValueError(f"Unknown pattern '{name}'. Use list_patterns() to see available patterns.")
    return _COMPILED[name]
