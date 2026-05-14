import re

with open('services/cleaning_engine.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Count triple quotes - if odd, file has unclosed string
n_triple = content.count('"""')
print(f'Triple quotes: {n_triple}')

# Count by splitting on """ and counting
parts = content.split('"""')
# Odd number of parts means unclosed string
if len(parts) % 2 == 0:
    print('Unclosed string likely!')
    # Find the section around line 2759
    lines = content.split('\n')
    print('Lines around 2759:')
    for i in range(2755, 2765):
        print(f'{i+1}: {lines[i][:60]}')
else:
    print('Triple quotes balanced')