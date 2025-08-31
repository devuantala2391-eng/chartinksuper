"""
Deploy fixed monthly/weekly SuperTrend calculation
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def deploy_fix():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )
    
    try:
        print("Deploying fixed weekly/monthly SuperTrend procedure...")
        
        with open('python-api/sql/stored_procedures/calculate_weekly_monthly_supertrend.sql', 'r') as f:
            sql = f.read()
        
        await conn.execute(sql)
        print("[OK] Procedure deployed successfully")
        
        # Test monthly calculation
        print("\nTesting monthly SuperTrend calculation...")
        result = await conn.fetchrow("""
            SELECT * FROM calculate_weekly_monthly_supertrend('monthly', 10, 3.0, '20MICRONS')
        """)
        
        print(f"Result: {dict(result)}")
        
        if result['updated_rows'] > 0:
            print(f"[OK] Successfully updated {result['updated_rows']} rows")
            
            # Verify data in database
            sample = await conn.fetchrow("""
                SELECT 
                    candle_key_id,
                    indicators->'monthly_supertrend_10_3' as value,
                    indicators->'monthly_supertrend_10_3_direction' as direction
                FROM daily_candles
                WHERE symbol = '20MICRONS'
                AND indicators ? 'monthly_supertrend_10_3'
                ORDER BY candle_sequence_number DESC
                LIMIT 1
            """)
            
            if sample:
                print(f"\nSample data from DB:")
                print(f"  {sample['candle_key_id']}: value={sample['value']}, direction={sample['direction']}")
        else:
            print(f"[WARNING] No rows updated")
            
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(deploy_fix())