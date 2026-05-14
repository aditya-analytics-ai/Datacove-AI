with open('services/cleaning_engine.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Check around _fuzzy_find_replace line
for i in range(2755, 2770):
    print(f'{i+1}: {lines[i][:60]}')