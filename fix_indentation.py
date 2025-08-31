"""
Fix indentation errors caused by commenting out JSON lines
"""

import sys
import io
from pathlib import Path

# Fix Unicode output on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def fix_indentation():
    """Fix indentation by properly handling the commented lines"""
    
    main_file = Path("python-api/main.py")
    
    with open(main_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace the broken commented sections with proper pass statements
    lines = content.split('\n')
    fixed_lines = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # If we find a commented JSON line that's causing indentation issues
        if line.strip().startswith('# DISABLED JSON:'):
            # Get the original indentation level
            original_line = line.replace('# DISABLED JSON: ', '')
            indent_level = len(original_line) - len(original_line.lstrip())
            
            # Check if this is inside a function/block that needs a statement
            if original_line.strip().startswith(('with open', 'json.dump', 'json.load')):
                # Replace with a pass statement at the same indentation level
                fixed_lines.append(' ' * indent_level + 'pass  # JSON functionality disabled')
            else:
                # Just comment it out properly
                fixed_lines.append('# ' + original_line)
        else:
            fixed_lines.append(line)
        
        i += 1
    
    # Write back the fixed content
    with open(main_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(fixed_lines))
    
    print("✅ Fixed indentation errors")
    
if __name__ == "__main__":
    fix_indentation()