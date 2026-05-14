"""
Learning Dashboard - Visualizes cleaning system learning progress.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

from utils.logger import logger


class LearningDashboard:
    def __init__(self, reports_folder: str):
        self.reports_folder = reports_folder
        self.reports = []
        self.analysis = None

    def load_data(self):
        """Load all data."""
        analysis_path = Path(self.reports_folder) / "pattern_analysis.json"
        if analysis_path.exists():
            with open(analysis_path) as f:
                self.analysis = json.load(f)

        for filepath in Path(self.reports_folder).glob("report_*.json"):
            with open(filepath) as f:
                self.reports.append(json.load(f))

    def generate_html(self) -> str:
        """Generate interactive HTML dashboard."""

        domains = self.analysis.get("domains", {})
        quality = self.analysis.get("quality", {})
        top_issues = self.analysis.get("top_issues", {})
        cleaning_actions = self.analysis.get("cleaning_actions", {})
        column_types = self.analysis.get("column_types", {})
        patterns = dict(
            sorted(self.analysis.get("patterns", {}).items(), key=lambda x: -x[1])[:10]
        )
        comparison = self.analysis.get("comparison", {})

        # Domain chart data
        domain_labels = list(domains.keys())
        domain_values = list(domains.values())
        domain_colors = [
            "#FF6B6B",
            "#4ECDC4",
            "#45B7D1",
            "#96CEB4",
            "#FFEAA7",
            "#DDA0DD",
            "#98D8C8",
            "#F7DC6F",
            "#BB8FCE",
            "#85C1E9",
            "#F8B500",
        ]

        # Quality comparison
        extreme_q = comparison.get("extreme", {}).get("avg_quality", 0)
        clean_q = comparison.get("clean", {}).get("avg_quality", 0)

        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DataCoVe Learning Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
        header {{
            text-align: center;
            padding: 30px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            margin-bottom: 30px;
        }}
        header h1 {{ 
            font-size: 2.5rem; 
            background: linear-gradient(90deg, #4ECDC4, #45B7D1);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 10px;
        }}
        header p {{ color: #888; font-size: 1.1rem; }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 25px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.1);
            transition: transform 0.3s, box-shadow 0.3s;
        }}
        .stat-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(78, 205, 196, 0.2);
        }}
        .stat-card .value {{
            font-size: 2.5rem;
            font-weight: bold;
            background: linear-gradient(90deg, #4ECDC4, #45B7D1);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .stat-card .label {{
            color: #888;
            margin-top: 5px;
            font-size: 0.9rem;
        }}
        
        .charts-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 30px;
            margin-bottom: 30px;
        }}
        .chart-card {{
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 25px;
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .chart-card h3 {{
            color: #4ECDC4;
            margin-bottom: 20px;
            font-size: 1.2rem;
        }}
        .chart-container {{ position: relative; height: 300px; }}
        
        .section {{
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 30px;
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .section h2 {{
            color: #4ECDC4;
            margin-bottom: 20px;
            font-size: 1.5rem;
        }}
        
        .recommendations {{
            display: grid;
            gap: 15px;
        }}
        .recommendation {{
            background: rgba(78, 205, 196, 0.1);
            border-left: 4px solid #4ECDC4;
            padding: 15px 20px;
            border-radius: 0 10px 10px 0;
        }}
        .recommendation h4 {{
            color: #4ECDC4;
            margin-bottom: 5px;
        }}
        .recommendation p {{
            color: #aaa;
            font-size: 0.9rem;
        }}
        
        .issues-list, .patterns-list {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 10px;
        }}
        .issue-item, .pattern-item {{
            background: rgba(255,255,255,0.05);
            padding: 10px 15px;
            border-radius: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .badge {{
            background: linear-gradient(90deg, #FF6B6B, #FF8E53);
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: bold;
        }}
        
        footer {{
            text-align: center;
            padding: 20px;
            color: #666;
            border-top: 1px solid rgba(255,255,255,0.1);
            margin-top: 30px;
        }}
        
        .loading {{
            text-align: center;
            padding: 50px;
            color: #888;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>DataCoVe Learning Dashboard</h1>
            <p>Intelligent Data Cleaning System - Training Progress</p>
        </header>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="value">{len(self.reports)}</div>
                <div class="label">Datasets Analyzed</div>
            </div>
            <div class="stat-card">
                <div class="value">{sum(domains.values()):,}</div>
                <div class="label">Total Rows Processed</div>
            </div>
            <div class="stat-card">
                <div class="value">{quality.get("final_avg", 0):.1f}%</div>
                <div class="label">Average Quality Score</div>
            </div>
            <div class="stat-card">
                <div class="value">{len(domains)}</div>
                <div class="label">Domains Detected</div>
            </div>
            <div class="stat-card">
                <div class="value">{quality.get("low_quality_count", 0)}</div>
                <div class="label">Low Quality Datasets</div>
            </div>
        </div>
        
        <div class="charts-grid">
            <div class="chart-card">
                <h3>Domain Distribution</h3>
                <div class="chart-container">
                    <canvas id="domainChart"></canvas>
                </div>
            </div>
            <div class="chart-card">
                <h3>Quality: Extreme vs Clean</h3>
                <div class="chart-container">
                    <canvas id="qualityChart"></canvas>
                </div>
            </div>
        </div>
        
        <div class="charts-grid">
            <div class="chart-card">
                <h3>Cleaning Actions</h3>
                <div class="chart-container">
                    <canvas id="actionsChart"></canvas>
                </div>
            </div>
            <div class="chart-card">
                <h3>Column Types Detected</h3>
                <div class="chart-container">
                    <canvas id="typesChart"></canvas>
                </div>
            </div>
        </div>
        
        <div class="section">
            <h2>Common Issues Found</h2>
            <div class="issues-list">
                {"".join(f'<div class="issue-item"><span>{issue}</span><span class="badge">{count}</span></div>' for issue, count in list(top_issues.items())[:8])}
            </div>
        </div>
        
        <div class="section">
            <h2>Patterns Detected</h2>
            <div class="patterns-list">
                {"".join(f'<div class="pattern-item"><span>{p}</span><span class="badge">{c}</span></div>' for p, c in patterns.items())}
            </div>
        </div>
        
        <div class="section">
            <h2>Recommendations</h2>
            <div class="recommendations">
                <div class="recommendation">
                    <h4>1. Handle Missing Values</h4>
                    <p>High missing values found in {top_issues.get("high_missing", 0)} datasets. Consider adding intelligent imputation strategies.</p>
                </div>
                <div class="recommendation">
                    <h4>2. Improve Duplicate Detection</h4>
                    <p>Duplicate rows found in {top_issues.get("duplicate_rows", 0)} datasets. System successfully removes these.</p>
                </div>
                <div class="recommendation">
                    <h4>3. Domain-Specific Cleaning</h4>
                    <p>E-commerce datasets benefit most from cleaning ({len([r for r in self.reports if r.get("detected_domain") == "ecommerce"])} datasets, avg 7325 cells cleaned).</p>
                </div>
                <div class="recommendation">
                    <h4>4. Extreme Dataset Handling</h4>
                    <p>Extreme datasets average {extreme_q:.1f}% quality vs {clean_q:.1f}% for clean datasets. Room for improvement in dirty data handling.</p>
                </div>
            </div>
        </div>
        
        <footer>
            <p>Generated on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | DataCoVe Learning System v1.0</p>
        </footer>
    </div>
    
    <script>
        // Domain Chart
        new Chart(document.getElementById('domainChart'), {{
            type: 'doughnut',
            data: {{
                labels: {domain_labels},
                datasets: [{{
                    data: {domain_values},
                    backgroundColor: {domain_colors[: len(domain_labels)]},
                    borderWidth: 0
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ position: 'right', labels: {{ color: '#fff' }} }}
                }}
            }}
        }});
        
        // Quality Chart
        new Chart(document.getElementById('qualityChart'), {{
            type: 'bar',
            data: {{
                labels: ['Extreme Datasets', 'Clean Datasets'],
                datasets: [{{
                    data: [{extreme_q:.1f}, {clean_q:.1f}],
                    backgroundColor: ['#FF6B6B', '#4ECDC4'],
                    borderWidth: 0,
                    borderRadius: 10
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    y: {{ 
                        beginAtZero: true, 
                        max: 100,
                        ticks: {{ color: '#888' }},
                        grid: {{ color: 'rgba(255,255,255,0.1)' }}
                    }},
                    x: {{ ticks: {{ color: '#888' }}, grid: {{ display: false }} }}
                }}
            }}
        }});
        
        // Actions Chart
        new Chart(document.getElementById('actionsChart'), {{
            type: 'bar',
            data: {{
                labels: {list(cleaning_actions.keys())},
                datasets: [{{
                    data: {list(cleaning_actions.values())},
                    backgroundColor: '#45B7D1',
                    borderWidth: 0,
                    borderRadius: 5
                }}]
            }},
            options: {{
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    x: {{ 
                        beginAtZero: true,
                        ticks: {{ color: '#888' }},
                        grid: {{ color: 'rgba(255,255,255,0.1)' }}
                    }},
                    y: {{ ticks: {{ color: '#fff' }}, grid: {{ display: false }} }}
                }}
            }}
        }});
        
        // Types Chart
        new Chart(document.getElementById('typesChart'), {{
            type: 'polarArea',
            data: {{
                labels: {list(column_types.keys())},
                datasets: [{{
                    data: {[v.get("total", 0) for v in column_types.values()]},
                    backgroundColor: ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFEAA7', '#DDA0DD', '#98D8C8'],
                    borderWidth: 0
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ position: 'right', labels: {{ color: '#fff' }} }} }}
            }}
        }});
    </script>
</body>
</html>
"""
        return html

    def save_dashboard(self, output_path: str = None):
        """Save the HTML dashboard."""
        if output_path is None:
            output_path = Path(self.reports_folder) / "dashboard.html"

        html = self.generate_html()
        with open(output_path, "w") as f:
            f.write(html)

        logger.info(f"Dashboard saved to: {output_path}")
        return output_path


if __name__ == "__main__":
    dashboard = LearningDashboard("D:/datacove_out/cleaning_reports")
    dashboard.load_data()
    dashboard.save_dashboard()
