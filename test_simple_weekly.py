"""
Simple test for weekly percentage calculation fix
"""

import asyncio
import sys
sys.path.append('python-api')
from services.ultra_fast_database_service import ultra_fast_db

async def test_data_and_calculation():
    print("=== CHECKING DATA FOR WEEKLY PERCENTAGE CALCULATION ===")
    
    await ultra_fast_db.initialize()
    
    async with ultra_fast_db.pool.acquire() as conn:
        # Check if we have daily data
        daily_count = await conn.fetchval(
            "SELECT COUNT(*) FROM daily_candles WHERE symbol = $1", 
            "20MICRONS"
        )
        print(f"Daily records for 20MICRONS: {daily_count}")
        
        if daily_count == 0:
            print("No daily data found. Cannot test weekly calculation.")
            return
        
        # Check weekly candles
        weekly_count = await conn.fetchval(
            "SELECT COUNT(*) FROM weekly_candles WHERE symbol = $1", 
            "20MICRONS"
        )
        print(f"Weekly candles for 20MICRONS: {weekly_count}")
        
        # Check linkage
        linked_count = await conn.fetchval(
            "SELECT COUNT(*) FROM daily_candles WHERE symbol = $1 AND weekly_candle_key_id IS NOT NULL", 
            "20MICRONS"
        )
        print(f"Daily records with weekly linkage: {linked_count}")
        
        # Check existing weekly percentages
        weekly_pct_count = await conn.fetchval(
            "SELECT COUNT(*) FROM daily_candles WHERE symbol = $1 AND indicators ? 'weekly_pctchg'", 
            "20MICRONS"
        )
        print(f"Records with existing weekly percentage: {weekly_pct_count}")
        
        # Test the stored procedure directly
        print("\n=== TESTING STORED PROCEDURE DIRECTLY ===")
        try:
            result = await conn.fetchrow(
                "SELECT * FROM calculate_weekly_percentage_change_for_symbol($1)",
                "20MICRONS"
            )
            print(f"Stored procedure result: {dict(result)}")
            
            # Check if any rows were actually updated
            updated_count = await conn.fetchval(
                "SELECT COUNT(*) FROM daily_candles WHERE symbol = $1 AND indicators ? 'weekly_pctchg'", 
                "20MICRONS"
            )
            print(f"Records with weekly percentage after calculation: {updated_count}")
            
            # Show some sample data
            if updated_count > 0:
                sample_records = await conn.fetch("""
                    SELECT datetime, close, indicators->'weekly_pctchg' as weekly_pct, weekly_candle_key_id
                    FROM daily_candles 
                    WHERE symbol = $1 AND indicators ? 'weekly_pctchg'
                    ORDER BY datetime DESC 
                    LIMIT 5
                """, "20MICRONS")
                
                print(f"\nSample records with weekly percentage:")
                for record in sample_records:
                    print(f"  {record['datetime']}: close={record['close']}, weekly%={record['weekly_pct']}, week_key={record['weekly_candle_key_id']}")
            
        except Exception as e:
            print(f"Error calling stored procedure: {e}")

if __name__ == "__main__":
    asyncio.run(test_data_and_calculation())