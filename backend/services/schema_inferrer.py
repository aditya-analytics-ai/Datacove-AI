"""
Enhanced schema inference for better type detection and handling.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class TypeSuggestion:
    column: str
    current_dtype: str
    suggested_dtype: str
    confidence: float
    reasoning: str
    sample_values: List[Any] = None
    conversion_params: Dict[str, Any] = None


@dataclass
class SchemaInferenceResult:
    suggestions: List[TypeSuggestion]
    quality_issues: List[str]
    mixed_type_columns: List[str]
    encoding_issues: List[str]


class TypeInferrer:
    """
    Intelligent type inference for mixed-type columns.
    """

    EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    PHONE_REGEX = re.compile(r"^[\d\s\-\(\)\+\.]{7,}$")
    URL_REGEX = re.compile(r"^https?://")
    CURRENCY_REGEX = re.compile(r"[$€£¥₹₽₿]?\s*[\d,]+\.?\d*")
    PERCENTAGE_REGEX = re.compile(r"^[\d.]+\s*%?$")

    DATE_PATTERNS = {
        "ISO": (r"^\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),
        "ISO_DATETIME": (r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", "%Y-%m-%d"),
        "US_SLASH": (r"^\d{1,2}/\d{1,2}/\d{4}", "%m/%d/%Y"),
        "EU_SLASH": (r"^\d{1,2}/\d{1,2}/\d{4}", "%d/%m/%Y"),
        "US_DASH": (r"^\d{1,2}-\d{1,2}-\d{4}", "%m-%d-%Y"),
        "EU_DASH": (r"^\d{1,2}-\d{1,2}-\d{4}", "%d-%m-%Y"),
        "TEXT_MONTH": (r"^\w{3,9}\s+\d{1,2},?\s+\d{4}", "%B %d, %Y"),
        "SHORT_TEXT_MONTH": (r"^\d{1,2}\s+\w{3}\s+\d{4}", "%d %b %Y"),
    }

    BOOLEAN_TRUE = {"true", "yes", "1", "y", "on", "t", "enabled", "active", "correct"}
    BOOLEAN_FALSE = {
        "false",
        "no",
        "0",
        "n",
        "off",
        "f",
        "disabled",
        "inactive",
        "incorrect",
    }

    @classmethod
    def infer_type(
        cls, series: pd.Series, sample_size: int = 500
    ) -> Tuple[str, float, Dict]:
        """
        Infer the best data type for a column.
        Returns (suggested_dtype, confidence, conversion_params)
        """
        sample = (
            series.dropna().astype(str).sample(min(sample_size, len(series.dropna())))
        )

        if len(sample) == 0:
            return "string", 1.0, {}

        type_scores = {
            "int": cls._score_int(sample),
            "float": cls._score_float(sample),
            "bool": cls._score_bool(sample),
            "date": cls._score_date(sample),
            "email": cls._score_email(sample),
            "phone": cls._score_phone(sample),
            "url": cls._score_url(sample),
            "currency": cls._score_currency(sample),
            "category": cls._score_category(sample),
            "string": cls._score_string(sample),
        }

        best_type = max(type_scores, key=type_scores.get)
        confidence = type_scores[best_type]

        params = {}
        if best_type == "date":
            params = cls._detect_date_format(sample)
        elif best_type == "bool":
            params = cls._detect_bool_mapping(sample)

        return best_type, confidence, params

    @classmethod
    def _score_int(cls, sample: pd.Series) -> float:
        """Score how well the sample fits integer type."""
        try:
            valid = 0
            for val in sample:
                s = str(val).strip()
                if re.match(r"^-?\d+$", s):
                    num = int(s)
                    if -(2**31) <= num <= 2**31 - 1:
                        valid += 1
            return valid / len(sample) if len(sample) > 0 else 0
        except:
            return 0

    @classmethod
    def _score_float(cls, sample: pd.Series) -> float:
        """Score how well the sample fits float type."""
        try:
            valid = 0
            for val in sample:
                s = str(val).strip().replace(",", "")
                if re.match(r"^-?\d+\.?\d*$", s):
                    valid += 1
            return valid / len(sample) if len(sample) > 0 else 0
        except:
            return 0

    @classmethod
    def _score_bool(cls, sample: pd.Series) -> float:
        """Score how well the sample fits boolean type."""
        try:
            valid = 0
            for val in sample:
                s = str(val).strip().lower()
                if s in cls.BOOLEAN_TRUE or s in cls.BOOLEAN_FALSE:
                    valid += 1
            return valid / len(sample) if len(sample) > 0 else 0
        except:
            return 0

    @classmethod
    def _score_date(cls, sample: pd.Series) -> float:
        """Score how well the sample fits date type."""
        try:
            valid = 0
            for val in sample:
                s = str(val).strip()
                for pattern_name, (pattern, _) in cls.DATE_PATTERNS.items():
                    if re.match(pattern, s):
                        valid += 1
                        break
                else:
                    try:
                        pd.to_datetime(s)
                        valid += 1
                    except:
                        pass
            return valid / len(sample) if len(sample) > 0 else 0
        except:
            return 0

    @classmethod
    def _score_email(cls, sample: pd.Series) -> float:
        """Score how well the sample fits email type."""
        try:
            valid = 0
            for val in sample:
                s = str(val).strip()
                if cls.EMAIL_REGEX.match(s):
                    valid += 1
            return valid / len(sample) if len(sample) > 0 else 0
        except:
            return 0

    @classmethod
    def _score_phone(cls, sample: pd.Series) -> float:
        """Score how well the sample fits phone type."""
        try:
            valid = 0
            for val in sample:
                s = str(val).strip()
                if cls.PHONE_REGEX.match(s) and len(re.sub(r"\D", "", s)) >= 7:
                    valid += 1
            return valid / len(sample) if len(sample) > 0 else 0
        except:
            return 0

    @classmethod
    def _score_url(cls, sample: pd.Series) -> float:
        """Score how well the sample fits URL type."""
        try:
            valid = 0
            for val in sample:
                s = str(val).strip()
                if cls.URL_REGEX.match(s):
                    valid += 1
            return valid / len(sample) if len(sample) > 0 else 0
        except:
            return 0

    @classmethod
    def _score_currency(cls, sample: pd.Series) -> float:
        """Score how well the sample fits currency type."""
        try:
            valid = 0
            for val in sample:
                s = str(val).strip()
                if cls.CURRENCY_REGEX.match(s) or cls.PERCENTAGE_REGEX.match(s):
                    valid += 1
            return valid / len(sample) if len(sample) > 0 else 0
        except:
            return 0

    @classmethod
    def _score_category(cls, sample: pd.Series) -> float:
        """Score how well the sample fits categorical type."""
        try:
            unique_ratio = sample.nunique() / len(sample)
            if unique_ratio < 0.5:
                return 0.8
            return 0.2
        except:
            return 0

    @classmethod
    def _score_string(cls, sample: pd.Series) -> float:
        """Score how well the sample fits string type (baseline)."""
        return 0.5

    @classmethod
    def _detect_date_format(cls, sample: pd.Series) -> Dict:
        """Detect the date format used in the sample."""
        for val in sample.head(20):
            s = str(val).strip()
            for pattern_name, (pattern, fmt) in cls.DATE_PATTERNS.items():
                if re.match(pattern, s):
                    return {"format": fmt, "pattern_type": pattern_name}
            try:
                parsed = pd.to_datetime(s)
                if not pd.isna(parsed):
                    return {"format": "%Y-%m-%d", "pattern_type": "auto"}
            except:
                pass
        return {"format": "%Y-%m-%d", "pattern_type": "default"}

    @classmethod
    def _detect_bool_mapping(cls, sample: pd.Series) -> Dict:
        """Detect the mapping used for boolean values."""
        mapping = {}
        for val in sample.unique():
            s = str(val).strip().lower()
            if s in cls.BOOLEAN_TRUE:
                mapping[s] = True
            elif s in cls.BOOLEAN_FALSE:
                mapping[s] = False
        return {"mapping": mapping}


class SchemaInferrer:
    """
    Enhanced schema inference with type conversion suggestions.
    """

    TYPE_REASONING = {
        "int": "Column contains only whole numbers",
        "float": "Column contains decimal numbers",
        "bool": "Column contains binary yes/no values",
        "date": "Column contains date/time values",
        "email": "Column contains email addresses",
        "phone": "Column contains phone numbers",
        "url": "Column contains URLs",
        "currency": "Column contains monetary values",
        "category": "Column has limited unique values",
        "string": "Column contains general text",
    }

    def __init__(self):
        self.type_inferrer = TypeInferrer()

    def infer_schema(
        self, df: pd.DataFrame, sample_size: int = 500
    ) -> SchemaInferenceResult:
        """
        Infer the schema for all columns and suggest type conversions.
        """
        suggestions = []
        quality_issues = []
        mixed_type_columns = []
        encoding_issues = []

        for col in df.columns:
            series = df[col]

            inferred_type, confidence, params = self.type_inferrer.infer_type(
                series, sample_size
            )

            current_dtype = str(series.dtype)

            if inferred_type != "string" and confidence > 0.7:
                suggestions.append(
                    TypeSuggestion(
                        column=col,
                        current_dtype=current_dtype,
                        suggested_dtype=inferred_type,
                        confidence=confidence,
                        reasoning=self.TYPE_REASONING.get(
                            inferred_type, "Type inference"
                        ),
                        sample_values=series.dropna().head(5).tolist(),
                        conversion_params=params,
                    )
                )

            if self._has_mixed_types(series):
                mixed_type_columns.append(col)
                quality_issues.append(f"Column '{col}' contains mixed data types")

            if series.isnull().mean() > 0.5:
                quality_issues.append(
                    f"Column '{col}' has {series.isnull().mean():.1%} missing values"
                )

        return SchemaInferenceResult(
            suggestions=suggestions,
            quality_issues=quality_issues,
            mixed_type_columns=mixed_type_columns,
            encoding_issues=encoding_issues,
        )

    def _has_mixed_types(self, series: pd.Series, sample_size: int = 100) -> bool:
        """Check if a column contains mixed data types."""
        sample = (
            series.dropna().astype(str).sample(min(sample_size, len(series.dropna())))
        )

        types_found = set()
        for val in sample:
            s = str(val).strip()

            if self.type_inferrer.EMAIL_REGEX.match(s):
                types_found.add("email")
            elif self.type_inferrer.PHONE_REGEX.match(s):
                types_found.add("phone")
            elif self.type_inferrer.URL_REGEX.match(s):
                types_found.add("url")
            elif re.match(r"^-?\d+\.?\d*$", s):
                types_found.add("number")
            elif re.match(r"^\d{4}-\d{2}-\d{2}", s):
                types_found.add("date")
            else:
                types_found.add("text")

        return len(types_found) > 2

    def get_conversion_suggestions(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Get a list of type conversion suggestions for API response."""
        result = self.infer_schema(df)

        suggestions = []
        for suggestion in result.suggestions:
            suggestions.append(
                {
                    "column": suggestion.column,
                    "current_type": suggestion.current_dtype,
                    "suggested_type": suggestion.suggested_dtype,
                    "confidence": round(suggestion.confidence * 100, 1),
                    "reason": suggestion.reasoning,
                    "sample_values": suggestion.sample_values,
                    "params": suggestion.conversion_params or {},
                }
            )

        return suggestions


def infer_schema(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Convenience function for schema inference."""
    inferrer = SchemaInferrer()
    return inferrer.get_conversion_suggestions(df)
