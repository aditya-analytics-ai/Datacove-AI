import re

with open('services/cleaning_engine.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the specific function using regex
old_func = r'def _coerce_numeric\(df: pd\.DataFrame, params: Dict\) -> pd\.DataFrame:.*?return df\n'

new_func = '''def _coerce_numeric(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    \"\"\"Coerce a column to numeric, turning non-numeric values to NaN.\"\"\"
    col = params.get("column")
    if col and col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df
'''

content_fixed = re.sub(old_func, new_func, content, count=1)

with open('services/cleaning_engine.py', 'w', encoding='utf-8') as f:
    f.write(content_fixed)

# Test parsing
import ast
ast.parse(content_fixed)
print('SUCCESS! File now parses correctly!')