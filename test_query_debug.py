#!/usr/bin/env python3
"""Test script to debug query processing issue"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'python-api'))

from services.query_service import parse_query, validate_query_fields
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_query_parsing():
    """Test the query parsing to see where it hangs"""
    
    # User's original complex query
    test_query = "daily_volume > 50000 and daily_pctchg_1 < 9 and daily_pctchg_1 > 0 and daily_close > 30 and weekly_volume > 1 week ago weekly_volume and weekly_close crossed above weekly_supertrend_10_2 and 1 day ago daily_volume > 10000"
    
    print(f"Testing query: {test_query}")
    print("=" * 50)
    
    try:
        print("Step 1: Parsing query...")
        parsed_query = parse_query(test_query)
        print(f"OK Query parsed successfully: {parsed_query}")
        
        print("\nStep 2: Validating query fields...")
        validation_result = validate_query_fields(parsed_query)
        print(f"OK Validation completed: {validation_result}")
        
        print("\nOK All steps completed successfully!")
        
    except Exception as e:
        print(f"ERROR Error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_query_parsing()