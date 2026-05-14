"""
Deep Dataset Cleaner - Detailed analysis and cleaning of each dataset.
Processes datasets one by one for thorough cleaning and pattern learning.
"""

from __future__ import annotations

import os
import json
import re
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from collections import defaultdict
import pandas as pd
import numpy as np

from column_cleaners import (
    clean_phone_number,
    clean_email,
    normalize_gender,
    clean_status,
    clean_address,
    clean_city,
    clean_state,
    clean_zipcode,
    clean_url,
    clean_sku,
    clean_invoice_number,
    clean_country,
    clean_currency,
    clean_date,
)
from utils.logger import logger
from anomaly_detector import detect_anomalies
from domain_rules import apply_domain_cleaning


@dataclass
class ColumnIssue:
    column: str
    issue_type: str
    severity: str
    description: str
    sample_values: List[Any] = field(default_factory=list)
    affected_count: int = 0
    recommended_action: str = ""


@dataclass
class ColumnInsight:
    column: str
    detected_type: str
    confidence: float
    format_detected: str = ""
    has_issues: bool = False
    cleaning_applied: List[str] = field(default_factory=list)


@dataclass
class DatasetReport:
    filename: str
    filepath: str
    folder: str
    total_rows: int
    total_columns: int
    file_size_kb: float
    detected_domain: str = "unknown"
    domain_confidence: float = 0.0
    initial_quality_score: float = 0.0
    final_quality_score: float = 0.0

    alternative_domains: Dict[str, float] = field(default_factory=dict)
    quality_improvement: float = 0.0
    issues_found: List[ColumnIssue] = field(default_factory=list)
    issues_summary: Dict[str, int] = field(default_factory=dict)
    column_insights: List[ColumnInsight] = field(default_factory=list)
    columns_by_type: Dict[str, List[str]] = field(default_factory=dict)
    cleaning_steps: List[Dict[str, Any]] = field(default_factory=list)
    cells_cleaned: int = 0
    rows_removed: int = 0
    columns_added: int = 0
    columns_removed: int = 0
    patterns_found: List[str] = field(default_factory=list)
    new_rules_generated: List[str] = field(default_factory=list)
    dtypes_found: Dict[str, int] = field(default_factory=dict)
    null_counts: Dict[str, int] = field(default_factory=dict)
    duplicate_count: int = 0
    constant_columns: List[str] = field(default_factory=list)
    index_columns: List[str] = field(default_factory=list)
    success: bool = True
    error_message: str = ""
    processed_at: str = field(default_factory=lambda: datetime.now().isoformat())


