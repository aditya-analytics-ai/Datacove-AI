with open('services/cleaning_engine.py', 'rb') as f:
    content = f.read()

# Simple split on triple quotes
parts = content.split(b'"""')
print('Parts:')
print(len(parts))

# Print last element 
last = parts[-1]
print('Last part length:', len(last))
print('Last part:', last[:50])