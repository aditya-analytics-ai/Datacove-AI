# Triple-quoted string inside triple-quoted string will be corrupted
# Replace line-by-line in binary
with open('services/cleaning_engine.py', 'rb') as f:
    content = f.read()

# The corrupted line has: """Coerce a column to numeric."""
# Replace with full corrected version
import re
# Match the specific corruped docstring line
content_fixed = re.sub(
    rb'    """Coerce a column to numeric\."""',
    rb'    """Coerce a column to numeric, turning non-numeric values to NaN."""',
    content
)

# Write fixed version
with open('services/cleaning_engine.py', 'wb') as f:
    f.write(content_fixed)

# Test
import ast
ast.parse(content_fixed.decode('utf-8'))
print('SUCCESS')