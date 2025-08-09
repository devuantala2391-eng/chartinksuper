import re

def test_parsing():
    query = "daily_pctchg_1 < 9 and daily_pctchg_1 > 0 and weekly_supertrend_30_1.56 > 20"
    
    print(f"Original query: {query}")
    print("-" * 60)
    
    # Split by 'and' and 'or' operators
    parts = re.split(r'\s+(and|or)\s+', query.lower())
    
    print("Parts after splitting:")
    for i, part in enumerate(parts):
        print(f"  Part {i}: '{part}'")
    print()
    
    # Test the basic pattern on each part
    basic_pattern = r'(\w+(?:\(\d+(?:,\d+)*\))?)\s*([><=!]+)\s*(.+)'
    
    for part in parts:
        if part not in ['and', 'or']:
            part = part.strip()
            print(f"Testing part: '{part}'")
            match = re.match(basic_pattern, part)
            if match:
                print(f"  Match groups: {match.groups()}")
            else:
                print(f"  NO MATCH")
            print()
    
    # Test a more inclusive pattern that handles decimals
    better_pattern = r'([\w\.]+(?:\(\d+(?:\.\d+)?(?:,\d+(?:\.\d+)?)*\))?)\s*([><=!]+)\s*(.+)'
    
    print("\nTesting with better pattern that handles decimals:")
    for part in parts:
        if part not in ['and', 'or']:
            part = part.strip()
            print(f"Testing part: '{part}'")
            match = re.match(better_pattern, part)
            if match:
                print(f"  Match groups: {match.groups()}")
            else:
                print(f"  NO MATCH")
            print()

if __name__ == "__main__":
    test_parsing()