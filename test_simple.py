# Simple test of the formatting function
def test_format_decimal():
    def format_decimal_param(value):
        if value == int(value):
            return str(int(value))
        else:
            return str(value).replace('.', 'dot')
    
    test_cases = [
        (2.5, "2dot5"),
        (3.0, "3"),
        (10.25, "10dot25"),
        (14, "14")
    ]
    
    print("Testing decimal parameter formatting...")
    for input_val, expected in test_cases:
        result = format_decimal_param(input_val)
        if result == expected:
            print(f"  SUCCESS: {input_val} -> '{result}'")
        else:
            print(f"  FAILED: {input_val} -> '{result}', expected '{expected}'")
    
    print("\nTesting key uniqueness...")
    key1 = f"supertrend_10_{format_decimal_param(2.0)}"
    key2 = f"supertrend_10_{format_decimal_param(2.5)}"
    key3 = f"supertrend_10_{format_decimal_param(3.0)}"
    
    print(f"  (10, 2.0) -> '{key1}'")
    print(f"  (10, 2.5) -> '{key2}'")
    print(f"  (10, 3.0) -> '{key3}'")
    
    if len(set([key1, key2, key3])) == 3:
        print("  SUCCESS: All keys are unique!")
    else:
        print("  FAILED: Keys are not unique")

if __name__ == "__main__":
    test_format_decimal()
