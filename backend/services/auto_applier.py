"""
Auto-Rule Application System
Automatically applies learned cleaning rules to datasets.
"""

import re
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path

try:
    from .rule_learner import RuleLearner
except ImportError:
    from rule_learner import RuleLearner


class AutoRuleApplier:
    """Automatically applies learned rules to datasets."""

    def __init__(
        self, rules_path: str = "D:/datacove_out/cleaning_reports/learned_rules.json"
    ):
        self.learner = RuleLearner(rules_path)
        self.action_registry = self._build_action_registry()

    def _build_action_registry(self) -> Dict[str, callable]:
        """Build registry of available cleaning actions."""
        return {
            "impute_missing": self._apply_impute_missing,
            "remove_duplicates": self._apply_remove_duplicates,
            "clean_phone": self._apply_clean_phone,
            "clean_city": self._apply_clean_city,
            "clean_state": self._apply_clean_state,
            "clean_email": self._apply_clean_email,
            "clean_status": self._apply_clean_status,
            "clean_gender": self._apply_clean_gender,
            "detect_anomalies": self._apply_detect_anomalies,
            "parse_dates": self._apply_parse_dates,
            "remove_special_chars": self._apply_remove_special_chars,
            "standardize_case": self._apply_standardize_case,
            "cap_outliers": self._apply_cap_outliers,
        }

    def apply_rules_to_dataset(
        self, df: pd.DataFrame, domain: str, min_confidence: float = 0.5
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Apply learned rules to a dataset.

        Args:
            df: Input DataFrame
            domain: Detected domain
            min_confidence: Minimum confidence threshold for rules

        Returns:
            Tuple of (cleaned DataFrame, report dict)
        """
        report = {
            "rules_applied": [],
            "cells_cleaned": 0,
            "changes": [],
        }

        rules = self.learner.get_rules_for_domain(domain)
        rules.extend(self.learner.get_rules_for_domain("general"))

        for rule in rules:
            if rule.confidence < min_confidence:
                continue

            column_pattern = rule.column_pattern
            if not column_pattern:
                continue

            matching_columns = self._find_matching_columns(df, column_pattern)

            for col in matching_columns:
                if col in df.columns:
                    action = rule.action
                    if action in self.action_registry:
                        result = self.action_registry[action](df, col)
                        if result["changed"]:
                            report["rules_applied"].append(
                                {
                                    "rule_id": rule.rule_id,
                                    "action": action,
                                    "column": col,
                                    "confidence": rule.confidence,
                                    "cells_affected": result["count"],
                                }
                            )
                            report["cells_cleaned"] += result["count"]
                            report["changes"].append(
                                {
                                    "column": col,
                                    "action": action,
                                    "before": result.get("before_sample"),
                                    "after": result.get("after_sample"),
                                }
                            )

        return df, report

    def _find_matching_columns(self, df: pd.DataFrame, pattern: str) -> List[str]:
        """Find columns matching a pattern."""
        matching = []
        pattern_map = {
            "email": r"email",
            "phone": r"phone|tel|mobile",
            "name": r"name|first|last|full",
            "address": r"address|street",
            "city": r"city",
            "state": r"state|province",
            "zip": r"zip|postal|pin",
            "date": r"date|time|dob|born",
            "price": r"price|cost|amount|value",
            "id": r"id|code|number",
            "status": r"status|state|flag",
            "gender": r"gender|sex",
            "url": r"url|link|website",
            "other": r".*",
        }

        regex = pattern_map.get(pattern, pattern)
        for col in df.columns:
            if re.search(regex, col.lower()):
                matching.append(col)
        return matching

    def _apply_impute_missing(self, df: pd.DataFrame, col: str) -> Dict[str, Any]:
        """Apply missing value imputation."""
        before_sample = df[col].head(3).tolist()
        missing_before = df[col].isna().sum()

        if pd.api.types.is_numeric_dtype(df[col]):
            median_val = df[col].median()
            df[col] = df[col].fillna(median_val)
        else:
            mode_val = df[col].mode().iloc[0] if not df[col].mode().empty else "Unknown"
            df[col] = df[col].fillna(mode_val)

        missing_after = df[col].isna().sum()
        changed = missing_after < missing_before

        return {
            "changed": changed,
            "count": missing_before - missing_after,
            "before_sample": before_sample,
            "after_sample": df[col].head(3).tolist(),
        }

    def _apply_remove_duplicates(self, df: pd.DataFrame, col: str) -> Dict[str, Any]:
        """Apply duplicate removal."""
        before_len = len(df)
        df.drop_duplicates(inplace=True)
        changed = len(df) < before_len

        return {
            "changed": changed,
            "count": before_len - len(df),
            "before_sample": [],
            "after_sample": [],
        }

    def _apply_clean_phone(self, df: pd.DataFrame, col: str) -> Dict[str, Any]:
        """Clean phone numbers."""
        before_sample = df[col].dropna().head(3).tolist()
        count_before = len(df[df[col].notna()])

        def clean_phone(val):
            if pd.isna(val):
                return val
            val = str(val).strip()
            val = re.sub(r"[^\d+]", "", val)
            if len(val) == 10:
                return f"({val[:3]}) {val[3:6]}-{val[6:]}"
            elif len(val) == 11 and val[0] == "1":
                return f"+1 ({val[1:4]}) {val[4:7]}-{val[7:]}"
            return val

        df[col] = df[col].apply(clean_phone)
        count_after = len(df[df[col].notna()])

        return {
            "changed": True,
            "count": count_before,
            "before_sample": before_sample,
            "after_sample": df[col].dropna().head(3).tolist(),
        }

    def _apply_clean_city(self, df: pd.DataFrame, col: str) -> Dict[str, Any]:
        """Clean city names."""
        before_sample = df[col].dropna().head(3).tolist()

        def clean_city(val):
            if pd.isna(val):
                return val
            val = str(val).strip().title()
            val = re.sub(r"\s+", " ", val)
            return val

        df[col] = df[col].apply(clean_city)

        return {
            "changed": True,
            "count": len(df[df[col].notna()]),
            "before_sample": before_sample,
            "after_sample": df[col].dropna().head(3).tolist(),
        }

    def _apply_clean_state(self, df: pd.DataFrame, col: str) -> Dict[str, Any]:
        """Clean state names."""
        before_sample = df[col].dropna().head(3).tolist()

        df[col] = df[col].apply(lambda x: str(x).strip().title() if pd.notna(x) else x)

        return {
            "changed": True,
            "count": len(df[df[col].notna()]),
            "before_sample": before_sample,
            "after_sample": df[col].dropna().head(3).tolist(),
        }

    def _apply_clean_email(self, df: pd.DataFrame, col: str) -> Dict[str, Any]:
        """Clean email addresses."""
        before_sample = df[col].dropna().head(3).tolist()

        def clean_email(val):
            if pd.isna(val):
                return val
            val = str(val).strip().lower()
            if "@" in val and "." in val.split("@")[1]:
                return val
            return val

        df[col] = df[col].apply(clean_email)

        return {
            "changed": True,
            "count": len(df[df[col].notna()]),
            "before_sample": before_sample,
            "after_sample": df[col].dropna().head(3).tolist(),
        }

    def _apply_clean_status(self, df: pd.DataFrame, col: str) -> Dict[str, Any]:
        """Clean status values."""
        before_sample = df[col].dropna().head(3).tolist()

        df[col] = df[col].apply(lambda x: str(x).strip().title() if pd.notna(x) else x)

        return {
            "changed": True,
            "count": len(df[df[col].notna()]),
            "before_sample": before_sample,
            "after_sample": df[col].dropna().head(3).tolist(),
        }

    def _apply_clean_gender(self, df: pd.DataFrame, col: str) -> Dict[str, Any]:
        """Standardize gender values."""
        before_sample = df[col].dropna().head(5).tolist()

        def clean_gender(val):
            if pd.isna(val):
                return val
            val = str(val).strip().lower()
            if val in ["m", "male", "man", "masculine"]:
                return "Male"
            elif val in ["f", "female", "woman", "feminine"]:
                return "Female"
            elif val in ["n", "non-binary", "other"]:
                return "Non-binary"
            return val

        df[col] = df[col].apply(clean_gender)

        return {
            "changed": True,
            "count": len(df[df[col].notna()]),
            "before_sample": before_sample,
            "after_sample": df[col].dropna().head(5).tolist(),
        }

    def _apply_detect_anomalies(self, df: pd.DataFrame, col: str) -> Dict[str, Any]:
        """Detect anomalies (mark only, don't remove)."""
        anomalies = []

        if pd.api.types.is_numeric_dtype(df[col]):
            Q1 = df[col].quantile(0.25)
            Q3 = df[col].quantile(0.75)
            IQR = Q3 - Q1
            lower = Q1 - 1.5 * IQR
            upper = Q3 + 1.5 * IQR
            anomalies = df[(df[col] < lower) | (df[col] > upper)].index.tolist()

        return {
            "changed": False,
            "count": len(anomalies),
            "before_sample": [],
            "after_sample": [],
        }

    def _apply_parse_dates(self, df: pd.DataFrame, col: str) -> Dict[str, Any]:
        """Parse and standardize dates."""
        before_sample = df[col].dropna().head(3).tolist()
        count_before = len(df[df[col].notna()])

        df[col] = pd.to_datetime(df[col], errors="coerce")
        df[col] = df[col].dt.strftime("%Y-%m-%d")

        count_after = len(df[df[col].notna()])

        return {
            "changed": count_after != count_before,
            "count": count_after,
            "before_sample": before_sample,
            "after_sample": df[col].dropna().head(3).tolist(),
        }

    def _apply_remove_special_chars(self, df: pd.DataFrame, col: str) -> Dict[str, Any]:
        """Remove special characters."""
        before_sample = df[col].dropna().head(3).tolist()

        def remove_special(val):
            if pd.isna(val):
                return val
            return re.sub(r"[@#$%^&*!]", "", str(val))

        df[col] = df[col].apply(remove_special)

        return {
            "changed": True,
            "count": len(df[df[col].notna()]),
            "before_sample": before_sample,
            "after_sample": df[col].dropna().head(3).tolist(),
        }

    def _apply_standardize_case(self, df: pd.DataFrame, col: str) -> Dict[str, Any]:
        """Standardize text case."""
        before_sample = df[col].dropna().head(3).tolist()

        def standardize(val):
            if pd.isna(val):
                return val
            return str(val).strip().title()

        df[col] = df[col].apply(standardize)

        return {
            "changed": True,
            "count": len(df[df[col].notna()]),
            "before_sample": before_sample,
            "after_sample": df[col].dropna().head(3).tolist(),
        }

    def _apply_cap_outliers(self, df: pd.DataFrame, col: str) -> Dict[str, Any]:
        """Cap outliers at IQR bounds."""
        if not pd.api.types.is_numeric_dtype(df[col]):
            return {
                "changed": False,
                "count": 0,
                "before_sample": [],
                "after_sample": [],
            }

        before_sample = df[col].head(3).tolist()
        Q1 = df[col].quantile(0.25)
        Q3 = df[col].quantile(0.75)
        IQR = Q3 - Q1
        lower = Q1 - 1.5 * IQR
        upper = Q3 + 1.5 * IQR

        capped_before = ((df[col] < lower) | (df[col] > upper)).sum()
        df[col] = df[col].clip(lower=lower, upper=upper)

        return {
            "changed": capped_before > 0,
            "count": capped_before,
            "before_sample": before_sample,
            "after_sample": df[col].head(3).tolist(),
        }


def auto_clean_dataset(
    df: pd.DataFrame,
    domain: str,
    rules_path: str = "D:/datacove_out/cleaning_reports/learned_rules.json",
    min_confidence: float = 0.5,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Automatically clean a dataset using learned rules.

    Args:
        df: Input DataFrame
        domain: Detected domain
        rules_path: Path to learned rules file
        min_confidence: Minimum confidence threshold

    Returns:
        Tuple of (cleaned DataFrame, report dict)
    """
    applier = AutoRuleApplier(rules_path)
    return applier.apply_rules_to_dataset(df, domain, min_confidence)
