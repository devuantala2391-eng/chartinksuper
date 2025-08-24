#!/usr/bin/env python3
"""
Debug Indicator Storage System
Tests the indicator calculation and storage pipeline in detail
"""

import asyncio
import logging
from services.ultra_fast_database_service import ultra_fast_db
from services.optimized_processor import optimized_processor

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def debug_indicator_storage():
    """Debug the complete indicator storage pipeline"""
    
    print("=" * 80)
    print("DEBUGGING INDICATOR STORAGE SYSTEM")
    print("=" * 80)
    
    try:
        # Initialize database
        print("1. Initializing database...")
        await ultra_fast_db.initialize()
        print("Database initialized successfully")
        
        # Get actual candles from database
        print("\n2. Getting real data from database...")
        symbol = "20MICRONS"
        candles = await ultra_fast_db.get_last_n_candles(symbol, 10)
        print(f"Retrieved {len(candles)} candles for {symbol}")
        
        if candles:
            print("Sample candles:")
            for i, candle in enumerate(candles[:3]):
                print(f"  Candle {i}: timestamp={candle.get('timestamp')}, close={candle.get('close')}, volume={candle.get('volume')}")
        
        # Convert to format expected by processor
        print("\n3. Converting data for processor...")
        stock_data = []
        for candle in candles:
            stock_data.append({
                'open': float(candle['open']) if candle.get('open') else 0,
                'high': float(candle['high']) if candle.get('high') else 0,
                'low': float(candle['low']) if candle.get('low') else 0,
                'close': float(candle['close']) if candle.get('close') else 0,
                'volume': float(candle['volume']) if candle.get('volume') else 0,
                'timestamp': candle['timestamp']
            })
        print(f"Converted {len(stock_data)} candles to processor format")
        
        # Test indicator calculation
        print("\n4. Testing indicator calculation...")
        indicator_def = {
            "name": "PercentageChange",
            "timeframe": "daily", 
            "params": {"lookback": 1}
        }
        
        print(f"Indicator definition: {indicator_def}")
        
        # Process with optimized processor
        success, result_data, error = optimized_processor.process_indicators(
            symbol,
            stock_data,
            [indicator_def], 
            ["daily"]
        )
        
        print(f"\nProcessor result: success={success}, error={error}")
        
        if success and result_data:
            print(f"Got {len(result_data)} processed candles")
            print("\nProcessed candle results:")
            for i, candle in enumerate(result_data[:5]):  # Show first 5
                pct_change = candle.get("daily_pctchg_1")
                print(f"  Candle {i}: timestamp={candle.get('timestamp')}, close={candle.get('close')}, daily_pctchg_1={pct_change}")
            
            # Test manual indicator storage
            print("\n5. Testing manual indicator storage...")
            indicator_key = "daily_pctchg_1"
            
            # Extract indicator values for storage
            indicator_values = []
            for candle in result_data:
                if 'daily_pctchg_1' in candle:
                    indicator_values.append({
                        'timestamp': candle.get('timestamp'),
                        'value': candle.get('daily_pctchg_1')
                    })
            
            print(f"Extracted {len(indicator_values)} indicator values:")
            for i, val in enumerate(indicator_values[:3]):
                print(f"  Value {i}: timestamp={val['timestamp']}, value={val['value']}")
            
            # Store in database
            if indicator_values:
                print("\n6. Storing in database...")
                success = await ultra_fast_db.update_indicator_in_jsonb(symbol, indicator_key, indicator_values)
                print(f"Storage result: {success}")
                
                # Verify storage
                print("\n7. Verifying storage...")
                verification_candles = await ultra_fast_db.get_last_n_candles(symbol, 5)
                print("Verification results:")
                for i, candle in enumerate(verification_candles):
                    # Handle both dict and string cases for indicators
                    indicators = candle.get('indicators', {})
                    if isinstance(indicators, str):
                        print(f"  Candle {i}: close={candle.get('close')}, indicators='{indicators}'")
                        continue
                    elif isinstance(indicators, dict):
                        pct_chg = indicators.get('daily_pctchg_1', 'NOT_FOUND')
                        print(f"  Candle {i}: close={candle.get('close')}, indicators={indicators}")
                        if pct_chg != 'NOT_FOUND':
                            print(f"    SUCCESS: daily_pctchg_1 = {pct_chg}")
                        else:
                            print(f"    ERROR: daily_pctchg_1 not found in indicators")
                    else:
                        print(f"  Candle {i}: close={candle.get('close')}, indicators={type(indicators).__name__}: {indicators}")
        else:
            print(f"ERROR: Processor failed: {error}")
        
        print("\nSUCCESS Debug test completed!")
        
    except Exception as e:
        print(f"\nERROR Debug test failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await ultra_fast_db.close()

if __name__ == "__main__":
    asyncio.run(debug_indicator_storage())