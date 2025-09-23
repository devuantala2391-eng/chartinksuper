"""
DEPRECATED: This script was used to populate the calculated_indicators table.
Since we've consolidated to indicator_registry as the single source of truth,
this script is no longer needed.

Use setup_default_indicators.py to add indicators to indicator_registry instead.
"""

import asyncio

async def populate_indicators():
    print("This script is deprecated.")
    print("Use setup_default_indicators.py to add indicators to indicator_registry instead.")
    print("calculated_indicators table has been removed in favor of indicator_registry.")

# All functions have been deprecated - use indicator_registry instead

if __name__ == "__main__":
    asyncio.run(populate_indicators())