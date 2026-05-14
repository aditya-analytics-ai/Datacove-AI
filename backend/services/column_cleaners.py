"""
Domain-Specific Cleaning Functions
Advanced cleaning rules based on column patterns and data types.
"""

import re
import pandas as pd
import numpy as np
from typing import Optional, List, Dict, Any


def clean_phone_number(value: Any) -> Optional[str]:
    """Clean and standardize phone numbers."""
    if pd.isna(value) or str(value).strip() == "":
        return None

    val = str(value).strip()
    digits = re.sub(r"\D", "", val)

    if len(digits) < 7 or len(digits) > 15:
        return val

    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    elif len(digits) == 11 and digits[0] == "1":
        return f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"

    return val


def clean_email(value: Any) -> Optional[str]:
    """Validate and clean email addresses."""
    if pd.isna(value) or str(value).strip() == "":
        return None

    val = str(value).strip().lower()

    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if re.match(email_pattern, val):
        return val

    return val


def normalize_gender(value: Any) -> Optional[str]:
    """Normalize gender values."""
    if pd.isna(value) or str(value).strip() == "":
        return None

    val = str(value).strip().lower()

    male_patterns = ["male", "man", "boy", "m"]
    female_patterns = ["female", "woman", "girl", "f"]

    for pattern in male_patterns:
        if pattern in val:
            return "Male"

    for pattern in female_patterns:
        if pattern in val:
            return "Female"

    if val in ["other", "o", "na", "n/a", "-", ""]:
        return "Other"

    return "Other"


def clean_status(value: Any) -> Optional[str]:
    """Normalize status values."""
    if pd.isna(value) or str(value).strip() == "":
        return None

    val = str(value).strip().lower()

    if any(s in val for s in ["active", "open", "current", "yes", "1", "true"]):
        return "Active"
    elif any(
        s in val
        for s in ["inactive", "closed", "past", "no", "0", "false", "terminated"]
    ):
        return "Inactive"
    elif any(s in val for s in ["pending", "waiting", "processing"]):
        return "Pending"

    return val.title()


def clean_address(value: Any) -> Optional[str]:
    """Clean and standardize addresses."""
    if pd.isna(value) or str(value).strip() == "":
        return None

    val = str(value).strip()

    replacements = {
        r"\bstreet\b": "St",
        r"\bst\b": "St",
        r"\bavenue\b": "Ave",
        r"\bav\b": "Ave",
        r"\bdrive\b": "Dr",
        r"\broad\b": "Rd",
        r"\blane\b": "Ln",
        r"\bboulevard\b": "Blvd",
        r"\bsuite\b": "Ste",
        r"\bapartment\b": "Apt",
        r"\bfloor\b": "Fl",
    }

    for pattern, replacement in replacements.items():
        val = re.sub(pattern, replacement, val, flags=re.IGNORECASE)

    return val.title()


def clean_city(value: Any) -> Optional[str]:
    """Clean city names."""
    if pd.isna(value) or str(value).strip() == "":
        return None

    val = str(value).strip()

    val = re.sub(r"[^a-zA-Z\s\-]", "", val)

    return val.title()


def clean_state(value: Any) -> Optional[str]:
    """Clean and standardize state names/codes."""
    if pd.isna(value) or str(value).strip() == "":
        return None

    val = str(value).strip()

    state_codes = {
        "al": "AL",
        "ak": "AK",
        "az": "AZ",
        "ar": "AR",
        "ca": "CA",
        "co": "CO",
        "ct": "CT",
        "de": "DE",
        "fl": "FL",
        "ga": "GA",
        "hi": "HI",
        "id": "ID",
        "il": "IL",
        "in": "IN",
        "ia": "IA",
        "ks": "KS",
        "ky": "KY",
        "la": "LA",
        "me": "ME",
        "md": "MD",
        "ma": "MA",
        "mi": "MI",
        "mn": "MN",
        "ms": "MS",
        "mo": "MO",
        "mt": "MT",
        "ne": "NE",
        "nv": "NV",
        "nh": "NH",
        "nj": "NJ",
        "nm": "NM",
        "ny": "NY",
        "nc": "NC",
        "nd": "ND",
        "oh": "OH",
        "ok": "OK",
        "or": "OR",
        "pa": "PA",
        "ri": "RI",
        "sc": "SC",
        "sd": "SD",
        "tn": "TN",
        "tx": "TX",
        "ut": "UT",
        "vt": "VT",
        "va": "VA",
        "wa": "WA",
        "wv": "WV",
        "wi": "WI",
        "wy": "WY",
    }

    val_lower = val.lower()
    if val_lower in state_codes:
        return state_codes[val_lower]

    if len(val) == 2 and val.isupper():
        return val.upper()

    return val.title()


def clean_zipcode(value: Any) -> Optional[str]:
    """Clean and standardize ZIP codes."""
    if pd.isna(value) or str(value).strip() == "":
        return None

    val = str(value).strip()
    digits = re.sub(r"\D", "", val)

    if len(digits) == 5 or len(digits) == 9:
        return digits[:5]
    elif len(digits) == 4:
        return "0" + digits

    return val


def clean_boolean(value: Any) -> Optional[bool]:
    """Convert various boolean representations to True/False."""
    if pd.isna(value):
        return None

    val = str(value).strip().lower()

    true_values = ["true", "t", "yes", "y", "1", "on", "active", "enabled", "correct"]
    false_values = [
        "false",
        "f",
        "no",
        "n",
        "0",
        "off",
        "inactive",
        "disabled",
        "incorrect",
    ]

    if val in true_values:
        return True
    elif val in false_values:
        return False

    return None


