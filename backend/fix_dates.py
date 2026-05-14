with open('services/cleaning_engine.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the entire problematic function definition
old = 'def _standardise_dates(df: pd.DataFrame, params: Dict) -> pd.DataFrame:\n    """Parse dates and reformat to ISO 8601 (YYYY-MM-DD)."""\n    col = params.get("column")'

new = 'def _standardise_dates(df: pd.DataFrame, params: Dict) -> pd.DataFrame:\n    doc = "Parse dates and reformat to ISO 8601 format"\n    col = params.get("column")'

content_fixed = content.replace(old, new)

with open('services/cleaning_engine.py', 'w', encoding='utf-8') as f:
    f.write(content_fixed)

import ast
ast.parse(content_fixed)
print('SUCCESS!')