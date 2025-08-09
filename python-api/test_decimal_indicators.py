import asyncio
import json
from pathlib import Path
import sys
sys.path.append('.')

async def add_decimal_indicators():
    """Manually add and calculate indicators with decimal parameters."""
    
    # The indicators you need with decimal parameters
    new_indicators = [
        {
            "id": "13",
            "timeframe": "daily",
            "name": "supertrend",
            "params": {
                "period": 10,
                "multiplier": 2.44
            },
            "description": "Daily SuperTrend 10,2.44"
        },
        {
            "id": "14", 
            "timeframe": "daily",
            "name": "bb",
            "params": {
                "period": 10,
                "stdDev": 1.22
            },
            "description": "Daily Bollinger Bands 10,1.22"
        }
    ]
    
    # Load existing indicators
    precalc_file = Path("precalculatedIndicators.json")
    if precalc_file.exists():
        with open(precalc_file, 'r') as f:
            data = json.load(f)
            existing_indicators = data.get('indicators', [])
    else:
        existing_indicators = []
    
    # Add new indicators
    for new_ind in new_indicators:
        # Check if already exists
        exists = any(
            ind.get('timeframe') == new_ind['timeframe'] and
            ind.get('name') == new_ind['name'] and
            ind.get('params') == new_ind['params']
            for ind in existing_indicators
        )
        
        if not exists:
            existing_indicators.append(new_ind)
            print(f"Added: {new_ind['description']}")
    
    # Save updated indicators
    from services.data_utils import get_day_of_week_name
    from datetime import datetime
    
    updated_data = {
        "status": "processing",
        "indicators": existing_indicators,
        "lastUpdated": datetime.utcnow().isoformat(),
        "dayOfWeek": get_day_of_week_name(datetime.utcnow().timestamp() * 1000)
    }
    
    with open(precalc_file, 'w') as f:
        json.dump(updated_data, f, indent=2)
    
    print("Saved updated indicators to precalculatedIndicators.json")
    print("Now calculating the indicators...")
    
    # Import and run the processing function
    from main import process_indicators_background
    
    # Process all indicators
    await process_indicators_background(existing_indicators)
    
    # Update status to completed
    updated_data["status"] = "completed"
    with open(precalc_file, 'w') as f:
        json.dump(updated_data, f, indent=2)
    
    print("Calculation completed!")

if __name__ == "__main__":
    asyncio.run(add_decimal_indicators())