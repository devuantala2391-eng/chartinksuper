#!/usr/bin/env python3
"""
Quick test script for the Latest Candle Update Service
"""

import asyncio
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from services.latest_candle_updater import latest_candle_updater

async def test_single_symbol():
    """Test updating a single symbol."""
    print("Testing single symbol update (RELIANCE)...")
    
    result = await latest_candle_updater.update_symbol("RELIANCE")
    print(f"Result: {result}")
    
    return result

async def test_market_hours():
    """Test market hours detection."""
    print(f"Current market hours status: {latest_candle_updater.is_market_hours()}")

async def test_multiple_symbols():
    """Test updating multiple symbols."""
    test_symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
    print(f"Testing multiple symbols: {test_symbols}")
    
    results = await latest_candle_updater.update_all_symbols(test_symbols)
    
    print("\nResults:")
    for symbol, message in results.items():
        print(f"  {symbol}: {message}")
    
    return results

async def main():
    """Run all tests."""
    print("="*60)
    print("LATEST CANDLE UPDATE SERVICE - TEST SCRIPT")
    print("="*60)
    
    # Test market hours
    await test_market_hours()
    print()
    
    # Test single symbol
    await test_single_symbol()
    print()
    
    # Test multiple symbols
    await test_multiple_symbols()
    print()
    
    print("="*60)
    print("TEST COMPLETED")
    print("="*60)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()