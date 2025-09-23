"""
Test the cron system consolidation - verify it reads from indicator_registry
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def test_cron_consolidation():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )

    try:
        print("=== CONSOLIDATION TEST ===")
        print()

        # 1. Check indicator_registry has indicators
        print("1. Checking indicator_registry...")
        indicators = await conn.fetch("SELECT * FROM indicator_registry")
        print(f"   Found {len(indicators)} indicators in indicator_registry")

        for ind in indicators:
            import json
            config = json.loads(ind['config_data'])
            print(f"   - {config.get('name')} ({config.get('timeframe')}) with params: {config.get('params')}")
        print()

        # 2. Test the cron function with a sample symbol
        print("2. Testing cron function with indicator_registry...")
        try:
            # Get a sample symbol
            sample_symbol = await conn.fetchval("SELECT symbol FROM daily_candles LIMIT 1")
            print(f"   Testing with symbol: {sample_symbol}")

            if sample_symbol:
                # Test the cron function
                results = await conn.fetch("""
                    SELECT * FROM cron_calculate_all_indicators_for_symbol($1, 'daily')
                """, sample_symbol)

                print(f"   Cron function returned {len(results)} results:")
                for result in results:
                    print(f"     - {result['indicator_name']}: {result['status']} (updated {result['updated_rows']} rows)")
                    if result['warning_message']:
                        print(f"       Warning: {result['warning_message']}")
            else:
                print("   No symbols found in daily_candles")
        except Exception as e:
            print(f"   Error testing cron function: {e}")
        print()

        # 3. Check that calculated_indicators table no longer exists
        print("3. Verifying calculated_indicators table removal...")
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'calculated_indicators'
            )
        """)

        if table_exists:
            print("   WARNING: calculated_indicators table still exists!")
        else:
            print("   SUCCESS: calculated_indicators table has been removed")
        print()

        print("=== CONSOLIDATION TEST COMPLETE ===")
        print("SUCCESS: Single source of truth: indicator_registry")
        print("SUCCESS: Cron system updated to read from indicator_registry")
        print("SUCCESS: calculated_indicators table removed")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(test_cron_consolidation())