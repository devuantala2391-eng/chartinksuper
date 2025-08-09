import asyncio
import json
from pathlib import Path
import sys
sys.path.append('.')

from main import add_missing_indicators_and_calculate

async def test_auto_calculation():
    """Test automatic calculation of new indicators."""
    
    # Test with a new indicator parameter
    missing_fields = ['daily_supertrend_7_3', 'daily_rsi_21']
    
    print(f"Testing auto-calculation for: {missing_fields}")
    print("-" * 50)
    
    # Check current indicators before
    precalc_file = Path("precalculatedIndicators.json")
    if precalc_file.exists():
        with open(precalc_file, 'r') as f:
            data = json.load(f)
            before_count = len(data.get('indicators', []))
            print(f"Indicators before: {before_count}")
    
    # Run auto-calculation
    print("\nRunning auto-calculation...")
    success = await add_missing_indicators_and_calculate(missing_fields)
    print(f"Success: {success}")
    
    # Check indicators after
    if precalc_file.exists():
        with open(precalc_file, 'r') as f:
            data = json.load(f)
            after_count = len(data.get('indicators', []))
            print(f"Indicators after: {after_count}")
            
            # Check if our new indicators were added
            indicators = data.get('indicators', [])
            
            # Check for daily_supertrend_7_3
            st_exists = any(
                ind.get('timeframe') == 'daily' and
                ind.get('name') == 'supertrend' and
                ind.get('params', {}).get('period') == 7 and
                ind.get('params', {}).get('multiplier') == 3
                for ind in indicators
            )
            print(f"daily_supertrend_7_3 added: {st_exists}")
            
            # Check for daily_rsi_21
            rsi_exists = any(
                ind.get('timeframe') == 'daily' and
                ind.get('name') == 'rsi' and
                ind.get('params', {}).get('period') == 21
                for ind in indicators
            )
            print(f"daily_rsi_21 added: {rsi_exists}")
    
    # Check if the data files were updated
    sample_file = Path("precalculatedStorage/3PLAND_piped.json")
    if sample_file.exists():
        with open(sample_file, 'r') as f:
            stock_data = json.load(f)
            if stock_data.get("data"):
                last_candle = stock_data["data"][-1]
                has_st = "daily_supertrend_7_3" in last_candle
                has_rsi = "daily_rsi_21" in last_candle
                print(f"\nData file has daily_supertrend_7_3: {has_st}")
                print(f"Data file has daily_rsi_21: {has_rsi}")
                
                if has_st:
                    print(f"daily_supertrend_7_3 value: {last_candle.get('daily_supertrend_7_3')}")
                if has_rsi:
                    print(f"daily_rsi_21 value: {last_candle.get('daily_rsi_21')}")

if __name__ == "__main__":
    asyncio.run(test_auto_calculation())