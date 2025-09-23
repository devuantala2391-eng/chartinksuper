"""
Test script to verify cron indicator calculations are using calculated_indicators table
"""

import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def test_cron_indicators():
    """Test that cron indicators are reading from calculated_indicators table"""

    # Connect to database
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )

    try:
        print("Testing cron indicator calculation system...")

        # Check if calculated_indicators table exists and has data
        print("\n1. Checking calculated_indicators table...")
        count_result = await conn.fetchrow("SELECT COUNT(*) as count FROM calculated_indicators WHERE status = 'active'")
        print(f"   Found {count_result['count']} active indicators in calculated_indicators table")

        if count_result['count'] == 0:
            print("   WARNING: No active indicators found. Let's check all indicators:")
            all_indicators = await conn.fetch("SELECT indicator_name, timeframe, parameters, status FROM calculated_indicators LIMIT 10")
            for ind in all_indicators:
                print(f"      - {ind['indicator_name']} ({ind['timeframe']}): {ind['status']}")
            return

        # Show some sample indicators
        print("\n2. Sample active indicators:")
        sample_indicators = await conn.fetch("""
            SELECT indicator_name, timeframe, parameters, indicator_key
            FROM calculated_indicators
            WHERE status = 'active'
            ORDER BY indicator_name, timeframe
            LIMIT 10
        """)

        for ind in sample_indicators:
            params = json.loads(ind['parameters']) if ind['parameters'] else {}
            print(f"   - {ind['indicator_name']} ({ind['timeframe']}): {params} -> {ind['indicator_key']}")

        # Test the cron function for a specific symbol and timeframe
        print("\n3. Testing cron calculation for a sample symbol...")

        # Get a sample symbol
        symbol_result = await conn.fetchrow("SELECT symbol FROM daily_candles LIMIT 1")
        if not symbol_result:
            print("   ERROR: No symbols found in daily_candles")
            return

        test_symbol = symbol_result['symbol']
        print(f"   Using symbol: {test_symbol}")

        # Test daily calculation
        try:
            results = await conn.fetch(
                "SELECT * FROM cron_calculate_all_indicators_for_symbol($1, $2)",
                test_symbol, 'daily'
            )

            print(f"\n4. Cron calculation results for {test_symbol} (daily):")
            for result in results:
                print(f"   - {result['indicator_name']}: {result['status']} ({result['execution_time_ms']}ms)")
                if result['warning_message']:
                    print(f"     Warning: {result['warning_message']}")

            # Show summary
            total_results = len(results)
            success_results = len([r for r in results if r['status'] in ['SUCCESS', 'FALLBACK']])
            error_results = len([r for r in results if r['status'] == 'ERROR'])

            print(f"\n   Summary: {success_results}/{total_results} successful, {error_results} errors")

        except Exception as e:
            print(f"   ERROR: Error testing cron calculation: {e}")

        print("\nTest completed!")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(test_cron_indicators())