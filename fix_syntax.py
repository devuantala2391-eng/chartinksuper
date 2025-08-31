#!/usr/bin/env python3
"""
Fix syntax errors in main.py - specifically incomplete dict literals
"""
import re

def fix_syntax_errors():
    with open('python-api/main.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("Original file size:", len(content.splitlines()), "lines")
    
    # Fix incomplete dict patterns
    patterns_to_fix = [
        # Pattern: {"key": value, "key2": "value"
        (r'(\s*)(.*\{[^}]*"[^"]*")\s*$', r'\1\2})'),
        
        # Pattern: .get("key", {
        (r'\.get\(([^,]+),\s*\{\s*$', r'.get(\1, {})'),
        
        # Pattern: .append({"stock": stock, "error": "message"
        (r'\.append\(\{"stock":\s*[^,]+,\s*"error":\s*"[^"]*"\s*$', r'&})'),
        
        # Pattern: errors.append({"stock": stock, "error": str(e)
        (r'errors\.append\(\{"stock":\s*[^,]+,\s*"error":\s*str\([^)]+\)\s*$', r'&})'),
    ]
    
    for pattern, replacement in patterns_to_fix:
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    
    # More specific fixes for common incomplete dict patterns
    lines = content.split('\n')
    fixed_lines = []
    
    for i, line in enumerate(lines):
        # Check if line has opening { but no closing }
        if '{' in line and '}' not in line and line.strip().endswith('"'):
            # This looks like an incomplete dict - try to close it
            if 'append(' in line and ('stock' in line or 'error' in line):
                line = line + '})'
            elif '.get(' in line:
                line = line.replace('{', '{})')
        
        # Check for lines that end with just a quote and are part of a dict
        if (line.strip().endswith('"') and 
            not line.strip().endswith('")') and 
            not line.strip().endswith('"}') and
            ('append({' in line or 'error":' in line or 'stock":' in line)):
            line = line + '})'
        
        fixed_lines.append(line)
    
    content = '\n'.join(fixed_lines)
    
    # Write the fixed content
    with open('python-api/main.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("Fixed file size:", len(content.splitlines()), "lines")
    print("Syntax fix completed!")

if __name__ == '__main__':
    fix_syntax_errors()