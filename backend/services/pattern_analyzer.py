"""
Pattern Analyzer - Analyzes cleaning reports to identify common patterns.
"""

import json
import os
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any

from utils.logger import logger


class PatternAnalyzer:
    def __init__(self, reports_folder: str):
        self.reports_folder = reports_folder
        self.reports = []
        self.patterns = defaultdict(list)
        self.domain_patterns = defaultdict(lambda: defaultdict(list))
        self.column_issues = defaultdict(int)
        self.cleaning_effectiveness = defaultdict(list)

    def load_reports(self):
        """Load all JSON reports."""
        for filepath in Path(self.reports_folder).glob("report_*.json"):
            with open(filepath) as f:
                self.reports.append(json.load(f))
        logger.info(f"Loaded {len(self.reports)} reports")

    def print_analysis(self):
        """Print all analysis results."""
        print("\n=== DOMAIN DISTRIBUTION ===")
        for report in self.reports:
            domain_counts[report["detected_domain"]] += 1

        print("\n=== DOMAIN DISTRIBUTION ===")
        for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
            pct = count / len(self.reports) * 100
            print(f"  {domain}: {count} ({pct:.1f}%)")

        return dict(domain_counts)

    def analyze_quality_scores(self):
        """Analyze quality score patterns."""
        initial_scores = [r["initial_quality_score"] for r in self.reports]
        final_scores = [r["final_quality_score"] for r in self.reports]

        print("\n=== QUALITY SCORE ANALYSIS ===")
        print(
            f"  Initial Quality - Avg: {sum(initial_scores) / len(initial_scores):.1f}%"
        )
        print(f"  Final Quality - Avg: {sum(final_scores) / len(final_scores):.1f}%")

        low_quality = [r for r in self.reports if r["final_quality_score"] < 70]
        print(f"  Low Quality Datasets (<70%): {len(low_quality)}")

        return {
            "initial_avg": sum(initial_scores) / len(initial_scores),
            "final_avg": sum(final_scores) / len(final_scores),
            "low_quality_count": len(low_quality),
        }

    def analyze_issues(self):
        """Analyze common issues found."""
        issue_types = defaultdict(int)
        issue_columns = defaultdict(int)

        for report in self.reports:
            for issue in report.get("issues_found", []):
                issue_types[issue["issue_type"]] += 1
                issue_columns[issue["column"]] += 1

        print("\n=== COMMON ISSUES ===")
        for issue, count in sorted(issue_types.items(), key=lambda x: -x[1])[:10]:
            print(f"  {issue}: {count} occurrences")

        print("\n=== MOST PROBLEMATIC COLUMNS ===")
        for col, count in sorted(issue_columns.items(), key=lambda x: -x[1])[:10]:
            print(f"  {col}: {count} datasets")

        return dict(issue_types)

    def analyze_cleaning_steps(self):
        """Analyze cleaning steps performed."""
        step_counts = defaultdict(int)
        step_by_domain = defaultdict(lambda: defaultdict(int))

        for report in self.reports:
            domain = report["detected_domain"]
            for step in report.get("cleaning_steps", []):
                action = step["action"]
                step_counts[action] += 1
                step_by_domain[domain][action] += 1

        print("\n=== CLEANING ACTIONS ===")
        for action, count in sorted(step_counts.items(), key=lambda x: -x[1]):
            print(f"  {action}: {count} times")

        return {"counts": dict(step_counts), "by_domain": dict(step_by_domain)}

    def analyze_columns(self):
        """Analyze column types and patterns."""
        column_types = defaultdict(list)

        for report in self.reports:
            for insight in report.get("column_insights", []):
                col_type = insight["detected_type"]
                column = insight["column"]
                column_types[col_type].append(column)

        print("\n=== COLUMN TYPES DETECTED ===")
        for col_type, columns in sorted(column_types.items(), key=lambda x: -len(x[1])):
            unique_cols = set(columns)
            print(
                f"  {col_type}: {len(columns)} occurrences ({len(unique_cols)} unique columns)"
            )

        return {
            k: {"total": len(v), "unique": len(set(v))} for k, v in column_types.items()
        }

    def analyze_dtypes(self):
        """Analyze data type distributions."""
        dtype_counts = defaultdict(int)

        for report in self.reports:
            for dtype, count in report.get("dtypes_found", {}).items():
                dtype_counts[dtype] += count

        print("\n=== DATA TYPES ===")
        for dtype, count in sorted(dtype_counts.items(), key=lambda x: -x[1]):
            print(f"  {dtype}: {count} columns")

        return dict(dtype_counts)

    def analyze_null_patterns(self):
        """Analyze null value patterns."""
        null_columns = defaultdict(int)

        for report in self.reports:
            for col, count in report.get("null_counts", {}).items():
                if count > 0:
                    null_columns[col] += 1

        print("\n=== COLUMNS WITH NULLS ===")
        for col, count in sorted(null_columns.items(), key=lambda x: -x[1])[:10]:
            print(f"  {col}: {count} datasets")

        return dict(null_columns)

    def find_common_patterns(self):
        """Find common patterns across datasets."""
        patterns = defaultdict(int)

        for report in self.reports:
            for pattern in report.get("patterns_found", []):
                patterns[pattern] += 1

        print("\n=== COMMON PATTERNS ===")
        for pattern, count in sorted(patterns.items(), key=lambda x: -x[1])[:15]:
            print(f"  {pattern}: {count} datasets")

        return dict(patterns)

    def analyze_extreme_vs_clean(self):
        """Compare extreme vs clean datasets."""
        extreme = [r for r in self.reports if "extreme" in r["filename"].lower()]
        clean = [r for r in self.reports if "_clean_" in r["filename"].lower()]

        print("\n=== EXTREME vs CLEAN DATASETS ===")
        if extreme:
            extreme_avg = sum(r["final_quality_score"] for r in extreme) / len(extreme)
            print(
                f"  Extreme datasets: {len(extreme)} (avg quality: {extreme_avg:.1f}%)"
            )
        if clean:
            clean_avg = sum(r["final_quality_score"] for r in clean) / len(clean)
            print(f"  Clean datasets: {len(clean)} (avg quality: {clean_avg:.1f}%)")

        return {
            "extreme": {
                "count": len(extreme),
                "avg_quality": extreme_avg if extreme else 0,
            },
            "clean": {"count": len(clean), "avg_quality": clean_avg if clean else 0},
        }

    def generate_learning_report(self):
        """Generate a comprehensive learning report."""
        self.load_reports()

        print("=" * 60)
        print("PATTERN ANALYSIS - LEARNING SYSTEM INSIGHTS")
        print("=" * 60)

        domains = self.analyze_domains()
        quality = self.analyze_quality_scores()
        issues = self.analyze_issues()
        cleaning = self.analyze_cleaning_steps()
        columns = self.analyze_columns()
        dtypes = self.analyze_dtypes()
        nulls = self.analyze_null_patterns()
        patterns = self.find_common_patterns()
        comparison = self.analyze_extreme_vs_clean()

        # Generate recommendations
        print("\n" + "=" * 60)
        print("RECOMMENDATIONS FOR IMPROVING CLEANING SYSTEM")
        print("=" * 60)

        # Most common issues
        if issues:
            top_issue = max(issues.items(), key=lambda x: x[1])
            print(
                f"\n1. Focus on fixing: {top_issue[0]} (found in {top_issue[1]} datasets)"
            )

        # Low quality datasets
        if quality["low_quality_count"] > 0:
            print(
                f"\n2. {quality['low_quality_count']} datasets still have low quality after cleaning"
            )
            print("   Consider adding more aggressive cleaning rules for these.")

        # Domain-specific patterns
        print("\n3. Domain-specific cleaning opportunities:")
        for domain in domains:
            domain_reports = [r for r in self.reports if r["detected_domain"] == domain]
            if domain_reports:
                cells = [
                    r["cells_cleaned"]
                    for r in domain_reports
                    if isinstance(r["cells_cleaned"], (int, float))
                ]
                if cells:
                    avg_cells = sum(cells) / len(cells)
                    print(
                        f"   - {domain}: avg {avg_cells:.0f} cells cleaned per dataset"
                    )

        # Save summary
        summary = {
            "total_reports": len(self.reports),
            "domains": domains,
            "quality": quality,
            "top_issues": dict(sorted(issues.items(), key=lambda x: -x[1])[:10]),
            "cleaning_actions": cleaning["counts"],
            "column_types": columns,
            "patterns": patterns,
            "comparison": comparison,
        }

        output_path = Path(self.reports_folder) / "pattern_analysis.json"
        with open(output_path, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"\n[Saved] Pattern analysis to {output_path}")

        return summary


if __name__ == "__main__":
    analyzer = PatternAnalyzer("D:/datacove_out/cleaning_reports")
    analyzer.generate_learning_report()
