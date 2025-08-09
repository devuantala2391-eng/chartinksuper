import asyncio
import aiohttp
import json
import time
from pathlib import Path

async def test_query_api_auto_calculation():
    """Test that query/latest API automatically detects and calculates new indicators."""
    
    base_url = "http://localhost:8001"
    
    # Test with a new indicator parameter that likely doesn't exist
    test_query = "daily_close > 100 and daily_supertrend_8_2.5 > 50 and daily_rsi_25 > 30"
    
    print(f"Testing query: {test_query}")
    print("-" * 60)
    
    # Check current indicators before
    precalc_file = Path("precalculatedIndicators.json")
    before_indicators = []
    if precalc_file.exists():
        with open(precalc_file, 'r') as f:
            data = json.load(f)
            before_indicators = data.get('indicators', [])
            print(f"Indicators before: {len(before_indicators)}")
            
            # Check if our test indicators exist
            st_exists = any(
                ind.get('timeframe') == 'daily' and
                ind.get('name') == 'supertrend' and
                ind.get('params', {}).get('period') == 8 and
                ind.get('params', {}).get('multiplier') == 2.5
                for ind in before_indicators
            )
            rsi_exists = any(
                ind.get('timeframe') == 'daily' and
                ind.get('name') == 'rsi' and
                ind.get('params', {}).get('period') == 25
                for ind in before_indicators
            )
            print(f"daily_supertrend_8_2.5 exists before: {st_exists}")
            print(f"daily_rsi_25 exists before: {rsi_exists}")
    
    print("\nMaking API request to /api/query/latest...")
    print("-" * 60)
    
    async with aiohttp.ClientSession() as session:
        try:
            # Make the query request
            async with session.post(
                f"{base_url}/api/query/latest",
                json={"query": test_query},
                timeout=aiohttp.ClientTimeout(total=300)  # 5 minutes timeout
            ) as response:
                status = response.status
                print(f"Response status: {status}")
                
                if status == 200:
                    result = await response.json()
                    print(f"Success! Found {len(result.get('result', []))} stocks")
                    
                    # Check if indicators were added
                    if precalc_file.exists():
                        with open(precalc_file, 'r') as f:
                            data = json.load(f)
                            after_indicators = data.get('indicators', [])
                            print(f"\nIndicators after: {len(after_indicators)}")
                            
                            # Check if our test indicators were added
                            st_added = any(
                                ind.get('timeframe') == 'daily' and
                                ind.get('name') == 'supertrend' and
                                ind.get('params', {}).get('period') == 8 and
                                ind.get('params', {}).get('multiplier') == 2.5
                                for ind in after_indicators
                            )
                            rsi_added = any(
                                ind.get('timeframe') == 'daily' and
                                ind.get('name') == 'rsi' and
                                ind.get('params', {}).get('period') == 25
                                for ind in after_indicators
                            )
                            print(f"daily_supertrend_8_2.5 added: {st_added}")
                            print(f"daily_rsi_25 added: {rsi_added}")
                            
                            if st_added or rsi_added:
                                print("\n✅ Auto-calculation is working! New indicators were detected and added.")
                            else:
                                print("\n❌ New indicators were not added automatically.")
                    
                    # Check if the data files have the new fields
                    sample_file = Path("precalculatedStorage/3PLAND_piped.json")
                    if sample_file.exists():
                        with open(sample_file, 'r') as f:
                            stock_data = json.load(f)
                            if stock_data.get("data"):
                                last_candle = stock_data["data"][-1]
                                has_st = "daily_supertrend_8_2.5" in last_candle
                                has_rsi = "daily_rsi_25" in last_candle
                                print(f"\nData file has daily_supertrend_8_2.5: {has_st}")
                                print(f"Data file has daily_rsi_25: {has_rsi}")
                                
                                if has_st:
                                    print(f"daily_supertrend_8_2.5 value: {last_candle.get('daily_supertrend_8_2.5')}")
                                if has_rsi:
                                    print(f"daily_rsi_25 value: {last_candle.get('daily_rsi_25')}")
                                    
                                if has_st and has_rsi:
                                    print("\n✅ Data files were updated with new indicator values!")
                                else:
                                    print("\n⚠️ Data files may not have been updated yet.")
                    
                    # Show sample results
                    if result.get('result'):
                        print(f"\nFirst result: {result['result'][0].get('symbol', 'N/A')}")
                        
                else:
                    error_text = await response.text()
                    print(f"Error response: {error_text}")
                    
        except asyncio.TimeoutError:
            print("Request timed out after 5 minutes")
        except Exception as e:
            print(f"Error making request: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Auto-Calculation in Query API")
    print("=" * 60)
    asyncio.run(test_query_api_auto_calculation())