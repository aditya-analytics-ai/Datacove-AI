"""
Batch Processor & Learning Engine
Processes folders of datasets, applies rules, and learns from results.
"""

from __future__ import annotations

import os
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

import pandas as pd
import numpy as np

from services.dataset_analyzer import DatasetAnalyzer, DatasetFeatures
from services.rule_miner import RuleMiner, CleaningRule
from services.smart_auto_clean import SmartAutoClean
from utils.logger import logger


@dataclass
class ProcessingResult:
    filename: str
    filepath: str

    detected_domain: str
    domain_confidence: float

    rows_before: int
    rows_after: int
    cells_cleaned: int = 0

    rules_applied: List[str] = field(default_factory=list)
    rules_succeeded: List[str] = field(default_factory=list)
    rules_failed: List[str] = field(default_factory=list)

    errors: List[str] = field(default_factory=list)

    processing_time: float = 0.0

    success: bool = True


@dataclass
class LearningSession:
    session_id: str
    folder_path: str
    started_at: str
    completed_at: Optional[str] = None

    datasets_found: int = 0
    datasets_processed: int = 0
    datasets_failed: int = 0

    results: List[ProcessingResult] = field(default_factory=list)

    new_rules_generated: int = 0
    total_cells_cleaned: int = 0

    domains_detected: Dict[str, int] = field(default_factory=dict)
    issues_found: Dict[str, int] = field(default_factory=dict)


class BatchProcessor:
    """
    Processes folders of datasets with learned rules.
    Tracks progress and learns from each processing.
    """

    def __init__(self, storage_path: str = "data/learning"):
        self.analyzer = DatasetAnalyzer()
        self.miner = RuleMiner()
        self.cleaner = SmartAutoClean()

        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.current_session: Optional[LearningSession] = None

        self._load_existing_rules()

    def _load_existing_rules(self):
        """Load existing rules from storage."""
        rules_file = self.storage_path / "rules.json"
        if rules_file.exists():
            try:
                count = self.miner.import_rules(str(rules_file))
                logger.info(f"Loaded {count} existing rules")
            except OSError as e:
                logger.warning(f"Could not load existing rules: {e}")

    def _save_rules(self):
        """Save rules to storage."""
        rules_file = self.storage_path / "rules.json"
        self.miner.export_rules(str(rules_file))

    def process_folder(
        self,
        folder_path: str,
        output_folder: Optional[str] = None,
        apply_cleaning: bool = True,
        learn_rules: bool = True,
        export_results: bool = True,
    ) -> LearningSession:
        """Process all datasets in a folder."""

        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.current_session = LearningSession(
            session_id=session_id,
            folder_path=folder_path,
            started_at=datetime.now().isoformat(),
        )

        logger.info(f"Starting session {session_id}")
        logger.info(f"Folder: {folder_path}")

        features_list = self.analyzer.analyze_folder(folder_path)
        self.current_session.datasets_found = len(features_list)

        print(f"Found {len(features_list)} datasets")

        if learn_rules:
            print("Mining rules from datasets...")
            new_rules = self.miner.mine_rules(features_list)
            self.current_session.new_rules_generated = len(new_rules)
            print(f"Generated {len(new_rules)} new rules")
            self._save_rules()

        if apply_cleaning:
            for features in features_list:
                result = self._process_single_dataset(features, output_folder)
                self.current_session.results.append(result)

                if result.success:
                    self.current_session.datasets_processed += 1
                else:
                    self.current_session.datasets_failed += 1

                self.current_session.total_cells_cleaned += result.cells_cleaned
                self.current_session.domains_detected[result.detected_domain] = (
                    self.current_session.domains_detected.get(result.detected_domain, 0)
                    + 1
                )

        self.current_session.completed_at = datetime.now().isoformat()

        if export_results:
            self._export_session_results()

        self._print_summary()

        return self.current_session

    def _process_single_dataset(
        self, features: DatasetFeatures, output_folder: Optional[str] = None
    ) -> ProcessingResult:
        """Process a single dataset."""
        import time

        start_time = time.time()

        result = ProcessingResult(
            filename=features.filename,
            filepath=features.filepath,
            detected_domain=features.detected_domain,
            domain_confidence=features.domain_confidence,
            rows_before=features.total_rows,
            rows_after=features.total_rows,
        )

        try:
            df = self._load_dataset(features.filepath)
            if df is None:
                raise ValueError("Could not load dataset")

            smart_result = self.cleaner.clean(df)

            result.rows_after = len(smart_result.df)
            result.cells_cleaned = sum(
                s.cells_changed for s in smart_result.steps if not s.skipped
            )
            result.rules_applied = [
                s.action for s in smart_result.steps if not s.skipped
            ]
            result.rules_succeeded = [
                s.action for s in smart_result.steps if not s.skipped and not s.error
            ]

            if output_folder:
                output_path = Path(output_folder) / features.filename
                smart_result.df.to_csv(output_path, index=False)

            for step in smart_result.steps:
                if step.error:
                    result.errors.append(f"{step.action}: {step.error}")
                    result.rules_failed.append(step.action)

        except Exception as e:
            result.success = False
            result.errors.append(str(e))

        result.processing_time = time.time() - start_time

        return result

    def _load_dataset(self, filepath: str) -> Optional[pd.DataFrame]:
        """Load dataset based on extension."""
        ext = Path(filepath).suffix.lower()

        try:
            if ext == ".csv":
                return pd.read_csv(filepath)
            elif ext in [".xlsx", ".xls"]:
                return pd.read_excel(filepath)
            elif ext == ".json":
                return pd.read_json(filepath)
        except Exception:
            return None

        return None

    def _export_session_results(self):
        """Export session results to JSON."""
        if not self.current_session:
            return

        results_file = (
            self.storage_path / f"session_{self.current_session.session_id}.json"
        )

        def convert_value(v):
            if isinstance(v, (np.int64, np.int32)):
                return int(v)
            if isinstance(v, (np.float64, np.float32)):
                return float(v)
            return v

        data = {
            "session": {
                "session_id": self.current_session.session_id,
                "folder_path": self.current_session.folder_path,
                "started_at": self.current_session.started_at,
                "completed_at": self.current_session.completed_at,
                "datasets_found": convert_value(self.current_session.datasets_found),
                "datasets_processed": convert_value(
                    self.current_session.datasets_processed
                ),
                "datasets_failed": convert_value(self.current_session.datasets_failed),
                "new_rules_generated": convert_value(
                    self.current_session.new_rules_generated
                ),
                "total_cells_cleaned": convert_value(
                    self.current_session.total_cells_cleaned
                ),
                "domains_detected": {
                    k: convert_value(v)
                    for k, v in self.current_session.domains_detected.items()
                },
            },
            "results": [
                {
                    "filename": r.filename,
                    "domain": r.detected_domain,
                    "domain_confidence": float(r.domain_confidence),
                    "rows_before": convert_value(r.rows_before),
                    "rows_after": convert_value(r.rows_after),
                    "cells_cleaned": convert_value(r.cells_cleaned),
                    "rules_applied": r.rules_applied,
                    "success": r.success,
                    "errors": r.errors,
                }
                for r in self.current_session.results
            ],
        }

        with open(results_file, "w") as f:
            json.dump(data, f, indent=2)

        print(f"Results saved to {results_file}")

    def _print_summary(self):
        """Print session summary."""
        if not self.current_session:
            return

        s = self.current_session

        print("\n" + "=" * 60)
        print("PROCESSING SUMMARY")
        print("=" * 60)
        print(f"Datasets found: {s.datasets_found}")
        print(f"Datasets processed: {s.datasets_processed}")
        print(f"Datasets failed: {s.datasets_failed}")
        print(f"Total cells cleaned: {s.total_cells_cleaned:,}")
        print(f"New rules generated: {s.new_rules_generated}")
        print(f"\nDomains detected:")
        for domain, count in sorted(s.domains_detected.items(), key=lambda x: -x[1]):
            print(f"  {domain}: {count}")
        print("=" * 60)

    def get_stats(self) -> Dict[str, Any]:
        """Get processor statistics."""
        return {
            "total_rules": len(self.miner.rules),
            "auto_apply_rules": len([r for r in self.miner.rules if r.auto_apply]),
            "rules_by_domain": {
                domain: len(rules) for domain, rules in self.miner.domain_rules.items()
            },
            "sessions_processed": len(list(self.storage_path.glob("session_*.json"))),
        }

    def suggest_new_rules(
        self, features_list: List[DatasetFeatures]
    ) -> List[CleaningRule]:
        """Suggest new rules based on dataset analysis."""
        suggestions = []

        pattern_counts = defaultdict(int)

        for features in features_list:
            for col_feat in features.column_features.values():
                for pattern in col_feat.patterns_found:
                    pattern_counts[pattern] += 1

        for pattern, count in pattern_counts.items():
            if count >= 3:
                suggestions.append(
                    {
                        "suggestion": f"Auto-apply {pattern} cleaning",
                        "confidence": min(0.95, count / 10),
                        "support": count,
                        "reason": f"Found in {count} datasets",
                    }
                )

        return suggestions


