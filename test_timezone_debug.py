#!/usr/bin/env python3

import sys
import os
from datetime import datetime, timezone, timedelta

# Add the python-api directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), 'python-api'))

from services.data_utils import get_day_of_week_name
from utils.constants import DAY_OF_WEEK

def test_timezone_issue():
    """Test the timezone issue with day of week calculation"""
    
    # Last timestamp from WORTH.json
    last_timestamp = 1753381800000
    
    print(f"Testing timestamp: {last_timestamp}")
    
    # Current implementation (UTC)
    current_result = get_day_of_week_name(last_timestamp)
    print(f"Current implementation (UTC): {current_result}")
    
    # Test with UTC explicitly
    utc_dt = datetime.fromtimestamp(last_timestamp / 1000, tz=timezone.utc)
    print(f"UTC datetime: {utc_dt} ({utc_dt.strftime('%A')})")
    
    # Test with IST (Indian Standard Time) - UTC+5:30
    ist_offset = timezone(timedelta(hours=5, minutes=30))
    ist_dt = datetime.fromtimestamp(last_timestamp / 1000, tz=ist_offset)
    print(f"IST datetime: {ist_dt} ({ist_dt.strftime('%A')})")
    
    # Test with local system timezone
    local_dt = datetime.fromtimestamp(last_timestamp / 1000)
    print(f"Local datetime: {local_dt} ({local_dt.strftime('%A')})")
    
    # Show current date for reference
    now_utc = datetime.now(timezone.utc)
    now_ist = datetime.now(ist_offset)
    print(f"\nCurrent UTC: {now_utc} ({now_utc.strftime('%A')})")
    print(f"Current IST: {now_ist} ({now_ist.strftime('%A')})")
    
    # Test the timestamp conversion manually
    print(f"\nManual conversion:")
    print(f"Timestamp in seconds: {last_timestamp / 1000}")
    print(f"UTC weekday(): {utc_dt.weekday()} -> {DAY_OF_WEEK.get(utc_dt.weekday())}")
    print(f"IST weekday(): {ist_dt.weekday()} -> {DAY_OF_WEEK.get(ist_dt.weekday())}")

def get_day_of_week_name_ist(timestamp):
    """Get the name of the day from a timestamp using IST."""
    if not timestamp:
        return None
    try:
        ist_offset = timezone(timedelta(hours=5, minutes=30))
        date = datetime.fromtimestamp(int(timestamp) / 1000, tz=ist_offset)
        return DAY_OF_WEEK.get(date.weekday())
    except (ValueError, TypeError):
        return None

if __name__ == "__main__":
    test_timezone_issue()
    
    # Show what the IST version would return
    last_timestamp = 1753381800000
    ist_result = get_day_of_week_name_ist(last_timestamp)
    print(f"\nWith IST timezone: {ist_result}")