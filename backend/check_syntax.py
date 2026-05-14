import ast
import re

with open('services/cleaning_engine.py', 'rb') as f:
    content = f.read()

# The problem might be in how Python parses date-like strings in docstrings
# Replace 01-07 with 1-7 in docstrings only
# Actually, fix by replacing date patterns in docstrings to avoid looking like numbers

# Find and replace specifically the problematic date
content_fixed = content.replace(b'2024-01-07', b'2024-Jan-07')

# Also avoid any date starting with 0X where X is digit
# Replace any patterns like MM-DD or YYYY-MM-DD in docstrings with alternative format

with open('services/cleaning_engine.py', 'wb') as f:
    f.write(content_fixed)

# Try parsing now
try:
    ast.parse(content_fixed)
    print('SUCCESS')
except SyntaxError as e:
    print(f'Error: {e}')