class DeepDatasetCleaner:
    """
    Performs detailed, one-by-one analysis and cleaning of datasets.
    Generates comprehensive reports for each dataset.
    """

    CURRENCY_SYMBOLS = [
        "$",
        "€",
        "£",
        "¥",
        "₹",
        "₽",
        "₿",
        "R$",
        "kr",
        "CHF",
        "A$",
        "C$",
    ]

    ERROR_VALUES = {
        "error",
        "unknown",
        "n/a",
        "na",
        "null",
        "none",
        "-",
        "--",
        "#n/a",
        "#error",
        "#value",
        "?",
        "??",
        "???",
        "N/A",
        "NA",
        "undefined",
        "missing",
        "empty",
        "blank",
        "none found",
        "not available",
    }

    DATE_PATTERNS = {
        r"^\d{4}-\d{2}-\d{2}$": "YYYY-MM-DD",
        r"^\d{2}/\d{2}/\d{4}$": "MM/DD/YYYY",
        r"^\d{2}-\d{2}-\d{4}$": "DD-MM-YYYY",
        r"^\d{1,2}/\d{1,2}/\d{4}$": "M/D/YYYY",
        r"^\w{3,9}\s+\d{1,2},?\s+\d{4}$": "Month DD, YYYY",
        r"^\d{4}/\d{2}/\d{2}$": "YYYY/MM/DD",
        r"^\d{10,13}$": "Unix Timestamp",
    }

    DOMAIN_SIGNATURES = {
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
                "first_name",
                "last_name",
            ],
            "columns": ["customer_id", "user_id", "name", "email", "phone"],
        },
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
            "columns": ["order_id", "transaction_id", "sale_id", "price", "quantity"],
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
                "job",
                "title",
            ],
            "columns": ["employee_id", "emp_id", "salary", "hire_date", "department"],
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
                "cart_id",
            ],
            "columns": ["product_id", "order_id", "user_id", "rating", "review"],
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
            "columns": ["sku", "product_id", "stock", "inventory_id"],
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
                "medical",
                "health",
                "hospital",
                "clinic",
                "icd",
                "cpt",
            ],
            "columns": ["patient_id", "doctor_id", "diagnosis", "treatment"],
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
                "bank",
            ],
            "columns": ["account_id", "transaction_id", "balance", "amount"],
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
                "ad",
            ],
            "columns": ["campaign_id", "lead_id", "conversion", "click"],
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
                "shipping",
                "freight",
            ],
            "columns": ["tracking_id", "shipment_id", "carrier", "destination"],
        },
        "iot": {
            "keywords": [
                "sensor",
                "device",
                "reading",
                "temperature",
                "humidity",
                "pressure",
                "location",
                "gps",
                "lat",
                "lon",
                "altitude",
                "speed",
                "motion",
                "accelerometer",
                "gyroscope",
                "mqtt",
                "iot",
            ],
            "columns": ["device_id", "sensor_id", "reading", "timestamp"],
        },
        "realestate": {
            "keywords": [
                "property",
                "real_estate",
                "house",
                "apartment",
                "condo",
                "rent",
                "lease",
                "sqft",
                "bedroom",
                "bathroom",
                "amenities",
                "listing",
                "address",
                "zillow",
                "realtor",
                "mortgage",
            ],
            "columns": ["property_id", "listing_id", "price", "sqft", "address"],
        },
        "education": {
            "keywords": [
                "student",
                "school",
                "university",
                "college",
                "course",
                "grade",
                "gpa",
                "score",
                "exam",
                "test",
                "quiz",
                "homework",
                "assignment",
                "professor",
                "teacher",
                "class",
                "semester",
                "enrollment",
            ],
            "columns": ["student_id", "course_id", "grade", "gpa"],
        },
        "survey": {
            "keywords": [
                "survey",
                "questionnaire",
                "respondent",
                "response",
                "answer",
                "rating",
                "scale",
                "agree",
                "disagree",
                "satisfied",
                "feedback",
                "opinion",
                "preference",
                "demographic",
            ],
            "columns": ["respondent_id", "question_id", "response", "rating"],
        },
    }

    def __init__(self):
        self.reports: List[DatasetReport] = []
        self.overall_stats = {
            "total_datasets": 0,
            "total_rows": 0,
            "total_cells_cleaned": 0,
            "domains_found": defaultdict(int),
            "issues_found": defaultdict(int),
            "patterns_found": defaultdict(int),
            "rules_generated": [],
        }

    def process_folder(
        self, folder_path: str, output_folder: Optional[str] = None
    ) -> List[DatasetReport]:
        """Process all datasets in a folder."""
        path = Path(folder_path)
        csv_files = list(path.rglob("*.csv"))

        logger.info(f"DEEP CLEANING - {len(csv_files)} datasets")

        for i, filepath in enumerate(csv_files):
            logger.info(f"[{i + 1}/{len(csv_files)}] Processing: {filepath.name}")
            report = self.process_dataset(str(filepath))
            self.reports.append(report)

            # Update stats
            self.overall_stats["total_datasets"] += 1
            self.overall_stats["total_rows"] += report.total_rows
            self.overall_stats["total_cells_cleaned"] += report.cells_cleaned
            self.overall_stats["domains_found"][report.detected_domain] += 1

            if report.success:
                logger.info(f"   [OK] {report.detected_domain} | Quality: {report.final_quality_score:.0f}% | Cleaned: {report.cells_cleaned}")
            else:
                logger.warning(f"   [X] {report.error_message}")

        if output_folder:
            self.export_reports(output_folder)

        return self.reports

    def process_dataset(self, filepath: str) -> DatasetReport:
        """Process a single dataset in detail."""
        try:
            df = pd.read_csv(filepath)
            filepath_path = Path(filepath)

            report = DatasetReport(
                filename=filepath_path.name,
                filepath=str(filepath),
                folder=filepath_path.parent.name,
                total_rows=len(df),
                total_columns=len(df.columns),
                file_size_kb=filepath_path.stat().st_size / 1024,
            )

            # Detect domain
            report.detected_domain, report.domain_confidence = self._detect_domain(df)
            report.alternative_domains = self._get_alternative_domains(df)

            # Analyze columns
            report = self._analyze_columns(df, report)

            # Find issues
            report = self._find_issues(df, report)

            # Calculate initial quality
            report.initial_quality_score = self._calculate_quality_score(df, report)

            # Apply cleaning
            report = self._apply_deep_cleaning(df, report)

            # Calculate final quality
            report.final_quality_score = self._calculate_quality_score(df, report)
            report.quality_improvement = (
                report.final_quality_score - report.initial_quality_score
            )

            report.success = True

        except Exception as e:
            report = DatasetReport(
                filename=Path(filepath).name,
                filepath=filepath,
                folder=Path(filepath).parent.name,
                total_rows=0,
                total_columns=0,
                file_size_kb=0,
                detected_domain="unknown",
                domain_confidence=0,
                initial_quality_score=0,
                final_quality_score=0,
                success=False,
                error_message=str(e),
            )

        return report

    def _detect_domain(self, df: pd.DataFrame) -> Tuple[str, float]:
        """Detect the domain type of the dataset."""
        col_names_lower = [c.lower() for c in df.columns]
        col_names_joined = " ".join(col_names_lower)

        scores = {}
        for domain, sig in self.DOMAIN_SIGNATURES.items():
            score = 0
            for kw in sig["keywords"]:
                if kw in col_names_joined:
                    score += 2
            for col in sig["columns"]:
                if any(col in c for c in col_names_lower):
                    score += 3
            scores[domain] = score

        if not scores or max(scores.values()) == 0:
            return "general", 0.3

        best_domain = max(scores, key=scores.get)
        max_score = scores[best_domain]
        confidence = min(0.95, max_score / 15)

        return best_domain, confidence

    def _get_alternative_domains(self, df: pd.DataFrame) -> Dict[str, float]:
        """Get alternative domain suggestions."""
        col_names_lower = [c.lower() for c in df.columns]
        col_names_joined = " ".join(col_names_lower)

        alternatives = {}
        for domain, sig in self.DOMAIN_SIGNATURES.items():
            score = 0
            for kw in sig["keywords"]:
                if kw in col_names_joined:
                    score += 1
            if score > 2:
                alternatives[domain] = min(0.8, score / 20)

        return dict(sorted(alternatives.items(), key=lambda x: -x[1])[:3])

    def _analyze_columns(
        self, df: pd.DataFrame, report: DatasetReport
    ) -> DatasetReport:
        """Detailed column analysis."""
        report.columns_by_type = {
            "numeric": [],
            "text": [],
            "categorical": [],
            "date": [],
            "boolean": [],
            "id": [],
            "mixed": [],
        }

        report.dtypes_found = {
            str(k): int(v) for k, v in df.dtypes.value_counts().items()
        }

        for col in df.columns:
            insight = ColumnInsight(column=col, detected_type="unknown", confidence=0)

            # Detect type
            dtype = str(df[col].dtype)
            null_count = df[col].isnull().sum()
            unique_count = df[col].nunique()
            sample = df[col].dropna().head(10).tolist()

            report.null_counts[col] = int(null_count)

            # Numeric detection
            if pd.api.types.is_numeric_dtype(df[col]):
                insight.detected_type = "numeric"
                insight.confidence = 0.95
                report.columns_by_type["numeric"].append(col)

            # Date detection
            elif self._is_date_column(df[col], col):
                insight.detected_type = "date"
                insight.confidence = 0.85
                report.columns_by_type["date"].append(col)

            # Boolean detection
            elif unique_count == 2 and df[col].dtype == object:
                insight.detected_type = "boolean"
                insight.confidence = 0.8
                report.columns_by_type["boolean"].append(col)

            # ID detection
            elif self._is_id_column(col, df[col]):
                insight.detected_type = "id"
                insight.confidence = 0.9
                report.columns_by_type["id"].append(col)

            # Categorical detection
            elif unique_count < 50:
                insight.detected_type = "categorical"
                insight.confidence = 0.75
                report.columns_by_type["categorical"].append(col)

            # Currency detection (only for price/value columns)
            elif self._has_currency(df[col]):
                col_lower = col.lower()
                non_currency_keywords = [
                    "email",
                    "name",
                    "first",
                    "last",
                    "full",
                    "phone",
                    "address",
                    "city",
                    "state",
                    "country",
                    "zip",
                    "code",
                    "id",
                    "user",
                    "customer",
                    "patient",
                    "doctor",
                    "agent",
                    "employee",
                    "student",
                    "supplier",
                    "merchant",
                    "sender",
                    "receiver",
                    "holder",
                    "category",
                    "brand",
                    "product",
                ]
                if not any(kw in col_lower for kw in non_currency_keywords):
                    insight.detected_type = "currency"
                    insight.confidence = 0.9
                    insight.format_detected = "currency_symbol"
                    report.patterns_found.append(f"currency:{col}")

            # Text detection
            else:
                insight.detected_type = "text"
                insight.confidence = 0.6
                report.columns_by_type["text"].append(col)

            # Check for mixed types
            if df[col].dtype == object:
                types_in_col = set()
                for val in df[col].dropna().head(100).astype(str):
                    if re.match(r"^-?\d+\.?\d*$", val):
                        types_in_col.add("number")
                    elif self._has_currency(pd.Series([val])):
                        types_in_col.add("currency")
                    elif re.match(r"^\d{4}-\d{2}-\d{2}", val):
                        types_in_col.add("date")
                    else:
                        types_in_col.add("text")

                if len(types_in_col) > 2:
                    insight.detected_type = "mixed"
                    insight.has_issues = True
                    report.columns_by_type["mixed"].append(col)
                    issue = ColumnIssue(
                        column=col,
                        issue_type="mixed_types",
                        severity="high",
                        description=f"Column contains {len(types_in_col)} different types: {types_in_col}",
                        sample_values=sample[:5],
                        affected_count=int(df[col].notna().sum() * 0.1),
                        recommended_action="Split or standardize column",
                    )
                    report.issues_found.append(issue)

            insight.sample_values = sample[:5]
            report.column_insights.append(insight)

        # Find constant columns
        report.constant_columns = [c for c in df.columns if df[c].nunique() == 1]

        # Find index columns
        if "RowNumber" in df.columns or "Index" in df.columns:
            report.index_columns = [
                c for c in ["RowNumber", "Index"] if c in df.columns
            ]

        # Duplicate count
        report.duplicate_count = int(df.duplicated().sum())

        return report

    def _is_date_column(self, series: pd.Series, col_name: str) -> bool:
        """Check if column contains dates."""
        col_lower = col_name.lower()
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
        ]

        if any(kw in col_lower for kw in date_keywords):
            return True

        if pd.api.types.is_numeric_dtype(series):
            return False

        try:
            sample = series.dropna().head(50)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                parsed = pd.to_datetime(sample, errors="coerce")
                if parsed.notna().mean() > 0.8:
                    return True
        except:
            pass

        return False

    def _is_id_column(self, col_name: str, series: pd.Series) -> bool:
        """Check if column is an ID column."""
        col_lower = col_name.lower()
        id_patterns = ["id", "_id", "uuid", "guid", "key", "pk", "fk"]

        for pattern in id_patterns:
            if pattern in col_lower:
                return True

        # Check if sequential
        try:
            if pd.api.types.is_numeric_dtype(series):
                vals = series.dropna().astype(int).tolist()
                if len(vals) > 10:
                    expected = list(range(1, len(vals) + 1))
                    if vals == expected:
                        return True
        except:
            pass

        return False

    def _has_currency(self, series: pd.Series) -> bool:
        """Check if column contains currency values."""
        sample = series.dropna().astype(str).head(50)
        for sym in self.CURRENCY_SYMBOLS:
            matches = sample.str.contains(sym, regex=False, na=False)
            if matches.mean() > 0.05:
                return True
        return False

    def _find_issues(self, df: pd.DataFrame, report: DatasetReport) -> DatasetReport:
        """Find all data quality issues."""

        # Check for duplicate rows
        dup_count = df.duplicated().sum()
        if dup_count > 0:
            report.issues_summary["duplicates"] = int(dup_count)
            issue = ColumnIssue(
                column="(all)",
                issue_type="duplicate_rows",
                severity="medium",
                description=f"Dataset contains {dup_count} duplicate rows",
                affected_count=int(dup_count),
                recommended_action="remove_duplicates",
            )
            report.issues_found.append(issue)

        # Check for constant columns
        for col in df.columns:
            if df[col].nunique() == 1:
                report.issues_summary["constant_columns"] = (
                    report.issues_summary.get("constant_columns", 0) + 1
                )
                issue = ColumnIssue(
                    column=col,
                    issue_type="constant_column",
                    severity="low",
                    description=f"Column has only one unique value: {df[col].iloc[0]}",
                    sample_values=[df[col].iloc[0]],
                    affected_count=len(df),
                    recommended_action="drop_column",
                )
                report.issues_found.append(issue)

        # Check for error placeholders
        for col in df.columns:
            if df[col].dtype == object:
                str_col = df[col].dropna().astype(str).str.lower()
                errors_found = []
                for val in str_col.unique():
                    if val.strip() in self.ERROR_VALUES:
                        errors_found.append(val)

                if errors_found:
                    count = str_col.isin(errors_found).sum()
                    report.issues_summary["error_placeholders"] = (
                        report.issues_summary.get("error_placeholders", 0) + count
                    )
                    issue = ColumnIssue(
                        column=col,
                        issue_type="error_placeholders",
                        severity="high",
                        description=f"Found error placeholders: {errors_found}",
                        sample_values=errors_found[:3],
                        affected_count=int(count),
                        recommended_action="replace_errors",
                    )
                    report.issues_found.append(issue)

        # Check for special characters
        for col in df.columns:
            if df[col].dtype == object:
                special_chars = (
                    df[col].astype(str).str.contains(r"[?�\x00]", regex=True, na=False)
                )
                if special_chars.sum() > 0:
                    report.issues_summary["special_characters"] = (
                        report.issues_summary.get("special_characters", 0)
                        + int(special_chars.sum())
                    )
                    issue = ColumnIssue(
                        column=col,
                        issue_type="special_characters",
                        severity="medium",
                        description=f"Found {special_chars.sum()} cells with special characters",
                        affected_count=int(special_chars.sum()),
                        recommended_action="clean_special_characters",
                    )
                    report.issues_found.append(issue)

        # Check for mixed types
        for col in df.columns:
            if df[col].dtype == object:
                unique_vals = df[col].dropna().astype(str).unique()
                type_indicators = {"numeric": 0, "date": 0, "text": 0}

                for val in unique_vals[:50]:
                    val_str = str(val)
                    if re.match(r"^-?\d+\.?\d*$", val_str):
                        type_indicators["numeric"] += 1
                    elif re.match(r"^\d{4}-\d{2}-\d{2}", val_str):
                        type_indicators["date"] += 1

                types_present = sum(
                    1 for v in type_indicators.values() if v > len(unique_vals) * 0.1
                )
                if types_present > 1:
                    issue = ColumnIssue(
                        column=col,
                        issue_type="mixed_types",
                        severity="high",
                        description=f"Column has mixed data types",
                        recommended_action="split_or_convert",
                    )
                    report.issues_found.append(issue)

        # Check for high null percentage
        for col in df.columns:
            null_pct = df[col].isnull().mean()
            if null_pct > 0.5:
                issue = ColumnIssue(
                    column=col,
                    issue_type="high_missing",
                    severity="high",
                    description=f"Column has {null_pct:.1%} missing values",
                    affected_count=int(df[col].isnull().sum()),
                    recommended_action="fill_missing or drop_column",
                )
                report.issues_found.append(issue)

        return report

    def _calculate_quality_score(
        self, df: pd.DataFrame, report: DatasetReport
    ) -> float:
        """Calculate comprehensive data quality score (0-100)."""
        if df is None or len(df) == 0 or len(df.columns) == 0:
            return 0.0

        score = 100.0

        # 1. Missing values (most important - 30 points)
        missing_pct = df.isnull().mean().mean()
        score -= missing_pct * 30

        # 2. Duplicate rows (20 points)
        dup_pct = df.duplicated().mean()
        score -= dup_pct * 20

        # 3. Data type consistency (15 points)
        type_issues = 0
        for col in df.columns:
            if df[col].dtype == object:
                sample = df[col].dropna().astype(str)
                if len(sample) > 0:
                    # Check for mixed types in text columns
                    numeric_ratio = sample.str.match(r"^-?\d+\.?\d*$").mean()
                    if 0.3 < numeric_ratio < 0.7:
                        type_issues += 1
        score -= min(type_issues * 3, 15)

        # 4. Format validation (15 points) - check known formats
        format_score = 0
        total_checks = 0
        for col in df.columns:
            col_lower = col.lower()
            sample = df[col].dropna().astype(str)
            if len(sample) == 0:
                continue
            total_checks += 1

            if "email" in col_lower:
                valid_emails = sample.str.match(r"^[\w.-]+@[\w.-]+\.\w+$").mean()
                format_score += valid_emails
            elif any(x in col_lower for x in ["phone", "tel", "mobile"]):
                valid_phones = sample.str.match(r"^[\d\s\-\(\)\+]+$").mean()
                format_score += valid_phones
            elif "date" in col_lower or "dob" in col_lower:
                try:
                    parsed = pd.to_datetime(sample, errors="coerce")
                    valid_dates = parsed.notna().mean()
                    format_score += valid_dates
                except:
                    format_score += 0.5
            elif any(x in col_lower for x in ["zip", "postal"]):
                valid_zips = sample.str.match(r"^\d{5}(-\d{4})?$").mean()
                format_score += valid_zips
            else:
                format_score += 0.8  # Default score for unknown formats

        if total_checks > 0:
            avg_format_score = format_score / total_checks
            score -= (1 - avg_format_score) * 15

        # 5. Critical issues (10 points)
        critical_issues = sum(
            1 for issue in report.issues_found if issue.severity == "high"
        )
        score -= min(critical_issues * 2, 10)

        # 6. Constant/low-variance columns (5 points)
        score -= min(len(report.constant_columns) * 2, 5)

        # 7. Column variety bonus (5 points)
        text_cols = sum(1 for col in df.columns if df[col].dtype == object)
        numeric_cols = sum(
            1 for col in df.columns if pd.api.types.is_numeric_dtype(df[col])
        )
        variety_bonus = min((text_cols + numeric_cols) / len(df.columns), 1) * 5
        score += variety_bonus

        return max(0, min(100, score))

    def _apply_deep_cleaning(
        self, df: pd.DataFrame, report: DatasetReport
    ) -> DatasetReport:
        """Apply comprehensive cleaning to the dataset."""

        initial_rows = len(df)
        initial_cols = len(df.columns)
        cells_cleaned_total = 0

        # Step 0: Detect anomalies for intelligent cleaning
        anomalies = detect_anomalies(df, domain=report.detected_domain)
        if anomalies["total_anomalies"] > 0:
            report.cleaning_steps.append(
                {
                    "step": 0,
                    "action": "detect_anomalies",
                    "description": f"Found {anomalies['total_anomalies']} anomalies ({anomalies['high_severity']} high severity)",
                    "anomalies_detected": anomalies["total_anomalies"],
                }
            )

        # Step 1: Remove duplicates
        if report.duplicate_count > 0:
            df = df.drop_duplicates()
            report.rows_removed = initial_rows - len(df)
            report.cleaning_steps.append(
                {
                    "step": 1,
                    "action": "remove_duplicates",
                    "description": f"Removed {report.rows_removed} duplicate rows",
                    "cells_affected": 0,
                }
            )

        # Step 1.5: Drop columns with excessive missing values (>80%)
        cols_to_drop = []
        for col in df.columns:
            missing_pct = df[col].isnull().mean()
            if missing_pct > 0.8:
                cols_to_drop.append(col)

        for col in cols_to_drop:
            df = df.drop(columns=[col])
            report.columns_removed += 1
            report.cleaning_steps.append(
                {
                    "step": len(report.cleaning_steps) + 1,
                    "action": "drop_high_missing_column",
                    "column": col,
                    "description": f"Dropped column with >80% missing values",
                    "cells_affected": 0,
                }
            )

        # Step 2: Clean error placeholders
        for col in df.columns:
            if df[col].dtype == object:
                str_col = df[col].dropna().astype(str).str.lower()
                errors_found = []
                for val in str_col.unique():
                    if val.strip() in self.ERROR_VALUES:
                        errors_found.append(val)

                if errors_found:
                    before = df[col].isnull().sum()
                    df[col] = df[col].replace(errors_found, np.nan)
                    cleaned = before - df[col].isnull().sum()
                    cells_cleaned_total += cleaned
                    report.cleaning_steps.append(
                        {
                            "step": len(report.cleaning_steps) + 1,
                            "action": "replace_errors",
                            "column": col,
                            "description": f"Replaced {len(errors_found)} error values with NaN",
                            "cells_affected": int(cleaned),
                        }
                    )

        # Step 3: Clean special characters and noise
        for col in df.columns:
            if df[col].dtype == object:
                original = df[col].copy()

                # Remove common noise patterns
                df[col] = df[col].str.replace(r"[?]+", "", regex=True)
                df[col] = df[col].str.replace(r"[@#$%^&*!]+", "", regex=True)
                df[col] = df[col].str.replace(
                    r"[\d]{10,}", "", regex=True
                )  # Remove long digit sequences
                df[col] = df[col].str.replace(
                    r"http[s]?://\S+", "", regex=True
                )  # Remove URLs
                df[col] = df[col].str.replace(
                    r"\s+", " ", regex=True
                )  # Normalize whitespace
                df[col] = df[col].str.strip()

                # Count changes
                changes = (original != df[col]).sum()
                if changes > 0:
                    cells_cleaned_total += changes
                    report.cleaning_steps.append(
                        {
                            "step": len(report.cleaning_steps) + 1,
                            "action": "clean_special_chars",
                            "column": col,
                            "description": f"Cleaned special characters from {changes} cells",
                            "cells_affected": changes,
                        }
                    )

        # Step 4: Parse currency columns
        for col in df.columns:
            if self._has_currency(df[col]):
                before_dtype = str(df[col].dtype)
                sample = df[col].dropna().head(5).tolist()
                df[col] = (
                    df[col]
                    .astype(str)
                    .str.replace(r"[$€£¥₹₽₿R$krCHFA$C\$]", "", regex=True)
                )
                df[col] = df[col].str.replace(",", "")
                df[col] = pd.to_numeric(df[col], errors="coerce")
                cells_cleaned_total += len(df)
                report.cleaning_steps.append(
                    {
                        "step": len(report.cleaning_steps) + 1,
                        "action": "parse_currency",
                        "column": col,
                        "description": f"Converted currency to numeric",
                        "cells_affected": len(df),
                        "before_dtype": before_dtype,
                        "after_dtype": "float64",
                    }
                )

        # Step 5: Standardize capitalization for text columns
        for col in df.columns:
            if (
                df[col].dtype == object
                and df[col].nunique() < 100
                and df[col].nunique() > 2
            ):
                before_null = df[col].isnull().sum()
                df[col] = df[col].str.strip()
                # Title case for most categorical columns
                if not any(kw in col.lower() for kw in ["email", "url", "id", "code"]):
                    df[col] = df[col].str.title()
                    cells_cleaned_total += df[col].notna().sum()
                    report.cleaning_steps.append(
                        {
                            "step": len(report.cleaning_steps) + 1,
                            "action": "standardize_capitalization",
                            "column": col,
                            "description": "Standardized text capitalization",
                            "cells_affected": int(df[col].notna().sum()),
                        }
                    )

        # Step 6: Drop constant columns
        for col in df.columns:
            if df[col].nunique() == 1:
                df = df.drop(columns=[col])
                report.columns_removed += 1
                report.cleaning_steps.append(
                    {
                        "step": len(report.cleaning_steps) + 1,
                        "action": "drop_constant_column",
                        "column": col,
                        "description": f"Dropped constant column",
                        "cells_affected": 0,
                    }
                )

        # Step 7: Drop index columns
        for col in ["RowNumber", "Index"]:
            if col in df.columns:
                df = df.drop(columns=[col])
                report.columns_removed += 1
                report.cleaning_steps.append(
                    {
                        "step": len(report.cleaning_steps) + 1,
                        "action": "drop_index_column",
                        "column": col,
                        "description": "Dropped unnecessary index column",
                        "cells_affected": 0,
                    }
                )

        # Step 8: Parse dates
        for col in df.columns:
            if self._is_date_column(df[col], col):
                before_dtype = str(df[col].dtype)
                try:
                    df[col] = pd.to_datetime(df[col], errors="coerce")
                    if df[col].notna().mean() > 0.5:
                        report.cleaning_steps.append(
                            {
                                "step": len(report.cleaning_steps) + 1,
                                "action": "parse_dates",
                                "column": col,
                                "description": "Converted to datetime format",
                                "cells_affected": int(df[col].notna().sum()),
                                "before_dtype": before_dtype,
                                "after_dtype": "datetime64",
                            }
                        )
                except:
                    pass

        # Step 8.5: Clean numeric columns with dirty values (inf, units, quotes)
        for col in df.columns:
            if df[col].dtype == object:
                original_nulls = df[col].isna().sum()
                cleaned = df[col].astype(str)
                cleaned = cleaned.str.replace(r"[\$€£¥₹]", "", regex=True)
                cleaned = cleaned.str.replace(
                    r"\s*(lbs?|kg|units?).*$", "", regex=True, case=False
                )
                cleaned = cleaned.str.strip()
                cleaned = cleaned.str.replace('"', "", regex=False)

                numeric_col = pd.to_numeric(cleaned, errors="coerce")
                if numeric_col.notna().mean() > 0.5:
                    valid_values = numeric_col.replace(
                        [np.inf, -np.inf], np.nan
                    ).dropna()
                    if len(valid_values) > 0:
                        median_val = valid_values.median()
                        numeric_col = numeric_col.fillna(median_val)
                        numeric_col = numeric_col.replace([np.inf, -np.inf], median_val)

                        before = df[col].notna().sum()
                        df[col] = numeric_col
                        after = df[col].notna().sum()
                        cleaned_count = max(0, after - before)

                        if cleaned_count > 0:
                            cells_cleaned_total += cleaned_count
                            report.cleaning_steps.append(
                                {
                                    "step": len(report.cleaning_steps) + 1,
                                    "action": "clean_numeric_column",
                                    "column": col,
                                    "description": f"Cleaned numeric values, filled with median",
                                    "cells_affected": cleaned_count,
                                }
                            )

        # Step 9: Intelligent missing value imputation
        for col in df.columns:
            null_count = df[col].isnull().sum()
            if null_count > 0 and null_count < len(df) * 0.7:
                before_null = df[col].isnull().sum()

                # Try to detect if column should be numeric
                is_numeric = pd.api.types.is_numeric_dtype(df[col])
                if not is_numeric and df[col].dtype == object:
                    sample = df[col].dropna().astype(str)
                    if len(sample) > 0:
                        numeric_ratio = sample.str.match(r"^-?\d+\.?\d*$").mean()
                        if numeric_ratio > 0.5:
                            is_numeric = True

                if is_numeric:
                    numeric_col = pd.to_numeric(df[col], errors="coerce")
                    numeric_col = numeric_col.replace([np.inf, -np.inf], np.nan)
                    if numeric_col.notna().mean() > 0.3:
                        median_val = numeric_col.median()
                        df[col] = numeric_col.fillna(median_val)
                        cells_cleaned_total += before_null - df[col].isnull().sum()
                        report.cleaning_steps.append(
                            {
                                "step": len(report.cleaning_steps) + 1,
                                "action": "impute_missing",
                                "column": col,
                                "description": f"Imputed {before_null} missing values with median",
                                "cells_affected": before_null - df[col].isnull().sum(),
                                "imputation_method": "median",
                            }
                        )
                else:
                    non_null = df[col].dropna()
                    if len(non_null) > 0:
                        mode_val = (
                            non_null.mode().iloc[0]
                            if len(non_null.mode()) > 0
                            else "Unknown"
                        )
                        df[col] = df[col].fillna(mode_val)
                        cells_cleaned_total += before_null - df[col].isnull().sum()
                        report.cleaning_steps.append(
                            {
                                "step": len(report.cleaning_steps) + 1,
                                "action": "impute_missing",
                                "column": col,
                                "description": f"Imputed {before_null} missing values with mode",
                                "cells_affected": before_null - df[col].isnull().sum(),
                                "imputation_method": "mode",
                            }
                        )

        # Step 10: Trim whitespace
        for col in df.columns:
            if df[col].dtype == object:
                before = df[col].astype(str).str.len().sum()
                df[col] = df[col].astype(str).str.strip()
                after = df[col].str.len().sum()
                if after < before:
                    cells_cleaned_total += 1
                    report.cleaning_steps.append(
                        {
                            "step": len(report.cleaning_steps) + 1,
                            "action": "trim_whitespace",
                            "column": col,
                            "description": "Trimmed leading/trailing whitespace",
                            "cells_affected": 1,
                        }
                    )

        # Step 11: Domain-specific column cleaning
        for col in df.columns:
            detection = detect_and_clean_column(df, col)
            if (
                detection["cleaning_function"]
                and detection["cleaning_function"] in COLUMN_CLEANERS
            ):
                before_count = len(df)
                func = COLUMN_CLEANERS[detection["cleaning_function"]]
                original_values = df[col].copy()

                try:
                    df[col] = df[col].apply(func)

                    changed = (original_values != df[col]).sum()
                    if changed > 0:
                        cells_cleaned_total += changed
                        report.cleaning_steps.append(
                            {
                                "step": len(report.cleaning_steps) + 1,
                                "action": f"clean_{detection['detected_type']}",
                                "column": col,
                                "description": f"Cleaned {changed} values ({detection['detected_type']})",
                                "cells_affected": changed,
                            }
                        )
                except:
                    pass

        # Step 12: Detect and handle outliers in numeric columns
        for col in df.columns:
            col_data = df[col].copy()

            if pd.api.types.is_numeric_dtype(col_data):
                col_data = col_data.replace([np.inf, -np.inf], np.nan)
            elif col_data.dtype == object:
                numeric_col = pd.to_numeric(col_data, errors="coerce")
                if numeric_col.notna().mean() > 0.5:
                    col_data = numeric_col

            if pd.api.types.is_numeric_dtype(col_data) and col_data.notna().sum() > 10:
                col_data = col_data.replace([np.inf, -np.inf], np.nan)
                valid_data = col_data.dropna()

                if len(valid_data) > 10:
                    Q1 = valid_data.quantile(0.25)
                    Q3 = valid_data.quantile(0.75)
                    IQR = Q3 - Q1

                    if IQR > 0:
                        lower_bound = Q1 - 3 * IQR
                        upper_bound = Q3 + 3 * IQR

                        outlier_mask = (col_data < lower_bound) | (
                            col_data > upper_bound
                        )
                        outlier_count = outlier_mask.sum()

                        if outlier_count > 0 and outlier_count < len(df) * 0.1:
                            median_val = valid_data.median()
                            df.loc[outlier_mask, col] = median_val
                            cells_cleaned_total += outlier_count
                            report.cleaning_steps.append(
                                {
                                    "step": len(report.cleaning_steps) + 1,
                                    "action": "cap_outliers",
                                    "column": col,
                                    "description": f"Capped {outlier_count} outliers to median",
                                    "cells_affected": outlier_count,
                                    "method": "iqr_3x",
                                }
                            )

        # Step 13: Clean text columns with high noise (detect repeated characters, common typos)
        for col in df.columns:
            if df[col].dtype == object and df[col].nunique() > 2:
                original = df[col].copy()

                # Remove repeated characters (e.g., "Malle" -> "Male", "Femmale" -> "Female")
                df[col] = df[col].str.replace(r"(.)\1+", r"\1", regex=True)

                # Clean up common OCR/typo patterns
                df[col] = df[col].str.replace(r"[^a-zA-Z0-9\s@.\-]", "", regex=True)
                df[col] = df[col].str.strip()

                changes = (original != df[col]).sum()
                if changes > 0 and changes < len(df) * 0.3:
                    cells_cleaned_total += changes
                    report.cleaning_steps.append(
                        {
                            "step": len(report.cleaning_steps) + 1,
                            "action": "clean_text_noise",
                            "column": col,
                            "description": f"Cleaned text noise from {changes} cells",
                            "cells_affected": changes,
                        }
                    )

        report.cells_cleaned = cells_cleaned_total

        # Step 14: Apply domain-specific cleaning
        if report.detected_domain in [
            "healthcare",
            "financial",
            "ecommerce",
            "hr",
            "logistics",
        ]:
            original_values = df.copy()
            df = apply_domain_cleaning(df, report.detected_domain)
            changed_cells = (original_values != df).sum().sum()
            if changed_cells > 0:
                cells_cleaned_total += changed_cells
                report.cells_cleaned = cells_cleaned_total
                report.cleaning_steps.append(
                    {
                        "step": 14,
                        "action": f"domain_cleaning_{report.detected_domain}",
                        "description": f"Applied {report.detected_domain}-specific cleaning rules",
                        "cells_affected": changed_cells,
                    }
                )

        return report

    def export_reports(self, output_folder: str):
        """Export all reports to JSON."""
        os.makedirs(output_folder, exist_ok=True)

        # Export summary
        summary = {
            "generated_at": datetime.now().isoformat(),
            "total_datasets": self.overall_stats["total_datasets"],
            "total_rows_processed": self.overall_stats["total_rows"],
            "total_cells_cleaned": self.overall_stats["total_cells_cleaned"],
            "domains_distribution": dict(self.overall_stats["domains_found"]),
            "quality_summary": {
                "avg_initial_quality": sum(
                    r.initial_quality_score for r in self.reports
                )
                / len(self.reports)
                if self.reports
                else 0,
                "avg_final_quality": sum(r.final_quality_score for r in self.reports)
                / len(self.reports)
                if self.reports
                else 0,
                "avg_improvement": sum(r.quality_improvement for r in self.reports)
                / len(self.reports)
                if self.reports
                else 0,
            },
        }

        with open(f"{output_folder}/summary.json", "w") as f:
            json.dump(summary, f, indent=2, default=str)

        # Export individual reports
        def json_safe_serializer(obj):
            if hasattr(obj, "__dict__"):
                return str(obj)
            return str(obj)

        for i, report in enumerate(self.reports):
            report_data = asdict(report)
            # Convert all keys to strings for JSON serialization
            for key in list(report_data.keys()):
                if not isinstance(key, str):
                    report_data[str(key)] = report_data.pop(key)
            with open(
                f"{output_folder}/report_{i + 1:03d}_{report.filename.replace('.csv', '.json')}",
                "w",
            ) as f:
                json.dump(report_data, f, indent=2, default=str)

        logger.info(f"Reports exported to {output_folder}")

    def print_summary(self):
        """Print overall summary."""
        logger.info("=" * 80)
        logger.info("DEEP CLEANING COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Total datasets: {self.overall_stats['total_datasets']}")
        logger.info(f"Total rows: {self.overall_stats['total_rows']:,}")
        logger.info(f"Total cells cleaned: {self.overall_stats['total_cells_cleaned']:,}")
        logger.info("Domains found:")
        for domain, count in sorted(
            self.overall_stats["domains_found"].items(), key=lambda x: -x[1]
        ):
            logger.info(f"  - {domain}: {count}")


if __name__ == "__main__":
    datasets_folder = "D:/datacove_out/Datasets"
    output_folder = "D:/datacove_out/cleaning_reports"
    cleaned_folder = "D:/datacove_out/cleaned_datasets"

    cleaner = DeepDatasetCleaner()
    cleaner.process_folder(datasets_folder, cleaned_folder)
    cleaner.export_reports(output_folder)
