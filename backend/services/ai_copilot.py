"""
ai_copilot.py - Natural Language to Pipeline transformation.

Uses AI to:
1. Convert natural language commands into pipeline steps
2. Suggest data cleaning actions based on data profile
3. Generate insights and data stories
4. Answer questions about the dataset
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import json

from config import settings
from utils.logger import logger


@dataclass
class CopilotSuggestion:
    action: str
    params: Dict[str, Any]
    reason: str
    confidence: float
    impact: str  # "high", "medium", "low"


@dataclass
class PipelineFromNL:
    steps: List[Dict[str, Any]]
    explanation: str
    warnings: List[str] = field(default_factory=list)


class AICopilot:
    """
    AI-powered data cleaning assistant.

    Converts natural language to pipeline steps and provides
    intelligent suggestions based on data profiling.
    """

    SYSTEM_PROMPT = """You are an expert data cleaning assistant for Datacove, an AI-powered data cleaning platform.

You help users clean, transform, and analyze their datasets using natural language commands.

Available transformations (use these exact action names):
- remove_duplicates: {"subset": ["col1", "col2"], "keep": "first"}
- fill_nulls: {"columns": ["col"], "strategy": "mean", "value": null}
- drop_columns: {"columns": ["col1", "col2"]}
- rename_columns: {"renames": {"old_name": "new_name"}}
- change_dtype: {"column": "col", "dtype": "integer"}
- trim_strings: {"columns": ["col1", "col2"]}
- find_replace: {"column": "col", "find": "old", "replace": "new", "regex": false}
- outlier_remove: {"columns": ["col"], "method": "iqr", "threshold": 1.5}
- normalize: {"columns": ["col"], "method": "minmax"}
- filter_rows: {"column": "col", "operator": "==", "value": "x"}
- filter_nulls: {"columns": ["col"], "how": "any"}
- derived_column: {"new_column": "col", "expression": "col1 * col2"}
- group_by: {"group_columns": ["col"], "aggregations": {"col": "sum"}}

Rules:
1. Always respond with valid JSON in the specified format
2. Break complex requests into multiple steps
3. Prefer safe operations (keep original data)
4. Suggest batch operations when possible
5. Always explain WHY each transformation is recommended
"""

    def __init__(self):
        self.client = self._get_client()

    def _get_client(self):
        """Get the configured AI client."""
        if settings.AI_PROVIDER == "openai":
            from openai import OpenAI

            return OpenAI(api_key=settings.OPENAI_API_KEY)
        elif settings.AI_PROVIDER == "anthropic":
            import anthropic

            return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        elif settings.AI_PROVIDER == "gemini":
            import google.generativeai as genai

            genai.configure(api_key=settings.GEMINI_API_KEY)
            return genai
        else:
            raise ValueError(f"Unknown AI provider: {settings.AI_PROVIDER}")

    def nl_to_pipeline(
        self,
        command: str,
        columns: List[str],
        column_types: Optional[Dict[str, str]] = None,
        sample_data: Optional[List[Dict]] = None,
    ) -> PipelineFromNL:
        """
        Convert natural language command to pipeline steps.

        Args:
            command: Natural language command (e.g., "remove duplicates, fill missing ages with median")
            columns: List of column names
            column_types: Optional dict of column -> dtype
            sample_data: Optional sample rows for context
        """
        column_info = ", ".join(
            [f"{c} ({column_types.get(c, 'unknown')})" for c in columns]
        )

        context = f"Columns: {column_info}"
        if sample_data:
            context += f"\nSample data: {json.dumps(sample_data[:3])}"

        user_prompt = f"""
Task: Convert this natural language command into pipeline steps.

Command: {command}

{context}

