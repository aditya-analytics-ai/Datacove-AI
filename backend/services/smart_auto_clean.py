"""
Smart Auto-Clean - Intelligent cleaning based on dataset analysis.
Combines profiling, domain detection, and schema inference for
targeted cleaning operations.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import re

import numpy as np
import pandas as pd

from services.dataset_profiler import DatasetProfiler, DatasetProfile, ColumnProfile
from services.domain_strategies import SmartAutoCleaner, CleaningStep
from services.schema_inferrer import SchemaInferrer
from services.cleaning_engine import apply_transformation


@dataclass
class AppliedStep:
    action: str
    params: Dict[str, Any]
    reason: str
    before_rows: int
    after_rows: int
    cells_changed: int
    affected_columns: List[str]
    error: Optional[str] = None
    skipped: bool = False


@dataclass
class AutoCleanResult:
    df: pd.DataFrame
    original_profile: DatasetProfile
    steps: List[AppliedStep]
    summary: str
    quality_improvement: float
    recommended_next_steps: List[Dict[str, Any]]


class SmartAutoClean:
    """
    Intelligent auto-cleaning with domain awareness.
    """

    def __init__(self):
        self.profiler = DatasetProfiler()
        self.cleaner = SmartAutoCleaner()
        self.schema_inferrer = SchemaInferrer()

    def clean(
        self, df: pd.DataFrame, intensity: str = "standard", dry_run: bool = False
    ) -> AutoCleanResult:
        """
        Clean a dataset using intelligent domain-aware strategies.

        Args:
            df: Input DataFrame
            intensity: "gentle" (basic cleaning only), "standard" (recommended),
                      "aggressive" (comprehensive cleaning)
            dry_run: If True, return steps without applying them

        Returns:
            AutoCleanResult with cleaned data and detailed report
        """
        original_df = df.copy()
        original_rows = len(df)

        original_profile = self.profiler.profile(df)

        steps = self._plan_steps(df, original_profile, intensity)

        if dry_run:
            return AutoCleanResult(
                df=df,
                original_profile=original_profile,
                steps=steps,
                summary=f"Planned {len(steps)} cleaning steps for {original_profile.domain_type} data",
                quality_improvement=0,
                recommended_next_steps=[],
            )

        df_cleaned, applied_steps = self._apply_steps(df, steps, original_profile)

        final_profile = self.profiler.profile(df_cleaned)
        quality_improvement = (
            final_profile.quality_score - original_profile.quality_score
        )

        summary = self._generate_summary(
            original_rows,
            len(df_cleaned),
            applied_steps,
            original_profile,
            final_profile,
        )

        recommended_next = self._get_recommended_next_steps(
            df_cleaned, final_profile, applied_steps
        )

        return AutoCleanResult(
            df=df_cleaned,
            original_profile=original_profile,
            steps=applied_steps,
            summary=summary,
            quality_improvement=quality_improvement,
            recommended_next_steps=recommended_next,
        )

    def _plan_steps(
        self, df: pd.DataFrame, profile: DatasetProfile, intensity: str
    ) -> List[AppliedStep]:
        """Plan cleaning steps based on profile and intensity."""
        planned_steps = []

        steps_from_strategy = self.cleaner.get_cleaning_steps(df, profile)

        for step in steps_from_strategy:
            if step.action == "remove_duplicates":
                planned_steps.append(
                    AppliedStep(
                        action=step.action,
                        params=step.params,
                        reason=step.reason,
                        before_rows=len(df),
                        after_rows=len(df),
                        cells_changed=0,
                        affected_columns=[],
                        skipped=True,
                    )
                )

            elif step.action in [
                "trim_whitespace",
                "standardise_capitalisation",
                "normalise_categories",
            ]:
                planned_steps.append(
                    AppliedStep(
                        action=step.action,
                        params=step.params,
                        reason=step.reason,
                        before_rows=len(df),
                        after_rows=len(df),
                        cells_changed=0,
                        affected_columns=self._get_target_columns(df, step.params),
                        skipped=True,
                    )
                )

            elif step.action == "parse_currency":
                currency_cols = self._detect_currency_columns(df)
                if currency_cols:
                    planned_steps.append(
                        AppliedStep(
                            action=step.action,
                            params={"column": currency_cols[0]},
                            reason=step.reason,
                            before_rows=len(df),
                            after_rows=len(df),
                            cells_changed=0,
                            affected_columns=currency_cols,
                            skipped=True,
                        )
                    )

            elif step.action == "parse_number_formatted":
                formatted_cols = self._detect_formatted_number_columns(df)
                if formatted_cols:
                    planned_steps.append(
                        AppliedStep(
                            action=step.action,
                            params={"column": formatted_cols[0]},
                            reason=step.reason,
                            before_rows=len(df),
                            after_rows=len(df),
                            cells_changed=0,
                            affected_columns=formatted_cols,
                            skipped=True,
                        )
                    )

            elif step.action == "standardise_dates":
                date_cols = profile.date_columns[:3]
                if date_cols:
                    planned_steps.append(
                        AppliedStep(
                            action=step.action,
                            params={"column": date_cols[0]},
                            reason=step.reason,
                            before_rows=len(df),
                            after_rows=len(df),
                            cells_changed=0,
                            affected_columns=date_cols,
                            skipped=True,
                        )
                    )

            elif step.action == "fill_missing":
                missing_cols = [
                    c for c, p in profile.column_profiles.items() if p.null_pct > 0.05
                ]
                if missing_cols:
                    planned_steps.append(
                        AppliedStep(
                            action=step.action,
                            params={"column": missing_cols[0], "strategy": "auto"},
                            reason=step.reason,
                            before_rows=len(df),
                            after_rows=len(df),
                            cells_changed=0,
                            affected_columns=missing_cols,
                            skipped=True,
                        )
                    )

            elif step.action == "clip_outliers":
                numeric_cols = profile.numeric_columns[:2]
                if numeric_cols:
                    planned_steps.append(
                        AppliedStep(
                            action=step.action,
                            params={"column": numeric_cols[0]},
                            reason=step.reason,
                            before_rows=len(df),
                            after_rows=len(df),
                            cells_changed=0,
                            affected_columns=numeric_cols,
                            skipped=True,
                        )
                    )

            elif step.action == "validate_email":
                email_cols = [
                    c
                    for c, p in profile.column_profiles.items()
                    if p.detected_category == "email"
                ]
                if email_cols:
                    planned_steps.append(
                        AppliedStep(
                            action=step.action,
                            params={"column": email_cols[0]},
                            reason=step.reason,
                            before_rows=len(df),
                            after_rows=len(df),
                            cells_changed=0,
                            affected_columns=email_cols,
                            skipped=True,
                        )
                    )

            elif step.action == "validate_phone":
                phone_cols = [
                    c
                    for c, p in profile.column_profiles.items()
                    if p.detected_category == "phone"
                ]
                if phone_cols:
                    planned_steps.append(
                        AppliedStep(
                            action=step.action,
                            params={"column": phone_cols[0]},
                            reason=step.reason,
                            before_rows=len(df),
                            after_rows=len(df),
                            cells_changed=0,
                            affected_columns=phone_cols,
                            skipped=True,
                        )
                    )

            elif step.action == "validate_postal_code":
                postal_cols = [
                    c
                    for c, p in profile.column_profiles.items()
                    if "zip" in c.lower() or "postal" in c.lower()
                ]
                if postal_cols:
                    planned_steps.append(
                        AppliedStep(
                            action=step.action,
                            params={"column": postal_cols[0]},
                            reason=step.reason,
                            before_rows=len(df),
                            after_rows=len(df),
                            cells_changed=0,
                            affected_columns=postal_cols,
                            skipped=True,
                        )
                    )

            else:
                planned_steps.append(
                    AppliedStep(
                        action=step.action,
                        params=step.params,
                        reason=step.reason,
                        before_rows=len(df),
                        after_rows=len(df),
                        cells_changed=0,
                        affected_columns=self._get_target_columns(df, step.params),
                        skipped=True,
                    )
                )

        return planned_steps

    def _apply_steps(
        self, df: pd.DataFrame, steps: List[AppliedStep], profile: DatasetProfile
    ) -> Tuple[pd.DataFrame, List[AppliedStep]]:
        """Apply cleaning steps to the dataframe."""
        from services.cleaning_engine import apply_transformation

        applied_steps = []

        currency_cols = self._detect_currency_columns(df)
        for col in currency_cols:
            try:
                df_before = df.copy()
                df = self._parse_currency_column(df, col)
                cells_changed = self._count_changed_cells(df_before, df, col)
                if cells_changed > 0:
                    applied_steps.append(
                        AppliedStep(
                            action="parse_currency",
                            params={"column": col},
                            reason="Extracted numeric values from currency strings",
                            before_rows=len(df),
                            after_rows=len(df),
                            cells_changed=cells_changed,
                            affected_columns=[col],
                        )
                    )
            except Exception as e:
                applied_steps.append(
                    AppliedStep(
                        action="parse_currency",
                        params={"column": col},
                        reason="Extracted numeric values from currency strings",
                        before_rows=len(df),
                        after_rows=len(df),
                        cells_changed=0,
                        affected_columns=[col],
                        error=str(e),
                    )
                )

        formatted_cols = self._detect_formatted_number_columns(df)
        for col in formatted_cols:
            try:
                df_before = df.copy()
                df = self._parse_formatted_number(df, col)
                cells_changed = self._count_changed_cells(df_before, df, col)
                if cells_changed > 0:
                    applied_steps.append(
                        AppliedStep(
                            action="parse_number_formatted",
                            params={"column": col},
                            reason="Standardized number format",
                            before_rows=len(df),
                            after_rows=len(df),
                            cells_changed=cells_changed,
                            affected_columns=[col],
                        )
                    )
            except Exception as e:
                applied_steps.append(
                    AppliedStep(
                        action="parse_number_formatted",
                        params={"column": col},
                        reason="Standardized number format",
                        before_rows=len(df),
                        after_rows=len(df),
                        cells_changed=0,
                        affected_columns=[col],
                        error=str(e),
                    )
                )

        date_cols = profile.date_columns
        for col in date_cols[:3]:
            try:
                df_before = df.copy()
                df = apply_transformation(
                    df, "standardise_mixed_dates", {"column": col}
                )
                cells_changed = self._count_changed_cells(df_before, df, col)
                if cells_changed > 0:
                    applied_steps.append(
                        AppliedStep(
                            action="standardise_dates",
                            params={"column": col},
                            reason="Standardized date format to ISO",
                            before_rows=len(df),
                            after_rows=len(df),
                            cells_changed=cells_changed,
                            affected_columns=[col],
                        )
                    )
            except Exception as e:
                applied_steps.append(
                    AppliedStep(
                        action="standardise_dates",
                        params={"column": col},
                        reason="Standardized date format",
                        before_rows=len(df),
                        after_rows=len(df),
                        cells_changed=0,
                        affected_columns=[col],
                        error=str(e),
                    )
                )

        try:
            rows_before = len(df)
            df = apply_transformation(df, "remove_duplicates", {})
            rows_removed = rows_before - len(df)
            if rows_removed > 0:
                applied_steps.append(
                    AppliedStep(
                        action="remove_duplicates",
                        params={},
                        reason="Removed duplicate rows",
                        before_rows=rows_before,
                        after_rows=len(df),
                        cells_changed=0,
                        affected_columns=[],
                    )
                )
        except Exception as e:
            applied_steps.append(
                AppliedStep(
                    action="remove_duplicates",
                    params={},
                    reason="Removed duplicate rows",
                    before_rows=len(df),
                    after_rows=len(df),
                    cells_changed=0,
                    affected_columns=[],
                    error=str(e),
                )
            )

        try:
            df_before = df.copy()
            df = apply_transformation(df, "trim_whitespace", {})
            text_cols = profile.text_columns
            total_changed = sum(
                self._count_changed_cells(df_before, df, c) for c in text_cols
            )
            if total_changed > 0:
                applied_steps.append(
                    AppliedStep(
                        action="trim_whitespace",
                        params={},
                        reason="Trimmed leading/trailing whitespace",
                        before_rows=len(df),
                        after_rows=len(df),
                        cells_changed=total_changed,
                        affected_columns=text_cols,
                    )
                )
        except Exception as e:
            applied_steps.append(
                AppliedStep(
                    action="trim_whitespace",
                    params={},
                    reason="Trimmed whitespace",
                    before_rows=len(df),
                    after_rows=len(df),
                    cells_changed=0,
                    affected_columns=[],
                    error=str(e),
                )
            )

        try:
            df_before = df.copy()
            df = apply_transformation(
                df, "standardise_capitalisation", {"strategy": "title"}
            )
            text_cols = profile.text_columns
            total_changed = sum(
                self._count_changed_cells(df_before, df, c) for c in text_cols
            )
            if total_changed > 0:
                applied_steps.append(
                    AppliedStep(
                        action="standardise_capitalisation",
                        params={"strategy": "title"},
                        reason="Standardized text capitalization to title case",
                        before_rows=len(df),
                        after_rows=len(df),
                        cells_changed=total_changed,
                        affected_columns=text_cols,
                    )
                )
        except Exception as e:
            applied_steps.append(
                AppliedStep(
                    action="standardise_capitalisation",
                    params={"strategy": "title"},
                    reason="Standardized capitalization",
                    before_rows=len(df),
                    after_rows=len(df),
                    cells_changed=0,
                    affected_columns=[],
                    error=str(e),
                )
            )

        cat_cols = [
            c
            for c, p in profile.column_profiles.items()
            if p.is_categorical or p.cardinality == "medium"
        ]
        if cat_cols:
            try:
                df_before = df.copy()
                df = apply_transformation(
                    df, "normalise_categories", {"columns": cat_cols}
                )
                total_changed = sum(
                    self._count_changed_cells(df_before, df, c) for c in cat_cols
                )
                if total_changed > 0:
                    applied_steps.append(
                        AppliedStep(
                            action="normalise_categories",
                            params={"columns": cat_cols},
                            reason="Normalized inconsistent category labels",
                            before_rows=len(df),
                            after_rows=len(df),
                            cells_changed=total_changed,
                            affected_columns=cat_cols,
                        )
                    )
            except Exception as e:
                applied_steps.append(
                    AppliedStep(
                        action="normalise_categories",
                        params={"columns": cat_cols},
                        reason="Normalized categories",
                        before_rows=len(df),
                        after_rows=len(df),
                        cells_changed=0,
                        affected_columns=cat_cols,
                        error=str(e),
                    )
                )

        missing_cols = [
            c for c, p in profile.column_profiles.items() if 0.05 < p.null_pct < 0.5
        ]
        for col in missing_cols[:3]:
            try:
                df_before = df.copy()
                strategy = "mean" if profile.column_profiles[col].is_numeric else "mode"
                df = apply_transformation(
                    df, "fill_missing", {"column": col, "strategy": strategy}
                )
                cells_changed = self._count_changed_cells(df_before, df, col)
                if cells_changed > 0:
                    applied_steps.append(
                        AppliedStep(
                            action="fill_missing",
                            params={"column": col, "strategy": strategy},
                            reason=f"Filled missing values using {strategy}",
                            before_rows=len(df),
                            after_rows=len(df),
                            cells_changed=cells_changed,
                            affected_columns=[col],
                        )
                    )
            except Exception as e:
                applied_steps.append(
                    AppliedStep(
                        action="fill_missing",
                        params={"column": col, "strategy": "mode"},
                        reason="Filled missing values",
                        before_rows=len(df),
                        after_rows=len(df),
                        cells_changed=0,
                        affected_columns=[col],
                        error=str(e),
                    )
                )

        if profile.domain_type == "hr":
            hr_steps = self._apply_hr_specific_cleaning(df, profile)
            applied_steps.extend(hr_steps)

            for step in hr_steps:
                if step.action == "clip_outliers":
                    df = apply_transformation(df, "clip_outliers", step.params)

        error_steps = self._clean_error_placeholders(df, profile)
        applied_steps.extend(error_steps)
        for step in error_steps:
            if step.action == "replace_errors":
                for col in step.affected_columns:
                    df[col] = df[col].replace(step.params.get("to_replace", []), np.nan)

        index_cols = self._detect_index_columns(df)
        if index_cols:
            try:
                df = df.drop(columns=index_cols)
                applied_steps.append(
                    AppliedStep(
                        action="drop_column",
                        params={"columns": index_cols},
                        reason=f"Removed unnecessary index column(s): {', '.join(index_cols)}",
                        before_rows=len(df) + len(index_cols),
                        after_rows=len(df),
                        cells_changed=0,
                        affected_columns=index_cols,
                    )
                )
            except Exception:
                pass

        special_char_steps = self._clean_special_characters(df)
        applied_steps.extend(special_char_steps)
        for step in special_char_steps:
            if step.action == "clean_special_chars":
                df[step.affected_columns[0]] = step.params.get("cleaned_col")

        return df, applied_steps

    def _clean_error_placeholders(self, df: pd.DataFrame, profile) -> List[AppliedStep]:
        """Detect and clean common error placeholders like ERROR, UNKNOWN, N/A, etc."""
        steps = []

        ERROR_VALUES = {
            "error",
            "unknown",
            "n/a",
            "na",
            "null",
            "none",
            "-",
            "--",
            "na",
            "n/a",
            "#n/a",
            "#error",
            "#value",
        }

        for col in df.columns:
            if df[col].dtype == object or pd.api.types.is_string_dtype(df[col]):
                str_col = df[col].dropna().astype(str).str.lower()
                sample_vals = str_col.head(100).tolist()
                error_count = sum(1 for v in sample_vals if v in ERROR_VALUES)

                if error_count >= 3:
                    to_replace = [
                        v
                        for v in df[col].dropna().unique()
                        if str(v).lower().strip() in ERROR_VALUES
                    ]
                    if to_replace:
                        try:
                            original_count = df[col].isna().sum()
                            df[col] = df[col].replace(to_replace, np.nan)
                            new_count = df[col].isna().sum()
                            cells_cleaned = new_count - original_count

                            if cells_cleaned > 0:
                                steps.append(
                                    AppliedStep(
                                        action="replace_errors",
                                        params={
                                            "column": col,
                                            "to_replace": to_replace,
                                        },
                                        reason=f"Replaced error placeholders ({', '.join(to_replace)}) with empty",
                                        before_rows=len(df),
                                        after_rows=len(df),
                                        cells_changed=cells_cleaned,
                                        affected_columns=[col],
                                    )
                                )
                        except Exception:
                            pass

        return steps

    def _apply_hr_specific_cleaning(
        self, df: pd.DataFrame, profile
    ) -> List[AppliedStep]:
        """Apply HR-specific cleaning for employee/salary data."""
        steps = []
        salary_cols = [
            c
            for c in profile.numeric_columns
            if "salary" in c.lower() or "pay" in c.lower()
        ]

        for col in salary_cols[:2]:
            try:
                original_max = df[col].max()
                df_clipped = apply_transformation(
                    df.copy(),
                    "clip_outliers",
                    {"column": col, "method": "iqr", "iqr_factor": 3.0},
                )
                clipped_max = df_clipped[col].max()

                if clipped_max < original_max:
                    df = df_clipped
                    cells_changed = (df[col] != df_clipped[col]).sum()
                    steps.append(
                        AppliedStep(
                            action="clip_outliers",
                            params={"column": col, "iqr_factor": 3.0},
                            reason=f"Capped salary outliers using IQR (3x) for {col}",
                            before_rows=len(df),
                            after_rows=len(df),
                            cells_changed=int(cells_changed),
                            affected_columns=[col],
                        )
                    )
            except Exception:
                pass

        return steps

    def _detect_currency_columns(self, df: pd.DataFrame) -> List[str]:
        """Detect columns with currency values."""
        currency_cols = []
        for col in df.columns:
            sample = df[col].dropna().astype(str).head(50)
            if len(sample) == 0:
                continue

            currency_symbols = ["$", "€", "£", "¥", "₹", "₽"]
            has_currency = any(
                any(sym in str(v) for sym in currency_symbols) for v in sample
            )

            if has_currency:
                currency_cols.append(col)

        return currency_cols

    def _detect_formatted_number_columns(self, df: pd.DataFrame) -> List[str]:
        """Detect columns with formatted numbers."""
        formatted_cols = []
        for col in df.columns:
            if df[col].dtype == object:
                sample = df[col].dropna().astype(str).head(50)
                if len(sample) == 0:
                    continue

                comma_separated = sum(
                    1 for v in sample if re.search(r"\d,\d{3}", str(v))
                )
                if comma_separated > len(sample) * 0.5:
                    formatted_cols.append(col)

        return formatted_cols

    def _detect_index_columns(self, df: pd.DataFrame) -> List[str]:
        """Detect columns that are sequential indices (1,2,3... or 0,1,2...)."""
        index_cols = []

        for col in df.columns:
            if df[col].dtype in [int, "int64", "int32"] and len(df) > 10:
                vals = df[col].dropna().astype(int).tolist()
                expected = list(range(1, len(vals) + 1))
                if vals == expected:
                    if col.lower() in [
                        "rownumber",
                        "index",
                        "id",
                        "row",
                        "no",
                        "number",
                    ]:
                        index_cols.append(col)

        return index_cols

    def _clean_special_characters(self, df: pd.DataFrame) -> List[AppliedStep]:
        """Detect and clean special characters like ? in text fields."""
        steps = []

        SPECIAL_CHARS = ["?", "�", "\x00", "\ufffd"]

        for col in df.columns:
            if df[col].dtype == object or pd.api.types.is_string_dtype(df[col]):
                sample = df[col].dropna().astype(str)
                special_count = sum(
                    1 for v in sample if any(sc in str(v) for sc in SPECIAL_CHARS)
                )

                if special_count > 0 and special_count / len(sample) > 0.001:
                    original = df[col].copy()
                    cleaned = df[col].str.replace(r"[?]+", "", regex=True)
                    cleaned = cleaned.str.strip()

                    cells_changed = (cleaned != original).sum()

                    if cells_changed > 0:
                        df[col] = cleaned
                        steps.append(
                            AppliedStep(
                                action="clean_special_chars",
                                params={"column": col, "cleaned_col": cleaned},
                                reason=f"Removed special characters (?) from {col}",
                                before_rows=len(df),
                                after_rows=len(df),
                                cells_changed=int(cells_changed),
                                affected_columns=[col],
                            )
                        )

        return steps

    def _parse_currency_column(self, df: pd.DataFrame, col: str) -> pd.DataFrame:
        """Extract numeric values from currency strings."""
        currency_symbols = ["$", "€", "£", "¥", "₹", "₽"]

        def extract_currency(val):
            if pd.isna(val):
                return val
            s = str(val)
            for sym in currency_symbols:
                s = s.replace(sym, "")
            s = s.replace(",", "")
            s = s.strip()
            try:
                return float(s)
            except ValueError:
                return np.nan

        df[col] = df[col].apply(extract_currency)
        return df

    def _parse_formatted_number(self, df: pd.DataFrame, col: str) -> pd.DataFrame:
        """Parse formatted number strings."""

        def parse_num(val):
            if pd.isna(val):
                return val
            s = str(val)

            if re.search(r"\d\.\d{3}", s):
                s = s.replace(".", "")
                s = s.replace(",", ".")
            else:
                s = s.replace(",", "")

            try:
                return float(s)
            except ValueError:
                return val

        df[col] = df[col].apply(parse_num)
        return df

    def _get_target_columns(self, df: pd.DataFrame, params: Dict) -> List[str]:
        """Get target columns from params."""
        if "column" in params:
            return [params["column"]]
        if "columns" in params:
            return params["columns"]
        if "column1" in params:
            return [params["column1"], params.get("column2", "")]
        return []

    def _count_changed_cells(
        self, df_before: pd.DataFrame, df_after: pd.DataFrame, col: str
    ) -> int:
        """Count number of cells that changed."""
        if col not in df_before.columns or col not in df_after.columns:
            return 0

        before = df_before[col].fillna("").astype(str).reset_index(drop=True)
        after = df_after[col].fillna("").astype(str).reset_index(drop=True)

        n = min(len(before), len(after))
        return int((before.iloc[:n] != after.iloc[:n]).sum())

    def _generate_summary(
        self,
        original_rows: int,
        final_rows: int,
        steps: List[AppliedStep],
        original_profile: DatasetProfile,
        final_profile: DatasetProfile,
    ) -> str:
        """Generate a human-readable summary."""
        parts = []

        rows_removed = original_rows - final_rows
        if rows_removed > 0:
            parts.append(f"removed {rows_removed:,} duplicate row(s)")

        total_cells = sum(s.cells_changed for s in steps)
        if total_cells > 0:
            parts.append(f"cleaned {total_cells:,} cell(s)")

        successful = len([s for s in steps if not s.error])
        total = len(steps)

        if not parts:
            return (
                f"Auto-clean complete - dataset was already clean. "
                f"Applied {successful}/{total} steps successfully."
            )

        summary = "Auto-clean complete: " + ", ".join(parts) + "."
        summary += f" Applied {successful}/{total} cleaning operations."
        summary += f" Detected as {original_profile.domain_type} data (confidence: {original_profile.domain_confidence:.0%})."

        return summary

    def _get_recommended_next_steps(
        self,
        df: pd.DataFrame,
        profile: DatasetProfile,
        applied_steps: List[AppliedStep],
    ) -> List[Dict[str, Any]]:
        """Get recommended next steps based on current state."""
        recommendations = []

        if profile.quality_score < 80:
            recommendations.append(
                {
                    "action": "Review remaining quality issues",
                    "reason": f"Quality score is {profile.quality_score:.0%}",
                    "priority": "high",
                }
            )

        for col, col_profile in profile.column_profiles.items():
            if col_profile.null_pct > 0.1 and col not in [
                s.affected_columns for s in applied_steps if s.action == "fill_missing"
            ]:
                recommendations.append(
                    {
                        "action": "fill_missing",
                        "params": {"column": col, "strategy": "auto"},
                        "reason": f"Column has {col_profile.null_pct:.1%} missing values",
                        "priority": "medium",
                    }
                )

        if profile.column_profiles:
            recommendations.append(
                {
                    "action": "Apply type suggestions",
                    "reason": "Some columns may benefit from type conversion",
                    "priority": "low",
                }
            )

        return recommendations[:5]


def smart_auto_clean(
    df: pd.DataFrame, intensity: str = "standard", dry_run: bool = False
) -> AutoCleanResult:
    """
    Convenience function for smart auto-cleaning.

    Args:
        df: Input DataFrame
        intensity: "gentle", "standard", or "aggressive"
        dry_run: If True, return planned steps without applying

    Returns:
        AutoCleanResult with cleaned data and report
    """
    cleaner = SmartAutoClean()
    return cleaner.clean(df, intensity=intensity, dry_run=dry_run)
