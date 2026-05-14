"""
Dataset Profiler - Intelligent dataset type detection and analysis.
Automatically detects dataset domain (sales, customer, financial, etc.)
and provides relevant cleaning recommendations.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class ColumnProfile:
    name: str
    dtype: str
    is_numeric: bool
    is_date: bool
    is_categorical: bool
    is_text: bool
    is_id: bool
    is_mixed_type: bool
    null_pct: float
    unique_count: int
    cardinality: str
    sample_values: List[Any] = field(default_factory=list)
    detected_format: Optional[str] = None
    detected_category: Optional[str] = None


@dataclass
class DatasetProfile:
    total_rows: int
    total_columns: int
    domain_type: str
    domain_confidence: float
    column_profiles: Dict[str, ColumnProfile]
    quality_score: float
    issues: List[str]
    recommendations: List[Dict[str, Any]]
    numeric_columns: List[str] = field(default_factory=list)
    date_columns: List[str] = field(default_factory=list)
    categorical_columns: List[str] = field(default_factory=list)
    text_columns: List[str] = field(default_factory=list)
    id_columns: List[str] = field(default_factory=list)


class DatasetTypeDetector:
    """
    Detects the type/domain of a dataset based on column names and patterns.
    """

    DOMAIN_SIGNATURES = {
        "sales": {
            "keywords": [
                "sale",
                "revenue",
                "order",
                "transaction",
                "invoice",
                "qty",
                "quantity",
                "price",
                "amount",
                "total",
                "subtotal",
                "discount",
                "tax",
                "profit",
                "customer_id",
                "product_id",
                "sku",
                "store",
                "channel",
            ],
            "required_cols": [],
            "numeric_expectations": ["amount", "quantity", "price", "total", "revenue"],
            "date_expectations": ["date", "order_date", "sale_date", "created"],
        },
        "customer": {
            "keywords": [
                "customer",
                "client",
                "user",
                "name",
                "email",
                "phone",
                "address",
                "city",
                "state",
                "country",
                "zip",
                "postal",
                "age",
                "gender",
                "dob",
                "birth",
                "signup",
                "registration",
                "account",
                "subscription",
            ],
            "required_cols": [],
            "numeric_expectations": ["age"],
            "date_expectations": ["date", "dob", "birth", "signup", "created"],
        },
        "financial": {
            "keywords": [
                "expense",
                "cost",
                "budget",
                "income",
                "asset",
                "liability",
                "equity",
                "debit",
                "credit",
                "account",
                "ledger",
                "balance",
                "payment",
                "fee",
                "interest",
                "loan",
                "mortgage",
                "investment",
                "dividend",
                "tax",
            ],
            "required_cols": [],
            "numeric_expectations": ["amount", "balance", "cost", "price"],
            "date_expectations": ["date", "payment_date", "transaction_date"],
        },
        "inventory": {
            "keywords": [
                "inventory",
                "stock",
                "warehouse",
                "product",
                "sku",
                "item",
                "supplier",
                "vendor",
                "purchase",
                "receiving",
                "shipping",
                "on_hand",
                "available",
                "reserved",
                "reorder",
                "lead_time",
                "lot",
                "batch",
            ],
            "required_cols": [],
            "numeric_expectations": ["quantity", "stock", "on_hand"],
            "date_expectations": ["date", "received_date", "expiry"],
        },
        "hr": {
            "keywords": [
                "employee",
                "staff",
                "hire",
                "termination",
                "department",
                "position",
                "salary",
                "bonus",
                "leave",
                "vacation",
                "sick",
                "attendance",
                "shift",
                "manager",
                "supervisor",
                "performance",
                "review",
                "tenure",
            ],
            "required_cols": [],
            "numeric_expectations": ["salary", "bonus"],
            "date_expectations": ["hire_date", "date", "birth", "review"],
        },
        "marketing": {
            "keywords": [
                "campaign",
                "lead",
                "conversion",
                "click",
                "impression",
                "ctr",
                "engagement",
                "subscribe",
                "unsubscribe",
                "newsletter",
                "promotion",
                "discount",
                "coupon",
                "referral",
                "source",
                "medium",
                "channel",
            ],
            "required_cols": [],
            "numeric_expectations": ["conversion", "clicks", "impressions"],
            "date_expectations": ["date", "campaign_date", "created"],
        },
        "logistics": {
            "keywords": [
                "shipment",
                "delivery",
                "tracking",
                "carrier",
                "route",
                "driver",
                "vehicle",
                "distance",
                "fuel",
                "eta",
                "departure",
                "arrival",
                "origin",
                "destination",
                "warehouse",
                "dispatch",
            ],
            "required_cols": [],
            "numeric_expectations": ["distance", "weight", "volume"],
            "date_expectations": ["date", "delivery_date", "ship_date", "eta"],
        },
        "healthcare": {
            "keywords": [
                "patient",
                "diagnosis",
                "treatment",
                "prescription",
                "doctor",
                "nurse",
                "department",
                "ward",
                "room",
                "bed",
                "admission",
                "discharge",
                "vital",
                "blood",
                "pressure",
                "temperature",
                "pulse",
                "weight",
                "height",
            ],
            "required_cols": [],
            "numeric_expectations": ["age", "weight", "height", "temperature"],
            "date_expectations": ["date", "admission_date", "discharge_date", "birth"],
        },
        "ecommerce": {
            "keywords": [
                "cart",
                "checkout",
                "payment",
                "shipping",
                "item",
                "product",
                "review",
                "rating",
                "wishlist",
                "wish_list",
                "browse",
                "session",
                "page_view",
                "add_to_cart",
                "purchase",
                "refund",
                "return",
            ],
            "required_cols": [],
            "numeric_expectations": ["price", "quantity", "total", "amount"],
            "date_expectations": ["date", "order_date", "created"],
        },
        "general": {
            "keywords": [],
            "required_cols": [],
            "numeric_expectations": [],
            "date_expectations": [],
        },
    }

    @classmethod
    def detect_domain(cls, df: pd.DataFrame) -> Tuple[str, float]:
        """
        Detect the domain type of the dataset.
        Returns (domain_type, confidence_score)
        """
        col_names_lower = [c.lower() for c in df.columns]
        col_names_joined = " ".join(col_names_lower)

        scores = {}

        for domain, signature in cls.DOMAIN_SIGNATURES.items():
            if domain == "general":
                continue

            score = 0
            matched_keywords = 0

            for keyword in signature["keywords"]:
                if keyword in col_names_joined:
                    score += 2
                    matched_keywords += 1

            for expected_col in signature["numeric_expectations"]:
                if any(expected_col in col for col in col_names_lower):
                    score += 1

            for expected_col in signature["date_expectations"]:
                if any(expected_col in col for col in col_names_lower):
                    score += 1

            if signature["required_cols"]:
                if all(req in col_names_lower for req in signature["required_cols"]):
                    score += 5

            scores[domain] = score

        if not scores or max(scores.values()) == 0:
            return "general", 0.3

        best_domain = max(scores, key=scores.get)
        max_score = scores[best_domain]

        total_keywords = len(cls.DOMAIN_SIGNATURES[best_domain]["keywords"])
        confidence = min(0.95, max_score / (total_keywords * 0.15))

        return best_domain, confidence


class ColumnProfiler:
    """
    Profiles individual columns to understand their characteristics.
    """

    EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    PHONE_PATTERN = re.compile(r"^[\d\s\-\(\)\+\.]{7,}$")
    URL_PATTERN = re.compile(r"^https?://")
    DATE_PATTERNS = [
        (r"^\d{4}-\d{2}-\d{2}", "ISO"),
        (r"^\d{2}/\d{2}/\d{4}", "US"),
        (r"^\d{2}-\d{2}-\d{4}", "EU"),
        (r"^\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", "Text"),
    ]
    ID_PATTERNS = [
        r"^id$",
        r"_id$",
        r"^uuid",
        r"^guid",
        r"^\d{6,}$",
        r"^[A-Z]{2,3}\d{4,}$",
    ]

    CURRENCY_SYMBOLS = ["$", "€", "£", "¥", "₹", "₽", "₿"]
    THOUSAND_SEPARATORS = [",", ".", " "]

    @classmethod
    def profile_column(cls, series: pd.Series, sample_size: int = 100) -> ColumnProfile:
        """Create a detailed profile of a single column."""
        name = series.name
        dtype = str(series.dtype)
        null_pct = series.isnull().mean()
        unique_count = series.nunique()

        sample = (
            series.dropna().sample(min(sample_size, len(series.dropna()))).astype(str)
        )

        is_numeric = pd.api.types.is_numeric_dtype(series)
        is_date = cls._detect_date_column(series)
        is_categorical = unique_count <= 50 and not is_numeric
        is_text = series.dtype == object
        is_mixed_type = cls._detect_mixed_types(series)

        cardinality = (
            "low" if unique_count <= 10 else "medium" if unique_count <= 100 else "high"
        )

        is_id = cls._detect_id_column(name, series)

        detected_format = cls._detect_value_format(sample)
        detected_category = cls._infer_category(name, series)

        return ColumnProfile(
            name=name,
            dtype=dtype,
            is_numeric=is_numeric,
            is_date=is_date,
            is_categorical=is_categorical,
            is_text=is_text,
            is_id=is_id,
            is_mixed_type=is_mixed_type,
            null_pct=null_pct,
            unique_count=unique_count,
            cardinality=cardinality,
            sample_values=sample.head(10).tolist(),
            detected_format=detected_format,
            detected_category=detected_category,
        )

    @classmethod
    def _detect_date_column(cls, series: pd.Series) -> bool:
        """Detect if column contains dates."""
        sample = series.dropna().head(100)
        if len(sample) == 0:
            return False

        if pd.api.types.is_numeric_dtype(series):
            return False

        try:
            parsed = pd.to_datetime(sample, errors="coerce")
            valid_ratio = parsed.notna().mean()
            if valid_ratio > 0.8:
                return True
        except Exception:
            pass

        name_lower = str(series.name).lower()
        date_keywords = [
            "date",
            "time",
            "day",
            "month",
            "year",
            "created",
            "updated",
            "timestamp",
            "dob",
            "birth",
            "expire",
            "deadline",
            "hire",
            "termination",
            "join",
        ]
        if any(kw in name_lower for kw in date_keywords):
            return True

        return False

    @classmethod
    def _detect_mixed_types(cls, series: pd.Series) -> bool:
        """Detect if column has mixed data types."""
        sample = series.dropna().head(100)
        if len(sample) < 10:
            return False

        type_counts = {}
        for val in sample:
            val_str = str(val).strip()

            if cls.EMAIL_PATTERN.match(val_str):
                t = "email"
            elif cls.PHONE_PATTERN.match(val_str):
                t = "phone"
            elif cls.URL_PATTERN.match(val_str):
                t = "url"
            elif re.match(r"^[\d\s\-\+\.]+$", val_str) and any(
                c.isdigit() for c in val_str
            ):
                t = "numeric"
            elif re.match(r"^\d{4}-\d{2}-\d{2}", val_str):
                t = "date"
            else:
                t = "text"

            type_counts[t] = type_counts.get(t, 0) + 1

        if len(type_counts) > 2:
            return True
        return False

    @classmethod
    def _detect_id_column(cls, name: str, series: pd.Series) -> bool:
        """Detect if column is an ID field."""
        name_lower = str(name).lower()

        for pattern in cls.ID_PATTERNS:
            if re.search(pattern, name_lower):
                return True

        sample = series.dropna().head(100)
        if len(sample) > 0:
            unique_ratio = sample.nunique() / len(sample)
            if unique_ratio > 0.95 and len(sample) > 50:
                return True

        return False

    @classmethod
    def _detect_value_format(cls, sample: pd.Series) -> Optional[str]:
        """Detect the format of values in a column."""
        sample_list = sample.head(50).tolist()
        if not sample_list:
            return None

        sample_strs = [str(v) for v in sample_list if v]

        has_currency = any(
            any(sym in s for sym in cls.CURRENCY_SYMBOLS) for s in sample_strs
        )
        if has_currency:
            return "currency"

        comma_separated = sum(
            1 for s in sample_strs if "," in s and re.search(r"\d,\d", s)
        )
        if comma_separated > len(sample_strs) * 0.5:
            if re.search(r"1,000|1.000", sample_strs[0]):
                return (
                    "eu_number"
                    if "." in sample_strs[0].replace(",", "")
                    else "us_number"
                )

        date_indicators = ["-", "/", "Jan", "Feb", "Mar"]
        date_count = sum(
            1 for s in sample_strs if any(ind in s for ind in date_indicators)
        )
        if date_count > len(sample_strs) * 0.5:
            return "date"

        percentage_count = sum(
            1
            for s in sample_strs
            if "%" in s
            or (re.match(r"^\d+\.?\d*$", s) and float(s) <= 100 and float(s) >= 0)
        )
        if percentage_count > len(sample_strs) * 0.8:
            return "percentage"

        return None

    @classmethod
    def _infer_category(cls, name: str, series: pd.Series) -> Optional[str]:
        """Infer the semantic category of a column."""
        name_lower = str(name).lower().replace("_", " ").replace("-", " ")

        categories = {
            "email": ["email", "e-mail", "mail"],
            "phone": ["phone", "tel", "mobile", "cell", "fax"],
            "url": ["url", "link", "website", "web", "http"],
            "name": [
                "name",
                "first_name",
                "last_name",
                "full_name",
                "surname",
                "fname",
                "lname",
            ],
            "address": [
                "address",
                "street",
                "city",
                "state",
                "country",
                "zip",
                "postal",
                "region",
            ],
            "age": ["age", "years_old", "dob", "birth"],
            "gender": ["gender", "sex", "male", "female"],
            "date": [
                "date",
                "time",
                "day",
                "month",
                "year",
                "created",
                "updated",
                "timestamp",
            ],
            "price": ["price", "cost", "amount", "fee", "charge"],
            "quantity": ["qty", "quantity", "count", "number", "units", "pieces"],
            "percentage": ["rate", "ratio", "%", "pct", "percent"],
            "boolean": ["is_", "has_", "can_", "flag", "status", "active", "enabled"],
        }

        for category, keywords in categories.items():
            if any(kw in name_lower for kw in keywords):
                return category

        return None


class DatasetProfiler:
    """
    Comprehensive dataset profiling and analysis.
    """

    def __init__(self):
        self.detector = DatasetTypeDetector()
        self.column_profiler = ColumnProfiler()

    def profile(self, df: pd.DataFrame) -> DatasetProfile:
        """Create a complete profile of the dataset."""
        total_rows = len(df)
        total_columns = len(df.columns)

        column_profiles = {}
        numeric_cols = []
        date_cols = []
        categorical_cols = []
        text_cols = []
        id_cols = []

        for col in df.columns:
            profile = self.column_profiler.profile_column(df[col])
            column_profiles[col] = profile

            if profile.is_numeric:
                numeric_cols.append(col)
            elif profile.is_date:
                date_cols.append(col)
            elif profile.is_categorical:
                categorical_cols.append(col)
            elif profile.is_text:
                text_cols.append(col)

            if profile.is_id:
                id_cols.append(col)

        domain_type, domain_confidence = self.detector.detect_domain(df)

        issues = self._identify_issues(df, column_profiles)
        quality_score = self._calculate_quality_score(df, issues)
        recommendations = self._generate_recommendations(
            df, column_profiles, domain_type, issues
        )

        return DatasetProfile(
            total_rows=total_rows,
            total_columns=total_columns,
            domain_type=domain_type,
            domain_confidence=domain_confidence,
            column_profiles=column_profiles,
            quality_score=quality_score,
            issues=issues,
            recommendations=recommendations,
            numeric_columns=numeric_cols,
            date_columns=date_cols,
            categorical_columns=categorical_cols,
            text_columns=text_cols,
            id_columns=id_cols,
        )

    def _identify_issues(
        self, df: pd.DataFrame, profiles: Dict[str, ColumnProfile]
    ) -> List[str]:
        """Identify data quality issues."""
        issues = []

        for col, profile in profiles.items():
            if profile.null_pct > 0.5:
                issues.append(
                    f"Column '{col}' has {profile.null_pct:.1%} missing values"
                )
            elif profile.null_pct > 0.1:
                issues.append(
                    f"Column '{col}' has {profile.null_pct:.1%} missing values"
                )

            if profile.is_mixed_type:
                issues.append(f"Column '{col}' contains mixed data types")

            if (
                profile.cardinality == "low"
                and not profile.is_categorical
                and profile.null_pct < 0.9
            ):
                issues.append(
                    f"Column '{col}' may be categorical (only {profile.unique_count} unique values)"
                )

        if df.duplicated().any():
            dup_count = df.duplicated().sum()
            issues.append(f"Dataset contains {dup_count} duplicate rows")

        date_cols = [c for c, p in profiles.items() if p.is_date]
        if date_cols:
            for col in date_cols:
                try:
                    parsed = pd.to_datetime(df[col], errors="coerce")
                    if parsed.isnull().mean() > 0.3:
                        issues.append(f"Date column '{col}' has inconsistent format")
                except Exception:
                    pass

        return issues

    def _calculate_quality_score(self, df: pd.DataFrame, issues: List[str]) -> float:
        """Calculate overall data quality score (0-100)."""
        score = 100.0

        missing_penalty = df.isnull().mean().mean() * 30
        score -= missing_penalty

        dup_penalty = df.duplicated().mean() * 20
        score -= dup_penalty

        issue_penalty = len(issues) * 2
        score -= issue_penalty

        return max(0, min(100, score))

    def _generate_recommendations(
        self,
        df: pd.DataFrame,
        profiles: Dict[str, ColumnProfile],
        domain_type: str,
        issues: List[str],
    ) -> List[Dict[str, Any]]:
        """Generate cleaning recommendations based on analysis."""
        recommendations = []

        for col, profile in profiles.items():
            if profile.null_pct > 0.1:
                recommendations.append(
                    {
                        "column": col,
                        "action": "fill_missing",
                        "reason": f"Fill {profile.null_pct:.1%} missing values",
                        "params": {
                            "column": col,
                            "strategy": "auto" if profile.is_numeric else "mode",
                        },
                    }
                )

            if profile.is_date:
                recommendations.append(
                    {
                        "column": col,
                        "action": "standardise_dates",
                        "reason": "Standardize date format",
                        "params": {"column": col},
                    }
                )

            if profile.detected_format == "currency":
                recommendations.append(
                    {
                        "column": col,
                        "action": "parse_currency",
                        "reason": "Extract numeric values from currency strings",
                        "params": {"column": col},
                    }
                )

            if profile.detected_format in ["us_number", "eu_number"]:
                recommendations.append(
                    {
                        "column": col,
                        "action": "parse_number_formatted",
                        "reason": "Standardize number format",
                        "params": {
                            "column": col,
                            "decimal_format": "eu"
                            if profile.detected_format == "eu_number"
                            else "us",
                        },
                    }
                )

            if profile.is_categorical and profile.cardinality == "medium":
                recommendations.append(
                    {
                        "column": col,
                        "action": "normalise_categories",
                        "reason": "Normalize categorical values",
                        "params": {"column": col},
                    }
                )

            if profile.cardinality == "high" and profile.is_text:
                recommendations.append(
                    {
                        "column": col,
                        "action": "trim_whitespace",
                        "reason": "Clean text values",
                        "params": {"column": col},
                    }
                )

        has_id_cols = any(p.is_id for p in profiles.values())
        if has_id_cols:
            recommendations.append(
                {
                    "column": None,
                    "action": "remove_duplicates",
                    "reason": "Remove duplicate rows (ID columns present)",
                    "params": {"subset": [c for c, p in profiles.items() if p.is_id]},
                }
            )

        return recommendations[:20]


def profile_dataset(df: pd.DataFrame) -> DatasetProfile:
    """Convenience function to profile a dataset."""
    profiler = DatasetProfiler()
    return profiler.profile(df)