Respond with ONLY this JSON format (no other text):
{{
    "steps": [
        {{"action": "action_name", "params": {{"param": "value"}}}},
        ...
    ],
    "explanation": "Brief explanation of what will be done",
    "warnings": ["any warnings about data loss or side effects"]
}}
"""

        response = self._call_llm(user_prompt)

        try:
            result = json.loads(response)
            return PipelineFromNL(
                steps=result.get("steps", []),
                explanation=result.get("explanation", ""),
                warnings=result.get("warnings", []),
            )
        except json.JSONDecodeError:
            logger.error(f"Failed to parse AI response: {response}")
            return PipelineFromNL(
                steps=[],
                explanation="Failed to parse AI response",
                warnings=["AI response was not valid JSON"],
            )

    def suggest_cleaning(
        self, profile: Dict[str, Any], issues: List[Dict[str, Any]], columns: List[str]
    ) -> List[CopilotSuggestion]:
        """
        Suggest cleaning actions based on data profile and detected issues.

        Args:
            profile: Dataset profile from profiling_engine
            issues: List of detected issues
            columns: Column names
        """
        column_info = ", ".join(columns)
        issues_str = json.dumps(issues[:10])
        profile_str = json.dumps(profile, default=str)[:2000]

        user_prompt = f"""
Based on this data profile and issues, suggest cleaning transformations.

Columns: {column_info}

Issues detected: {issues_str}

Profile summary: {profile_str}

Respond with ONLY this JSON format:
{{
    "suggestions": [
        {{
            "action": "action_name",
            "params": {{"param": "value"}},
            "reason": "Why this action helps",
            "confidence": 0.95,
            "impact": "high"
        }}
    ]
}}
"""

        response = self._call_llm(user_prompt)

        try:
            result = json.loads(response)
            return [
                CopilotSuggestion(
                    action=s["action"],
                    params=s.get("params", {}),
                    reason=s.get("reason", ""),
                    confidence=s.get("confidence", 0.5),
                    impact=s.get("impact", "medium"),
                )
                for s in result.get("suggestions", [])
            ]
        except (json.JSONDecodeError, KeyError):
            logger.error(f"Failed to parse suggestions: {response}")
            return []

    def explain_column(self, column: str, profile: Dict[str, Any]) -> str:
        """Get AI explanation of a column."""
        user_prompt = f"""
Explain this data column in simple terms for a data analyst.

Column: {column}
Profile: {json.dumps(profile, default=str)}

Respond with a 2-3 sentence explanation.
"""
        return self._call_llm(user_prompt)

    def generate_story(self, profile: Dict[str, Any], insights: List[str]) -> str:
        """Generate a data story/narrative from profiling results."""
        user_prompt = f"""
Generate a concise data story summarizing this dataset.
Include key findings and interesting patterns.

Profile: {json.dumps(profile, default=str)[:3000]}
Insights: {insights}

Write 3-5 bullet points highlighting the most important findings.
"""
        return self._call_llm(user_prompt)

    def answer_question(
        self, question: str, profile: Dict[str, Any], sample_data: List[Dict]
    ) -> str:
        """Answer a question about the dataset."""
        user_prompt = f"""
Answer this question about the dataset.

Question: {question}

Profile: {json.dumps(profile, default=str)[:2000]}
Sample data: {json.dumps(sample_data[:5])}

Provide a direct, helpful answer. If you need to run a calculation, explain how.
"""
        return self._call_llm(user_prompt)

    def _call_llm(self, user_prompt: str) -> str:
        """Call the configured LLM."""
        try:
            if settings.AI_PROVIDER == "openai":
                response = self.client.chat.completions.create(
                    model=settings.OPENAI_MODEL or "gpt-4",
                    messages=[
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                    max_tokens=2000,
                )
                return response.choices[0].message.content

            elif settings.AI_PROVIDER == "anthropic":
                response = self.client.messages.create(
                    model=settings.ANTHROPIC_MODEL or "claude-3-sonnet-20240229",
                    max_tokens=2000,
                    system=self.SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                return response.content[0].text

            elif settings.AI_PROVIDER == "gemini":
                model = self.client.GenerativeModel(
                    settings.GEMINI_MODEL or "gemini-pro"
                )
                response = model.generate_content(
                    contents=[{"role": "user", "parts": [user_prompt]}]
                )
                return response.text

        except Exception as e:
            logger.error(f"AI call failed: {e}")
            return json.dumps({"error": str(e)})


def get_copilot() -> AICopilot:
    """Get AI copilot instance."""
    return AICopilot()
