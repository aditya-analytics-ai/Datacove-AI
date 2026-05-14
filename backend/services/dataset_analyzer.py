"""
Dataset Analyzer - Scans folders and profiles datasets.
Extracts features, detects patterns, and identifies issues for rule learning.
"""

from __future__ import annotations

import os
import json
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import re

import pandas as pd
import numpy as np

from utils.logger import logger


@dataclass
class ColumnFeatures:
    name: str
    dtype: str
    null_pct: float
    unique_count: int
    cardinality: str
    sample_values: List[Any] = field(default_factory=list)

    patterns_found: List[str] = field(default_factory=list)
    detected_type: Optional[str] = None
    detected_format: Optional[str] = None
    is_numeric: bool = False
    is_categorical: bool = False
    is_id: bool = False

    value_patterns: Dict[str, int] = field(default_factory=dict)
    common_prefixes: List[str] = field(default_factory=list)
    common_suffixes: List[str] = field(default_factory=list)


@dataclass
class DatasetFeatures:
    filename: str
    filepath: str
    file_hash: str

    total_rows: int
    total_columns: int

    detected_domain: str = "unknown"
    domain_confidence: float = 0.0

    column_features: Dict[str, ColumnFeatures] = field(default_factory=dict)

    quality_issues: List[str] = field(default_factory=list)

    column_count: int = 0
    numeric_count: int = 0
    categorical_count: int = 0
    text_count: int = 0
    date_count: int = 0

    currency_columns: List[str] = field(default_factory=list)
    id_columns: List[str] = field(default_factory=list)
    error_placeholders: Dict[str, List[str]] = field(default_factory=dict)

    row_dup_pct: float = 0.0
    constant_columns: List[str] = field(default_factory=list)
    index_columns: List[str] = field(default_factory=list)

    analyzed_at: str = field(default_factory=lambda: datetime.now().isoformat())

    raw_features: Dict[str, Any] = field(default_factory=dict)


