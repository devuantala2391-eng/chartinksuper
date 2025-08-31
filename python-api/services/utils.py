"""
Utility functions for the application
"""

def format_multiplier_for_key(multiplier):
    """
    Format a multiplier value for use in indicator keys.
    Converts float to string with limited decimal places.
    
    Examples:
    - 3.0 -> "3"
    - 3.5 -> "3dot5"
    - 1.6 -> "1dot6"
    - 1.600000000000000088817841970012523233890533447265625 -> "1dot6"
    """
    # Handle None or invalid input
    if multiplier is None:
        return "2"  # Default multiplier
    
    # Convert to float if not already
    try:
        multiplier = float(multiplier)
    except (ValueError, TypeError):
        return "2"  # Default multiplier
    
    # Check if it's effectively an integer
    if multiplier == int(multiplier):
        return str(int(multiplier))
    
    # Round to 2 decimal places to avoid floating point precision issues
    rounded = round(multiplier, 2)
    
    # Format as string with minimal decimal places
    if rounded == int(rounded):
        return str(int(rounded))
    else:
        # Remove trailing zeros and convert to dot notation
        formatted = f"{rounded:.2f}".rstrip('0').rstrip('.')
        return formatted.replace('.', 'dot')

def format_period_for_key(period):
    """
    Format a period value for use in indicator keys.
    Always returns an integer string.
    
    Examples:
    - 10.0 -> "10"
    - 10 -> "10"
    - 14.0 -> "14"
    """
    # Handle None or invalid input
    if period is None:
        return "10"  # Default period
    
    # Convert to float first, then to int
    try:
        period = float(period)
        return str(int(period))
    except (ValueError, TypeError):
        return "10"  # Default period