class LearningEngine:
    """
    Continuously learns from cleaning results to improve rules.
    """

    def __init__(self, processor: BatchProcessor):
        self.processor = processor
        self.learned_patterns = defaultdict(int)
        self.failed_patterns = defaultdict(int)

    def record_result(self, result: ProcessingResult):
        """Record a processing result for learning."""
        for rule in result.rules_applied:
            if rule in result.rules_succeeded:
                self.learned_patterns[rule] += 1
            if rule in result.rules_failed:
                self.failed_patterns[rule] += 1

    def get_improvements(self) -> List[Dict[str, Any]]:
        """Get suggested rule improvements."""
        improvements = []

        for rule, success_count in self.learned_patterns.items():
            fail_count = self.failed_patterns.get(rule, 0)
            total = success_count + fail_count

            if total >= 5:
                success_rate = success_count / total

                if success_rate < 0.7:
                    improvements.append(
                        {
                            "rule": rule,
                            "success_rate": success_rate,
                            "suggestion": "Consider disabling this rule",
                            "confidence": 0.8,
                        }
                    )
                elif success_rate > 0.95:
                    improvements.append(
                        {
                            "rule": rule,
                            "success_rate": success_rate,
                            "suggestion": "Make this rule auto-apply",
                            "confidence": 0.9,
                        }
                    )

        return improvements

    def export_learnings(self, filepath: str):
        """Export learned patterns."""
        data = {
            "learned_patterns": dict(self.learned_patterns),
            "failed_patterns": dict(self.failed_patterns),
            "improvements": self.get_improvements(),
            "exported_at": datetime.now().isoformat(),
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        return filepath