class DatasetAnalyzer:
    """
    Analyzes datasets to extract features for rule mining.
    """

    CURRENCY_SYMBOLS = ["$", "€", "£", "¥", "₹", "₽", "₿"]

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
    }

    DATE_PATTERNS = [
        r"^\d{4}-\d{2}-\d{2}",
        r"^\d{2}/\d{2}/\d{4}",
        r"^\d{2}-\d{2}-\d{4}",
        r"^\w{3,9}\s+\d{1,2},?\s+\d{4}",
    ]

    EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    PHONE_PATTERN = re.compile(r"^[\d\s\-\(\)\+\.]{7,}$")
    URL_PATTERN = re.compile(r"^https?://")

    ID_PATTERNS = [
        r"^id$",
        r"_id$",
        r"^uuid",
        r"^guid",
        r"^[A-Z]{2,3}\d{4,}$",
        r"^TXN_",
        r"^ORD_",
        r"^INV_",
    ]

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
                "discount",
            ],
            "numeric": ["amount", "quantity", "price", "total", "revenue"],
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
                "age",
                "gender",
                "dob",
                "birth",
            ],
            "numeric": ["age"],
        },
        "financial": {
            "keywords": [
                "expense",
                "cost",
                "budget",
                "income",
                "asset",
                "liability",
                "balance",
                "payment",
                "fee",
                "interest",
                "loan",
            ],
            "numeric": ["amount", "balance", "cost", "price"],
        },
        "hr": {
            "keywords": [
                "employee",
                "staff",
                "hire",
                "department",
                "position",
                "salary",
                "bonus",
                "leave",
                "manager",
                "performance",
            ],
            "numeric": ["salary", "bonus", "age"],
        },
        "ecommerce": {
            "keywords": [
                "cart",
                "checkout",
                "payment",
                "shipping",
                "product",
                "review",
                "rating",
                "wishlist",
                "purchase",
                "refund",
            ],
            "numeric": ["price", "quantity", "total", "rating"],
        },
        "inventory": {
            "keywords": [
                "inventory",
                "stock",
                "warehouse",
                "product",
                "sku",
                "supplier",
                "purchase",
                "shipping",
                "on_hand",
            ],
            "numeric": ["quantity", "stock", "on_hand"],
        },
        "marketing": {
            "keywords": [
                "campaign",
                "lead",
                "conversion",
                "click",
                "impression",
                "engagement",
                "subscribe",
                "promotion",
                "coupon",
            ],
            "numeric": ["conversion", "clicks", "impressions", "spend"],
        },
        "healthcare": {
            "keywords": [
                "patient",
                "diagnosis",
                "treatment",
                "doctor",
                "nurse",
                "department",
                "admission",
                "discharge",
                "vital",
            ],
            "numeric": ["age", "weight", "height", "temperature"],
        },
    }

    def __init__(self):
        self.stats = {
            "datasets_analyzed": 0,
            "total_rows": 0,
            "patterns_found": {},
            "domains_detected": {},
        }

    def analyze_file(self, filepath: str) -> Optional[DatasetFeatures]:
        """Analyze a single file and return features."""
        try:
            df = self._load_file(filepath)
            if df is None or df.empty:
                return None

            features = DatasetFeatures(
                filename=os.path.basename(filepath),
                filepath=filepath,
                file_hash=self._compute_hash(df),
                total_rows=len(df),
                total_columns=len(df.columns),
            )

            features = self._profile_columns(df, features)
            features = self._detect_domain(df, features)
            features = self._detect_issues(df, features)
            features = self._extract_patterns(df, features)

            self._update_stats(features)

            return features

        except Exception as e:
            logger.error(f"Error analyzing {filepath}: {e}")
            return None

    def analyze_folder(
        self, folder_path: str, recursive: bool = True
    ) -> List[DatasetFeatures]:
        """Analyze all datasets in a folder."""
        features_list = []

        patterns = ["**/*.csv", "**/*.xlsx", "**/*.xls", "**/*.json", "**/*.tsv"]

        for pattern in patterns:
            files = (
                Path(folder_path).glob(pattern)
                if recursive
                else Path(folder_path).glob(os.path.basename(pattern))
            )

            for filepath in files:
                if filepath.is_file():
                    features = self.analyze_file(str(filepath))
                    if features:
                        features_list.append(features)

        return features_list

    def _load_file(self, filepath: str) -> Optional[pd.DataFrame]:
        """Load file based on extension."""
        ext = Path(filepath).suffix.lower()

        try:
            if ext == ".csv":
                return pd.read_csv(filepath)
            elif ext in [".xlsx", ".xls"]:
                return pd.read_excel(filepath)
            elif ext == ".json":
                return pd.read_json(filepath)
            elif ext == ".tsv":
                return pd.read_csv(filepath, sep="\t")
        except Exception:
            return None

        return None

    def _compute_hash(self, df: pd.DataFrame) -> str:
        """Compute hash of dataframe for uniqueness."""
        content = str(df.shape) + str(df.columns.tolist()) + str(df.head(3).to_dict())
        return hashlib.md5(content.encode()).hexdigest()[:8]

    def _profile_columns(
        self, df: pd.DataFrame, features: DatasetFeatures
    ) -> DatasetFeatures:
        """Profile each column and extract features."""
        for col in df.columns:
            is_num = pd.api.types.is_numeric_dtype(df[col])
            is_cat = self._is_categorical(df[col])

            col_feat = ColumnFeatures(
                name=col,
                dtype=str(df[col].dtype),
                null_pct=df[col].isnull().mean(),
                unique_count=df[col].nunique(),
                cardinality=self._get_cardinality(df[col]),
                sample_values=df[col].dropna().head(5).tolist(),
                is_numeric=is_num,
                is_categorical=is_cat,
            )

            features.column_features[col] = col_feat

            if is_num:
                features.numeric_count += 1
            elif is_cat:
                features.categorical_count += 1
            elif self._is_date_column(df[col]):
                features.date_count += 1
            else:
                features.text_count += 1

        features.column_count = len(df.columns)
        return features

    def _get_cardinality(self, series: pd.Series) -> str:
        """Determine cardinality level."""
        unique_ratio = series.nunique() / len(series.dropna())
        if unique_ratio < 0.05:
            return "low"
        elif unique_ratio < 0.5:
            return "medium"
        return "high"

    def _is_categorical(self, series: pd.Series) -> bool:
        """Check if column is categorical."""
        if series.dtype == object or pd.api.types.is_categorical_dtype(series):
            unique_ratio = series.nunique() / len(series.dropna())
            return unique_ratio < 0.1
        return False

    def _is_date_column(self, series: pd.Series) -> bool:
        """Check if column contains dates."""
        name_lower = str(series.name).lower()
        date_keywords = [
            "date",
            "time",
            "day",
            "month",
            "year",
            "created",
            "dob",
            "birth",
        ]

        if any(kw in name_lower for kw in date_keywords):
            return True

        if pd.api.types.is_datetime64_any_dtype(series):
            return True

        try:
            sample = series.dropna().head(50)
            parsed = pd.to_datetime(sample, errors="coerce")
            if parsed.notna().mean() > 0.8:
                return True
        except:
            pass

        return False

    def _detect_domain(
        self, df: pd.DataFrame, features: DatasetFeatures
    ) -> DatasetFeatures:
        """Detect the domain type of the dataset."""
        col_names_lower = [c.lower() for c in df.columns]
        col_names_joined = " ".join(col_names_lower)

        scores = {}

        for domain, sig in self.DOMAIN_SIGNATURES.items():
            score = 0
            for kw in sig["keywords"]:
                if kw in col_names_joined:
                    score += 2

            scores[domain] = score

        if scores and max(scores.values()) > 0:
            best_domain = max(scores, key=scores.get)
            max_score = scores[best_domain]
            confidence = min(0.95, max_score / 10)

            features.detected_domain = best_domain
            features.domain_confidence = confidence

        return features

    def _detect_issues(
        self, df: pd.DataFrame, features: DatasetFeatures
    ) -> DatasetFeatures:
        """Detect data quality issues."""
        features.row_dup_pct = df.duplicated().mean()

        if df.duplicated().any():
            features.quality_issues.append(
                f"Contains {df.duplicated().sum()} duplicate rows"
            )

        for col in df.columns:
            if df[col].dtype == object:
                str_col = df[col].dropna().astype(str).str.lower()

                error_count = sum(1 for v in str_col if v.strip() in self.ERROR_VALUES)

                if error_count > 5:
                    errors_found = [
                        v for v in str_col.unique() if v.strip() in self.ERROR_VALUES
                    ]
                    features.error_placeholders[col] = errors_found
                    features.quality_issues.append(
                        f"Column '{col}' has {error_count} error placeholder values"
                    )

        for col in df.columns:
            if df[col].nunique() == 1:
                features.constant_columns.append(col)
                features.quality_issues.append(f"Column '{col}' has only one value")

        if "RowNumber" in df.columns or "Index" in df.columns:
            index_cols = [c for c in ["RowNumber", "Index"] if c in df.columns]
            features.index_columns.extend(index_cols)

        return features

    def _extract_patterns(
        self, df: pd.DataFrame, features: DatasetFeatures
    ) -> DatasetFeatures:
        """Extract value patterns from columns."""
        for col in df.columns:
            if df[col].dtype == object:
                str_col = df[col].dropna().astype(str)

                if self._has_currency(str_col):
                    features.currency_columns.append(col)
                    features.column_features[col].detected_format = "currency"
                    features.column_features[col].patterns_found.append(
                        "currency_symbol"
                    )

                for id_pattern in self.ID_PATTERNS:
                    if re.search(id_pattern, col, re.IGNORECASE):
                        features.id_columns.append(col)
                        break

                prefixes = self._extract_prefixes(str_col)
                suffixes = self._extract_suffixes(str_col)

                if prefixes:
                    features.column_features[col].common_prefixes = prefixes
                if suffixes:
                    features.column_features[col].common_suffixes = suffixes

        features.raw_features = {
            "currency_count": len(features.currency_columns),
            "id_count": len(features.id_columns),
            "date_count": features.date_count,
            "numeric_count": features.numeric_count,
            "categorical_count": features.categorical_count,
            "error_cols": len(features.error_placeholders),
        }

        return features

    def _has_currency(self, series: pd.Series) -> bool:
        """Check if column contains currency values."""
        sample = series.head(50)
        for sym in self.CURRENCY_SYMBOLS:
            if any(sym in str(v) for v in sample):
                return True
        return False

    def _extract_prefixes(self, series: pd.Series, top_n: int = 3) -> List[str]:
        """Extract common prefixes from values."""
        prefixes = {}
        for val in series.head(100):
            s = str(val)
            parts = re.split(r"[\s_\-]+", s)
            if len(parts) > 1:
                prefix = parts[0]
                prefixes[prefix] = prefixes.get(prefix, 0) + 1

        if prefixes:
            total = sum(prefixes.values())
            return [
                p
                for p, c in sorted(prefixes.items(), key=lambda x: -x[1])
                if c / total > 0.1
            ][:top_n]
        return []

    def _extract_suffixes(self, series: pd.Series, top_n: int = 3) -> List[str]:
        """Extract common suffixes from values."""
        suffixes = {}
        for val in series.head(100):
            s = str(val)
            parts = re.split(r"[\s_\-]+", s)
            if len(parts) > 1:
                suffix = parts[-1]
                suffixes[suffix] = suffixes.get(suffix, 0) + 1

        if suffixes:
            total = sum(suffixes.values())
            return [
                s
                for s, c in sorted(suffixes.items(), key=lambda x: -x[1])
                if c / total > 0.1
            ][:top_n]
        return []

    def _update_stats(self, features: DatasetFeatures):
        """Update analyzer statistics."""
        self.stats["datasets_analyzed"] += 1
        self.stats["total_rows"] += features.total_rows

        domain = features.detected_domain
        self.stats["domains_detected"][domain] = (
            self.stats["domains_detected"].get(domain, 0) + 1
        )

        for pattern in ["currency", "id", "error"]:
            count = sum(
                1
                for pf in features.column_features.values()
                if pattern in pf.patterns_found
            )
            self.stats["patterns_found"][pattern] = (
                self.stats["patterns_found"].get(pattern, 0) + count
            )

    def get_stats(self) -> Dict[str, Any]:
        """Get analyzer statistics."""
        return self.stats

    def export_features(self, features_list: List[DatasetFeatures], output_path: str):
        """Export features to JSON file."""
        data = {
            "exported_at": datetime.now().isoformat(),
            "total_datasets": len(features_list),
            "features": [
                {
                    "filename": f.filename,
                    "filepath": f.filepath,
                    "domain": f.detected_domain,
                    "domain_confidence": f.domain_confidence,
                    "rows": f.total_rows,
                    "columns": f.total_columns,
                    "currency_columns": f.currency_columns,
                    "error_placeholders": f.error_placeholders,
                    "quality_issues": f.quality_issues,
                    "column_count": f.column_count,
                }
                for f in features_list
            ],
        }

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

        return output_path
