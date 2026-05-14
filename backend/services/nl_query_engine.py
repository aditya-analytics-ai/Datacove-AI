"""
Natural language cleaning command parser.
Converts plain English commands into structured action dicts.
Falls back to rule-based parsing when no LLM key is set.
"""
from typing import Any, Dict, List, Optional
import re
from config import OPENAI_API_KEY, OPENAI_MODEL, GOOGLE_API_KEY, GOOGLE_MODEL
from utils.ai_rate_limiter import ai_rate_limiter


def parse_command(command: str, df_columns: Optional[List[str]] = None,
                  history: Optional[List[dict]] = None) -> Dict[str, Any]:
    """
    Convert a natural-language cleaning command to a structured action dict.
    Returns {"action": str, "params": dict} or {"error": str}.
    history is a list of {"role": "user"|"assistant", "content": str} dicts
    for multi-turn LLM context.
    """
    df_columns = df_columns or []
    history    = history or []

    if GOOGLE_API_KEY or OPENAI_API_KEY:
        result = _llm_parse(command, df_columns, history)
        if "error" not in result:
            return result
        # Fall through to rule-based on LLM failure

    return _rule_parse(command, df_columns)


# ── Rule-based parser ─────────────────────────────────────────────────────────

def _rule_parse(command: str, columns: List[str]) -> Dict[str, Any]:
    cmd = command.lower().strip()

    # remove duplicates
    if re.search(r"remove\s+duplicates?|drop\s+duplicates?|deduplicate", cmd):
        return {"action": "remove_duplicates", "params": {}}

    # fill missing [column] [with] [strategy]
    m = re.search(r"fill\s+(?:missing|null|nan|empty)(?:\s+(?:values?\s+)?in)?\s+['\"]?([a-z0-9_ ]+?)['\"]?"
                  r"(?:\s+with)?\s*(mean|median|mode|zero|0)?", cmd)
    if m:
        col      = _best_match(m.group(1).strip(), columns)
        strategy = m.group(2) or "median"
        if strategy == "zero": strategy = "value"
        return {"action": "fill_missing", "params": {"column": col, "strategy": strategy}}

    # generic fill missing
    if re.search(r"fill\s+(missing|null|nan|empty)", cmd):
        strategy = "median" if re.search(r"median", cmd) else ("mean" if re.search(r"mean", cmd) else "mode")
        return {"action": "fill_missing", "params": {"strategy": strategy}}

    # drop column [name]
    m = re.search(r"drop\s+(?:column\s+)?['\"]?([a-z0-9_ ]+)['\"]?", cmd)
    if m:
        col = _best_match(m.group(1).strip(), columns)
        return {"action": "drop_column", "params": {"column": col}}

    # trim whitespace
    if re.search(r"trim|strip|whitespace|extra\s+spaces?", cmd):
        return {"action": "trim_whitespace", "params": {}}

    # normalize / standardise text / capitalisation
    if re.search(r"normaliz|standardis|capitaliz|lowercase|uppercase", cmd):
        if re.search(r"lower", cmd):
            return {"action": "standardise_capitalisation", "params": {"strategy": "lower"}}
        if re.search(r"upper", cmd):
            return {"action": "standardise_capitalisation", "params": {"strategy": "upper"}}
        return {"action": "standardise_capitalisation", "params": {"strategy": "title"}}

    # coerce / convert numeric
    m = re.search(r"(?:coerce|convert|make)\s+['\"]?([a-z0-9_ ]+)['\"]?\s+(?:to\s+)?numeric", cmd)
    if m:
        col = _best_match(m.group(1).strip(), columns)
        return {"action": "coerce_numeric", "params": {"column": col}}

    # standardise dates
    m = re.search(r"standardis[ae]\s+dates?\s+(?:in\s+)?['\"]?([a-z0-9_ ]+)['\"]?", cmd)
    if m:
        col = _best_match(m.group(1).strip(), columns)
        return {"action": "standardise_dates", "params": {"column": col}}

    # auto clean - use __auto_clean__ sentinel so frontend calls the correct endpoint
    if re.search(r"auto\s*clean|full\s*clean|clean\s+all|clean\s+dataset", cmd):
        return {"action": "__auto_clean__", "params": {}}

    return {"error": f"Could not parse command: '{command}'. Try: 'remove duplicates', 'fill missing age', 'drop column city'."}


def _best_match(fragment: str, columns: List[str]) -> str:
    """Return the closest column name, or the fragment itself if no match."""
    fragment_lower = fragment.lower()
    for col in columns:
        if col.lower() == fragment_lower:
            return col
    for col in columns:
        if fragment_lower in col.lower() or col.lower() in fragment_lower:
            return col
    return fragment


# ── LLM parser ────────────────────────────────────────────────────────────────

def _llm_parse(command: str, columns: List[str], history: Optional[List[dict]] = None) -> Dict[str, Any]:
    try:
        import json
        ai_rate_limiter.check()

        system_prompt = f"""You are a data cleaning assistant. Convert the user command to a JSON action.
Available columns: {json.dumps(columns)}
Available actions:
  remove_duplicates, trim_whitespace, standardise_capitalisation, normalise_categories,
  fill_missing, fill_missing_ffill, fill_missing_bfill, fill_missing_interpolate,
  drop_rows_missing_threshold, coerce_numeric, standardise_dates, flag_invalid_emails,
  rename_column, drop_column, drop_rows_where,
  find_replace, strip_characters, normalize_unicode, normalize_phone,
  map_values, split_column, merge_columns,
  extract_numeric, clip_outliers, replace_outliers, round_numeric, scale_numeric, bin_numeric,
  cast_type, conditional_column, drop_constant_columns, drop_high_missing_columns,
  fuzzy_remove_duplicates, sql_apply

Return JSON: {{"action": "<action>", "params": {{...}}}}
Only respond with valid JSON, no markdown."""

        if GOOGLE_API_KEY:
            import google.generativeai as genai
            genai.configure(api_key=GOOGLE_API_KEY)
            model = genai.GenerativeModel(
                model_name=GOOGLE_MODEL,
                system_instruction=system_prompt,
            )
            # Build conversation history for multi-turn context
            chat_history = []
            for h in (history or []):
                if h.get("role") in ("user", "assistant") and h.get("content"):
                    role = "model" if h["role"] == "assistant" else "user"
                    chat_history.append({"role": role, "parts": [h["content"]]})
            chat = model.start_chat(history=chat_history)
            response = chat.send_message(command)
            text = response.text.strip()
        else:
            import openai
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
            messages = [{"role": "system", "content": system_prompt}]
            for h in (history or []):
                if h.get("role") in ("user", "assistant") and h.get("content"):
                    messages.append({"role": h["role"], "content": h["content"]})
            messages.append({"role": "user", "content": command})
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                temperature=0,
            )
            text = response.choices[0].message.content.strip()

        # Strip accidental markdown fences
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(text)
    except Exception as exc:
        return {"error": str(exc)}
