"""
Quick fix to comment out JSON references so server can start
"""

import sys
import io
from pathlib import Path

# Fix Unicode output on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def quick_fix_main():
    """Comment out JSON references so server starts"""
    
    main_file = Path("python-api/main.py")
    
    with open(main_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    modified_lines = []
    json_references_found = 0
    
    for line in lines:
        # Comment out lines that reference precalculatedIndicators.json
        if 'precalculatedIndicators.json' in line and not line.strip().startswith('#'):
            modified_lines.append(f"# DISABLED JSON: {line}")
            json_references_found += 1
        # Comment out lines that do file operations on precalc files
        elif ('precalc_file' in line or 'precalc_config_file' in line) and ('Path(' in line or 'open(' in line) and not line.strip().startswith('#'):
            modified_lines.append(f"# DISABLED JSON: {line}")
            json_references_found += 1
        else:
            modified_lines.append(line)
    
    # Write back
    with open(main_file, 'w', encoding='utf-8') as f:
        f.writelines(modified_lines)
    
    print(f"✅ Commented out {json_references_found} JSON references")
    print("🚀 Server should now start successfully!")
    print("\n📋 Note: JSON functionality disabled, database-based solution active")
    
if __name__ == "__main__":
    quick_fix_main()