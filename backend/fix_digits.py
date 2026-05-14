import re

with open('services/cleaning_engine.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix broken digits from incorrect regex: d(\d) -> 0\1
# But we need to be careful not to break legitimate uses  
# Actually we broke: 86d1 -> 8601, d00 -> 000

# Fix specific patterns we broke
fixes = [
    ('86d1', '8601'),
    ('d00', '000'),
    ('1d0', '100'),  
    ('d1', '01'),
    ('d2', '02'),
    ('d3', '03'),
    ('d4', '04'),
    ('d5', '05'),
    ('d6', '06'),
    ('d7', '07'),
    ('d8', '08'),
    ('d9', '09'),
    # Fix _CHUNK constants
    ('1d0_d00', '100_000'),
    ('50_d00', '50_000'),
]

content_fixed = content
for old, new in fixes:
    if old in content_fixed:
        content_fixed = content_fixed.replace(old, new)
        print(f'Fixed: {old} -> {new}')

with open('services/cleaning_engine.py', 'w', encoding='utf-8') as f:
    f.write(content_fixed)

# Test
import ast
ast.parse(content_fixed)
print('SUCCESS!')