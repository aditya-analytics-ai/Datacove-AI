import re

with open('services/cleaning_engine.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Count
n = content.count('"""')
print(f'Found {n} triple quote pairs')

# Fix: Find lines with "0d-" and replace with "dd-"
# This was causing parse errors  
content_fixed = re.sub(r'0(\d)', r'd\1', content)

with open('services/cleaning_engine.py', 'w', encoding='utf-8') as f:
    f.write(content_fixed)

# Test
import ast
try:
    ast.parse(content_fixed)
    print('SUCCESS - File parses!')
except SyntaxError as e:
    print(f'Still error: {e}')