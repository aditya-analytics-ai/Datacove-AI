with open('services/cleaning_engine.py', 'rb') as f:
    content = f.read()

# The bug: docstring ending with """ followed directly by non-newline
# Replace pattern: """" followed by whitespace but not newline with proper ending
# Actually: find """" then space-then-continuation (wrong!)

# Find all occurrences where docstring end is followed by non-newline content  
import re

# Replace pattern where after docstring closing we don't have proper newline
# Match: """ + any whitespace (not newline) + alphachar 
pattern = rb'(\."""\r)(\s+)([a-zA-Z])'

def fix(m):
    # Replace with proper newline in between
    return m.group(1) + rb'\r\n' + m.group(3)

content_fixed = re.sub(pattern, fix, content)

# Write and test
with open('services/cleaning_engine.py', 'wb') as f:
    f.write(content_fixed)

import ast
ast.parse(content_fixed)
print('SUCCESS - All fixed!')