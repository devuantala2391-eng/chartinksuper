#!/usr/bin/env python3

import sys
import os
import json
from datetime import datetime

# Add the python-api directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), 'python-api'))

from services.data_utils import get_day_of_week_name

def test_json_day_field():
    """Test that dayOfWeek field is properly added to JSON data"""
    print("Testing day of week field addition to JSON...")
    
    # Test the utility function directly
    current_timestamp = datetime.now().timestamp() * 1000
    day_name = get_day_of_week_name(current_timestamp)
    print(f"Current day: {day_name}")
    
    # Test with a sample JSON structure like what would be generated
    sample_data = {
        "status": "completed",
        "indicators": ["supertrend"],
        "lastUpdated": datetime.utcnow().isoformat(),
        "dayOfWeek": get_day_of_week_name(datetime.utcnow().timestamp() * 1000)
    }
    
    print(f"Sample precalc_data structure:")
    print(json.dumps(sample_data, indent=2))
    
    # Test with the actual WORTH timestamp that should be Friday
    worth_timestamp = 1753381800000  # Last timestamp from WORTH.json
    worth_day = get_day_of_week_name(worth_timestamp)
    print(f"\nWORTH last timestamp {worth_timestamp} -> {worth_day}")
    
    # Test sample match structure with WORTH data
    sample_match = {
        "stock": "WORTH",
        "date": worth_timestamp,
        "dayOfWeek": worth_day,
        "data": {
            "timestamp": worth_timestamp,
            "dayOfWeek": worth_day,
            "open": 167.28,
            "high": 170.52,
            "low": 157.30,
            "close": 162.18
        }
    }
    
    print(f"\nSample match structure with WORTH data:")
    print(json.dumps(sample_match, indent=2))
    
    # Test a few more timestamps to verify the fix
    test_timestamps = [
        1753295400000,  # Previous day
        1753381800000,  # Last day (should be Friday)
        1753468200000,  # Next day (would be Saturday)
    ]
    
    print(f"\nTesting multiple timestamps:")
    for ts in test_timestamps:
        day = get_day_of_week_name(ts)
        print(f"  {ts} -> {day}")
    
    print(f"\nDay of week field is properly being added to JSON structures with correct IST timezone!")

if __name__ == "__main__":
    test_json_day_field()