def clean_percentage(value: Any) -> Optional[float]:
    """Convert percentage strings to float."""
    if pd.isna(value) or str(value).strip() == "":
        return None

    val = str(value).strip()
    val = val.replace("%", "").replace(",", "")

    try:
        return float(val)
    except ValueError:
        return None


def clean_name(value: Any) -> Optional[str]:
    """Clean and standardize names."""
    if pd.isna(value) or str(value).strip() == "":
        return None

    val = str(value).strip()

    val = re.sub(r"[^a-zA-Z\s\-\.]", "", val)

    words = val.split()
    cleaned_words = []

    for word in words:
        if len(word) > 0:
            cleaned_words.append(word.capitalize())

    return " ".join(cleaned_words)


def clean_url(value: Any) -> Optional[str]:
    """Clean URLs."""
    if pd.isna(value) or str(value).strip() == "":
        return None

    val = str(value).strip()

    if not val.startswith(("http://", "https://", "www.")):
        val = "https://" + val

    return val.lower()


def clean_sku(value: Any) -> Optional[str]:
    """Clean SKU/product codes."""
    if pd.isna(value) or str(value).strip() == "":
        return None

    val = str(value).strip().upper()

    val = re.sub(r"[^A-Z0-9\-_]", "", val)

    return val


def detect_and_clean_column(df: pd.DataFrame, col: str) -> Dict[str, Any]:
    """Automatically detect column type and apply appropriate cleaning."""
    results = {
        "column": col,
        "original_dtype": str(df[col].dtype),
        "detected_type": "unknown",
        "cleaned": False,
        "cleaning_function": None,
        "values_changed": 0,
    }

    sample = df[col].dropna().astype(str).head(100)
    if len(sample) == 0:
        return results

    col_lower = col.lower()

    if "email" in col_lower and "@" in sample.iloc[0]:
        results["detected_type"] = "email"
        results["cleaning_function"] = "clean_email"

    elif any(kw in col_lower for kw in ["phone", "tel", "mobile", "fax"]):
        results["detected_type"] = "phone"
        results["cleaning_function"] = "clean_phone"

    elif "gender" in col_lower:
        results["detected_type"] = "gender"
        results["cleaning_function"] = "normalize_gender"

    elif "status" in col_lower:
        results["detected_type"] = "status"
        results["cleaning_function"] = "clean_status"

    elif any(kw in col_lower for kw in ["address", "street"]):
        results["detected_type"] = "address"
        results["cleaning_function"] = "clean_address"

    elif "city" in col_lower:
        results["detected_type"] = "city"
        results["cleaning_function"] = "clean_city"

    elif "state" in col_lower:
        results["detected_type"] = "state"
        results["cleaning_function"] = "clean_state"

    elif any(kw in col_lower for kw in ["zip", "postal"]):
        results["detected_type"] = "zipcode"
        results["cleaning_function"] = "clean_zipcode"

    elif any(kw in col_lower for kw in ["url", "link", "website"]):
        results["detected_type"] = "url"
        results["cleaning_function"] = "clean_url"

    elif "sku" in col_lower or "product_code" in col_lower:
        results["detected_type"] = "sku"
        results["cleaning_function"] = "clean_sku"

    elif df[col].nunique() == 2:
        unique_vals = df[col].dropna().unique()
        str_vals = [str(v).lower() for v in unique_vals]
        if any(v in str_vals for v in ["true", "false", "yes", "no", "1", "0"]):
            results["detected_type"] = "boolean"
            results["cleaning_function"] = "clean_boolean"

    elif "%" in sample.iloc[0] or sample.str.contains("%").mean() > 0.3:
        results["detected_type"] = "percentage"
        results["cleaning_function"] = "clean_percentage"

    return results


def apply_column_cleaning(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Apply cleaning function to a column based on detected type."""
    detection = detect_and_clean_column(df, col)

    if detection["cleaning_function"] is None:
        return df

    func_name = detection["cleaning_function"]

    cleaning_functions = {
        "clean_email": clean_email,
        "clean_phone": clean_phone_number,
        "normalize_gender": normalize_gender,
        "clean_status": clean_status,
        "clean_address": clean_address,
        "clean_city": clean_city,
        "clean_state": clean_state,
        "clean_zipcode": clean_zipcode,
        "clean_url": clean_url,
        "clean_sku": clean_sku,
        "clean_boolean": clean_boolean,
        "clean_percentage": clean_percentage,
        "clean_name": clean_name,
    }

    if func_name in cleaning_functions:
        func = cleaning_functions[func_name]

        if func_name in ["normalize_gender", "clean_status", "clean_boolean"]:
            df[col] = df[col].apply(func)
        else:
            df[col] = df[col].apply(func)

    return df


# Registry of cleaning functions by column type
COLUMN_CLEANERS = {
    "clean_email": clean_email,
    "clean_phone": clean_phone_number,
    "normalize_gender": normalize_gender,
    "clean_status": clean_status,
    "clean_address": clean_address,
    "clean_city": clean_city,
    "clean_state": clean_state,
    "clean_zipcode": clean_zipcode,
    "clean_url": clean_url,
    "clean_sku": clean_sku,
    "clean_boolean": clean_boolean,
    "clean_percentage": clean_percentage,
    "clean_name": clean_name,
}


def auto_clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Automatically detect and clean common column types."""
    cleaned_columns = []

    for col in df.columns:
        detection = detect_and_clean_column(df, col)
        if detection["cleaning_function"]:
            df = apply_column_cleaning(df, col)
            cleaned_columns.append(detection)

    return df, cleaned_columns
