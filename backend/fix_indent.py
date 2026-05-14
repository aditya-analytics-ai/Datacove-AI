with open('services/cleaning_engine.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find line 1564 and add the missing space
# The line starts with 3 spaces but should have 4
content_fixed = content.replace(
    '\n   -> prevent incorrect date parsing.\n',
    '\n    -> prevent incorrect date parsing.\n'
)

with open('services/cleaning_engine.py', 'w', encoding='utf-8') as f:
    f.write(content_fixed)

# Test
import ast
ast.parse(content_fixed)
print('SUCCESS - All fixed!')