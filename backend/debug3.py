with open('services/cleaning_engine.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Count opening vs closing - this is just counting occurrences
# But need to track whether they're opening or closing

# Let's print lines around 740 and 2759 more carefully
lines = content.split('\n')
print('Lines around 738-745:')
for i in range(735, 745):
    print(f'{i+1}: {lines[i][:70]}')

print('\nLines around 2755-2765:')
for i in range(2753, 2765):
    print(f'{i+1}: {lines[i][:70]}')