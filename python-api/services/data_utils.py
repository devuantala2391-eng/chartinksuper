from datetime import datetime, timezone, timedelta
from utils.constants import DAY_OF_WEEK

def get_day_of_week_name(timestamp):
    """Get the name of the day from a timestamp using IST (Indian Standard Time)."""
    if not timestamp:
        return None
    try:
        # Use IST timezone (UTC+5:30) for Indian stock market data
        ist_offset = timezone(timedelta(hours=5, minutes=30))
        date = datetime.fromtimestamp(int(timestamp) / 1000, tz=ist_offset)
        return DAY_OF_WEEK.get(date.weekday())
    except (ValueError, TypeError):
        return None

def get_next_day_timestamp(date_string):
    """Get the next day timestamp by adding 19800000 milliseconds (5.5 hours)."""
    try:
        if isinstance(date_string, str):
            parsed = int(date_string)
        else:
            parsed = int(date_string)
        return parsed + 19800000
    except (ValueError, TypeError):
        print(f"Error in get_next_day_timestamp: {date_string}")
        return None