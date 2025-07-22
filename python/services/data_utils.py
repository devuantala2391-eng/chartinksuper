from datetime import datetime, timezone
from utils.constants import DAY_OF_WEEK

def get_day_of_week_name(timestamp):
    """Get the name of the day from a timestamp."""
    if not timestamp:
        return None
    try:
        date = datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc)
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