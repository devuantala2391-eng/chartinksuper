#!/usr/bin/env python3
"""
Comprehensive fix for all syntax issues in main.py
"""
import re

def comprehensive_fix():
    with open('python-api/main.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("Starting comprehensive fix...")
    
    # Remove all orphaned }) patterns that were added incorrectly
    content = re.sub(r'"})\s*\n\s*}', '"\n                            }', content)
    content = re.sub(r'"}\)\s*\n\s*}', '"\n                            }', content)
    
    # Fix lines that end with }) followed by }
    lines = content.split('\n')
    fixed_lines = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Check if current line ends with }) and next line is just }
        if (i < len(lines) - 1 and 
            line.strip().endswith('})') and 
            lines[i+1].strip() == '}'):
            # Remove the }) from current line and keep the } on next line
            line = line.replace('})', '"')
            fixed_lines.append(line)
            # Skip the current behavior and add the next line
            i += 1
            fixed_lines.append(lines[i])
        else:
            fixed_lines.append(line)
        
        i += 1
    
    content = '\n'.join(fixed_lines)
    
    # Fix any remaining patterns
    content = re.sub(r'})$', '}', content, flags=re.MULTILINE)
    
    # Write the fixed content
    with open('python-api/main.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("Comprehensive fix completed!")

if __name__ == '__main__':
    comprehensive_fix()