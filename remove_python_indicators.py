"""Remove Python indicator calculation files"""

import os
import sys
import io

# Fix Unicode output on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

files_to_remove = [
    r"D:\chartinksuper\python-api\services\vectorized_indicators.py",
    r"D:\chartinksuper\python-api\services\static_indicator_calculator.py"
]

print("=" * 60)
print("REMOVING PYTHON INDICATOR CALCULATION FILES")
print("=" * 60)

for file_path in files_to_remove:
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            print(f"✅ DELETED: {os.path.basename(file_path)}")
        except Exception as e:
            print(f"❌ FAILED to delete {os.path.basename(file_path)}: {e}")
    else:
        print(f"⚠️ NOT FOUND: {os.path.basename(file_path)} (already deleted or doesn't exist)")

print("\nNow checking for import references...")

# Check for files that import these modules
import_patterns = [
    "from services.vectorized_indicators",
    "import vectorized_indicators",
    "from services.static_indicator_calculator", 
    "import static_indicator_calculator"
]

services_dir = r"D:\chartinksuper\python-api\services"
files_with_imports = []

for root, dirs, files in os.walk(services_dir):
    for file in files:
        if file.endswith('.py'):
            file_path = os.path.join(root, file)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    for pattern in import_patterns:
                        if pattern in content:
                            files_with_imports.append((file_path, pattern))
                            break
            except Exception as e:
                pass

if files_with_imports:
    print("\n⚠️ Files that need import cleanup:")
    for file_path, pattern in files_with_imports:
        print(f"  - {os.path.basename(file_path)}: {pattern}")
else:
    print("\n✅ No import references found!")

print("\n" + "=" * 60)
print("CLEANUP COMPLETE!")
print("=" * 60)
print("\nNext steps:")
print("1. Remove any import references if found above")
print("2. Test the system with hard refresh")
print("3. Verify indicators are calculated via stored procedures only")