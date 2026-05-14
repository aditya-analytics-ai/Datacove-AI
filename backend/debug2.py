import re

with open('services/cleaning_engine.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Print lines around line 67 (index 66)
for i in range(63, 72):
    print(f'{i+1}: {lines[i][:70]}')