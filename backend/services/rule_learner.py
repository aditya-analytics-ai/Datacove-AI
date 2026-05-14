"""
Automated Rule Learning System
Learns new cleaning rules from successful dataset cleanings.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from collections import Counter
from datetime import datetime

from utils.logger import logger


@dataclass
class LearnedRule:
    rule_id: str
    pattern: str
    action: str
    confidence: float
    times_applied: int
    success_rate: float
    domain: Optional[str] = None
    column_pattern: Optional[str] = None
    created_at: str = ""
    last_used: str = ""
    description: str = ""


class RuleLearner:
    """Learns new cleaning rules from cleaning operations."""

    def __init__(
        self, rules_path: str = "D:/datacove_out/cleaning_reports/learned_rules.json"
    ):
        self.rules_path = Path(rules_path)
        self.rules: Dict[str, LearnedRule] = {}
        self.load_rules()

    def load_rules(self):
        """Load existing learned rules."""
        if self.rules_path.exists():
            with open(self.rules_path) as f:
                data = json.load(f)
                for rule_id, rule_data in data.items():
                    self.rules[rule_id] = LearnedRule(**rule_data)

    def save_rules(self):
        """Save learned rules to file."""
        self.rules_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.rules_path, "w") as f:
            rules_data = {k: asdict(v) for k, v in self.rules.items()}
            json.dump(rules_data, f, indent=2)

    def learn_from_report(self, report: Dict[str, Any]):
        """Learn rules from a cleaning report."""
        domain = report.get("detected_domain", "general")
        cleaning_steps = report.get("cleaning_steps", [])

        for step in cleaning_steps:
            action = step.get("action", "")
            column = step.get("column", "")
            cells_affected = step.get("cells_affected", 0)

            if not action or not column:
                continue

            rule_pattern = self._generate_pattern(column, action)

            if rule_pattern in self.rules:
                self.rules[rule_pattern].times_applied += 1
                self.rules[rule_pattern].last_used = datetime.now().isoformat()
            else:
                if isinstance(cells_affected, dict):
                    affected_count = cells_affected.get("count", 0)
                elif isinstance(cells_affected, (int, float)):
                    affected_count = int(cells_affected)
                elif isinstance(cells_affected, str):
                    try:
                        affected_count = int(cells_affected)
                    except ValueError:
                        affected_count = 0
                else:
                    affected_count = 0
                success_rate = 0.8 if affected_count > 0 else 0.5

                new_rule = LearnedRule(
                    rule_id=rule_pattern,
                    pattern=rule_pattern,
                    action=action,
                    confidence=0.5,
                    times_applied=1,
                    success_rate=success_rate,
                    domain=domain,
                    column_pattern=self._extract_column_pattern(column),
                    created_at=datetime.now().isoformat(),
                    last_used=datetime.now().isoformat(),
                    description=f"Learned from cleaning {column} with {action}",
                )
                self.rules[rule_pattern] = new_rule

        self._update_confidences()
        self.save_rules()

    def _generate_pattern(self, column: str, action: str) -> str:
        """Generate a unique pattern identifier."""
        col_clean = re.sub(r"[^a-zA-Z0-9]", "_", column.lower())
        return f"{action}:{col_clean}"

    def _extract_column_pattern(self, column: str) -> str:
        """Extract pattern from column name."""
        column_lower = column.lower()

        patterns = {
            "email": r"email",
            "phone": r"phone|tel|mobile",
            "name": r"name|first|last|full",
            "address": r"address|street",
            "city": r"city",
            "state": r"state",
            "zip": r"zip|postal|pin",
            "date": r"date|time|dob|born",
            "price": r"price|cost|amount",
            "id": r"id|code|number",
            "status": r"status|state|flag",
            "gender": r"gender|sex",
            "url": r"url|link|website",
        }

        for pattern_name, pattern_regex in patterns.items():
            if re.search(pattern_regex, column_lower):
                return pattern_name

        return "other"

    def _update_confidences(self):
        """Update confidence scores based on usage."""
        for rule in self.rules.values():
            if rule.times_applied >= 10:
                rule.confidence = min(0.95, 0.5 + rule.times_applied * 0.02)
            elif rule.times_applied >= 5:
                rule.confidence = min(0.85, 0.4 + rule.times_applied * 0.04)

            if rule.success_rate > 0.9:
                rule.confidence = min(0.99, rule.confidence + 0.1)

    def get_rules_for_domain(self, domain: str) -> List[LearnedRule]:
        """Get rules applicable to a domain."""
        domain_rules = [
            r for r in self.rules.values() if r.domain == domain or r.domain is None
        ]
        return sorted(domain_rules, key=lambda x: -x.confidence)

    def get_rules_for_column(self, column: str) -> List[LearnedRule]:
        """Get rules applicable to a column type."""
        col_pattern = self._extract_column_pattern(column)
        matching_rules = [
            r for r in self.rules.values() if r.column_pattern == col_pattern
        ]
        return sorted(matching_rules, key=lambda x: -x.confidence)

    def suggest_rules(self, domain: str, columns: List[str]) -> List[Dict[str, Any]]:
        """Suggest rules to apply based on domain and columns."""
        suggestions = []

        for col in columns:
            col_pattern = self._extract_column_pattern(col)
            rules = [r for r in self.rules.values() if r.column_pattern == col_pattern]

            if rules:
                best_rule = max(rules, key=lambda x: x.confidence)
                suggestions.append(
                    {
                        "column": col,
                        "suggested_action": best_rule.action,
                        "confidence": best_rule.confidence,
                        "based_on": best_rule.times_applied,
                    }
                )

        return suggestions

    def export_rules(self, output_path: str) -> str:
        """Export rules to a portable format."""
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        export_data = {
            "exported_at": datetime.now().isoformat(),
            "total_rules": len(self.rules),
            "rules": {k: asdict(v) for k, v in self.rules.items()},
        }

        with open(output, "w") as f:
            json.dump(export_data, f, indent=2)

        return str(output)

    def import_rules(self, input_path: str) -> int:
        """Import rules from a file."""
        with open(input_path) as f:
            data = json.load(f)

        imported = 0
        for rule_id, rule_data in data.get("rules", {}).items():
            if rule_id not in self.rules:
                self.rules[rule_id] = LearnedRule(**rule_data)
                imported += 1
            elif rule_data.get("times_applied", 0) > self.rules[rule_id].times_applied:
                self.rules[rule_id] = LearnedRule(**rule_data)
                imported += 1

        self.save_rules()
        return imported


class PatternMiner:
    """Mines patterns from datasets to suggest new rules."""

    def __init__(self):
        self.patterns = Counter()
        self.column_patterns = Counter()

    def analyze_dataset(self, df, domain: str = None) -> Dict[str, Any]:
        """Analyze a dataset for learnable patterns."""
        findings = {
            "domain": domain,
            "column_patterns": {},
            "suggested_rules": [],
        }

        for col in df.columns:
            col_lower = col.lower()
            values = df[col].dropna().astype(str)

            pattern_type = self._detect_pattern_type(values, col_lower)
            findings["column_patterns"][col] = pattern_type

            if pattern_type["type"] == "mixed":
                findings["suggested_rules"].append(
                    {
                        "column": col,
                        "suggested_action": "split_column",
                        "reason": f"Mixed data types: {pattern_type['types']}",
                        "priority": "high",
                    }
                )

            if pattern_type["type"] == "unstructured":
                findings["suggested_rules"].append(
                    {
                        "column": col,
                        "suggested_action": "standardize_format",
                        "reason": "Unstructured text data",
                        "priority": "medium",
                    }
                )

        return findings

    def _detect_pattern_type(self, values, col_name) -> Dict[str, Any]:
        """Detect the type of pattern in a column."""
        sample = values.head(100)

        types = {
            "numeric": sample.str.match(r"^-?\d+\.?\d*$").mean(),
            "date": sample.str.match(r"\d{4}[-/]\d{2}[-/]\d{2}").mean(),
            "email": sample.str.match(r"^[\w.-]+@[\w.-]+\.\w+$").mean(),
            "phone": sample.str.match(r"^[\d\s\-\(\)\+]+$").mean()
            if len(sample) > 0
            else 0,
        }

        max_type = max(types, key=types.get)
        max_ratio = types[max_type]

        if max_ratio < 0.5:
            return {"type": "unstructured", "confidence": 0.5}

        return {
            "type": max_type if max_ratio > 0.7 else "mixed",
            "confidence": max_ratio,
            "types": {k: v for k, v in types.items() if v > 0.1},
        }


def learn_from_reports(reports_folder: str = "D:/datacove_out/cleaning_reports"):
    """Learn rules from all cleaning reports."""
    learner = RuleLearner()

    for report_file in Path(reports_folder).glob("report_*.json"):
        try:
            with open(report_file) as f:
                report = json.load(f)
                learner.learn_from_report(report)
        except OSError as e:
            logger.warning(f"Error processing {report_file}: {e}")

    learner.save_rules()
    logger.info(f"Learned {len(learner.rules)} rules from {len(list(Path(reports_folder).glob('report_*.json')))} reports")
    return learner


def get_rule_suggestions(domain: str, columns: List[str]) -> List[Dict[str, Any]]:
    """Get suggested cleaning rules for a dataset."""
    learner = RuleLearner()
    return learner.suggest_rules(domain, columns)
