"""
Remove all JSON file dependencies from main.py and other files
"""

import os
import re
import sys
import io
from pathlib import Path

# Fix Unicode output on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def remove_json_dependencies():
    """Remove JSON file dependencies from Python files"""
    
    print("=" * 60)
    print("REMOVING JSON FILE DEPENDENCIES")
    print("=" * 60)
    
    files_to_update = [
        "python-api/main.py",
        "python-api/services/database_health_manager.py",
        "python-api/services/highspeed_query_validator.py",
        "python-api/services/latest_day_precalculator.py",
        "python-api/services/query_service.py"
    ]
    
    json_patterns_to_remove = [
        # precalculatedIndicators.json patterns
        r'.*precalculatedIndicators\.json.*\n',
        r'.*precalc_file.*Path.*precalculatedIndicators.*\n',
        r'.*with open.*precalculatedIndicators.*\n',
        r'.*json\.dump.*precalculatedIndicators.*\n',
        r'.*json\.load.*precalculatedIndicators.*\n',
        
        # schema_indicators.json patterns  
        r'.*schema_indicators\.json.*\n',
        r'.*config_path.*schema_indicators.*\n',
        
        # File existence checks for JSON files
        r'.*if.*\.exists\(\).*precalc.*\n',
        r'.*precalc_config_file.*exists.*\n',
    ]
    
    for file_path in files_to_update:
        file_obj = Path(file_path)
        if not file_obj.exists():
            print(f"⚠️ File not found: {file_path}")
            continue
            
        print(f"\n🔧 Processing {file_path}...")
        
        with open(file_obj, 'r', encoding='utf-8') as f:
            content = f.read()
            
        original_content = content
        lines_removed = 0
        
        # Remove JSON file related patterns
        for pattern in json_patterns_to_remove:
            old_content = content
            content = re.sub(pattern, '', content, flags=re.MULTILINE | re.IGNORECASE)
            if content != old_content:
                lines_removed += old_content.count('\n') - content.count('\n')
        
        # Remove specific function blocks that deal with JSON files
        json_functions_to_remove = [
            r'def.*precalculate.*indicator.*\(.*\):.*?(?=def|\Z)',
            r'def.*load.*precalculated.*\(.*\):.*?(?=def|\Z)',
            r'def.*save.*precalculated.*\(.*\):.*?(?=def|\Z)',
            r'async def.*precalculate.*indicator.*\(.*\):.*?(?=async def|def|\Z)',
        ]
        
        for func_pattern in json_functions_to_remove:
            old_content = content
            content = re.sub(func_pattern, '', content, flags=re.DOTALL | re.MULTILINE)
            if content != old_content:
                print(f"  📝 Removed function block")
        
        # Remove imports of deleted modules
        import_patterns_to_remove = [
            r'from.*precalculated.*import.*\n',
            r'import.*precalculated.*\n',
            r'from pathlib import Path.*# For JSON files.*\n',
        ]
        
        for import_pattern in import_patterns_to_remove:
            content = re.sub(import_pattern, '', content, flags=re.IGNORECASE)
        
        # Clean up empty lines (more than 2 consecutive)
        content = re.sub(r'\n\n\n+', '\n\n', content)
        
        if content != original_content:
            # Backup original
            backup_path = file_obj.with_suffix('.py.backup')
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(original_content)
            
            # Write cleaned content
            with open(file_obj, 'w', encoding='utf-8') as f:
                f.write(content)
                
            print(f"  ✅ Updated {file_path}")
            print(f"  📁 Backup saved to {backup_path}")
            if lines_removed > 0:
                print(f"  🗑️ Removed ~{lines_removed} lines")
        else:
            print(f"  ℹ️ No changes needed for {file_path}")
    
    # Remove the JSON files themselves
    print(f"\n🗑️ Removing JSON files...")
    
    json_files_to_remove = [
        "python-api/python-api/config/dynamic_indicators.json",
        "python-api/config/dynamic_indicators.json", 
        "python-api/precalculatedIndicators.json",
        "python-api/config/schema_indicators.json"
    ]
    
    for json_file in json_files_to_remove:
        file_obj = Path(json_file)
        if file_obj.exists():
            # Backup before deleting
            backup_path = file_obj.with_suffix('.json.backup')
            file_obj.rename(backup_path)
            print(f"  📁 Moved {json_file} to {backup_path}")
        else:
            print(f"  ℹ️ File not found: {json_file}")
    
    print(f"\n✅ JSON Dependencies Removal Complete!")
    print(f"\n📋 What was done:")
    print(f"  • Removed JSON file read/write operations")
    print(f"  • Removed precalculated indicator functions")
    print(f"  • Backed up original files (.backup extension)")
    print(f"  • Moved JSON files to .backup")
    print(f"\n🎯 System now uses database as single source of truth!")

if __name__ == "__main__":
    remove_json_dependencies()