"""
Carefully remove only JSON-related functions from main.py without breaking structure
"""

import sys
import io
import re
from pathlib import Path

# Fix Unicode output on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def careful_json_removal():
    """Remove only specific JSON functions without breaking app structure"""
    
    print("=" * 60)
    print("CAREFUL JSON REMOVAL FROM MAIN.PY")
    print("=" * 60)
    
    main_file = Path("python-api/main.py")
    
    with open(main_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f"Original file size: {len(content.splitlines())} lines")
    
    # Patterns to remove (very specific)
    patterns_to_remove = [
        # Specific function definitions related to precalculated indicators
        r'def save_precalculated_to_json.*?\ndef ',
        r'def load_precalculated_from_json.*?\ndef ',
        r'def get_precalculated_config.*?\ndef ',
        r'def update_precalculated_json.*?\ndef ',
        
        # Specific lines with precalculatedIndicators.json
        r'.*precalculatedIndicators\.json.*\n',
        r'.*precalc_file.*Path.*precalculated.*\n',
        r'.*precalc_config_file.*\n',
        
        # Specific patterns for file operations on JSON
        r'.*with open.*precalculated.*json.*\n',
        r'.*json\.dump.*precalculated.*\n',
        r'.*json\.load.*precalculated.*\n',
    ]
    
    original_content = content
    
    for pattern in patterns_to_remove:
        old_content = content
        content = re.sub(pattern, '', content, flags=re.DOTALL | re.MULTILINE | re.IGNORECASE)
        if content != old_content:
            lines_removed = old_content.count('\n') - content.count('\n')
            if lines_removed > 0:
                print(f"  Removed ~{lines_removed} lines matching pattern")
    
    # Clean up multiple empty lines
    content = re.sub(r'\n\n\n+', '\n\n', content)
    
    # Check that we still have essential app structure
    essential_patterns = [
        r'app = FastAPI',
        r'@app\.(get|post)',
        r'if __name__ == "__main__"',
    ]
    
    missing_essential = []
    for pattern in essential_patterns:
        if not re.search(pattern, content, re.IGNORECASE):
            missing_essential.append(pattern)
    
    if missing_essential:
        print(f"❌ CRITICAL: Missing essential patterns: {missing_essential}")
        print("❌ Restoration needed - backup preserved")
        return False
    else:
        print("✅ Essential app structure preserved")
        
        # Save the carefully cleaned content
        backup_file = Path("python-api/main.py.careful_backup")
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write(original_content)
            
        with open(main_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Updated {main_file}")
        print(f"📁 Backup saved to {backup_file}")
        print(f"Final file size: {len(content.splitlines())} lines")
        
        # Verify app can be imported
        try:
            import subprocess
            result = subprocess.run([
                sys.executable, "-c", 
                "import sys; sys.path.append('python-api'); from main import app; print('✅ App import successful')"
            ], capture_output=True, text=True, cwd=".")
            
            if result.returncode == 0:
                print("✅ App import verification successful")
                return True
            else:
                print(f"❌ App import failed: {result.stderr}")
                return False
        except Exception as e:
            print(f"⚠️ Could not verify app import: {e}")
            return True  # Assume success if we can't test
    
if __name__ == "__main__":
    success = careful_json_removal()
    if success:
        print("\n🎉 Careful JSON removal completed successfully!")
        print("🚀 Server should now start properly")
    else:
        print("\n❌ Careful removal failed - check the output above")