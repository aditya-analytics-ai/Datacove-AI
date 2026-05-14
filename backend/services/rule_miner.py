"""
Rule Miner - Learns cleaning patterns from datasets and generates rules.
Extracts rules based on detected patterns, column names, and value characteristics.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

import pandas as pd
import numpy as np

from services.dataset_analyzer import DatasetFeatures, ColumnFeatures


@dataclass
class CleaningRule:
    rule_id: str
    name: str
    description: str

    trigger_type: str
    trigger_pattern: str

    action: str
    params: Dict[str, Any]

    applicable_domains: List[str] = field(default_factory=list)
    applicable_columns: List[str] = field(default_factory=list)

    confidence: float = 0.5
    support: int = 0
    times_applied: int = 0
    times_succeeded: int = 0

    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_used: Optional[str] = None

    enabled: bool = True
    auto_apply: bool = False

    examples: List[Dict[str, Any]] = field(default_factory=list)


class RuleMiner:
    """
    Mines cleaning rules from analyzed datasets.
    Generates rules based on patterns, domains, and column characteristics.
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

    COLUMN_RULE_TEMPLATES = {
        "currency": {
            "action": "parse_currency",
            "params": {"strip_symbols": True, "convert_to": "float"},
            "description": "Extract numeric value from currency string",
        },
        "percentage": {
            "action": "parse_percentage",
            "params": {"strip_percent": True},
            "description": "Extract numeric value from percentage string",
        },
        "special_chars": {
            "action": "clean_special_characters",
            "params": {"chars_to_remove": ["?", "�", "\ufffd"]},
            "description": "Remove special characters from text",
        },
        "whitespace": {
            "action": "trim_whitespace",
            "params": {},
            "description": "Trim leading/trailing whitespace",
        },
        "case": {
            "action": "standardise_capitalisation",
            "params": {"strategy": "title"},
            "description": "Standardize text capitalization",
        },
        "duplicates": {
            "action": "remove_duplicates",
            "params": {},
            "description": "Remove duplicate rows",
        },
    }

    VALUE_PATTERN_RULES = {
        r"^\d{4}-\d{2}-\d{2}": {"action": "standardise_dates", "format": "%Y-%m-%d"},
        r"^\d{2}/\d{2}/\d{4}": {"action": "standardise_dates", "format": "detect"},
        r"^\$[\d,]+\.?\d*": {"action": "parse_currency", "strip_symbol": "$"},
        r"^€[\d,]+\.?\d*": {"action": "parse_currency", "strip_symbol": "€"},
        r"^₹[\d,]+\.?\d*": {"action": "parse_currency", "strip_symbol": "₹"},
        r"^\d+%$": {"action": "parse_percentage"},
        r"^[\d,]+\.?\d*$": {"action": "parse_number_formatted"},
    }

    def __init__(self):
        self.rules: List[CleaningRule] = []
        self.rule_counter = 0
        self.pattern_rules: Dict[str, List[CleaningRule]] = defaultdict(list)
        self.domain_rules: Dict[str, List[CleaningRule]] = defaultdict(list)
        self.column_rules: Dict[str, List[CleaningRule]] = defaultdict(list)

    def mine_rules(self, features_list: List[DatasetFeatures]) -> List[CleaningRule]:
        """Mine rules from a list of analyzed datasets."""
        new_rules = []

        new_rules.extend(self._mine_column_rules(features_list))
        new_rules.extend(self._mine_pattern_rules(features_list))
        new_rules.extend(self._mine_domain_rules(features_list))
        new_rules.extend(self._mine_error_rules(features_list))

        self.rules.extend(new_rules)
        self._index_rules()

        return new_rules

    def _mine_column_rules(
        self, features_list: List[DatasetFeatures]
    ) -> List[CleaningRule]:
        """Generate rules based on column patterns and names."""
        rules = []
        column_rule_counts = defaultdict(int)

        for features in features_list:
            for col_name, col_feat in features.column_features.items():
                col_lower = col_name.lower()

                if "price" in col_lower or "cost" in col_lower or "amount" in col_lower:
                    rule = self._create_column_rule(
                        name=f"Parse {col_name} as currency",
                        description=f"Extract numeric values from {col_name}",
                        col_name=col_name,
                        rule_type="currency",
                        confidence=0.9 if features.currency_columns else 0.7,
                        features=features,
                    )
                    if rule:
                        column_rule_counts[f"currency_{col_lower}"] += 1
                        rules.append(rule)

                if any(kw in col_lower for kw in ["email", "mail"]):
                    rule = self._create_column_rule(
                        name=f"Validate {col_name} as email",
                        description=f"Validate email format in {col_name}",
                        col_name=col_name,
                        rule_type="email",
                        confidence=0.95,
                        features=features,
                    )
                    if rule:
                        rules.append(rule)

                if any(kw in col_lower for kw in ["phone", "tel", "mobile", "cell"]):
                    rule = self._create_column_rule(
                        name=f"Normalize {col_name} phone",
                        description=f"Standardize phone number format",
                        col_name=col_name,
                        rule_type="phone",
                        confidence=0.9,
                        features=features,
                    )
                    if rule:
                        rules.append(rule)

                if any(
                    kw in col_lower
                    for kw in ["salary", "balance", "revenue", "income", "expense"]
                ):
                    rule = self._create_column_rule(
                        name=f"Clean numeric values in {col_name}",
                        description=f"Parse and validate numeric values",
                        col_name=col_name,
                        rule_type="numeric",
                        confidence=0.85,
                        features=features,
                    )
                    if rule:
                        rules.append(rule)

                if col_feat.cardinality == "low" and not col_feat.is_numeric:
                    rule = self._create_column_rule(
                        name=f"Normalize categories in {col_name}",
                        description=f"Standardize category labels",
                        col_name=col_name,
                        rule_type="categorical",
                        confidence=0.8,
                        features=features,
                    )
                    if rule:
                        rules.append(rule)

                if any(kw in col_lower for kw in ["date", "created", "updated", "dob"]):
                    rule = self._create_column_rule(
                        name=f"Standardize {col_name} dates",
                        description=f"Convert dates to standard format",
                        col_name=col_name,
                        rule_type="date",
                        confidence=0.9,
                        features=features,
                    )
                    if rule:
                        rules.append(rule)

        return rules

    def _mine_pattern_rules(
        self, features_list: List[DatasetFeatures]
    ) -> List[CleaningRule]:
        """Generate rules based on value patterns."""
        rules = []

        for features in features_list:
            for col_name, col_feat in features.column_features.items():
                if not col_feat.sample_values:
                    continue

                sample_str = str(col_feat.sample_values[0])

                for pattern, rule_def in self.VALUE_PATTERN_RULES.items():
                    if re.search(pattern, sample_str):
                        rule = CleaningRule(
                            rule_id=self._generate_rule_id(),
                            name=f"Apply {rule_def['action']} to {col_name}",
                            description=f"Match pattern {pattern} in {col_name}",
                            trigger_type="value_pattern",
                            trigger_pattern=pattern,
                            action=rule_def["action"],
                            params=rule_def,
                            applicable_domains=[features.detected_domain],
                            applicable_columns=[col_name],
                            confidence=0.85,
                            support=1,
                            examples=[{"column": col_name, "sample": sample_str}],
                        )
                        rules.append(rule)

        return rules

    def _mine_domain_rules(
        self, features_list: List[DatasetFeatures]
    ) -> List[CleaningRule]:
        """Generate domain-specific rules."""
        rules = []

        domain_rule_map = {
            "hr": [
                {
                    "name": "Cap salary outliers",
                    "action": "clip_outliers",
                    "params": {"iqr_factor": 3.0},
                },
                {
                    "name": "Normalize titles",
                    "action": "normalise_categories",
                    "params": {},
                },
            ],
            "sales": [
                {
                    "name": "Parse all currency values",
                    "action": "parse_currency",
                    "params": {},
                },
                {
                    "name": "Standardize dates",
                    "action": "standardise_dates",
                    "params": {},
                },
            ],
            "customer": [
                {"name": "Validate emails", "action": "validate_email", "params": {}},
                {
                    "name": "Normalize phone numbers",
                    "action": "normalize_phone",
                    "params": {},
                },
            ],
            "ecommerce": [
                {
                    "name": "Parse product prices",
                    "action": "parse_currency",
                    "params": {},
                },
                {
                    "name": "Clean ratings",
                    "action": "validate_range",
                    "params": {"min": 1, "max": 5},
                },
            ],
        }

        for features in features_list:
            domain = features.detected_domain
            if domain in domain_rule_map:
                for rule_def in domain_rule_map[domain]:
                    rule = CleaningRule(
                        rule_id=self._generate_rule_id(),
                        name=rule_def["name"],
                        description=f"Domain-specific rule for {domain} data",
                        trigger_type="domain",
                        trigger_pattern=domain,
                        action=rule_def["action"],
                        params=rule_def["params"],
                        applicable_domains=[domain],
                        confidence=0.8,
                        support=1,
                    )
                    rules.append(rule)

        return rules

    def _mine_error_rules(
        self, features_list: List[DatasetFeatures]
    ) -> List[CleaningRule]:
        """Generate rules for error placeholder values."""
        rules = []

        for features in features_list:
            for col_name, errors in features.error_placeholders.items():
                if errors:
                    rule = CleaningRule(
                        rule_id=self._generate_rule_id(),
                        name=f"Replace error values in {col_name}",
                        description=f"Replace {errors} with NaN",
                        trigger_type="error_values",
                        trigger_pattern=str(errors),
                        action="replace_errors",
                        params={
                            "column": col_name,
                            "error_values": errors,
                            "replace_with": np.nan,
                        },
                        applicable_domains=[features.detected_domain],
                        applicable_columns=[col_name],
                        confidence=0.95,
                        support=1,
                        auto_apply=True,
                        examples=[{"column": col_name, "errors_found": errors}],
                    )
                    rules.append(rule)

        return rules

    def _create_column_rule(
        self,
        name: str,
        description: str,
        col_name: str,
        rule_type: str,
        confidence: float,
        features: DatasetFeatures,
    ) -> Optional[CleaningRule]:
        """Create a rule for a specific column."""
        if rule_type in self.COLUMN_RULE_TEMPLATES:
            template = self.COLUMN_RULE_TEMPLATES[rule_type]
            return CleaningRule(
                rule_id=self._generate_rule_id(),
                name=name,
                description=description,
                trigger_type="column_pattern",
                trigger_pattern=col_name.lower(),
                action=template["action"],
                params=template["params"],
                applicable_domains=[features.detected_domain],
                applicable_columns=[col_name],
                confidence=confidence,
                support=1,
                auto_apply=rule_type in ["currency", "whitespace", "special_chars"],
            )
        return None

    def _generate_rule_id(self) -> str:
        """Generate a unique rule ID."""
        self.rule_counter += 1
        return f"rule_{self.rule_counter}_{datetime.now().strftime('%Y%m%d')}"

    def _index_rules(self):
        """Index rules by type for fast lookup."""
        self.pattern_rules.clear()
        self.domain_rules.clear()
        self.column_rules.clear()

        for rule in self.rules:
            if rule.trigger_type == "value_pattern":
                self.pattern_rules[rule.trigger_pattern].append(rule)

            for domain in rule.applicable_domains:
                self.domain_rules[domain].append(rule)

            for col in rule.applicable_columns:
                self.column_rules[col.lower()].append(rule)

    def get_rules_for_dataset(self, features: DatasetFeatures) -> List[CleaningRule]:
        """Get applicable rules for a dataset."""
        applicable = []

        for rule in self.rules:
            if not rule.enabled:
                continue

            if features.detected_domain in rule.applicable_domains:
                applicable.append(rule)

            for col in features.column_features.keys():
                col_lower = col.lower()
                if any(
                    col_lower in rc.lower() or rc.lower() in col_lower
                    for rc in rule.applicable_columns
                ):
                    if rule not in applicable:
                        applicable.append(rule)

        applicable.sort(key=lambda r: (-r.confidence, -r.support, -r.auto_apply))

        return applicable

    def update_rule_stats(self, rule_id: str, success: bool):
        """Update rule statistics after application."""
        for rule in self.rules:
            if rule.rule_id == rule_id:
                rule.times_applied += 1
                if success:
                    rule.times_succeeded += 1
                rule.confidence = (
                    rule.times_succeeded / rule.times_applied
                    if rule.times_applied > 0
                    else 0.5
                )
                rule.last_used = datetime.now().isoformat()
                break

    def export_rules(self, filepath: str):
        """Export rules to JSON file."""
        import json

        data = {
            "exported_at": datetime.now().isoformat(),
            "total_rules": len(self.rules),
            "rules": [
                {
                    "rule_id": r.rule_id,
                    "name": r.name,
                    "description": r.description,
                    "trigger_type": r.trigger_type,
                    "trigger_pattern": r.trigger_pattern,
                    "action": r.action,
                    "params": r.params,
                    "applicable_domains": r.applicable_domains,
                    "applicable_columns": r.applicable_columns,
                    "confidence": r.confidence,
                    "support": r.support,
                    "times_applied": r.times_applied,
                    "times_succeeded": r.times_succeeded,
                    "auto_apply": r.auto_apply,
                    "enabled": r.enabled,
                }
                for r in self.rules
            ],
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)
        return filepath

    def import_rules(self, filepath: str):
        """Import rules from JSON file."""
        import json

        with open(filepath, "r") as f:
            data = json.load(f)

        for rule_data in data.get("rules", []):
            rule = CleaningRule(
                rule_id=rule_data["rule_id"],
                name=rule_data["name"],
                description=rule_data["description"],
                trigger_type=rule_data["trigger_type"],
                trigger_pattern=rule_data["trigger_pattern"],
                action=rule_data["action"],
                params=rule_data["params"],
                applicable_domains=rule_data.get("applicable_domains", []),
                applicable_columns=rule_data.get("applicable_columns", []),
                confidence=rule_data.get("confidence", 0.5),
                support=rule_data.get("support", 0),
                times_applied=rule_data.get("times_applied", 0),
                times_succeeded=rule_data.get("times_succeeded", 0),
                auto_apply=rule_data.get("auto_apply", False),
                enabled=rule_data.get("enabled", True),
            )
            self.rules.append(rule)

        self._index_rules()
        return len(self.rules)
