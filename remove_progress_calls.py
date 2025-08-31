"""
Remove all update_progress calls from main.py
"""
import re

def remove_progress_calls():
    with open('python-api/main.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Remove all update_progress calls
    # More comprehensive pattern to match any update_progress call
    # This pattern matches the function call and all its content until the closing parenthesis
    pattern = r'\s*update_progress\s*\([^)]*(?:\{[^}]*\}[^)]*)*\)\s*\n?'
    
    original_lines = len(content.split('\n'))
    
    # Use a more sophisticated approach to remove complete update_progress calls
    lines = content.split('\n')
    filtered_lines = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        if 'update_progress(' in line:
            # Skip this line and any continuation lines until we find the closing parenthesis
            open_parens = line.count('(') - line.count(')')
            while open_parens > 0 and i + 1 < len(lines):
                i += 1
                line = lines[i]
                open_parens += line.count('(') - line.count(')')
            # Skip the line with closing parenthesis
            i += 1
        else:
            filtered_lines.append(line)
            i += 1
    
    content = '\n'.join(filtered_lines)
    
    # Clean up any double empty lines
    content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
    
    # Save the cleaned content
    with open('python-api/main.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    new_lines = len(content.split('\n'))
    print(f"Removed progress calls. Lines reduced from {original_lines} to {new_lines}")
    
    # Verify no update_progress calls remain
    remaining = content.count('update_progress(')
    print(f"Remaining update_progress calls: {remaining}")

if __name__ == '__main__':
    remove_progress_calls()