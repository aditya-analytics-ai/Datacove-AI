with open('services/cleaning_engine.py', 'rb') as f:
    content = f.read()

# Find position
pos = content.find(b')."""')
print('Position of ):', pos)

if pos > 0:
    print('Next bytes:', content[pos:pos+15])
    
    # Find where docstring should have newline after it
    # Looking for pattern: ..."""\r\n    col
    # But our bug is missing the newline: ..."""    col
    
    # Replace pattern: ..."""    col (no newline) 
    # with: ..."""\r\n    col (with newline)
    content_fixed = content.replace(
        b')."""    col',
        b')."""\r\n    col'
    )
    
    with open('services/cleaning_engine.py', 'wb') as f:
        f.write(content_fixed)
    print('Fixed!')

# Now test parse
import ast
ast.parse(content_fixed)
print('SUCCESS!')