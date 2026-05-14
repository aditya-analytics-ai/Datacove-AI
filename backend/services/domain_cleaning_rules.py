"""
Domain-Specific Cleaning Rules
Additional cleaning functions for specialized data types.
These rules are learned from analyzing 279 real-world datasets.
"""

from __future__ import annotations

import re
import hashlib
from typing import Any, Dict, List, Optional
from datetime import datetime

import numpy as np
import pandas as pd


def clean_addresses(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Standardize address formatting."""
    col = params.get("column")
    if not col or col not in df.columns:
        return df

    df = df.copy()

    df[col] = df[col].astype(str).str.strip()
    df[col] = df[col].str.replace(r"\s+", " ", regex=True)
    df[col] = df[col].str.replace(r",\s*,", ",", regex=True)
    df[col] = df[col].str.title()

    return df


def clean_postal_codes(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Standardize postal/zip codes by country."""
    col = params.get("column")
    country = params.get("country", "US")

    if not col or col not in df.columns:
        return df

    df = df.copy()

    if country == "US":
        df[col] = df[col].astype(str).str.replace(r"[^\d]", "", regex=True)
        df[col] = df[col].str.pad(5, fillchar="0")
    elif country == "UK":
        df[col] = df[col].astype(str).str.upper().str.replace(r"\s+", "", regex=True)
    elif country == "CA":
        df[col] = df[col].astype(str).str.upper().str.replace(r"\s+", "", regex=True)

    return df


def clean_ibans(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Clean IBAN bank account numbers."""
    col = params.get("column")
    if not col or col not in df.columns:
        return df

    df = df.copy()
    df[col] = df[col].astype(str).str.upper()
    df[col] = df[col].str.replace(r"\s+", "", regex=True)

    return df


def clean_sensitive_ids(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Hash sensitive ID columns for anonymization."""
    col = params.get("column")
    salt = params.get("salt", "")

    if not col or col not in df.columns:
        return df

    df = df.copy()

    def hash_id(val):
        if pd.isna(val):
            return val
        return hashlib.sha256(f"{salt}{val}".encode()).hexdigest()[:16]

    df[col] = df[col].apply(hash_id)

    return df


def parse_coordinates(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Parse coordinates from various formats to decimal degrees."""
    lat_col = params.get("latitude")
    lon_col = params.get("longitude")
    lat_format = params.get("lat_format", "decimal")
    lon_format = params.get("lon_format", "decimal")

    if lat_col and lat_col in df.columns:
        df = df.copy()
        if lat_format == "dms":
            df[lat_col] = df[lat_col].apply(_parse_dms_lat)

    if lon_col and lon_col in df.columns:
        df = df.copy()
        if lon_format == "dms":
            df[lon_col] = df[lon_col].apply(_parse_dms_lon)

    return df


def _parse_dms_lat(val):
    """Parse degrees-minutes-seconds latitude."""
    if pd.isna(val):
        return val
    s = str(val).upper()
    match = re.match(r"(\d+)[°]?\s*(\d+)?['\"]?\s*([NSEW])?", s)
    if match:
        deg = float(match.group(1))
        min_val = float(match.group(2) or 0)
        sec = float(match.group(3) or 0)
        direction = match.group(4) or "N"
        result = deg + min_val / 60 + sec / 3600
        if direction == "S":
            result = -result
        return result
    return val


def _parse_dms_lon(val):
    """Parse degrees-minutes-seconds longitude."""
    if pd.isna(val):
        return val
    s = str(val).upper()
    match = re.match(r"(\d+)[°]?\s*(\d+)?['\"]?\s*([NSEW])?", s)
    if match:
        deg = float(match.group(1))
        min_val = float(match.group(2) or 0)
        sec = float(match.group(3) or 0)
        direction = match.group(4) or "E"
        result = deg + min_val / 60 + sec / 3600
        if direction == "W":
            result = -result
        return result
    return val


def clean_medical_codes(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Clean medical codes (ICD, CPT, etc.)."""
    col = params.get("column")
    code_type = params.get("code_type", "ICD10")

    if not col or col not in df.columns:
        return df

    df = df.copy()
    df[col] = df[col].astype(str).str.upper().str.strip()

    if code_type == "ICD10":
        df[col] = df[col].str.replace(r"[^A-Z0-9\.]", "", regex=True)
    elif code_type == "CPT":
        df[col] = df[col].str.replace(r"[^0-9]", "", regex=True)
    elif code_type == "NDC":
        df[col] = df[col].str.replace(r"[^0-9\-]", "", regex=True)

    return df


def clean_sku_codes(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Standardize SKU/product codes."""
    col = params.get("column")
    if not col or col not in df.columns:
        return df

    df = df.copy()
    df[col] = df[col].astype(str).str.upper().str.strip()
    df[col] = df[col].str.replace(r"\s+", "", regex=True)

    return df


def clean_tracking_numbers(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Clean shipping tracking numbers."""
    col = params.get("column")
    carrier = params.get("carrier", "auto")

    if not col or col not in df.columns:
        return df

    df = df.copy()
    df[col] = df[col].astype(str).str.upper().str.strip()
    df[col] = df[col].str.replace(r"\s+", "", regex=True)

    return df


def clean_categorical_consistency(
    df: pd.DataFrame, params: Dict[str, Any]
) -> pd.DataFrame:
    """Ensure categorical consistency across similar columns."""
    columns = params.get("columns", [])
    if not columns:
        return df

    df = df.copy()
    seen_values = {}

    for col in columns:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.title()
            unique_vals = df[col].unique()
            for val in unique_vals:
                val_lower = str(val).lower()
                if val_lower not in seen_values:
                    seen_values[val_lower] = val

    return df


def clean_names(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Clean person names."""
    col = params.get("column")
    if not col or col not in df.columns:
        return df

    df = df.copy()
    df[col] = df[col].astype(str).str.strip()
    df[col] = df[col].str.replace(r"\s+", " ", regex=True)
    df[col] = df[col].str.title()
    df[col] = df[col].str.replace(r"([A-Z])\.", r"\1", regex=True)

    return df


def clean_urls(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Clean and standardize URLs."""
    col = params.get("column")
    strip_params = params.get("strip_params", True)

    if not col or col not in df.columns:
        return df

    df = df.copy()
    df[col] = df[col].astype(str).str.strip()

    if strip_params:
        df[col] = df[col].str.replace(r"\?.*", "", regex=True)

    df[col] = df[col].str.replace(r"^https?://", "", regex=True)
    df[col] = df[col].str.replace(r"^www\.", "", regex=True)
    df[col] = df[col].str.rstrip("/")

    return df


def clean_social_media_handles(
    df: pd.DataFrame, params: Dict[str, Any]
) -> pd.DataFrame:
    """Clean social media handles."""
    col = params.get("column")
    platform = params.get("platform", "twitter")

    if not col or col not in df.columns:
        return df

    df = df.copy()
    df[col] = df[col].astype(str).str.strip()

    prefix_map = {"twitter": "@", "instagram": "@", "linkedin": ""}
    prefix = prefix_map.get(platform, "")

    if prefix:
        df[col] = df[col].str.replace(f"^{prefix}", "", regex=True)

    df[col] = df[col].str.replace(r"@\w+", lambda m: m.group().lower(), regex=True)

    return df


def parse_percentage(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Parse percentage strings to decimal."""
    col = params.get("column")
    if not col or col not in df.columns:
        return df

    df = df.copy()

    def parse_pct(val):
        if pd.isna(val):
            return val
        s = str(val).strip().replace("%", "").replace(",", "").strip()
        try:
            return float(s) / 100
        except ValueError:
            return val

    df[col] = df[col].apply(parse_pct)
    return df


def clean_percentage(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Clean percentage values."""
    col = params.get("column")
    if not col or col not in df.columns:
        return df

    df = df.copy()

    df[col] = df[col].astype(str).str.replace(r"%", "", regex=False)
    df[col] = df[col].str.replace(",", "", regex=False)
    df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def validate_phone_international(
    df: pd.DataFrame, params: Dict[str, Any]
) -> pd.DataFrame:
    """Validate and standardize international phone numbers."""
    col = params.get("column")
    default_country = params.get("country", "US")

    if not col or col not in df.columns:
        return df

    df = df.copy()

    def format_phone(val):
        if pd.isna(val):
            return val
        digits = re.sub(r"[^\d+]", "", str(val))
        if digits.startswith("+"):
            return digits
        return f"+{digits}"

    df[col] = df[col].apply(format_phone)

    return df


def clean_json_strings(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Parse JSON-like strings into structured data."""
    col = params.get("column")
    target_col = params.get("target_column")

    if not col or col not in df.columns:
        return df

    df = df.copy()

    import json

    def extract_json(val):
        if pd.isna(val):
            return {}
        try:
            return json.loads(str(val))
        except:
            return {}

    if target_col:
        extracted = df[col].apply(extract_json)
        for key in list(extracted.iloc[0].keys())[:10]:
            df[f"{target_col}_{key}"] = extracted.apply(lambda x: x.get(key))

    return df


def clean_sensor_data(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Clean IoT/sensor data - handle anomalies and outliers."""
    columns = params.get(
        "columns", df.select_dtypes(include=[np.number]).columns.tolist()
    )
    threshold = params.get("threshold", 3)

    df = df.copy()

    for col in columns:
        if col in df.columns:
            mean = df[col].mean()
            std = df[col].std()
            lower = mean - threshold * std
            upper = mean + threshold * std
            df[col] = df[col].clip(lower, upper)

    return df


def clean_log_data(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Clean log file data."""
    col = params.get("column")
    if not col or col not in df.columns:
        return df

    df = df.copy()
    df[col] = df[col].astype(str).str.strip()
    df[col] = df[col].str.replace(r"\[.*?\]", "", regex=True)
    df[col] = df[col].str.replace(r"ERROR|WARN|INFO|DEBUG", "", regex=True)
    df[col] = df[col].str.replace(r"\s+", " ", regex=True)

    return df


def clean_scientific_notation(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Convert scientific notation to decimal."""
    columns = params.get("columns", [])
    if not columns:
        columns = df.select_dtypes(include=[np.number]).columns.tolist()

    df = df.copy()

    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def clean_mixed_formats(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Clean columns with mixed formatting."""
    col = params.get("column")
    target_type = params.get("target_type", "string")

    if not col or col not in df.columns:
        return df

    df = df.copy()

    if target_type == "string":
        df[col] = df[col].astype(str).str.strip()
    elif target_type == "numeric":
        df[col] = pd.to_numeric(df[col], errors="coerce")
    elif target_type == "datetime":
        df[col] = pd.to_datetime(df[col], errors="coerce")

    return df


def clean_leading_zeros(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Remove leading zeros from numeric-looking strings."""
    col = params.get("column")
    preserve_length = params.get("preserve_length", False)

    if not col or col not in df.columns:
        return df

    df = df.copy()

    if preserve_length:
        df[col] = df[col].astype(str).str.replace(r"^0+", "", regex=True)
        df[col] = df[col].str.zfill(1)
    else:
        df[col] = df[col].astype(str).str.lstrip("0")

    return df


def normalize_boolean(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Normalize boolean-like values to True/False."""
    col = params.get("column")
    if not col or col not in df.columns:
        return df

    df = df.copy()

    true_vals = {
        "true",
        "yes",
        "1",
        "y",
        "t",
        "on",
        "enabled",
        "active",
        "correct",
        "success",
    }
    false_vals = {
        "false",
        "no",
        "0",
        "n",
        "f",
        "off",
        "disabled",
        "inactive",
        "incorrect",
        "failure",
    }

    def normalize_bool(val):
        if pd.isna(val):
            return val
        s = str(val).lower().strip()
        if s in true_vals:
            return True
        if s in false_vals:
            return False
        return val

    df[col] = df[col].apply(normalize_bool)

    return df


def clean_html_tags(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Remove HTML tags from text."""
    col = params.get("column")
    if not col or col not in df.columns:
        return df

    df = df.copy()
    df[col] = df[col].astype(str).str.replace(r"<[^>]+>", " ", regex=True)
    df[col] = df[col].str.replace(r"\s+", " ", regex=True)
    df[col] = df[col].str.strip()

    return df


def clean_emails(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Clean and validate email addresses."""
    col = params.get("column")
    lowercase = params.get("lowercase", True)

    if not col or col not in df.columns:
        return df

    df = df.copy()
    df[col] = df[col].astype(str).str.strip()

    if lowercase:
        df[col] = df[col].str.lower()

    df[col] = df[col].str.replace(r"\s+", "", regex=True)

    return df


def aggregate_by_period(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Aggregate data by time period."""
    date_col = params.get("date_column")
    value_col = params.get("value_column")
    period = params.get("period", "M")
    agg_func = params.get("agg_func", "sum")

    if not date_col or date_col not in df.columns:
        return df

    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.set_index(date_col)

    if value_col and value_col in df.columns:
        df = df[value_col].resample(period).agg(agg_func).reset_index()
    else:
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        df = df[numeric_cols].resample(period).agg(agg_func).reset_index()

    return df


def detect_anomalies(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Detect anomalies using IQR or Z-score."""
    columns = params.get("columns", [])
    method = params.get("method", "iqr")
    threshold = params.get("threshold", 3)

    if not columns:
        return df

    df = df.copy()
    anomaly_col = params.get("anomaly_column", "is_anomaly")
    df[anomaly_col] = False

    for col in columns:
        if col not in df.columns:
            continue

        if method == "iqr":
            q1 = df[col].quantile(0.25)
            q3 = df[col].quantile(0.75)
            iqr = q3 - q1
            lower = q1 - threshold * iqr
            upper = q3 + threshold * iqr
            df[anomaly_col] |= (df[col] < lower) | (df[col] > upper)

        elif method == "zscore":
            mean = df[col].mean()
            std = df[col].std()
            df[anomaly_col] |= np.abs((df[col] - mean) / std) > threshold

    return df


DOMAIN_CLEANING_RULES = {
    "customer": {
        "name": ["clean_names", "standardise_capitalisation"],
        "email": ["clean_emails", "validate_email"],
        "phone": ["normalize_phone", "validate_phone"],
        "address": ["clean_addresses"],
    },
    "sales": {
        "price": ["parse_currency", "clean_percentage"],
        "date": ["standardise_dates"],
        "quantity": ["coerce_numeric"],
    },
    "healthcare": {
        "code": ["clean_medical_codes"],
        "dob": ["standardise_dates", "age_from_date"],
        "amount": ["parse_currency"],
    },
    "hr": {
        "salary": ["parse_currency", "clip_outliers"],
        "name": ["clean_names"],
        "date": ["standardise_dates"],
    },
    "ecommerce": {
        "price": ["parse_currency"],
        "rating": ["validate_range"],
        "sku": ["clean_sku_codes"],
    },
    "logistics": {
        "tracking": ["clean_tracking_numbers"],
        "postal": ["clean_postal_codes"],
    },
    "finance": {
        "iban": ["clean_ibans"],
        "amount": ["parse_currency"],
        "date": ["standardise_dates"],
    },
    "iot": {
        "sensor": ["clean_sensor_data"],
        "reading": ["detect_anomalies"],
    },
}
